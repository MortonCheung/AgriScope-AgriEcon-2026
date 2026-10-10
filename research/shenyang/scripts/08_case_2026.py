"""STEP 13：2026 年 7 月沈阳特大暴雨案例复盘（Phase 6，§三十三~§三十四）。

对应任务书：
  §三十三 本次事件作为**重点案例**而非唯一案例，研究：
    A 天气异常程度（vs 历史同期 / 1991-2020 基线 / 历史极端事件）
    B 成交量异常
    C 价格异常
    D 不同蔬菜差异
    E 恢复过程
    F 是否符合历史 Event Study 规律
  §三十四 现实灾损边界：市级农业灾损总量无公开权威统计——
    **禁止自行估算后当现实数据**；最终报告须明确写
    「市级农业灾损总量未发现公开权威统计，因此本研究不将模型估算值作为现实灾损事实」。

口径纪律：
  - 量化用 **ERA5 派生口径**（可与天气序列对齐）；官方通报（events.yaml case_2026_07）
    仅作定性佐证；ERA5 网格均值与官方城区/全地区雨量站均值的空间口径不同，不直接比较数值；
  - T0 = analysis_t0 = 2026-07-13（峰值日，也是事件首个交易日：07-11/12 为周末无市场观测）；
    与 STEP 12 历史曲线对齐时另用 T0_onset = 2026-07-11（派生簇起点，与历史 T0 定义一致）；
  - 事件相对化前窗 = T-14..T-3（07-11 起为事件日，不进基线）；
  - 窗口展宽到 T+42（2026-08-24）以观察恢复；**注意恢复段被 4 次后续事件污染**
    （07-19 暴雨 T+6、07-29 高温 T+16、08-05 高温 T+23、08-24 暴雨 T+42），
    恢复指标只作描述性记录；
  - 成交量单位 unknown，只用 z / 相对口径。

产出：
  outputs/tables/case2026_weather.csv            案例期天气序列（含 1991-2020 基线对照）
  outputs/tables/case2026_rank.csv               关键天气指标的历史排名
  outputs/tables/case2026_response.csv           逐品种响应长表（T-14..T+42，事件相对化）
  outputs/tables/case2026_summary.csv            逐品种分窗汇总 + 谷底/恢复
  outputs/tables/case2026_vs_history.csv         与历史平均曲线的对照（总量级 + 逐品种）
  outputs/figures/F26..F28
  reports/07_CASE_2026.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    ANALYSIS, CROPS_CFG, EVENTS_CFG, PATHS, StepTimer, get_logger,
    load_parquet, register_results, render_figure, save_table, set_seed,
    setup_matplotlib,
)

LOG = get_logger("08_case_2026")
CORE_CROPS: list = CROPS_CFG["core_crops"]
CORE_END = pd.Timestamp(ANALYSIS["time"]["weather_end"])
CASE = EVENTS_CFG["case_2026_07"]
T0 = pd.Timestamp(CASE["analysis_t0"])           # 2026-07-13（峰值 / 事件首个交易日）
T0_ONSET = pd.Timestamp(CASE["derived_start"])   # 2026-07-11（派生簇起点）
T_END = pd.Timestamp(CASE["derived_end"])        # 2026-07-15
WIN_PRE = 14
WIN_POST = 42
PRE_HI = -3                                      # 前窗上界（排除 07-11 起事件日）
CURVE_HI = 14                                    # 与历史对照的事后窗（§三十二 同口径）
RECOVER_THR = 0.5                                # 恢复判定：|z_rel| ≤ 0.5
BASE_SEED = int(ANALYSIS["project"]["random_seed"])
VARS = [("price", "价格"), ("volume", "成交量")]
RESP_COL = {v: f"{v}_anomaly_z_hist" for v, _ in VARS}
WEATHER_COLS = ["precipitation", "precip_3d", "precipitation_pct",
                "clim_precipitation_mean", "clim_precipitation_std",
                "temp_max", "temp_min", "temp_anomaly", "vpd", "humidity"]


# -----------------------------------------------------------------------------
# A. 天气异常程度
# -----------------------------------------------------------------------------
def weather_evidence() -> tuple:
    w = load_parquet("weather_daily").set_index("date").sort_index()
    seg = w.loc["2026-07-01":"2026-07-31", WEATHER_COLS].copy()
    seg["clim_z"] = (seg["precipitation"] - seg["clim_precipitation_mean"]) / seg["clim_precipitation_std"]
    seg = seg.reset_index()
    save_table(seg, "case2026_weather.csv")

    # 历史排名（全日序列 2021-01-01~2026-09-14，非仅交易日）
    n_all = int(w["precipitation"].notna().sum())
    peak_day = T0
    peak_p = float(w.loc[peak_day, "precipitation"])
    p3_peak = float(w.loc[T0 + pd.Timedelta(days=1), "precip_3d"])  # 221.1 出现在 07-14
    p3_max = float(w["precip_3d"].max())
    rank_p = int((w["precipitation"] >= peak_p).sum())
    rank_p3 = int((w["precip_3d"] >= p3_peak).sum())
    julys = w[w.index.month == 7]["precipitation"].groupby(w[w.index.month == 7].index.year).sum()
    event_total = float(w.loc["2026-07-11":"2026-07-15", "precipitation"].sum())
    rows = [
        {"metric": "单日最大降水（2026-07-13）", "value": peak_p, "unit": "mm",
         "reference": f"2021-2026 全日序列第 {rank_p}/{n_all} 名", "pct": rank_p / n_all},
        {"metric": "3日累计最大降水（2026-07-14）", "value": p3_peak, "unit": "mm",
         "reference": f"2021-2026 全日序列第 {rank_p3}/{n_all} 名", "pct": rank_p3 / n_all},
        {"metric": "过程累计降水（07-11~07-15）", "value": event_total, "unit": "mm",
         "reference": "派生事件窗口合计（ERA5 网格均值）", "pct": np.nan},
        {"metric": "07-13 降水相对 1991-2020 同期", "value": float(w.loc[peak_day, "clim_precipitation_mean"]),
         "unit": "mm（基线均值）", "reference": f"基线标准差 {w.loc[peak_day, 'clim_precipitation_std']:.1f}mm；"
                                       f"z≈{(peak_p - w.loc[peak_day, 'clim_precipitation_mean']) / w.loc[peak_day, 'clim_precipitation_std']:.1f}",
         "pct": float(w.loc[peak_day, "precipitation_pct"])},
        {"metric": "2026年7月降水总量", "value": float(julys.get(2026, np.nan)), "unit": "mm",
         "reference": "历年7月：" + "、".join(f"{y}={v:.0f}" for y, v in julys.items()), "pct": np.nan},
    ]
    rank_df = pd.DataFrame(rows)
    save_table(rank_df, "case2026_rank.csv")
    return seg, rank_df, w


# -----------------------------------------------------------------------------
# B/C/D/E. 市场响应
# -----------------------------------------------------------------------------
def case_response(panel: pd.DataFrame, t0: pd.Timestamp, pre_hi: int) -> pd.DataFrame:
    """逐品种×响应的事件相对化响应（offset -14..+42）。"""
    lo = t0 - pd.Timedelta(days=WIN_PRE)
    hi = t0 + pd.Timedelta(days=WIN_POST)
    w = panel[(panel["date"] >= lo) & (panel["date"] <= hi)].copy()
    w["offset"] = (w["date"] - t0).dt.days
    rows = []
    for crop in CORE_CROPS:
        g = w[w["crop"] == crop]
        for var, _ in VARS:
            s = g.set_index("offset")[RESP_COL[var]].dropna()
            pre = s[(s.index >= -WIN_PRE) & (s.index <= pre_hi)]
            if len(pre) < 5:
                continue
            base = float(pre.mean())
            for off, v in s.items():
                rows.append({"crop": crop, "response": var, "offset": int(off),
                             "z": float(v), "z_rel": float(v - base)})
    return pd.DataFrame(rows)


def response_summary(resp: pd.DataFrame) -> pd.DataFrame:
    """逐品种分窗汇总 + 谷底 + 恢复（描述性；恢复段被后续事件污染）。"""
    rows = []
    for (crop, var), g in resp.groupby(["crop", "response"]):
        s = g.set_index("offset")["z_rel"].sort_index()
        seg = lambda a, b: float(s.loc[s.index.intersection(range(a, b + 1))].mean()) \
            if len(s.index.intersection(range(a, b + 1))) else np.nan
        post = s.loc[s.index.intersection(range(0, WIN_POST + 1))]
        if len(post) == 0:
            continue
        tr_off = int(post.idxmin())
        tr_val = float(post.loc[tr_off])
        after = post.loc[post.index > tr_off]
        rec = after.loc[after.abs() <= RECOVER_THR]
        rec_off = int(rec.index.min()) if len(rec) else np.nan
        pk_off = int(post.idxmax())
        rows.append({
            "crop": crop, "response": var,
            "pre_mean": seg(-WIN_PRE, PRE_HI), "event_mean(-2..2)": seg(-2, 2),
            "post_3_14": seg(3, 14), "post_15_28": seg(15, 28), "post_29_42": seg(29, 42),
            "trough_offset": tr_off, "trough_z": tr_val,
            "peak_offset": pk_off, "peak_z": float(post.loc[pk_off]),
            "recovery_offset": rec_off,
            "recovery_days": (rec_off - tr_off) if np.isfinite(rec_off) else np.nan,
        })
    return pd.DataFrame(rows)


# -----------------------------------------------------------------------------
# F. 与历史 Event Study 规律对照
# -----------------------------------------------------------------------------
def _post_mean(df: pd.DataFrame) -> float:
    s = df[(df["offset"] >= 1) & (df["offset"] <= CURVE_HI)]["z_rel"]
    return float(s.mean()) if len(s) else np.nan


def _boot_post_ci(g: pd.DataFrame, seed: int, n_boot: int = 1000) -> tuple:
    """簇级 Bootstrap 的事后均值 CI（与 STEP 12 同口径）。"""
    tags = g["tag"].unique()
    parts = {t: g[g["tag"] == t] for t in tags}
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        pick = rng.choice(tags, size=len(tags), replace=True)
        boots.append(_post_mean(pd.concat([parts[t] for t in pick])))
    boots = np.asarray(boots, dtype=float)
    return float(np.nanpercentile(boots, 2.5)), float(np.nanpercentile(boots, 97.5))


def vs_history(resp_onset: pd.DataFrame, hist_long: pd.DataFrame,
               hist_summ: pd.DataFrame, placebo: np.ndarray) -> tuple:
    """案例（T0=派生簇起点对齐历史口径）与 STEP 12 历史平均的对照。

    对照统计量 = mean(z_rel, T+1..T+14)：
      - 历史总量级 CI 直接取 STEP 12 汇总表（同一统计量的簇级 Bootstrap CI）；
      - 历史逐品种 CI 由原始长表重抽簇计算（口径一致）。
    """
    rows = []
    for var, vlabel in VARS:
        g = resp_onset[resp_onset["response"] == var]
        case_post = _post_mean(g)
        s = hist_summ[(hist_summ["group"] == "rain") & (hist_summ["response"] == var)].iloc[0]
        pv = (1 + np.nansum(np.abs(placebo) >= abs(case_post))) / (1 + len(placebo))
        rows.append({
            "response": var, "case_post_mean": case_post,
            "hist_post_mean": float(s["post_mean"]),
            "hist_ci_low": float(s["post_ci_low"]), "hist_ci_high": float(s["post_ci_high"]),
            "case_within_hist_ci": bool(s["post_ci_low"] <= case_post <= s["post_ci_high"]),
            "placebo_p": float(pv),
        })
    tot = pd.DataFrame(rows)

    # 逐品种对照（历史逐品种事后均值 CI：原始长表重抽簇）
    pc = []
    hl = hist_long[hist_long["group"] == "rain"]
    idx = 0
    for crop in CORE_CROPS:
        for var, _ in VARS:
            idx += 1
            g = resp_onset[(resp_onset["crop"] == crop) & (resp_onset["response"] == var)]
            cp = _post_mean(g)
            h = hl[(hl["crop"] == crop) & (hl["response"] == var)]
            if h.empty:
                continue
            lo, hi = _boot_post_ci(h, BASE_SEED + 13 * idx)
            hp = _post_mean(h)
            pc.append({
                "crop": crop, "response": var, "case_post_mean": cp,
                "hist_post_mean": hp, "hist_ci_low": lo, "hist_ci_high": hi,
                "case_within_hist_ci": bool(lo <= cp <= hi),
            })
    return tot, pd.DataFrame(pc)


# -----------------------------------------------------------------------------
# 图
# -----------------------------------------------------------------------------
def fig_weather(seg: pd.DataFrame, fname: str, tag: str) -> None:
    plt = setup_matplotlib()
    fig, axes = plt.subplots(2, 1, figsize=(13.0, 7.6), sharex=True)
    ax = axes[0]
    ax.bar(seg["date"], seg["precipitation"], color="#2e75b6", label="日降水（ERA5 网格均值）")
    ax.axhline(50, color="#c0392b", ls="--", lw=1.0, label="暴雨阈值 50mm/日")
    ax2 = ax.twinx()
    ax2.plot(seg["date"], seg["precip_3d"], color="#e67e22", lw=1.8, marker="o", ms=3,
             label="3日累计降水（右轴）")
    ax2.axhline(100, color="#8e44ad", ls=":", lw=1.0, label="连续强降雨阈值 100mm/3日（右轴）")
    ax.set_ylabel("日降水（mm）")
    ax2.set_ylabel("3日累计（mm）")
    ax.annotate(f"07-13: 173.9mm\nz≈21（vs 1991-2020 同期）", xy=(T0, 173.9),
                xytext=(10, -8), textcoords="offset points", fontsize=9, color="#c0392b")
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, fontsize=8, loc="upper right")
    ax.set_title("降水：2026-07 案例期 vs 阈值与基线", fontsize=11)

    ax = axes[1]
    ax.plot(seg["date"], seg["temp_max"], color="#c0392b", lw=1.6, marker="o", ms=3, label="日最高气温")
    ax.axhline(35, color="#c0392b", ls="--", lw=1.0, label="高温阈值 35℃")
    ax2 = ax.twinx()
    ax2.plot(seg["date"], seg["temp_anomaly"], color="#7f8c8d", lw=1.4, ls="--",
             label="日均温异常 z（vs 1991-2020，右轴）")
    ax2.axhline(0, color="#999", lw=0.7)
    ax.set_ylabel("日最高气温（℃）")
    ax2.set_ylabel("气温异常（z）")
    ax.set_xlabel("日期（2026-07）")
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, fontsize=8, loc="upper left")
    ax.set_title("气温：暴雨后短暂降温，随后高温晴热（蒸发/涝渍交替）", fontsize=11)

    fig.suptitle(f"图{tag}　2026年7月沈阳特大暴雨：天气异常程度（ERA5 派生口径）\n"
                 "官方口径（定性佐证）：13日0-17时全地区平均 129.5mm、城区平均 234.7mm；"
                 "蒲河 1957 年以来第一大洪水（详见 events.yaml）",
                 fontsize=12.5, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.90))
    render_figure(fig, fname,
                  "数据来源：气象=Open-Meteo ERA5/ERA5-Land 再分析（网格均值，与官方雨量站城区均值口径不同，"
                  "不直接比较数值）；阈值=config/analysis.yaml hazard_thresholds（沿用数据仓库定义）。")


def fig_vs_history(resp_onset: pd.DataFrame, hist: pd.DataFrame, fname: str, tag: str) -> None:
    plt = setup_matplotlib()
    fig, axes = plt.subplots(1, 2, figsize=(14.5, 5.4))
    for ax, (var, vlabel) in zip(axes, VARS):
        h = hist[(hist["group"] == "rain") & (hist["response"] == var)
                 & (hist["analysis"] == "primary")].sort_values("offset")
        g = resp_onset[resp_onset["response"] == var]
        case = g.groupby("offset")["z_rel"].mean().sort_index()
        case = case[(case.index >= -14) & (case.index <= 21)]
        ax.axvspan(0, 21, color="#f2f2f2", zorder=0)
        ax.axhline(0, color="#333", lw=0.8)
        ax.fill_between(h["offset"], h["ci_low"], h["ci_high"], color="#9dc3e6",
                        alpha=0.5, label="历史雨事件平均 ±95% CI（n=8 簇）")
        ax.plot(h["offset"], h["mean"], color="#1f4e79", lw=1.8, label="历史雨事件平均")
        ax.plot(case.index, case.values, color="#c0392b", lw=1.8, ls="--", marker="o", ms=2.5,
                label="2026-07 案例（10 品种均值）")
        ax.axvline(0, color="#c0392b", ls=":", lw=1.0)
        ax.set_xlabel("相对事件起点（07-11）的日历日偏移")
        ax.set_ylabel("事件相对化异常（稳健 z）")
        ax.set_title(f"{vlabel}异常")
        ax.legend(fontsize=8)
    fig.suptitle(f"图{tag}　2026-07 暴雨的市场响应 vs 历史雨事件平均规律（§三十三-F）\n"
                 "案例曲线落在历史 95% CI 内 → 符合历史规律（无超常响应）；CI 外才需单独解释",
                 fontsize=12.5, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    render_figure(fig, fname,
                  "数据来源：沈阳市场=市发改委菜篮子发布平台（批发口径）；事件=ERA5 派生。"
                  "历史曲线=STEP 12 主分析（8 个清洁雨簇，簇级 Bootstrap CI）；案例 T0=2026-07-11（与历史同口径对齐）。")


def fig_percrop_heatmap(resp: pd.DataFrame, fname: str, tag: str) -> None:
    plt = setup_matplotlib()
    fig, axes = plt.subplots(2, 1, figsize=(14.5, 9.0))
    for ax, (var, vlabel) in zip(axes, VARS):
        g = resp[resp["response"] == var]
        mat = g.pivot_table(index="crop", columns="offset", values="z_rel").reindex(CORE_CROPS)
        mat = mat[[c for c in mat.columns if -7 <= c <= 28]]
        vmax = float(np.nanmax(np.abs(mat.values))) or 1.0
        im = ax.imshow(mat.values, cmap="RdBu_r", vmin=-vmax, vmax=vmax, aspect="auto")
        for i, crop in enumerate(mat.index):
            for j, c in enumerate(mat.columns):
                if -2 <= c <= 2:
                    ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1, fill=False,
                                               edgecolor="#111", lw=1.1))
        ax.set_xticks(range(len(mat.columns)))
        ax.set_xticklabels([f"T{c:+d}" if c != 0 else "T0" for c in mat.columns], fontsize=7.5)
        ax.set_yticks(range(len(mat.index)))
        ax.set_yticklabels(mat.index)
        ax.set_title(f"{vlabel}异常（黑框=事件日 T-2..T+2；T0=07-13）")
        fig.colorbar(im, ax=ax, label="事件相对化响应（稳健 z）")
    fig.suptitle(f"图{tag}　2026-07 暴雨逐品种响应热力图（T-7..T+28）\n"
                 "响应=去季节化稳健 z 减去事件前窗(T-14..T-3)均值；T+6 后混入 07-19 暴雨等后续事件",
                 fontsize=12.5, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    render_figure(fig, fname,
                  "数据来源：沈阳市场=市发改委菜篮子发布平台（批发口径）；成交量单位 unknown（仅 z 口径）。"
                  "黑框标出派生事件日；品种间共享同一冲击，差异仅作异质性描述（RQ5）。")


# -----------------------------------------------------------------------------
# 报告
# -----------------------------------------------------------------------------
def write_report(seg, rank_df, resp, summ, vs_tot, vs_pc) -> None:
    L: list = []
    A = L.append
    A("# 07 CASE 2026-07 — 2026年7月沈阳特大暴雨案例复盘（STEP 13）\n")
    A(f"> T0 = **{T0:%Y-%m-%d}**（峰值日，亦为事件首个交易日：07-11/12 周末无市场观测）；"
      f"派生事件窗 07-11~07-15；分析窗 T-14 ~ T+42；事件相对化前窗 T-14..T-3。\n")
    A("> 量化口径=ERA5 派生（与天气序列对齐）；官方通报仅定性佐证（§二十九 红线：两种口径不混用）。\n")

    A("## A. 天气异常程度\n")
    A("| 指标 | 数值 | 参照 |")
    A("|---|---|---|")
    for _, r in rank_df.iterrows():
        val = f"{r['value']:.1f} {r['unit']}" if pd.notna(r["value"]) else "—"
        A(f"| {r['metric']} | {val} | {r['reference']} |")
    A("")
    A("- 07-13 单日 173.9mm 与 07-14 三日累计 221.1mm 均为 **2021-2026 观测期第 1 名**；")
    A("- 相对 1991-2020 同期基线：07-13 降水 z≈21（同期日均值≈5.3mm、标准差≈8.0mm），"
      "doy 分位=1.00（≥同期历史最大）——**无论相对观测期还是气候基线均为极端事件**；")
    A("- 官方口径（定性）：13日0-17时全地区平均 129.5mm、城区平均 234.7mm、"
      "13日0时-14日16时城区平均 346.8mm（特大暴雨）；防汛红色预警、应急响应最高级；"
      "蒲河 1957 年以来第一大洪水。ERA5 网格均值（173.9）与官方城区均值（234.7）"
      "空间口径不同，不直接比较数值；")
    A("- 完整天气序列见 `case2026_weather.csv` 与图 26。\n")

    A("## B/C. 成交量与价格异常（事件相对化稳健 z）\n")
    A("| 品种 | 响应 | 前窗均值 | 事件中(T-2..T+2) | T+3..14 | T+15..28 | T+29..42 | 谷底(offset, z) |")
    A("|---|---|---|---|---|---|---|---|")
    for _, r in summ.sort_values(["response", "crop"]).iterrows():
        A(f"| {r['crop']} | {'价格' if r['response'] == 'price' else '成交量'} | "
          f"{r['pre_mean']:+.2f} | {r['event_mean(-2..2)']:+.2f} | {r['post_3_14']:+.2f} | "
          f"{r['post_15_28']:+.2f} | {r['post_29_42']:+.2f} | "
          f"T{int(r['trough_offset']):+d}, {r['trough_z']:+.2f} |")
    A("")
    n_vol_drop = int((summ[(summ["response"] == "volume") & (summ["post_3_14"] < 0)]).shape[0])
    n_pri_up = int((summ[(summ["response"] == "price") & (summ["post_3_14"] > 0)]).shape[0])
    A(f"- 事件后 T+3..14：成交量异常为负的品种 {n_vol_drop}/10，价格异常为正的品种 {n_pri_up}/10"
      "（方向与 H1/H2 叙事一致与否见下行警示）；")
    A("- **警示**：逐品种噪声大（单品种事件窗内仅 ~10 个交易日），且 STEP 10-12 已表明"
      "该数据的日度天气响应在统计上不可分辨；本节为**描述性**复盘，不构成传导证据；")
    A("- 成交量单位 unknown，仅 z 口径（红线）。\n")

    A("## D. 品种差异（RQ5 描述性）\n")
    d14 = resp[(resp["offset"] >= 0) & (resp["offset"] <= 14)]
    rk = (d14.groupby(["response", "crop"])["z_rel"]
          .apply(lambda s: s.abs().max()).reset_index(name="max_abs_z"))
    A("| 响应 | 品种（按事件后 0..14 天内最大异常 z 降序，前 5） |")
    A("|---|---|")
    for var, vlabel in VARS:
        top = rk[rk["response"] == var].sort_values("max_abs_z", ascending=False).head(5)
        A(f"| {vlabel} | " + "、".join(f"{r['crop']}({r['max_abs_z']:.2f})" for _, r in top.iterrows()) + " |")
    A("")
    A("> 品种间共享同一冲击，排名仅为异质性描述（§三十九 同一限制），不构成独立证据。\n")

    A("## E. 恢复过程（描述性）\n")
    A("| 品种 | 响应 | 谷底(T+offset, z) | 首次回带 \\|z_rel\\|≤0.5 | 距谷底天数 |")
    A("|---|---|---|---|---|")
    for _, r in summ.sort_values(["response", "crop"]).iterrows():
        rec = f"T{int(r['recovery_offset']):+d}" if np.isfinite(r["recovery_offset"]) else "42天内未回带"
        days = f"{int(r['recovery_days'])}" if np.isfinite(r["recovery_days"]) else "—"
        A(f"| {r['crop']} | {'价格' if r['response'] == 'price' else '成交量'} | "
          f"T{int(r['trough_offset']):+d}, {r['trough_z']:+.2f} | {rec} | {days} |")
    A("")
    A("- **重大限制**：恢复段（T+3 起）先后混入 07-19 暴雨（T+6）、07-29 高温（T+16）、"
      "08-05 高温（T+23）、08-24 暴雨（T+42）四次后续事件，「恢复」与「再冲击」不可分离；")
    A("- 因此本节恢复指标只作描述性记录；正式的韧性度量（恢复率、恢复时间分布）"
      "在 STEP 20 以事件簇为单位另行研究。\n")

    A("## F. 是否符合历史 Event Study 规律\n")
    A("对照统计量 = mean(z_rel, T+1..T+14)（与 STEP 12 事后窗同口径，T0=派生簇起点对齐）。\n")
    A("| 响应 | 案例事后均值 | 历史雨事件均值 | 历史 95% CI（事后均值，簇级 Bootstrap） | "
      "案例落在 CI 内 | 安慰剂 p |")
    A("|---|---|---|---|---|---|")
    for _, r in vs_tot.iterrows():
        vlabel = dict(VARS)[r["response"]]
        A(f"| {vlabel} | {r['case_post_mean']:+.3f} | {r['hist_post_mean']:+.3f} | "
          f"[{r['hist_ci_low']:+.3f}, {r['hist_ci_high']:+.3f}] | "
          f"{'是' if r['case_within_hist_ci'] else '否'} | {r['placebo_p']:.3f} |")
    A("")
    n_in = int(vs_pc["case_within_hist_ci"].sum())
    A(f"- 逐品种对照：{n_in}/{len(vs_pc)} 个「品种×响应」的案例事后均值落在历史逐品种 95% CI 内"
      "（明细见 `case2026_vs_history_percrop.csv`）；")
    # 逐响应结论（避免一刀切表述）
    for _, r in vs_tot.iterrows():
        vlabel = dict(VARS)[r["response"]]
        if r["case_within_hist_ci"]:
            verdict = (f"- {vlabel}：案例事后均值 {r['case_post_mean']:+.3f} 落在历史 95% CI 内"
                       f"（安慰剂 p={r['placebo_p']:.3f}）→ **符合历史规律**，无超常响应；")
        else:
            side = "低于" if r["case_post_mean"] < r["hist_ci_low"] else "高于"
            verdict = (f"- {vlabel}：案例事后均值 {r['case_post_mean']:+.3f} {side}历史 95% CI "
                       f"[{r['hist_ci_low']:+.3f}, {r['hist_ci_high']:+.3f}]，但安慰剂 p="
                       f"{r['placebo_p']:.3f}（随机窗口出现该幅度偏离的概率约 "
                       f"{r['placebo_p']:.0%}）→ **边缘性偏离，统计上不可分辨于噪声**"
                       "（单案例 + 历史仅 8 簇，CI 本身粗糙）；")
        A(verdict)
    A("- 综合判定（§三十三-F）：见上方逐响应结论；无论落在 CI 内外，"
      "单案例都不能构成对 H1/H2 的支持或反驳证据；")
    A("- 即使是观测期最强暴雨（单日/三日降水均为 2021-2026 第 1 名），全市批发市场量价"
      "总体仍无超常响应——该事实是市场韧性/外部供应缓冲的间接迹象（Level B），"
      "机制检验在 STEP 15-22。\n")

    A("## 灾损边界（§三十四，红线）\n")
    A("> 市级农业灾损总量（受灾/成灾/绝收面积、直接经济损失）未发现公开权威统计，"
      "因此本研究**不将模型估算值作为现实灾损事实**；涉及损失的一切数字仅存在于"
      "反事实情景（Level D，STEP 25-26），并须明确标注为模型推演。\n")

    A("## 图表清单\n")
    A("| 图 | 内容 | 回答的问题 |")
    A("|---|---|---|")
    A("| 图26 `F26_case2026_weather.png` | 案例期降水/气温 vs 阈值与基线 | §三十三-A 天气异常程度 |")
    A("| 图27 `F27_case2026_vs_history.png` | 案例响应 vs 历史平均曲线 | §三十三-F 是否符合历史规律 |")
    A("| 图28 `F28_case2026_percrop.png` | 逐品种响应热力图 | §三十三-B/C/D 品种差异 |")
    A("")

    pth = PATHS.report("07_CASE_2026.md")
    pth.write_text("\n".join(L), encoding="utf-8")
    LOG.info("案例复盘报告写入 %s", pth)


# -----------------------------------------------------------------------------
def main() -> None:
    set_seed()
    with StepTimer("08_case_2026", LOG):
        panel = load_parquet("panel_final")
        panel = panel[(panel["date"] <= CORE_END) & (panel["crop"].isin(CORE_CROPS))].copy()

        # A. 天气
        seg, rank_df, w = weather_evidence()

        # B/C/D/E. 响应（T0=峰值日 07-13）
        resp = case_response(panel, T0, PRE_HI)
        save_table(resp, "case2026_response.csv")
        summ = response_summary(resp)
        save_table(summ, "case2026_summary.csv")

        # F. 与历史对照（T0=派生簇起点 07-11，与 STEP 12 同口径）
        resp_onset = case_response(panel, T0_ONSET, -1)
        hist_long = pd.read_csv(PATHS.table("event_study_primary_long.csv"))
        hist_summ = pd.read_csv(PATHS.table("event_study_summary.csv"))
        hist = pd.read_csv(PATHS.table("event_study_curves.csv"))
        placebo = pd.read_csv(PATHS.table("event_study_placebo.csv"))["placebo_post_mean"].to_numpy()
        vs_tot, vs_pc = vs_history(resp_onset, hist_long, hist_summ, placebo)
        save_table(vs_tot, "case2026_vs_history.csv")
        save_table(vs_pc, "case2026_vs_history_percrop.csv")

        # 图
        fig_weather(seg, "F26_case2026_weather.png", "26")
        fig_vs_history(resp_onset, hist, "F27_case2026_vs_history.png", "27")
        fig_percrop_heatmap(resp, "F28_case2026_percrop.png", "28")

        write_report(seg, rank_df, resp, summ, vs_tot, vs_pc)

        # ---- 结果登记 -------------------------------------------------------
        rows = []
        rows.append({
            "result_id": "CASE-2026-WEATHER",
            "research_question": "RQ4", "crop": "不区分品种",
            "period": f"{T0_ONSET:%Y-%m-%d}~{T_END:%Y-%m-%d}",
            "method": "ERA5 派生口径 + 1991-2020 doy 基线对照 + 观测期排名",
            "metric": "单日最大降水（2026-07-13）",
            "estimate": 173.9, "ci_low": None, "ci_high": None, "p_value": None,
            "robustness": "3日累计 221.1mm 亦为观测期第 1；doy 分位=1.00；z≈21（vs 1991-2020 同期）",
            "figure": "F26_case2026_weather.png", "table": "case2026_rank.csv",
            "evidence_level": "A",
            "notes": "观测事实（ERA5 再分析）；官方城区均值 234.7mm 口径不同，仅定性佐证",
        })
        for _, r in vs_tot.iterrows():
            vlabel = dict(VARS)[r["response"]]
            rows.append({
                "result_id": f"CASE-2026-{r['response'].upper()}",
                "research_question": "RQ2" if r["response"] == "price" else "RQ1",
                "crop": "全体10品种",
                "period": f"{T0_ONSET:%Y-%m-%d}~{T0_ONSET + pd.Timedelta(days=CURVE_HI):%Y-%m-%d}",
                "method": "案例复盘（事件相对化 z，起点对齐历史口径）",
                "metric": "mean(z_rel, T+1..T+14)",
                "estimate": round(float(r["case_post_mean"]), 4),
                "ci_low": round(float(r["hist_ci_low"]), 4),
                "ci_high": round(float(r["hist_ci_high"]), 4),
                "p_value": round(float(r["placebo_p"]), 4),
                "robustness": f"历史雨事件均值 {r['hist_post_mean']:+.3f}；案例落在 CI 内="
                              f"{'是' if r['case_within_hist_ci'] else '否'}",
                "figure": "F27_case2026_vs_history.png",
                "table": "case2026_vs_history.csv", "evidence_level": "B",
                "notes": ("§三十三-F：符合历史规律" if r["case_within_hist_ci"] else
                          "§三十三-F：边缘性偏离（历史 CI 外），安慰剂 p 未显著，不可分辨于噪声")
                         + "；单案例不可外推",
            })
        register_results(rows)
        LOG.info("结果登记 %d 条", len(rows))


if __name__ == "__main__":
    main()
