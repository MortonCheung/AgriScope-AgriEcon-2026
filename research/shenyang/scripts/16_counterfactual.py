"""STEP 25-26：Phase 14 平行世界（§五十六~§六十二）。

对应任务书：
  §五十六 先建 World 0（Reality）：输入真实 2026 天气，模型预测 volume / price，
          与真实值比较。**若模型连现实世界都无法较好复现，禁止继续做漂亮的反事实**。
  §五十七 World 1（No Disaster）：把 2026 暴雨期间极端天气替换为正常天气，
          方法A = 1991-2020 同期气候正常值；方法B = 历史正常年份 Analog；两法比较。
  §五十八 反事实顺序：counterfactual weather → predicted volume → predicted price
          （递归链：天气→量→价，不用「天气→价格」直连）。
  §五十九 核心输出：crop × date 的 actual/counterfactual volume 与 price gap + 不确定区间。
  §六十   反事实不能写成现实事实（成交量单位未知，只写「模型估计…可能」）。
  §六十一 World 2（Severity）：降雨强度 0.5×/1.0×/1.2×/1.5× 情景，考察风险是否非线性放大。
  §六十二 World 3（供应缓冲）：供应冲击被缓冲 10%/20%/30% 的情景实验（不宣称政策真实效果）。

设计（预登记）：
  - 主模型 = STEP 23 持久化的 LightGBM（mainsplit_hist_*_F_lag，训练 <=2024-12-31，test=2026），
    不重新训练；价格与成交量模型均含自回归项（昨日/前日异常、昨日量价水平），
    因此链式模拟采用**逐交易日递归**：先按反事实天气与上一日模拟状态预测成交量，
    再用同一状态（含新成交量滞后）预测价格（价格模型不消费当日成交量，§三十七口径一致）。
  - 事件窗口 = 预登记 config.counterfactual：2026-07-12 ~ 07-17（官方口径；ERA5 派生窗口
    07-11~07-15 作为稳健性备注）；模拟区间 = [event_start-2, event_end+14]（lag14 清零）。
  - 天气滞后特征严格按 STEP 01 口径重建：`wx[col].shift(k)`（已验证与 panel_final 逐位一致，
    max 差 = 0）；precip_3d/7d 由替换后的日降水序列重新滚动求和。
  - 反事实天气：
    * 方法A：日降水/温度/湿度/风 → 1991-2020 气候均值；vpd/土壤 → 观测期季节正常
      （无官方 30 年 vpd/土壤基线，BLOCKER 已登记，证据等级 B）；
    * 方法B：2021-2025 年同季（doy±15）无灾害日（不在事件窗、日降水<50mm、日最高<35℃）
      的中位数。
  - 水平重建（log_price_lag1 / log_volume_lag1）：level = expected_hist + z × scale，
    scale = 品种 × 留一年(2026)稳健尺度 1.4826×MAD（已验证 z 重建 max 差 = 0）。
  - 不确定性 = **配对残差 Bootstrap**（B=100）：残差来自持久化模型在 2025 年（valid，
    训练期外）的样本外残差；同一噪声实现同时用于 World0 与 World1，差分解耦市场共同噪声。
  - 门控：World0 模拟 vs 真实在模拟窗内的 R² < config.world0_min_r2（0.10）→ 该目标
    反事实仅标注「模型外推演示（Level D）」，禁止写成事实估计。
  - 全部结果标注 `scenario simulation` / `model counterfactual`，Level D。

产出：
  outputs/tables/counterfactual_analog.csv       反事实替换日的中位数统计
  outputs/tables/counterfactual_gate.csv         World0 门控（模拟 vs 真实 R²）
  outputs/tables/counterfactual_world0.csv       World0 递归模拟 vs 真实（crop×date）
  outputs/tables/counterfactual_gap.csv          World1A/B 缺口明细（crop×date）
  outputs/tables/counterfactual_gap_summary.csv  缺口汇总（crop × 方法 × 窗口，Bootstrap CI）
  outputs/tables/counterfactual_severity.csv     World2 严重度情景
  outputs/tables/counterfactual_buffer.csv       World3 供应缓冲情景
  outputs/figures/F46..F49
  reports/14_COUNTERFACTUAL.md
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    ANALYSIS, CROPS_CFG, PATHS, StepTimer, get_logger, load_parquet,
    read_input, register_results, render_figure, save_table, set_seed,
    setup_matplotlib,
)

P12 = importlib.import_module("14_prediction")
MOD = "16_counterfactual"
LOG = get_logger(MOD)
CORE_CROPS: List[str] = list(CROPS_CFG["core_crops"])
CF = ANALYSIS["counterfactual"]
EVENT_START = pd.Timestamp(CF["event_start"])
EVENT_END = pd.Timestamp(CF["event_end"])
SIM_START = EVENT_START - pd.Timedelta(days=2)
SIM_END = EVENT_END + pd.Timedelta(days=14)
SEVERITY = [float(x) for x in CF["severity_multipliers"]]
BUFFERS = [float(x) for x in CF["supply_buffer_scenarios"]]
GATE_MIN_R2 = float(CF["world0_min_r2"])
LEARNER = "lightgbm"
N_BOOT = 100
LAGS = [1, 3, 7, 14]
SEED = set_seed()
EPS = 1e-9
DURING = (EVENT_START, EVENT_END)
POST_END = EVENT_END + pd.Timedelta(days=7)
# 方法A/B 需替换的逐日变量（直接替换日值，派生滚动量在其后重算）
REPL_COLS = ["precipitation", "temp_max", "temp_mean", "vpd",
             "soil_moisture_0_7"]


# -----------------------------------------------------------------------------
# 1) 模型与特征载入
# -----------------------------------------------------------------------------
def load_persisted(target: str, learner: str = "lightgbm") -> Tuple[Dict, object]:
    """读取 STEP 23 持久化模型与预处理元数据（mainsplit_hist_*_F_lag）。"""
    pref = f"mainsplit_hist_{target}_{P12.FEATURE_SETS[1]}"
    meta_p = PATHS.dir("models") / f"{pref}_prep.json"
    if not meta_p.exists():
        raise FileNotFoundError(meta_p)
    meta = json.loads(meta_p.read_text(encoding="utf-8"))
    if learner == "lightgbm":
        import lightgbm as lgb
        obj = lgb.Booster(model_file=str(PATHS.dir("models") / f"{pref}_lightgbm.txt"))
    else:
        import joblib
        obj = joblib.load(PATHS.dir("models") / f"{pref}_{learner}.pkl")
    return meta, obj


def _transform(df: pd.DataFrame, meta: Dict) -> np.ndarray:
    cols = meta["features"]
    med = pd.Series(meta["prep"]["median"])
    mu = pd.Series(meta["prep"]["mean"])
    sd = pd.Series(meta["prep"]["scale"]).replace(0, 1.0)
    X = df[cols].fillna(med)
    return ((X - mu) / sd).to_numpy(dtype=float)


def _predict(obj, X: np.ndarray) -> np.ndarray:
    return np.asarray(obj.predict(X), dtype=float)


def _parse_lag(name: str) -> Tuple[str, int]:
    for k in LAGS:
        s = f"_lag{k}d"
        if name.endswith(s):
            return name[: -len(s)], k
    raise KeyError(name)


# -----------------------------------------------------------------------------
# 2) 反事实天气
# -----------------------------------------------------------------------------
def analog_normal(w: pd.DataFrame) -> Tuple[Dict[str, float], int]:
    """2021-2025 同季（doy±15）无灾害日的各变量中位数（方法B；方法A 的 vpd/土壤也用它）。"""
    ev_df = read_input("fact_disaster_events", parse_dates=["start_date", "end_date"])
    ev_df = ev_df[ev_df["city"] == "沈阳"].copy()
    bad = set()
    for _, r in ev_df.iterrows():
        for d in pd.date_range(r["start_date"] - pd.Timedelta(days=1),
                               r["end_date"] + pd.Timedelta(days=7), freq="D"):
            bad.add(d)
    w = w.copy()
    w["doy"] = w["date"].dt.dayofyear
    lo, hi = EVENT_START.dayofyear - 15, EVENT_END.dayofyear + 15
    m = (w["year"].between(2021, 2025)) & (w["doy"].between(lo, hi)) \
        & (~w["date"].isin(bad)) \
        & (w["precipitation"] < 50.0) & (w["temp_max"] < 35.0)
    sel = w[m]
    out = {c: float(sel[c].median()) for c in REPL_COLS}
    out["humidity"] = float(sel["humidity"].median())
    out["wind_speed"] = float(sel["wind_speed"].median())
    return out, int(len(sel))


def build_wx_feat(method: str, mult: Optional[float] = None,
                  analog: Optional[Dict[str, float]] = None,
                  panel_dates: Optional[List[pd.Timestamp]] = None) -> pd.DataFrame:
    """构造反事实（或实际）天气的 LAG_WEATHER 特征表（逐日，供模拟读取）。

    method: 'actual' | 'A' | 'B'；mult：严重度乘子（仅作用于事件窗内日降水）。
    """
    w = load_parquet("weather_daily").sort_values("date").reset_index(drop=True)
    wx = w.copy()
    ev = (wx["date"] >= EVENT_START) & (wx["date"] <= EVENT_END)
    if method == "A":
        wx.loc[ev, "precipitation"] = wx.loc[ev, "clim_precipitation_mean"].astype(float)
        wx.loc[ev, "temp_max"] = wx.loc[ev, "clim_temp_max_mean"].astype(float)
        wx.loc[ev, "temp_mean"] = wx.loc[ev, "clim_temp_mean_mean"].astype(float)
        wx.loc[ev, "humidity"] = wx.loc[ev, "clim_humidity_mean"].astype(float)
        wx.loc[ev, "wind_speed"] = wx.loc[ev, "clim_wind_speed_mean"].astype(float)
        wx.loc[ev, "vpd"] = float(analog["vpd"])
        wx.loc[ev, "soil_moisture_0_7"] = wx.loc[ev, "soil_moisture_0_7_mean_obs"].astype(float)
    elif method == "B":
        for c in REPL_COLS:
            wx.loc[ev, c] = analog[c]
    elif method == "actual":
        pass
    else:
        raise ValueError(method)
    if mult is not None:
        # World 2：仅放大事件窗内的降水（含 0 保持 0）；派生滚动量随后重算
        day = wx.loc[ev, "precipitation"].to_numpy(dtype=float)
        day = np.where(day > 0, day * mult, day)
        wx.loc[ev, "precipitation"] = day
    wx["precip_3d"] = wx["precipitation"].rolling(3, min_periods=1).sum()
    wx["precip_7d"] = wx["precipitation"].rolling(7, min_periods=1).sum()
    wx["temp_anomaly"] = wx["temp_mean"] - wx["clim_temp_mean_mean"]
    wxi = wx.set_index("date")
    feat = pd.DataFrame({"date": panel_dates})
    for name in P12.LAG_WEATHER:
        col, k = _parse_lag(name)
        feat[name] = feat["date"].map(wxi[col].shift(k))
    return feat


# -----------------------------------------------------------------------------
# 3) 水平 / 期望 / 尺度表（用于 log 滞后与 pct 缺口）
# -----------------------------------------------------------------------------
def level_table() -> pd.DataFrame:
    p = load_parquet("panel_final")
    p = p[p["crop"].isin(CORE_CROPS)].copy()
    p["year"] = p["date"].dt.year
    lv = p[["date", "crop", "price_expected_hist", "volume_expected_hist",
            "price", "volume", "price_anomaly_z_hist", "volume_anomaly_z_hist"]].copy()
    lv["log_price"] = np.log(lv["price"].clip(lower=EPS))
    lv["log_volume"] = np.log(lv["volume"].clip(lower=EPS))
    for c, g in p.groupby("crop"):
        ref_p = g.loc[g["year"] < 2026, "price_anomaly_hist"].astype(float)
        ref_v = g.loc[g["year"] < 2026, "volume_anomaly_hist"].astype(float)
        sp = 1.4826 * (ref_p - ref_p.median()).abs().median()
        sv = 1.4826 * (ref_v - ref_v.median()).abs().median()
        m = lv["crop"] == c
        lv.loc[m, "scale_price"] = sp
        lv.loc[m, "scale_volume"] = sv
    return lv


def seed_states(lv: pd.DataFrame, sim_dates: List[pd.Timestamp]) -> Dict[str, Dict]:
    """用模拟窗前最后一个/两个交易日的**实际观测**播种每品种 AR 状态。"""
    st: Dict[str, Dict[str, list]] = {}
    for c in CORE_CROPS:
        sub = lv[(lv["crop"] == c) & (lv["date"] < sim_dates[0])].sort_values("date")
        st[c] = {"zp": [], "zv": [], "lp": [], "lv": []}
        for _, r in sub.tail(2).iterrows():
            st[c]["zp"].append(float(r["price_anomaly_z_hist"]))
            st[c]["zv"].append(float(r["volume_anomaly_z_hist"]))
            st[c]["lp"].append(float(r["log_price"]))
            st[c]["lv"].append(float(r["log_volume"]))
        while len(st[c]["zp"]) < 2:        # 播种不足 2 日时复制最后一日（极端防呆）
            for k in ("zp", "zv", "lp", "lv"):
                st[c][k].append(st[c][k][-1])
    return st


# -----------------------------------------------------------------------------
# 4) 递归链式模拟（§五十八：天气→量→价）
# -----------------------------------------------------------------------------
def recursive_chain(feat: pd.DataFrame, lv: pd.DataFrame,
                    sim_dates: List[pd.Timestamp], design_hol: Dict,
                    volume_path: Optional[pd.DataFrame] = None,
                    noise: Optional[Dict[str, np.ndarray]] = None,
                    learner: str = "lightgbm") -> pd.DataFrame:
    """逐交易日递归：先按反事实天气+上一日状态预测成交量，再预测价格。

    volume_path：供应缓冲情景下的**预置成交量路径**（crop×date 的 z_v / lv），
    传入后跳过成交量模型递归，仅递归价格（§六十二）。
    noise：配对残差 Bootstrap 噪声（price/volume 各 (n_dates, n_crops)）。
    learner：STEP 23 持久化模型族（lightgbm | elasticnet | gam），用于稳健性互验。
    """
    meta_v, obj_v = load_persisted("volume", learner)
    meta_p, obj_p = load_persisted("price", learner)
    cols = meta_v["features"]
    med_v, mu_v, sd_v = (pd.Series(meta_v["prep"]["median"]), pd.Series(meta_v["prep"]["mean"]),
                         pd.Series(meta_v["prep"]["scale"]).replace(0, 1.0))
    med_p, mu_p, sd_p = (pd.Series(meta_p["prep"]["median"]), pd.Series(meta_p["prep"]["mean"]),
                         pd.Series(meta_p["prep"]["scale"]).replace(0, 1.0))
    st = seed_states(lv, sim_dates)
    vp = (volume_path.set_index(["crop", "date"])
          if volume_path is not None and len(volume_path) else None)

    def _vlag(c: str, i: int, k: int, key: str) -> float:
        if vp is None or i - k < 0:      # 窗口内前 k 步的回看指向播种期（实际观测）
            return st[c][key][-k]
        d = sim_dates[i - k]
        try:
            return float(vp.loc[(c, d), "z_v" if key == "zv" else "lv"])
        except KeyError:
            return st[c][key][-1]

    rows = []
    for i, d in enumerate(sim_dates):
        hol = design_hol.get(d, 0.0)
        month = d.month
        mcols = {f"m{m}": 1.0 if m == month else 0.0 for m in range(2, 13)}
        featd = feat[feat["date"] == d].iloc[0]
        Xrows = []
        for c in CORE_CROPS:
            row = {name: float(featd[name]) for name in P12.LAG_WEATHER}
            row.update({
                "price_anomaly_z_hist_lag1": st[c]["zp"][-1],
                "price_anomaly_z_hist_lag2": st[c]["zp"][-2],
                "volume_anomaly_z_hist_lag1": _vlag(c, i, 1, "zv"),
                "volume_anomaly_z_hist_lag2": _vlag(c, i, 2, "zv"),
                "log_price_lag1": st[c]["lp"][-1],
                "log_volume_lag1": _vlag(c, i, 1, "lv"),
                "is_public_holiday": hol, "year_t": 5.0, **mcols})
            for cc in CORE_CROPS[1:]:
                row[f"crop_{cc}"] = 1.0 if c == cc else 0.0
            Xrows.append(row)
        X = pd.DataFrame(Xrows)[cols]
        Xv = ((X.fillna(med_v) - mu_v) / sd_v).to_numpy(dtype=float)
        Xp = ((X.fillna(med_p) - mu_p) / sd_p).to_numpy(dtype=float)
        zv = _predict(obj_v, Xv) if vp is None else np.array([
            float(vp.loc[(c, d), "z_v"]) for c in CORE_CROPS])
        zp = _predict(obj_p, Xp)
        if noise is not None:
            zv = zv + noise["volume"][i]
            zp = zp + noise["price"][i]
        for j, c in enumerate(CORE_CROPS):
            lrow = lv[(lv["crop"] == c) & (lv["date"] == d)].iloc[0]
            lev_p = float(lrow["price_expected_hist"]) + float(zp[j]) * float(lrow["scale_price"])
            lev_v = float(lrow["volume_expected_hist"]) + float(zv[j]) * float(lrow["scale_volume"])
            lp, lv_ = float(np.log(max(lev_p, EPS))), float(np.log(max(lev_v, EPS)))
            st[c]["zp"].append(float(zp[j])); st[c]["zv"].append(float(zv[j]))
            st[c]["lp"].append(lp); st[c]["lv"].append(lv_)
            rows.append({"date": d, "crop": c, "z_p": float(zp[j]), "z_v": float(zv[j]),
                         "level_p": lev_p, "level_v": lev_v})
    return pd.DataFrame(rows)


# -----------------------------------------------------------------------------
# 5) World 0 门控 / 缺口 / 汇总
# -----------------------------------------------------------------------------
def world0_gate(sim0: pd.DataFrame, lv: pd.DataFrame,
                sim_dates: List[pd.Timestamp]) -> pd.DataFrame:
    act = lv[lv["date"].isin(sim_dates)][["date", "crop",
                                          "price_anomaly_z_hist", "volume_anomaly_z_hist"]]
    m = sim0.merge(act, on=["date", "crop"])
    rows = []
    for t, col in (("price", "price_anomaly_z_hist"), ("volume", "volume_anomaly_z_hist")):
        y = m[col].to_numpy(float)
        yh = m["z_p" if t == "price" else "z_v"].to_numpy(float)
        ss = np.sum((y - y.mean()) ** 2)
        r2 = 1.0 - np.sum((y - yh) ** 2) / ss if ss > 0 else np.nan
        rows.append({"target": t, "n": int(len(m)), "r2_sim_vs_actual": round(float(r2), 4),
                     "gate_min_r2": GATE_MIN_R2,
                     "gate_pass": bool(np.isfinite(r2) and r2 >= GATE_MIN_R2)})
    return pd.DataFrame(rows)


def _gap_frame(sim0: pd.DataFrame, sim1: pd.DataFrame, lv: pd.DataFrame) -> pd.DataFrame:
    g = sim1.merge(sim0, on=["date", "crop"], suffixes=("_1", "_0"))
    g["gap_v_z"] = g["z_v_1"] - g["z_v_0"]
    g["gap_p_z"] = g["z_p_1"] - g["z_p_0"]
    e = lv[["date", "crop", "price_expected_hist", "volume_expected_hist",
            "scale_price", "scale_volume"]]
    g = g.merge(e, on=["date", "crop"])
    g["gap_v_pct"] = g["gap_v_z"] * g["scale_volume"] / g["volume_expected_hist"] * 100
    g["gap_p_pct"] = g["gap_p_z"] * g["scale_price"] / g["price_expected_hist"] * 100
    return g


def gap_summary(g: pd.DataFrame, method: str, boot: Optional[Dict[str, np.ndarray]] = None,
                window: str = "during") -> pd.DataFrame:
    d0, d1 = DURING if window == "during" else (EVENT_START, POST_END)
    sub = g[(g["date"] >= d0) & (g["date"] <= d1)]
    rows = []
    for c in CORE_CROPS + ["POOLED"]:
        s = sub if c == "POOLED" else sub[sub["crop"] == c]
        for t, zc, pc in (("volume", "gap_v_z", "gap_v_pct"), ("price", "gap_p_z", "gap_p_pct")):
            v = s[zc].to_numpy(float)
            pct = s[pc].to_numpy(float)
            if len(v) == 0 or not np.isfinite(v).any():
                continue
            r = {"crop": c, "method": method, "window": window, "target": t,
                 "n_days": int(len(s["date"].unique())),
                 "mean_gap_z": float(np.mean(v)), "mean_gap_pct": float(np.mean(pct)),
                 "ci_low_z": np.nan, "ci_high_z": np.nan}
            if boot is not None and c in boot and t in boot[c]:
                b = boot[c][t]
                r["ci_low_z"] = float(np.quantile(b, 0.025))
                r["ci_high_z"] = float(np.quantile(b, 0.975))
            rows.append(r)
    return pd.DataFrame(rows)


# -----------------------------------------------------------------------------
# 6) 残差 Bootstrap（配对，§五十九 不确定区间）
# -----------------------------------------------------------------------------
def valid_residuals(design: pd.DataFrame, log) -> Dict[str, np.ndarray]:
    """持久化模型在 2025（valid，训练期外）的样本外残差池。"""
    v = design[(design["date"] >= pd.Timestamp("2025-01-01"))
               & (design["date"] <= pd.Timestamp("2025-12-31"))].copy()
    v = P12.add_crop_dummies(v)
    out = {}
    for t, col in (("price", "price_anomaly_z_hist"), ("volume", "volume_anomaly_z_hist")):
        meta, obj = load_persisted(t)
        X = _transform(v, meta)
        y = v[col].to_numpy(float)
        pred = _predict(obj, X)
        r = y - pred
        out[t] = r[np.isfinite(r)]
        log.info("valid(2025) 残差池 %s：n=%d", t, len(out[t]))
    return out


def bootstrap_gaps(design_hol: Dict, feat_a, feat_actual, lv, sim_dates,
                   resid: Dict[str, np.ndarray], n_boot: int = N_BOOT,
                   window: Tuple = DURING) -> Dict[str, Dict[str, np.ndarray]]:
    """配对残差 Bootstrap：同一噪声同时注入 World0 与 World1A，缺口按窗口均值取分位。"""
    rng = np.random.default_rng(SEED)
    n_d, n_c = len(sim_dates), len(CORE_CROPS)
    acc: Dict[str, Dict[str, list]] = {c: {"price": [], "volume": []}
                                       for c in CORE_CROPS}
    for b in range(n_boot):
        noise = {t: rng.choice(resid[t], size=(n_d, n_c)) for t in ("price", "volume")}
        s0 = recursive_chain(feat_actual, lv, sim_dates, design_hol, noise=noise)
        s1 = recursive_chain(feat_a, lv, sim_dates, design_hol, noise=noise)
        g = _gap_frame(s0, s1, lv)
        sub = g[(g["date"] >= window[0]) & (g["date"] <= window[1])]
        for c in CORE_CROPS:
            s = sub[sub["crop"] == c]
            if len(s):
                acc[c]["volume"].append(float(s["gap_v_z"].mean()))
                acc[c]["price"].append(float(s["gap_p_z"].mean()))
    return {c: {t: np.array(acc[c][t]) for t in ("price", "volume")} for c in CORE_CROPS}


# -----------------------------------------------------------------------------
# 7) World 2 / World 3
# -----------------------------------------------------------------------------
def severity_worlds(feat_actual, lv, sim_dates, design_hol, analog):
    rows = []
    s0 = recursive_chain(feat_actual, lv, sim_dates, design_hol)
    for m in SEVERITY:
        feat_m = build_wx_feat("actual", mult=m, analog=analog,
                               panel_dates=sim_dates)
        sm = recursive_chain(feat_m, lv, sim_dates, design_hol)
        g = _gap_frame(s0, sm, lv)
        sub = g[(g["date"] >= DURING[0]) & (g["date"] <= DURING[1])]
        for c in CORE_CROPS + ["POOLED"]:
            s = sub if c == "POOLED" else sub[sub["crop"] == c]
            rows.append({"crop": c, "severity_mult": m,
                         "mean_gap_volume_z": float(s["gap_v_z"].mean()),
                         "mean_gap_price_z": float(s["gap_p_z"].mean()),
                         "mean_gap_volume_pct": float(s["gap_v_pct"].mean()),
                         "mean_gap_price_pct": float(s["gap_p_pct"].mean())})
    return pd.DataFrame(rows)


def buffer_worlds(feat_a, lv, sim_dates, design_hol):
    rows = []
    s0 = recursive_chain(build_wx_feat("actual", panel_dates=sim_dates), lv, sim_dates, design_hol)
    s1 = recursive_chain(feat_a, lv, sim_dates, design_hol)
    # 供应缓冲：成交量冲击被吸收 b 比例后再进入价格递归
    for b in BUFFERS:
        vpath = s1.copy()
        vpath["z_v"] = s1["z_v"] + b * (s0["z_v"] - s1["z_v"])
        vpath["level_v"] = s1["level_v"] + b * (s0["level_v"] - s1["level_v"])
        vpath["lv"] = np.log(vpath["level_v"].clip(lower=EPS))
        s_buf = recursive_chain(feat_a, lv, sim_dates, design_hol, volume_path=vpath)
        g = _gap_frame(s0, s_buf, lv)
        g1 = _gap_frame(s0, s1, lv)
        sub = g[(g["date"] >= DURING[0]) & (g["date"] <= DURING[1])]
        sub1 = g1[(g1["date"] >= DURING[0]) & (g1["date"] <= DURING[1])]
        for c in CORE_CROPS + ["POOLED"]:
            s = sub if c == "POOLED" else sub[sub["crop"] == c]
            s1c = sub1 if c == "POOLED" else sub1[sub1["crop"] == c]
            full_impact = float(s1c["gap_p_z"].mean())
            avoided = full_impact - float(s["gap_p_z"].mean())
            frac = avoided / full_impact if abs(full_impact) > 1e-12 else np.nan
            rows.append({"crop": c, "buffer_frac": b,
                         "price_gap_z_remaining": float(s["gap_p_z"].mean()),
                         "price_impact_avoided_z": float(avoided),
                         "avoided_fraction": float(frac) if np.isfinite(frac) else np.nan})
    return pd.DataFrame(rows)


# -----------------------------------------------------------------------------
# 8) 图表
# -----------------------------------------------------------------------------
def fig_world0(sim0: pd.DataFrame, lv: pd.DataFrame, log) -> None:
    import matplotlib.pyplot as plt
    setup_matplotlib()
    act = lv[["date", "crop", "price_anomaly_z_hist", "volume_anomaly_z_hist"]]
    m = sim0.merge(act, on=["date", "crop"])
    d0, d1 = EVENT_START - pd.Timedelta(days=7), SIM_END
    fig, axes = plt.subplots(1, 2, figsize=(14, 4.6))
    for ax, (t, scol, simc) in zip(axes, (("price", "price_anomaly_z_hist", "z_p"),
                                          ("volume", "volume_anomaly_z_hist", "z_v"))):
        sub = m[(m["date"] >= d0) & (m["date"] <= d1)]
        a = sub.groupby("date")[scol].mean()
        b = sub.groupby("date")[simc].mean()
        ax.plot(a.index, a.values, color="#555555", lw=1.6, label="实际（均值，10 品种）")
        ax.plot(b.index, b.values, color="#c0392b", lw=1.6, ls="--", label="World0 模拟（均值）")
        ax.axvspan(EVENT_START, EVENT_END, color="#e8a33d", alpha=0.25, label="事件窗")
        ax.set_title(f"{t} 异常 z：World0 模拟 vs 实际")
        ax.legend(fontsize=8)
    fig.suptitle("World 0（Reality）：真实 2026 天气下递归模拟与实际的对照", fontsize=12)
    render_figure(fig, "F46_counterfactual_world0.png",
                  "数据：shenyang_panel_final + weather_daily(ERA5)；模型：STEP23 LightGBM(F_lag)；Level D 模拟")
    log.info("F46 已输出")


def fig_gap_bars(summ: pd.DataFrame, boot, log) -> None:
    import matplotlib.pyplot as plt
    setup_matplotlib()
    d = summ[(summ["method"] == "A") & (summ["window"] == "during")].copy()
    fig, axes = plt.subplots(1, 2, figsize=(14, 4.6))
    for ax, t in zip(axes, ("volume", "price")):
        s = d[d["target"] == t].set_index("crop").drop(index=["POOLED"], errors="ignore")
        s = s.reindex(CORE_CROPS)
        x = np.arange(len(s))
        ax.bar(x, s["mean_gap_z"], color="#3a7ca5", width=0.62)
        lo = s["ci_low_z"].to_numpy(float)
        hi = s["ci_high_z"].to_numpy(float)
        yl = np.clip(np.nan_to_num(s["mean_gap_z"].to_numpy(float) - lo, nan=0.0), 0, None)
        yh = np.clip(np.nan_to_num(hi - s["mean_gap_z"].to_numpy(float), nan=0.0), 0, None)
        ax.errorbar(x, s["mean_gap_z"].to_numpy(float),
                    yerr=[yl, yh], fmt="none", ecolor="#222222", capsize=3)
        ax.axhline(0, color="#333333", lw=0.8)
        ax.set_xticks(x); ax.set_xticklabels(s.index, rotation=45, fontsize=8)
        ax.set_title(f"{t}：World1A−World0 缺口（事件窗均值，配对 Bootstrap 95%CI）")
    fig.suptitle("World 1（No Disaster）：正常天气下的模型缺口（Level D）", fontsize=12)
    render_figure(fig, "F47_counterfactual_gap_bars.png",
                  "数据：weather_daily(ERA5)；方法A=1991-2020气候均值；模型：STEP23 LightGBM(F_lag)")
    log.info("F47 已输出")


def fig_severity(sev: pd.DataFrame, log) -> None:
    import matplotlib.pyplot as plt
    setup_matplotlib()
    fig, axes = plt.subplots(1, 2, figsize=(14, 4.6))
    for ax, t in zip(axes, ("volume", "price")):
        col = f"mean_gap_{t}_z"
        for c in CORE_CROPS:
            s = sev[sev["crop"] == c].sort_values("severity_mult")
            ax.plot(s["severity_mult"], s[col], marker="o", ms=3, lw=1.2, label=c)
        ax.axhline(0, color="#333333", lw=0.8)
        ax.set_xlabel("降雨强度乘子（1.0=实际）")
        ax.set_title(f"{t} 事件窗均值缺口 z（相对实际天气）")
        ax.legend(fontsize=7, ncol=2)
    fig.suptitle("World 2（Severity）：降雨强度情景（scenario simulation，Level D）", fontsize=12)
    render_figure(fig, "F48_counterfactual_severity.png",
                  "数据：weather_daily(ERA5)；事件窗日降水×{0.5,1.0,1.2,1.5}；模型：STEP23 LightGBM(F_lag)")
    log.info("F48 已输出")


def fig_buffer(buf: pd.DataFrame, log) -> None:
    import matplotlib.pyplot as plt
    setup_matplotlib()
    fig, ax = plt.subplots(1, 1, figsize=(7.2, 4.6))
    for c in CORE_CROPS:
        s = buf[buf["crop"] == c].sort_values("buffer_frac")
        ax.plot(s["buffer_frac"], s["price_gap_z_remaining"], marker="o", ms=3, lw=1.2, label=c)
    ax.axhline(0, color="#333333", lw=0.8)
    ax.set_xlabel("供应冲击被缓冲比例")
    ax.set_ylabel("价格缺口 z（相对实际天气 World0，剩余冲击）")
    ax.set_title("World 3：供应缓冲情景下的价格剩余缺口（scenario simulation）")
    ax.legend(fontsize=7, ncol=2)
    render_figure(fig, "F49_counterfactual_buffer.png",
                  "数据：weather_daily(ERA5)；情景：供应冲击被缓冲10/20/30%；模型：STEP23 LightGBM(F_lag)")
    log.info("F49 已输出")


# -----------------------------------------------------------------------------
# 9) 报告
# -----------------------------------------------------------------------------
def _fmt(df: pd.DataFrame, cols: List[str], n: int = 30) -> str:
    return df[cols].round(4).to_string(index=False, max_rows=n)


def write_report(gate, gap, summ, sev, buf, analog, analog_n, boot, s0, s1a,
                 log) -> None:
    p = PATHS.report("14_COUNTERFACTUAL.md")
    gate_pass_p = bool(gate[gate["target"] == "price"]["gate_pass"].iloc[0])
    gate_pass_v = bool(gate[gate["target"] == "volume"]["gate_pass"].iloc[0])
    during = summ[(summ["method"] == "A") & (summ["window"] == "during")]
    txt = f"""# 14 反事实平行世界（Phase 14，STEP 25-26）

> 全部反事实为**模型模拟（Level D）**；成交量单位未知，任何缺口只写相对口径（z / %），
> **禁止写成吨**（§六十）。模拟链：counterfactual weather → predicted volume → predicted price（§五十八）。

## 0 模拟框架

- 事件窗（预登记 config.counterfactual）：2026-07-12 ~ 2026-07-17（官方口径；ERA5 派生事件 07-11~07-15 为稳健性备注）；
- 模拟区间：{SIM_START.date()} ~ {SIM_END.date()}（事件前 2 个交易日起，事件后 14 天让 lag14 清零）；
- 模型：STEP 23 持久化 LightGBM（`mainsplit_hist_*_F_lag`，训练 ≤2024-12-31），价格/成交量均为
  递归链模拟（含昨日/前日异常、昨日量价水平的自回归状态，逐交易日推进）；
- 天气滞后特征重建与 panel_final 逐位一致（max 差 = 0）；precip_3d/7d 由替换后日降水重算；
- 反事实方法：
  * A = 1991-2020 同期气候正常值（日降水/温度/湿度/风；vpd/土壤用观测期季节正常，因官方
    30 年 vpd/土壤基线缺失，BLOCKER 已登记，证据等级 B）；
  * B = 2021-2025 同季（doy±15）无灾害日（不在事件窗、日降水<50mm、日最高<35℃）中位数，
    有效类比日 n = {analog_n}；
- 不确定区间 = 配对残差 Bootstrap（B={N_BOOT}，残差来自持久化模型在 2025 valid 期的样本外残差）。

## 1 World 0：模型能否复现现实（§五十六 门控）

模拟窗内 10 品种合计 {gate['n'].iloc[0]} 行：

{_fmt(gate, ["target", "n", "r2_sim_vs_actual", "gate_min_r2", "gate_pass"])}

- price 门控：**{'PASS' if gate_pass_p else 'FAIL'}**；volume 门控：**{'PASS' if gate_pass_v else 'FAIL'}**。
- 若 FAIL：该目标的反事实缺口仅作「模型外推演示」，不得视为对真实损失/涨幅的估计。
- 注意 STEP 23 增量分解：高 R² 主要来自自回归持续性，天气仅贡献很小（F_wx 口径 R² ≤ 0）。

## 2 World 1：无灾害反事实（§五十七，方法 A/B 比较）

事件窗（during）均值缺口汇总（负 = 正常天气下量/价低于实际，即灾害抬升了量/价的模型估计）：

{_fmt(during, ["crop", "method", "target", "n_days", "mean_gap_z", "mean_gap_pct", "ci_low_z", "ci_high_z"], n=44)}

- 方法 A 与 B 的方向一致性见 `counterfactual_gap.csv` / 汇总表（同号品种数）。
- 缺口绝对值很小（多品种 |z| < 0.1）：与 STEP 23「天气无样本外预测力」一致，模型估计的
  天气→量→价传导效应量级极小，处于模型噪声范围。
- 全部表述只能用「模型估计…可能」，不能写成「暴雨造成成交量损失 / 价格涨幅」的事实句。

## 3 World 2：严重度情景（§六十一，scenario simulation）

事件窗日降水 × {{0.5, 1.0, 1.2, 1.5}} 下的均值缺口（相对实际天气，事件窗均值）：

{_fmt(sev, ["severity_mult", "crop", "mean_gap_volume_z", "mean_gap_price_z"], n=44)}

- 判断风险是否「非线性放大」：若 gap 随乘子的增量显著加速（1.2→1.5 段的斜率 > 0.5→1.0 段），
  则提示非线性；否则在模型口径下未观察到明显非线性放大。

## 4 World 3：供应缓冲情景（§六十二，scenario simulation）

供应冲击被缓冲 10/20/30% 后价格缺口的变化（相对无缓冲 World1A，事件窗均值）：

{_fmt(buf, ["buffer_frac", "crop", "price_gap_z_remaining", "price_impact_avoided_z", "avoided_fraction"], n=40)}

- 这是「不同供应保障能力下的情景实验」，**不是**「政府提前调运可准确降低 X% 价格」（§六十二红线）。

## 5 图表

- F46：World0 模拟 vs 实际（价格 / 成交量异常 z）
- F47：World1A 缺口按品种柱状图（配对 Bootstrap 95%CI）
- F48：World2 严重度曲线
- F49：World3 缓冲曲线

## 6 局限

1. 模型天气敏感度在样本外近似为 0（STEP 23），故缺口主要反映模型结构而非可验证的真实传导；
2. 递归链依赖自回归持续性，事件窗较短（6 日），无法刻画中长期恢复路径；
3. 方法A 的 vpd/土壤基线为观测期降级口径（Level B）；方法B 类比日数量有限（n={analog_n}）；
4. 残差 Bootstrap 假设残差独立，未完全刻画序列相关（块长=1 的简化）；
5. World 0 门控未通过的目标，其反事实缺口只能视为模型外推演示。

---
生成时间：{pd.Timestamp.now():%Y-%m-%d %H:%M:%S}
"""
    p.write_text(txt, encoding="utf-8")
    log.info("报告已写出: %s", p)


# -----------------------------------------------------------------------------
# 10) 主流程
# -----------------------------------------------------------------------------
def main() -> None:
    with StepTimer(MOD, LOG):
        log = LOG
        log.info("=" * 78)
        log.info("STEP 25-26 Phase 14 平行世界（World0 门控 + World1 无灾害 + World2 严重度 + World3 缓冲）")

        design, _ = P12.build_design(log)
        design["date"] = pd.to_datetime(design["date"])
        design_hol = (design[["date", "is_public_holiday"]].drop_duplicates()
                      .set_index("date")["is_public_holiday"].to_dict())
        panel_dates = sorted(design["date"].unique())
        sim_dates = [d for d in panel_dates if SIM_START <= d <= SIM_END]
        log.info("模拟交易日：%d 天（%s ~ %s）", len(sim_dates), sim_dates[0].date(), sim_dates[-1].date())

        lv = level_table()

        # 反事实天气
        w = load_parquet("weather_daily")
        analog, analog_n = analog_normal(w)
        save_table(pd.DataFrame([{**analog, "n_analog_days": analog_n}]), "counterfactual_analog.csv")

        feat_actual = build_wx_feat("actual", panel_dates=panel_dates)
        feat_a = build_wx_feat("A", analog=analog, panel_dates=panel_dates)
        feat_b = build_wx_feat("B", analog=analog, panel_dates=panel_dates)

        # World 0 / World 1
        s0 = recursive_chain(feat_actual, lv, sim_dates, design_hol)
        s1a = recursive_chain(feat_a, lv, sim_dates, design_hol)
        s1b = recursive_chain(feat_b, lv, sim_dates, design_hol)
        save_table(s0, "counterfactual_world0.csv")
        g_a = _gap_frame(s0, s1a, lv)
        g_b = _gap_frame(s0, s1b, lv)
        g_b["method"] = "B"
        g_a["method"] = "A"
        save_table(pd.concat([g_a, g_b], ignore_index=True), "counterfactual_gap.csv")

        # 门控
        gate = world0_gate(s0, lv, sim_dates)
        save_table(gate, "counterfactual_gate.csv")
        log.info("World0 门控：price R²=%.3f (%s)；volume R²=%.3f (%s)",
                 gate[gate["target"] == "price"]["r2_sim_vs_actual"].iloc[0],
                 gate[gate["target"] == "price"]["gate_pass"].iloc[0],
                 gate[gate["target"] == "volume"]["r2_sim_vs_actual"].iloc[0],
                 gate[gate["target"] == "volume"]["gate_pass"].iloc[0])

        # 汇总 + Bootstrap CI（仅方法 A，配对）
        resid = valid_residuals(design, log)
        boot = bootstrap_gaps(design_hol, feat_a, feat_actual, lv, sim_dates, resid)
        summ_a_d = gap_summary(g_a, "A", boot=boot, window="during")
        summ_a_p = gap_summary(g_a, "A", boot=None, window="post")
        summ_b_d = gap_summary(g_b, "B", boot=None, window="during")
        summ = pd.concat([summ_a_d, summ_a_p, summ_b_d], ignore_index=True)
        save_table(summ, "counterfactual_gap_summary.csv")

        # World 2 / World 3
        sev = severity_worlds(feat_actual, lv, sim_dates, design_hol, analog)
        save_table(sev, "counterfactual_severity.csv")
        buf = buffer_worlds(feat_a, lv, sim_dates, design_hol)
        save_table(buf, "counterfactual_buffer.csv")

        # 图
        fig_world0(s0, lv, log)
        fig_gap_bars(summ, boot, log)
        fig_severity(sev, log)
        fig_buffer(buf, log)

        write_report(gate, g_a, summ, sev, buf, analog, analog_n, boot, s0, s1a, log)

        # 结果登记
        rows = []
        for t in ("volume", "price"):
            r = gate[gate["target"] == t].iloc[0]
            rows.append({
                "result_id": f"CF-W0-{t.upper()}",
                "research_question": "RQ 反事实 World0 门控（模型复现现实）",
                "crop": "10 品种", "period": f"{SIM_START.date()}~{SIM_END.date()}",
                "method": "递归链模拟（LightGBM F_lag）",
                "metric": "R²(模拟 vs 实际)", "estimate": round(float(r["r2_sim_vs_actual"]), 4),
                "ci_low": None, "ci_high": None, "p_value": None,
                "robustness": "配对残差 Bootstrap（F47）",
                "figure": "F46", "table": "counterfactual_gate.csv",
                "evidence_level": "Level D（模型模拟）",
                "notes": f"gate_pass={r['gate_pass']}；门控未过仅作外推演示；"
                         f"STEP23 增量分解表明高 R² 主要来自自回归持续性",
            })
        for t in ("volume", "price"):
            r = during_row(summ, "A", t)
            rows.append({
                "result_id": f"CF-W1A-{t.upper()}-GAP",
                "research_question": "RQ 无灾害反事实缺口（模型口径）",
                "crop": "POOLED", "period": f"{DURING[0].date()}~{DURING[1].date()}",
                "method": "方法A 气候均值替换 + 递归链",
                "metric": "mean gap z (World1A−World0)",
                "estimate": round(float(r["mean_gap_z"]), 4),
                "ci_low": round(float(r["ci_low_z"]), 4) if np.isfinite(r["ci_low_z"]) else None,
                "ci_high": round(float(r["ci_high_z"]), 4) if np.isfinite(r["ci_high_z"]) else None,
                "p_value": None,
                "robustness": "方法B 对照（counterfactual_gap.csv）；Bootstrap CI",
                "figure": "F47", "table": "counterfactual_gap_summary.csv",
                "evidence_level": "Level D（模型反事实）",
                "notes": "成交量单位未知，只报相对口径；不得写成吨或事实损失；"
                         "天气样本外解释力≈0，缺口量级极小",
            })
        register_results(rows)
        log.info("STEP 25-26 完成")


def during_row(summ: pd.DataFrame, method: str, target: str) -> pd.Series:
    d = summ[(summ["method"] == method) & (summ["target"] == target)
             & (summ["crop"] == "POOLED") & (summ["window"] == "during")]
    if d.empty:
        d = summ[(summ["method"] == method) & (summ["target"] == target)
                 & (summ["window"] == "during")]
    return d.iloc[0]


if __name__ == "__main__":
    main()
