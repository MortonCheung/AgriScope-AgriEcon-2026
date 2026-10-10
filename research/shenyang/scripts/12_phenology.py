"""STEP 21 — Phase 10：物候机制解释层（任务书 §四十五 ~ §四十六）。

研究问题
--------
当沈阳本地某品种进入本地生产/上市窗口时，极端天气是否同时伴随**更强**的市场异常？

红线（§四十五 / §四十六）
------------------------
1. 批发市场商品来源不一定是沈阳本地。因此物候数据只允许作为
   **本地农业生产风险解释层（农业气象机制解释层）**，
   禁止当作「当天批发市场所有该品种商品都处于某生育期」的来源标签。
2. 因此结论只能表述为：「这一时间重叠与农业生育期敏感机制一致」，
   不得表述为「市场商品全部因为本地生育期受灾」。

数据可用性与降级（本轮实测，同时写入 reports/BLOCKERS.md）
----------------------------------------------------------
- `data/raw/metadata/crop_calendar.csv` 共 22 行，**没有任何一行**给出
  flowering_period / fruiting_period 等**阶段级**日期；原文粒度仅到「旬/月」，
  多数行只给播种期与采收期。
  => 无法构造「开花坐果期 / 结球期 / 块茎膨大期」的日窗口。
  => 本模块以**本地采收上市窗口（harvest_start ~ harvest_end）**作为
     `Local Crop Stage` 的代理，并在报告中显式降级说明。
- 旬/月 → 日序(DOY) 转换采用确定性规则（上旬=1-10，中旬=11-20，下旬=21-月末），
  不声称获得比原文更细的时间精度。

窗口口径（两个 scope，避免把机制问题搅在一起）
----------------------------------------------
- `open_field`（**主口径**）：仅**露地**生产行。机制先验：露地货源直接暴露于
  降水/高温/风，天气冲击最可能在此产生可识别的额外放大；设施（温室/大棚/拱棚）
  削弱气象暴露，因此不进入主口径。
- `all`（**次口径**）：本地全部生产行（露地 + 设施 + 混合）的并集，
  代表「本地可能上市期」的最宽定义。
- 两个口径分别做多重检验校正，互不混合。

输出
----
tables/  phenology_windows.csv                （明细，含 scope 与来源审计字段）
         phenology_window_summary.csv          （crop × scope 合并后区间）
         phenology_interaction_by_crop.csv
         phenology_interaction_pooled.csv
         phenology_desc_by_window.csv
figures/ F34_phenology_windows.png
         F35_phenology_interaction.png
reports/ 10_PHENOLOGY.md
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from _common import (
    ANALYSIS,
    CROPS_CFG,
    PATHS,
    bh_fdr,
    get_logger,
    hac_ols,
    load_parquet,
    log_blocker,
    register_results,
    render_figure,
    require_columns,
    save_table,
    set_seed,
    setup_matplotlib,
)

MOD = "12_phenology"
CORE_CROPS: List[str] = list(CROPS_CFG["core_crops"])
HAZARDS = list(ANALYSIS["transmission"]["hazards"])
HAC_LAGS = int(ANALYSIS["lag"]["hac_maxlags"])
MIN_OBS_CROP = 200
MIN_OBS_POOL = 800
RESPONSES = [
    ("price", "price_anomaly_z_hist", "价格异常度（稳健z，去季节化主方法）"),
    ("volume", "volume_anomaly_z_hist", "成交量异常度（稳健z，去季节化主方法）"),
]
SCOPES = ["open_field", "all"]

# 本地来源判定：地区字段包含任一关键词即视为本地生产日历行
LOCAL_KEYS = ("辽宁", "沈阳", "北方", "东北")
PROTECTED_KEYS = ("设施", "温室", "大棚", "拱棚", "保护地")

# 月 → 非闰年首/末 DOY
_MONTH_START = [0, 1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335]
_MONTH_END = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365]
_DECADE_RANGE = {"上旬": (1, 10), "中旬": (11, 20), "下旬": (21, 31)}
_PT_RE = re.compile(r"(\d{1,2})\s*月")
_DAY_RE = re.compile(r"(\d{1,2})\s*[日号]")


# -----------------------------------------------------------------------------
# 1) 历法文本 → DOY 区间
# -----------------------------------------------------------------------------
def parse_point(txt) -> Optional[Tuple[int, int]]:
    """把「X月上/中/下旬」「X月」「X月Y日」解析为 (doy_start, doy_end)。

    无法解析（如「苗龄50-60天定植」）返回 None。原文粒度不提升。
    """
    if txt is None or (isinstance(txt, float) and np.isnan(txt)):
        return None
    s = str(txt).strip()
    if s in ("", "nan", "NaN"):
        return None
    if "全年" in s:
        return (1, 365)

    m = _PT_RE.search(s)
    if not m:
        return None
    month = int(m.group(1))
    if not (1 <= month <= 12):
        return None

    if "中下旬" in s:                      # 必须先于「下旬」判断
        lo, hi = 11, 31
    elif "上旬" in s:
        lo, hi = _DECADE_RANGE["上旬"]
    elif "中旬" in s:
        lo, hi = _DECADE_RANGE["中旬"]
    elif "下旬" in s:
        lo, hi = _DECADE_RANGE["下旬"]
    else:
        lo, hi = 1, 31

    dm = _DAY_RE.search(s)                 # 给出具体日则覆盖范围
    if dm:
        day = int(dm.group(1))
        if 1 <= day <= 31:
            lo = hi = day

    last = _MONTH_END[month] - _MONTH_START[month] + 1
    hi = min(hi, last)
    return (_MONTH_START[month] + lo - 1, _MONTH_START[month] + hi - 1)


def parse_interval(start_txt, end_txt) -> Tuple[List[Tuple[int, int]], bool]:
    """解析 harvest_start~harvest_end，返回 (区间列表, 是否跨年)。"""
    a = parse_point(start_txt)
    b = parse_point(end_txt)
    if a is None and b is None:
        return [], False
    if a is None:
        a = b
    if b is None:
        b = a
    s, e = a[0], b[1]
    if e < s:                              # 如 11月 ~ 翌年7月
        return [(s, 365), (1, e)], True
    return [(s, e)], False


def union_intervals(ivs: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """合并重叠/相邻区间（避免重复计数）。"""
    if not ivs:
        return []
    s = sorted(ivs)
    out = [list(s[0])]
    for a, b in s[1:]:
        if a <= out[-1][1] + 1:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(int(a), int(b)) for a, b in out]


def scope_of(cultivation, note_raw) -> str:
    """划分生产口径：open_field（纯露地）/ protected（含设施）/ mixed / unspecified。"""
    s = f"{cultivation} {note_raw}"
    has_p = any(k in s for k in PROTECTED_KEYS)
    has_o = "露地" in s
    if has_p and has_o:
        return "mixed"
    if has_p:
        return "protected"
    if has_o:
        return "open_field"
    return "unspecified"


# -----------------------------------------------------------------------------
# 2) 构建物候窗口表
# -----------------------------------------------------------------------------
def build_windows(log):
    """返回 (明细表, 汇总表, windows_map)。windows_map[(crop, scope)] = 合并区间。"""
    cal = pd.read_csv(PATHS.inp("crop_calendar"))
    agr = pd.read_csv(PATHS.inp("crop_agronomy"))
    loc = cal[cal["region"].astype(str).str.contains("|".join(LOCAL_KEYS), na=False)].copy()
    log.info("本地生产日历行：%d / %d", len(loc), len(cal))

    rows: List[Dict] = []
    skipped: List[str] = []
    for _, r in loc.iterrows():
        crop = str(r["crop"]).strip()
        if crop not in CORE_CROPS:
            continue
        iv, wraps = parse_interval(r.get("harvest_start"), r.get("harvest_end"))
        field = "harvest_start~harvest_end"
        if not iv:                          # 退化：用成熟期字段（粒度仍为旬/月）
            iv, wraps = parse_interval(r.get("maturity_period"), None)
            field = "maturity_period（harvest 缺失，已降级）"
        if not iv:
            skipped.append(f"{crop}|{r['region']}|{r.get('cultivation')}")
            continue
        sc = scope_of(r.get("cultivation"), r.get("note_raw"))
        for (s, e) in iv:
            rows.append({
                "crop": crop,
                "region": r["region"],
                "cultivation": r.get("cultivation"),
                "scope_row": sc,
                "window_label": f"{r.get('harvest_start')} ~ {r.get('harvest_end')}",
                "doy_start": int(s), "doy_end": int(e),
                "wraps_year": bool(wraps), "window_field": field,
                "granularity": r.get("granularity"),
                "source_type": r.get("source_type"),
                "source": r.get("source"),
            })
    det = pd.DataFrame(rows)
    if det.empty:
        log_blocker(MOD, "crop_calendar 无法解析出任何本地窗口", "见 12_phenology 日志")
        return det, pd.DataFrame(), {}

    agr_c = agr[agr["crop"].isin(CORE_CROPS)].set_index("crop")

    # 两个口径的区间集合
    windows_map: Dict[Tuple[str, str], List[Tuple[int, int]]] = {}
    for crop in CORE_CROPS:
        sub = det[det["crop"] == crop]
        sel_open = sub[sub["scope_row"] == "open_field"]
        windows_map[(crop, "open_field")] = union_intervals(
            list(zip(sel_open["doy_start"], sel_open["doy_end"])))
        windows_map[(crop, "all")] = union_intervals(
            list(zip(sub["doy_start"], sub["doy_end"])))

    summ_rows: List[Dict] = []
    for crop in CORE_CROPS:
        for scope in SCOPES:
            ivs = windows_map[(crop, scope)]
            cover = int(sum(b - a + 1 for a, b in ivs))
            base = det[det["crop"] == crop]
            used = base if scope == "all" else base[base["scope_row"] == "open_field"]
            summ_rows.append({
                "crop": crop, "scope": scope,
                "n_intervals": len(ivs),
                "intervals_doy": "; ".join(f"{a}-{b}" for a, b in ivs),
                "window_days_total": cover,
                "window_share_of_year": round(cover / 365.0, 3),
                "identified_interaction": bool(0 < cover < 365),
                "n_source_rows": int(len(used)),
                "source_scopes_used": ("; ".join(sorted(set(used["scope_row"]))) if len(used) else None),
                "granularities": (" / ".join(sorted(set(base["granularity"].dropna().astype(str)))) if len(base) else None),
                "sensitive_stage_agronomy": (agr_c.loc[crop, "growth_stage"] if crop in agr_c.index else None),
                "heat_risk_note": (agr_c.loc[crop, "heat_risk"] if crop in agr_c.index else None),
                "waterlogging_note": (agr_c.loc[crop, "waterlogging_risk"] if crop in agr_c.index else None),
                "rainfall_risk_note": (agr_c.loc[crop, "rainfall_risk"] if crop in agr_c.index else None),
                "window_is_harvest_proxy": True,
            })
    summ = pd.DataFrame(summ_rows)

    save_table(det, "phenology_windows.csv")
    save_table(summ, "phenology_window_summary.csv")

    if skipped:
        log_blocker(MOD, "crop_calendar 中部分本地行无可用采收/成熟日期，已跳过（不插补）",
                    "skipped=" + " ; ".join(skipped))
    degen = summ[(summ["scope"] == "all") & (~summ["identified_interaction"])]
    if len(degen):
        log_blocker(MOD, "部分品种在本地日历中为全年窗口（或空窗口），交互项不可识别",
                    "crops=" + ",".join(degen["crop"].tolist()) +
                    "；处理=不进入该口径的检验与 FDR 家族")
    log.info("窗口汇总：open_field 可用品种 %d/%d；all 可用品种 %d/%d",
             int(((summ["scope"] == "open_field") & summ["identified_interaction"]).sum()),
             len(CORE_CROPS),
             int(((summ["scope"] == "all") & summ["identified_interaction"]).sum()),
             len(CORE_CROPS))
    return det, summ, windows_map


def in_window_flags(doy: np.ndarray, intervals: List[Tuple[int, int]]) -> np.ndarray:
    m = np.zeros(len(doy), dtype=bool)
    for a, b in intervals:
        m |= (doy >= a) & (doy <= b)
    return m


# -----------------------------------------------------------------------------
# 3) 交互检验：hazard × in_window
# -----------------------------------------------------------------------------
def hazard_scales(weather: pd.DataFrame) -> Dict[str, Tuple[float, float]]:
    """按全序列均值/标准差标准化（与 STEP15-17 同口径）。"""
    sc = {}
    for h in HAZARDS:
        v = pd.to_numeric(weather[h["col"]], errors="coerce")
        sc[h["key"]] = (float(v.mean()), float(v.std(ddof=0)))
    return sc


def _design(df: pd.DataFrame, haz_col: str, mu: float, sd: float, crop_fe: bool):
    z = (pd.to_numeric(df[haz_col], errors="coerce") - mu) / sd
    win = df["in_win"].astype(float)
    cols = {
        "hazard_z": z.to_numpy(dtype=float),
        "hazard_z_x_inwin": (z * win).to_numpy(dtype=float),
        "in_win": win.to_numpy(dtype=float),
        "is_public_holiday": df["is_public_holiday"].to_numpy(dtype=float),
    }
    if crop_fe:
        d = pd.get_dummies(df["crop"], prefix="crop", drop_first=True, dtype=float)
        for c in d.columns:
            cols[c] = d[c].to_numpy(dtype=float)
    names = list(cols.keys())
    X = np.column_stack([cols[n] for n in names])
    y = df["y"].to_numpy(dtype=float)
    ok = ~(np.isnan(y) | np.isnan(X).any(axis=1))
    return y[ok], X[ok], names, int(ok.sum())


def _slope(z: np.ndarray, y: np.ndarray, m: np.ndarray) -> float:
    k = m & np.isfinite(z) & np.isfinite(y)
    if int(k.sum()) < 60:
        return np.nan
    return float(np.polyfit(z[k], y[k], 1)[0])


def _mean_or_nan(v: np.ndarray, m: np.ndarray) -> float:
    if int(m.sum()) == 0:
        return np.nan
    return float(np.nanmean(v[m]))


def run_interactions(panel: pd.DataFrame, summ: pd.DataFrame,
                     windows_map, weather: pd.DataFrame, log):
    sc_h = hazard_scales(weather)
    rows_crop: List[Dict] = []
    rows_pool: List[Dict] = []
    rows_desc: List[Dict] = []

    for rkey, ycol, _ylab in RESPONSES:
        base = panel.copy()
        base["y"] = pd.to_numeric(base[ycol], errors="coerce")
        doy_all = base["doy"].to_numpy()
        crop_all = base["crop"].to_numpy()

        # ---- 逐品种 ----
        for scope in SCOPES:
            for crop in CORE_CROPS:
                row = summ[(summ["crop"] == crop) & (summ["scope"] == scope)]
                if row.empty or not bool(row["identified_interaction"].iloc[0]):
                    continue
                ivs = windows_map[(crop, scope)]
                sub = base[base["crop"] == crop].copy()
                if len(sub) < MIN_OBS_CROP:
                    continue
                sub["in_win"] = in_window_flags(sub["doy"].to_numpy(), ivs)
                if sub["in_win"].nunique() < 2:
                    continue
                ya = sub["y"].to_numpy()
                for h in HAZARDS:
                    mu, sd = sc_h[h["key"]]
                    if not np.isfinite(mu) or not np.isfinite(sd) or sd <= 0:
                        continue
                    y, X, names, n = _design(sub, h["col"], mu, sd, crop_fe=False)
                    if n < MIN_OBS_CROP:
                        continue
                    res = hac_ols(y, X, maxlags=HAC_LAGS)
                    coef = pd.Series(res["coef"], index=["const"] + names)
                    pv = pd.Series(res["p"], index=["const"] + names)
                    za = ((pd.to_numeric(sub[h["col"]], errors="coerce") - mu) / sd).to_numpy()
                    inw = sub["in_win"].to_numpy()
                    rows_crop.append({
                        "scope": scope, "response": rkey, "crop": crop,
                        "hazard": h["key"], "hazard_label": h["label"],
                        "window_days": int(inw.sum()),
                        "beta_hazard": float(coef["hazard_z"]),
                        "p_hazard": float(pv["hazard_z"]),
                        "beta_interaction": float(coef["hazard_z_x_inwin"]),
                        "p_interaction": float(pv["hazard_z_x_inwin"]),
                        "n": n, "r2": float(res["r2"]),
                        "slope_in_window": _slope(za, ya, inw),
                        "slope_out_window": _slope(za, ya, ~inw),
                    })
                    rows_desc.append({
                        "scope": scope, "response": rkey, "crop": crop,
                        "hazard": h["key"],
                        "mean_y_in_win": _mean_or_nan(ya, inw),
                        "mean_y_out_win": _mean_or_nan(ya, ~inw),
                        "sd_y_in_win": (float(np.nanstd(ya[inw])) if int(inw.sum()) else np.nan),
                        "sd_y_out_win": (float(np.nanstd(ya[~inw])) if int((~inw).sum()) else np.nan),
                    })

            # ---- pooled（品种固定效应）----
            usable = summ[(summ["scope"] == scope) & summ["identified_interaction"]]["crop"].tolist()
            if not usable:
                continue
            flags = np.zeros(len(base), dtype=bool)
            for crop in usable:
                flags |= (crop_all == crop) & in_window_flags(
                    doy_all, windows_map[(crop, scope)])
            sub = base[base["crop"].isin(usable)].copy()
            sub["in_win"] = flags[base["crop"].isin(usable).to_numpy()]
            for h in HAZARDS:
                mu, sd = sc_h[h["key"]]
                y, X, names, n = _design(sub, h["col"], mu, sd, crop_fe=True)
                if n < MIN_OBS_POOL:
                    continue
                res = hac_ols(y, X, maxlags=HAC_LAGS)
                coef = pd.Series(res["coef"], index=["const"] + names)
                pv = pd.Series(res["p"], index=["const"] + names)
                k = names.index("hazard_z_x_inwin") + 1
                b = float(res["coef"][k])
                se = float(res["se"][k])
                rows_pool.append({
                    "scope": scope, "response": rkey,
                    "hazard": h["key"], "hazard_label": h["label"],
                    "n_crops": len(usable),
                    "beta_interaction": b, "se": se,
                    "ci_low": b - 1.96 * se, "ci_high": b + 1.96 * se,
                    "p_interaction": float(res["p"][k]),
                    "beta_hazard": float(coef["hazard_z"]),
                    "p_hazard": float(pv["hazard_z"]),
                    "n": n, "r2": float(res["r2"]),
                })

    bc = pd.DataFrame(rows_crop)
    bc["fdr_p_interaction"] = np.nan
    for scope in SCOPES:                     # 每个口径单独校正，不混合
        m = bc["scope"] == scope
        if int(m.sum()):
            bc.loc[m, "fdr_p_interaction"] = bh_fdr(bc.loc[m, "p_interaction"].to_numpy())
    bc["sig_fdr05"] = bc["fdr_p_interaction"] < 0.05

    pl = pd.DataFrame(rows_pool)
    if not pl.empty:
        pl["fdr_p_interaction"] = np.nan
        for scope in SCOPES:
            m = pl["scope"] == scope
            if int(m.sum()):
                pl.loc[m, "fdr_p_interaction"] = bh_fdr(pl.loc[m, "p_interaction"].to_numpy())
        pl["sig_fdr05"] = pl["fdr_p_interaction"] < 0.05

    desc = pd.DataFrame(rows_desc)
    save_table(bc.sort_values(["scope", "response", "crop", "hazard"]),
               "phenology_interaction_by_crop.csv")
    save_table(pl, "phenology_interaction_pooled.csv")
    save_table(desc, "phenology_desc_by_window.csv")
    log.info("逐品种交互 %d 行，FDR 显著 %d；pooled %d 行，FDR 显著 %d",
             len(bc), int(bc["sig_fdr05"].sum()), len(pl),
             int(pl["sig_fdr05"].sum()) if not pl.empty else 0)
    return bc, pl, desc


# -----------------------------------------------------------------------------
# 4) 图
# -----------------------------------------------------------------------------
def fig_windows(det: pd.DataFrame, summ: pd.DataFrame):
    plt = setup_matplotlib()
    order = sorted(CORE_CROPS,
                   key=lambda c: min([a for a, _ in union_intervals(
                       list(zip(det.loc[det["crop"] == c, "doy_start"],
                                det.loc[det["crop"] == c, "doy_end"])))] or [999]))
    fig, ax = plt.subplots(figsize=(11.6, 5.4))
    for i, c in enumerate(order):
        for scope, color in (("all", "#c9d9e6"), ("open_field", "#1f5f8b")):
            row = summ[(summ["crop"] == c) & (summ["scope"] == scope)]
            if row.empty or row["n_intervals"].iloc[0] == 0:
                continue
            ivs = union_intervals([tuple(map(int, s.split("-")))
                                   for s in row["intervals_doy"].iloc[0].split("; ")])
            for a, b in ivs:
                if scope == "all":
                    ax.barh(i, b - a + 1, left=a, height=0.72, color=color,
                            edgecolor="white", linewidth=0.5, zorder=1)
                else:
                    ax.barh(i, b - a + 1, left=a, height=0.30, color=color,
                            edgecolor="white", linewidth=0.4, zorder=3)
        st = summ[(summ["crop"] == c) & (summ["scope"] == "all")]
        lab = st["sensitive_stage_agronomy"].iloc[0] if len(st) else ""
        ax.text(368, i, f" 农学高敏感期：{lab}", va="center", fontsize=8.2, color="#333333")
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels(order)
    ax.set_xlim(1, 530)
    ax.set_xticks([1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335])
    ax.set_xticklabels(["1月", "2月", "3月", "4月", "5月", "6月", "7月",
                        "8月", "9月", "10月", "11月", "12月"])
    ax.invert_yaxis()
    ax.set_xlabel("日序（DOY，非闰年）")
    ax.set_title("图 F34：沈阳本地核心蔬菜的采收上市窗口（物候机制解释层）\n"
                 "浅蓝=全部本地生产行并集（all）；深蓝=仅露地（open_field，主口径）；"
                 "原文粒度：旬/月，未提升精度\n"
                 "仅表示本地生产上市时段，不代表批发市场商品真实来源")
    render_figure(fig, "F34_phenology_windows.png")


def fig_interaction(bc: pd.DataFrame):
    plt = setup_matplotlib()
    hz = [h["key"] for h in HAZARDS]
    hlab = [h["label"] for h in HAZARDS]
    fig, axes = plt.subplots(2, 2, figsize=(13.0, 9.4))
    for ri, scope in enumerate(SCOPES):
        for ai, (rkey, ylab) in enumerate([("price", "价格异常度 z"), ("volume", "成交量异常度 z")]):
            ax = axes[ri][ai]
            sub = bc[(bc["response"] == rkey) & (bc["scope"] == scope)]
            crops = [c for c in CORE_CROPS
                     if len(sub[sub["crop"] == c])]
            M = np.full((len(crops), len(hz)), np.nan)
            S = np.zeros((len(crops), len(hz)), dtype=bool)
            for i, c in enumerate(crops):
                for j, k in enumerate(hz):
                    r = sub[(sub["crop"] == c) & (sub["hazard"] == k)]
                    if len(r):
                        M[i, j] = r["beta_interaction"].iloc[0]
                        S[i, j] = bool(r["sig_fdr05"].iloc[0])
            vmax = np.nanmax(np.abs(M)) if np.isfinite(M).any() else 1.0
            im = ax.imshow(M, cmap="RdBu_r", vmin=-vmax, vmax=vmax, aspect="auto")
            ax.set_xticks(range(len(hz)))
            ax.set_xticklabels(hlab, rotation=22, ha="right", fontsize=8.5)
            ax.set_yticks(range(len(crops)))
            ax.set_yticklabels(crops, fontsize=9)
            for i in range(len(crops)):
                for j in range(len(hz)):
                    if np.isfinite(M[i, j]):
                        ax.text(j, i, f"{M[i, j]:+.2f}" + ("*" if S[i, j] else ""),
                                ha="center", va="center", fontsize=8)
            ttl = "露地（主口径）" if scope == "open_field" else "全部本地生产行"
            ax.set_title(f"{ttl} | {ylab}", fontsize=10.5)
            fig.colorbar(im, ax=ax, shrink=0.80)
    fig.suptitle("图 F35：本地上市窗口对「极端天气 → 市场异常」的放大效应（交互项，逐品种，HAC-14）\n"
                 "数值 = 窗口内天气响应斜率的额外变化；* = BH-FDR<0.05（按口径内家族校正）；"
                 "空白 = 该口径下无可用窗口",
                 fontsize=11.2, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.91))
    render_figure(fig, "F35_phenology_interaction.png")


# -----------------------------------------------------------------------------
# 5) main
# -----------------------------------------------------------------------------
def main() -> None:
    set_seed()
    log = get_logger(MOD)
    log.info("=" * 78)
    log.info("STEP 21 物候机制解释层（§四十五~§四十六）")

    det, summ, windows_map = build_windows(log)
    if det.empty:
        return

    panel = load_parquet("panel_final")
    weather = load_parquet("weather_daily")
    require_columns(panel, ["date", "crop", "doy", "is_public_holiday",
                           "price_anomaly_z_hist", "volume_anomaly_z_hist"], MOD)
    require_columns(weather, [h["col"] for h in HAZARDS], MOD)

    bc, pl, desc = run_interactions(panel, summ, windows_map, weather, log)
    fig_windows(det, summ)
    fig_interaction(bc)

    n_sig_of = int(bc[(bc["scope"] == "open_field")]["sig_fdr05"].sum())
    n_sig_all = int(bc[(bc["scope"] == "all")]["sig_fdr05"].sum())
    n_open = int(summ[(summ["scope"] == "open_field") & summ["identified_interaction"]].shape[0])
    n_all = int(summ[(summ["scope"] == "all") & summ["identified_interaction"]].shape[0])

    # ---- 报告 --------------------------------------------------------------
    L: List[str] = []
    L.append("# STEP 21 物候机制解释层（Phase 10，§四十五~§四十六）\n")
    L.append("## 0. 定位与红线\n")
    L.append("- 本层是**农业气象机制解释层**，不是市场商品来源标签。")
    L.append("- 批发市场货源不一定来自沈阳本地。因此所有结论只能表述为"
             "「本地上市窗口与天气冲击的时间重叠与生育期敏感机制**一致**」，"
             "**不得**表述为「市场商品因本地生育期受灾」。\n")

    L.append("## 1. 数据可用性与降级说明（重要）\n")
    L.append("- `data/raw/metadata/crop_calendar.csv` 共 22 行；**10 个核心品种的本地行"
             "全部未提供 flowering_period / fruiting_period 等阶段级日期**，"
             "原文粒度仅到「旬/月」，多数行只给播种期与采收期。")
    L.append("- 因此**无法**构造「开花坐果期 / 结球期 / 块茎膨大期」的日窗口。"
             "本模块以**本地采收上市窗口（harvest_start ~ harvest_end）**作为 "
             "`Local Crop Stage` 的代理 → **窗口构造含代理降级**。")
    L.append("- 农学高敏感期（`crop_agronomy.growth_stage`，如黄瓜「开花坐果期」）"
             "仅作为窗口内的机制描述文本保留，**未**用于构造窗口。")
    L.append("- 旬/月 → DOY 的转换规则：上旬=1-10，中旬=11-20，下旬=21-月末；"
             "「中下旬」=11-月末；给出具体日则用具体日。不提升原文精度。\n")

    L.append("## 2. 窗口口径（两个 scope，主/次分开）\n")
    L.append("- **`open_field`（主口径）**：仅**露地**生产行。机制先验：露地货源直接"
             "暴露于降水/高温/风，天气冲击最可能在此产生可识别的额外放大；"
             "设施（温室/大棚/拱棚）削弱气象暴露，故不进入主口径。")
    L.append("- **`all`（次口径）**：本地全部生产行（露地 + 设施 + 混合）并集，"
             "代表「本地可能上市期」的最宽定义。")
    L.append("- 说明：辽宁/沈阳的**西红柿、青椒、茄子**本地日历行**全部为设施**，"
             "故在主口径下无可用窗口（空白，非缺失填补）。\n")
    L.append("### 2.1 合并后窗口一览（已去重叠）\n")
    L.append("| 品种 | 口径 | 区间数 | 日序区间（DOY） | 覆盖天数 | 占全年 | 交互可识别 | 农学高敏感期 |")
    L.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for _, r in summ.iterrows():
        sn = "露地" if r["scope"] == "open_field" else "全部"
        L.append(f"| {r['crop']} | {sn} | {r['n_intervals']} | {r['intervals_doy']} | "
                 f"{r['window_days_total']} | {r['window_share_of_year']} | "
                 f"{'是' if r['identified_interaction'] else '否'} | "
                 f"{r['sensitive_stage_agronomy']} |")
    L.append("")
    L.append(f"主口径可用品种：**{n_open}/10**；次口径可用品种：**{n_all}/10**"
             "（韭菜因农技资料记为「全年割茬」而交互不可识别，已排除，不插补）。\n")

    L.append("## 3. 检验设计\n")
    L.append("```text")
    L.append("y = b0 + b1*z_hazard + b2*(z_hazard x in_window) + b3*in_window")
    L.append("      + b4*is_public_holiday  ( + 品种固定效应，pooled 时 )")
    L.append("```\n")
    L.append(f"- 估计：Newey-West / HAC，maxlags={HAC_LAGS}。")
    L.append("- y = 去季节化稳健 z（主方法：留一年法历史同期中位数）；"
             "`z_hazard` 按全序列 sd 标准化（与 STEP15-17 同口径）。")
    L.append("- 关注系数 **b2**：窗口内天气响应斜率的**额外**变化。b2≠0 即窗口内外响应不同。")
    L.append("- 多重检验：**按口径内家族**分别 BH-FDR"
             "（主口径 6×5×2=60，次口径 9×5×2=90），两口径不混合。")
    L.append("- 未加入完整日期固定效应（§三十九：会吸收天气变异）；"
             "响应变量本身已去季节化。\n")

    L.append("## 4. 结果\n")
    L.append(f"- 主口径（露地）逐品种交互：FDR<0.05 者 **{n_sig_of}** 个。")
    L.append(f"- 次口径（全部本地行）逐品种交互：FDR<0.05 者 **{n_sig_all}** 个。")
    if not pl.empty:
        pooled_sig = int(pl["sig_fdr05"].sum())
        L.append(f"- pooled（品种固定效应）交互：{len(pl)} 个，FDR<0.05 者 **{pooled_sig}** 个。")
        L.append("\n### 4.1 pooled 交互项\n")
        L.append("| 口径 | 响应 | 天气变量 | 品种数 | b2(交互) | 95%CI | p | FDR p | n |")
        L.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for _, r in pl.iterrows():
            sn = "露地" if r["scope"] == "open_field" else "全部"
            rn = "价格" if r["response"] == "price" else "成交量"
            L.append(f"| {sn} | {rn} | {r['hazard_label']} | {r['n_crops']} | "
                     f"{r['beta_interaction']:+.4f} | [{r['ci_low']:+.4f}, {r['ci_high']:+.4f}] | "
                     f"{r['p_interaction']:.4f} | {r['fdr_p_interaction']:.4f} | {r['n']} |")
    sig_rows = bc[bc["sig_fdr05"]] if len(bc) else bc
    L.append("")
    if len(sig_rows):
        L.append("### 4.2 FDR 显著的逐品种交互\n")
        L.append("| 口径 | 响应 | 品种 | 天气变量 | b2(交互) | p | FDR p |")
        L.append("| --- | --- | --- | --- | --- | --- | --- |")
        for _, r in sig_rows.iterrows():
            sn = "露地" if r["scope"] == "open_field" else "全部"
            rn = "价格" if r["response"] == "price" else "成交量"
            L.append(f"| {sn} | {rn} | {r['crop']} | {r['hazard_label']} | "
                     f"{r['beta_interaction']:+.4f} | {r['p_interaction']:.4f} | "
                     f"{r['fdr_p_interaction']:.4f} |")
    else:
        L.append("### 4.2 FDR 显著的逐品种交互\n")
        L.append("无（全部 NULL 结果如实呈现，未挑结果）。")

    L.append("\n### 4.3 窗口内外描述性斜率（不构成因果推断）\n")
    if not bc.empty:
        piv = (bc.assign(ab=lambda d: d["slope_in_window"].abs() - d["slope_out_window"].abs(),
                         valid=lambda d: d["slope_in_window"].notna() & d["slope_out_window"].notna())
                 .query("valid")
                 .groupby(["scope", "response", "hazard"])
                 .agg(n_crop=("crop", "size"),
                      n_in_abs_larger=("ab", lambda s: int((s > 0).sum())),
                      median_abs_delta=("ab", "median"))
                 .reset_index())
        L.append("| 口径 | 响应 | 天气变量 | 品种数 | |窗口内斜率|更大者 | 中位 |Δ斜率| |")
        L.append("| --- | --- | --- | --- | --- | --- |")
        for _, r in piv.iterrows():
            sn = "露地" if r["scope"] == "open_field" else "全部"
            rn = "价格" if r["response"] == "price" else "成交量"
            L.append(f"| {sn} | {rn} | {r['hazard']} | {r['n_crop']} | "
                     f"{r['n_in_abs_larger']} | {r['median_abs_delta']:+.4f} |")
        L.append("")
        L.append("> 该表仅为描述性对照；斜率差异未做显著性检验，窗口内外样本的天气分布"
                 "本就不同，**不得**据此宣称放大效应。")

    L.append("\n## 5. 结论（对应 §四十六）\n")
    pooled_sig = 0 if pl.empty else int(pl["sig_fdr05"].sum())
    if n_sig_of == 0 and n_sig_all == 0 and pooled_sig == 0:
        L.append("**NOT SUPPORTED BY CURRENT DATA**。在现行数据条件下，"
                 "未发现「本地上市窗口 × 极端天气」对市场价格/成交量异常存在"
                 "可统计识别的额外放大效应（主口径与次口径一致）。")
        L.append("- 因此**不能**表述为「本地生育期敏感机制解释了市场异常」，"
                 "也不能据此推断批发市场货源来源。")
        L.append("- 该 NULL 与 STEP 10-17 的整体结论一致（天气→量价、"
                 "冷量价链式传导均未获统计支持）。")
        L.append("- 额外的机制观察（描述性、非检验）：辽宁/沈阳的西红柿、青椒、茄子"
                 "本地日历行**全部为设施栽培**，本来就不具备「露地直接暴露」的机制条件；"
                 "这与「未发现放大效应」在方向上是自洽的。")
    else:
        L.append("存在少数 FDR 显著交互项（见 4.2）。按 §四十六，"
                 "只能表述为「该时间重叠与农业生育期敏感机制一致」，"
                 "**不得**升级为因果或来源归因结论；须在 STEP 26-27 稳健性中复核"
                 "（替换窗口口径、安慰剂窗口、HAC 阶数敏感性）。")

    L.append("\n## 6. 输出清单与证据分级\n")
    L.append("- 表：`phenology_windows.csv`、`phenology_window_summary.csv`、"
             "`phenology_interaction_by_crop.csv`、`phenology_interaction_pooled.csv`、"
             "`phenology_desc_by_window.csv`")
    L.append("- 图：`F34_phenology_windows.png`、`F35_phenology_interaction.png`")
    L.append("- 证据分级：窗口构造 = **Level C（机制证据）+ 代理降级**；"
             "交互检验 = **Level B（统计关联）**。")

    PATHS.report("10_PHENOLOGY.md").write_text("\n".join(L), encoding="utf-8")
    log.info("报告已写出: %s", PATHS.report("10_PHENOLOGY.md"))

    register_results([{
        "result_id": "PHENO-INTERACT",
        "research_question": "RQ6",
        "crop": "全体10品种",
        "period": "2021-01-01~2026-09-14",
        "method": "物候窗口交互检验（本地采收上市窗口 × 标准化天气；HAC-14；"
                  "按口径内家族 BH-FDR）",
        "metric": "交互项 b2（露地主口径 / 全部本地行次口径）",
        "estimate": (float(pl.loc[pl["scope"] == "open_field", "beta_interaction"].abs().max())
                     if (not pl.empty and (pl["scope"] == "open_field").any()) else np.nan),
        "p_value": (float(pl.loc[pl["scope"] == "open_field", "p_interaction"].min())
                    if (not pl.empty and (pl["scope"] == "open_field").any()) else np.nan),
        "robustness": "窗口为采收上市期代理（原文旬/月粒度，无阶段级日期）；"
                      "露地/设施分口径；韭菜全年窗口不可识别已排除",
        "figure": "F35_phenology_interaction.png",
        "table": "phenology_interaction_pooled.csv",
        "evidence_level": "B",
        "notes": (f"NOT SUPPORTED BY CURRENT DATA：露地主口径 FDR 显著 {n_sig_of}/{len(bc[bc['scope']=='open_field'])}，"
                  f"全部本地行口径 {n_sig_all}/{len(bc[bc['scope']=='all'])}，"
                  f"pooled 显著 {pooled_sig}/{len(pl)}；"
                  "crop_calendar 无阶段级日期，窗口以采收上市期代理并已降级登记；"
                  "西红柿/青椒/茄子本地行全为设施，露地主口径无可用窗口（空白非填补）；"
                  "§四十五/四十六：仅作机制解释层，不作市场来源标签"),
    }])
    log.info("STEP 21 完成")


if __name__ == "__main__":
    main()
