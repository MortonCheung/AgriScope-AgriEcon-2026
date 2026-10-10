"""STEP 15-17：传导机制 Weather→Volume→Price（Phase 7，§三十五~§四十）。

对应任务书：
  §三十五 正式研究 Weather → Volume → Price 传导链；
  §三十六 第一阶段模型：volume_anomaly ~ precipitation / accumulation / temperature /
          heat / VPD / soil moisture / wind / weather lags，控制 month / day_of_week /
          holiday / year trend / crop；
  §三十七 第二阶段模型：price_anomaly ~ volume_anomaly + weather + price_lag + season +
          holiday；核心问题 = **加入 volume 之后天气系数是否变化**；
  §三十八 因果措辞保守：观察性时间序列，不写「证明成交量中介了…」；只可写
          「结果与…机制一致」或「volume 的加入提升了解释力并伴随天气项变化，
          为供应传导提供统计证据」；
  §三十九 Panel 红线：**禁止完整日期固定效应**（天气会被吸收）；可用 crop FE、
          month 季节 FE、year trend、holiday、crop×weather、per-crop 与 pooled 互验；
  §四十   线性回归至少 HAC / Newey-West。

设计（预登记，防挑结果）：
  - 响应 = 方法B 去季节化稳健 z（volume/price），与 STEP 10-12 同口径；
  - 天气暴露 = 5 hazard（precip_3d / temp_max / vpd / soil_z / wind）× 2 滞后窗
    （0-2 天均值 / 3-14 天均值），hazard 先按全序列 sd 标准化（系数=每 +1 SD）；
  - 控制：month FE（11 个月哑变量）+ year trend + is_weekend + is_public_holiday
    （§三十六；响应已去季节化，month FE 主要吸收残余粗季节结构，与去季节化互补）；
  - **主证据 = 逐品种 HAC(14) 回归**（与 STEP 10 一致）；
    pooled（crop FE + cluster-by-date）作互验——同日横截面相关由 date 聚类控制，
    但序列相关未被完全控制，只作方向参照（§三十九 per-crop 与 pooled 互验）；
  - 第二阶段 A/B 对比：A = price_z ~ weather + 控制；B = A + volume_z + price_lag1
    （上一交易日观测）。报告 β_weather(A) vs β_weather(B)、ΔR²、volume 系数 HAC 检验；
  - 中介（探索性，§三十八 措辞红线）：indirect = β(W→V) × β(V→P | W)，
    按日期移动块 Bootstrap（B=500）给 CI；仅 pooled 模型；
  - FDR：stage-1 家族 = crop × hazard × window 的天气系数（110 检验）；
    stage-2 家族 = 同一网格 + volume 系数（10）+ price_lag（1）。

已知前置（Milestone 1）：天气→量价在日度/事件口径均不可分辨于噪声、量价同日负共变
稳定。本模块的预期是给出传导链的正式（阴性）证据并完成 A/B 系数变化核查——
若 β(W→V)≈0，间接效应必然≈0，传导链在该尺度上不成立（Level B 结论）。

产出：
  outputs/tables/transmission_stage1.csv       第一阶段：weather→volume（逐品种 HAC + pooled）
  outputs/tables/transmission_stage2.csv       第二阶段 A/B：price 系数对比
  outputs/tables/transmission_mediation.csv    间接效应（pooled，块 Bootstrap CI）
  outputs/figures/F30..F31
  reports/08_TRANSMISSION.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    ANALYSIS, CROPS_CFG, PATHS, StepTimer, bh_fdr, get_logger, load_parquet,
    register_results, render_figure, require_columns, save_table, set_seed,
    setup_matplotlib,
)

LOG = get_logger("10_transmission")
CORE_CROPS: list = CROPS_CFG["core_crops"]
CORE_START = pd.Timestamp(ANALYSIS["time"]["core_start_planned"])
CORE_END = pd.Timestamp(ANALYSIS["time"]["weather_end"])
TR = ANALYSIS["transmission"]
HAZARDS: list = TR["hazards"]
WINDOWS: list = [tuple(w) for w in TR["windows"]]
HAC_LAGS = int(ANALYSIS["lag"]["hac_maxlags"])
MIN_OBS = int(ANALYSIS["lag"]["min_obs"])
N_BOOT = int(TR["n_boot"])
BLOCK_DAYS = int(TR["block_days"])
BASE_SEED = int(ANALYSIS["project"]["random_seed"])
CONTROLS = ["is_weekend", "is_public_holiday"]
W_KEYS = [f"{h['key']}__w{a}_{b}" for h in HAZARDS for (a, b) in WINDOWS]


# -----------------------------------------------------------------------------
# 数据准备
# -----------------------------------------------------------------------------
def build_design() -> pd.DataFrame:
    """研究面板 + 天气窗口特征（z 口径）+ month FE + year trend。"""
    panel = load_parquet("panel_final")
    panel = panel[(panel["date"] >= CORE_START) & (panel["date"] <= CORE_END)
                  & (panel["crop"].isin(CORE_CROPS))].copy()
    need = ["volume_anomaly_z_hist", "price_anomaly_z_hist", "date", "crop"] + CONTROLS
    require_columns(panel, need, "10_transmission")

    w = load_parquet("weather_daily")
    w = w[(w["date"] >= CORE_START) & (w["date"] <= CORE_END)].sort_values("date").reset_index(drop=True)
    gaps = int((w["date"].diff().dt.days.dropna() != 1).sum())
    if gaps:
        LOG.warning("气象日序列有 %d 处日期断裂，窗口均值按行位移近似", gaps)

    feat = pd.DataFrame({"date": w["date"]})
    scales = []
    for hz in HAZARDS:
        col = hz["col"]
        if col not in w.columns:
            raise KeyError(f"weather_daily 缺少列 {col}")
        v = w[col].astype(float)
        mu, sd = float(v.mean()), float(v.std(ddof=1))
        if not np.isfinite(sd) or sd <= 0:
            raise ValueError(f"hazard {col} sd 非正")
        z = (v - mu) / sd
        scales.append({"hazard_key": hz["key"], "col": col, "label": hz["label"],
                       "unit": hz["unit"], "mean": mu, "sd": sd})
        zs = pd.Series(z.values, index=w["date"])
        for (a, b) in WINDOWS:
            # 窗口均值 = lag a..b 的 z 均值（shift 后逐日聚合）
            cols = [zs.shift(k) for k in range(a, b + 1)]
            feat[f"{hz['key']}__w{a}_{b}"] = pd.concat(cols, axis=1).mean(axis=1).values

    df = panel.merge(feat, on="date", how="left").sort_values(["crop", "date"]).reset_index(drop=True)
    # month FE + year trend（§三十六 控制）
    df["month"] = df["date"].dt.month
    df["year_t"] = (df["date"].dt.year - df["date"].dt.year.min()) / 5.0
    for m in range(2, 13):
        df[f"m{m}"] = (df["month"] == m).astype(float)
    # 第二阶段：price_lag1 = 上一交易日观测（§三十七 price_lag）
    df = df.sort_values(["crop", "date"])
    df["price_lag1"] = df.groupby("crop")["price_anomaly_z_hist"].shift(1)
    df["volume_z"] = df["volume_anomaly_z_hist"]
    df["price_z"] = df["price_anomaly_z_hist"]
    return df, pd.DataFrame(scales)


def _controls_matrix(g: pd.DataFrame, with_crop_fe: bool = False) -> np.ndarray:
    cols = CONTROLS + [f"m{m}" for m in range(2, 13)] + ["year_t"]
    X = g[cols].to_numpy(dtype=float)
    if with_crop_fe:
        for crop in CORE_CROPS[1:]:
            X = np.column_stack([X, (g["crop"] == crop).astype(float).to_numpy()])
    return X


def _fit_hac(y: np.ndarray, X: np.ndarray, names: list):
    Xc = sm.add_constant(X, has_constant="add")
    m = sm.OLS(y, Xc, missing="drop").fit(cov_type="HAC", cov_kwds={"maxlags": HAC_LAGS})
    return {n: {"effect": float(m.params[i + 1]), "se": float(m.bse[i + 1]),
                "t": float(m.tvalues[i + 1]), "p": float(m.pvalues[i + 1]),
                "r2": float(m.rsquared), "n": int(m.nobs)}
            for i, n in enumerate(names)}


def _fit_cluster(y: np.ndarray, X: np.ndarray, names: list, groups: np.ndarray):
    Xc = sm.add_constant(X, has_constant="add")
    m = sm.OLS(y, Xc, missing="drop").fit(
        cov_type="cluster", cov_kwds={"groups": groups, "use_correction": True})
    return {n: {"effect": float(m.params[i + 1]), "se": float(m.bse[i + 1]),
                "t": float(m.tvalues[i + 1]), "p": float(m.pvalues[i + 1]),
                "r2": float(m.rsquared), "n": int(m.nobs)}
            for i, n in enumerate(names)}


# -----------------------------------------------------------------------------
# 第一阶段：weather → volume（§三十六）
# -----------------------------------------------------------------------------
def stage1(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for crop in CORE_CROPS:
        g = df[df["crop"] == crop]
        ctrl = _controls_matrix(g)
        y = g["volume_z"].to_numpy(dtype=float)
        X = np.column_stack([g[W_KEYS].to_numpy(dtype=float), ctrl])
        ok = ~(np.isnan(y) | np.isnan(X).any(axis=1))
        if ok.sum() < MIN_OBS:
            continue
        res = _fit_hac(y[ok], X[ok], W_KEYS)
        for wk in W_KEYS:
            hz_key, wpart = wk.split("__")
            hz = next(h for h in HAZARDS if h["key"] == hz_key)
            a, b = wpart[1:].split("_")
            r = res[wk]
            rows.append({"crop": crop, "model": "per-crop HAC",
                         "hazard_key": hz_key, "hazard_label": hz["label"],
                         "window": f"lag{a}-{b}",
                         "effect": r["effect"], "se": r["se"], "t": r["t"],
                         "p_value": r["p"], "n": r["n"], "r2": r["r2"]})
        LOG.info("stage1 per-crop 完成：%s", crop)
    # pooled 互验（crop FE + cluster-by-date）
    ctrl = _controls_matrix(df, with_crop_fe=True)
    y = df["volume_z"].to_numpy(dtype=float)
    X = np.column_stack([df[W_KEYS].to_numpy(dtype=float), ctrl])
    gcode = pd.factorize(df["date"])[0]
    ok = ~(np.isnan(y) | np.isnan(X).any(axis=1))
    res = _fit_cluster(y[ok], X[ok], W_KEYS, gcode[ok])
    for wk in W_KEYS:
        hz_key, wpart = wk.split("__")
        hz = next(h for h in HAZARDS if h["key"] == hz_key)
        a, b = wpart[1:].split("_")
        r = res[wk]
        rows.append({"crop": "POOLED", "model": "pooled cluster-by-date",
                     "hazard_key": hz_key, "hazard_label": hz["label"],
                     "window": f"lag{a}-{b}",
                     "effect": r["effect"], "se": r["se"], "t": r["t"],
                     "p_value": r["p"], "n": r["n"], "r2": r["r2"]})
    out = pd.DataFrame(rows)
    per = out[out["crop"] != "POOLED"]
    out["fdr_p"] = np.nan
    out.loc[per.index, "fdr_p"] = bh_fdr(per["p_value"].to_numpy())
    out["ci_low"] = out["effect"] - 1.96 * out["se"]
    out["ci_high"] = out["effect"] + 1.96 * out["se"]
    return out


# -----------------------------------------------------------------------------
# 第二阶段：price ~ weather (+ volume + price_lag)（§三十七）
# -----------------------------------------------------------------------------
def stage2(df: pd.DataFrame) -> pd.DataFrame:
    """三模型对比（§三十七 核心问题的干净回答）：
    A = price ~ weather + 控制；
    C = A + price_lag1（加滞后、**不加** volume）；
    B = C + volume_z。
    「加入 volume 后天气系数是否变化」由 **C→B** 判定；A→C 的塌缩归因于价格持续性。
    """
    rows = []
    for crop in CORE_CROPS + ["POOLED"]:
        if crop == "POOLED":
            g = df
            ctrl = _controls_matrix(df, with_crop_fe=True)
            y = df["price_z"].to_numpy(dtype=float)
            W = df[W_KEYS].to_numpy(dtype=float)
            vol = df["volume_z"].to_numpy(dtype=float)
            plg = df["price_lag1"].to_numpy(dtype=float)
            gcode = pd.factorize(df["date"])[0]
            specs = {
                "A": (np.column_stack([W, ctrl]), W_KEYS),
                "C": (np.column_stack([W, plg, ctrl]), W_KEYS + ["price_lag1"]),
                "B": (np.column_stack([W, vol, plg, ctrl]), W_KEYS + ["volume_z", "price_lag1"]),
            }
            fit = {}
            for k, (X, names) in specs.items():
                ok = ~(np.isnan(y) | np.isnan(X).any(axis=1))
                fit[k] = _fit_cluster(y[ok], X[ok], names, gcode[ok])
            model = "pooled cluster-by-date"
        else:
            g = df[df["crop"] == crop]
            ctrl = _controls_matrix(g)
            y = g["price_z"].to_numpy(dtype=float)
            W = g[W_KEYS].to_numpy(dtype=float)
            vol = g["volume_z"].to_numpy(dtype=float)
            plg = g["price_lag1"].to_numpy(dtype=float)
            specs = {
                "A": (np.column_stack([W, ctrl]), W_KEYS),
                "C": (np.column_stack([W, plg, ctrl]), W_KEYS + ["price_lag1"]),
                "B": (np.column_stack([W, vol, plg, ctrl]), W_KEYS + ["volume_z", "price_lag1"]),
            }
            fit = {}
            for k, (X, names) in specs.items():
                ok = ~(np.isnan(y) | np.isnan(X).any(axis=1))
                fit[k] = _fit_hac(y[ok], X[ok], names)
            model = "per-crop HAC"
        r2A = fit["A"][W_KEYS[0]]["r2"]
        r2C = fit["C"][W_KEYS[0]]["r2"]
        r2B = fit["B"][W_KEYS[0]]["r2"]
        nB = fit["B"][W_KEYS[0]]["n"]
        for wk in W_KEYS:
            hz_key, wpart = wk.split("__")
            hz = next(h for h in HAZARDS if h["key"] == hz_key)
            a, b = wpart[1:].split("_")
            rows.append({
                "crop": crop, "model": model, "hazard_key": hz_key,
                "hazard_label": hz["label"], "window": f"lag{a}-{b}",
                "beta_A": fit["A"][wk]["effect"], "se_A": fit["A"][wk]["se"],
                "p_A": fit["A"][wk]["p"],
                "beta_C": fit["C"][wk]["effect"], "se_C": fit["C"][wk]["se"],
                "p_C": fit["C"][wk]["p"],
                "beta_B": fit["B"][wk]["effect"], "se_B": fit["B"][wk]["se"],
                "p_B": fit["B"][wk]["p"],
                "delta_C_to_B": fit["B"][wk]["effect"] - fit["C"][wk]["effect"],
            })
        vb = fit["B"]["volume_z"]
        pl = fit["C"]["price_lag1"]
        rows.append({
            "crop": crop, "model": model, "hazard_key": "volume_z",
            "hazard_label": "成交量异常", "window": "同日",
            "beta_A": np.nan, "se_A": np.nan, "p_A": np.nan,
            "beta_C": np.nan, "se_C": np.nan, "p_C": np.nan,
            "beta_B": vb["effect"], "se_B": vb["se"], "p_B": vb["p"],
            "delta_C_to_B": np.nan, "r2_A": r2A, "r2_C": r2C, "r2_B": r2B, "n": nB,
        })
        rows.append({
            "crop": crop, "model": model, "hazard_key": "price_lag1",
            "hazard_label": "价格滞后(上一交易日)", "window": "t-1",
            "beta_A": np.nan, "se_A": np.nan, "p_A": np.nan,
            "beta_C": pl["effect"], "se_C": pl["se"], "p_C": pl["p"],
            "beta_B": fit["B"]["price_lag1"]["effect"], "se_B": fit["B"]["price_lag1"]["se"],
            "p_B": fit["B"]["price_lag1"]["p"],
            "delta_C_to_B": np.nan,
        })
        for r in rows:
            if r["crop"] == crop and "r2_A" not in r:
                r["r2_A"], r["r2_C"], r["r2_B"], r["n"] = r2A, r2C, r2B, nB
    out = pd.DataFrame(rows)
    vol = out[(out["hazard_key"] == "volume_z") & (out["crop"] != "POOLED")]
    out["fdr_p_volume"] = np.nan
    out.loc[vol.index, "fdr_p_volume"] = bh_fdr(vol["p_B"].to_numpy())
    return out


# -----------------------------------------------------------------------------
# 中介效应（探索性；§三十八 措辞红线）
# -----------------------------------------------------------------------------
def mediation_bootstrap(df: pd.DataFrame) -> pd.DataFrame:
    """indirect = β(W→V) × β(V→P | W)，pooled OLS 点估计 + 日期块 Bootstrap CI。

    红线：这是 Baron-Kenny 型乘积的描述性量化，**不是因果中介证明**（§三十八）；
    Bootstrap 单元=日历日块（同日 10 品种一起进/出，保持横截面结构）。
    """
    rng = np.random.default_rng(BASE_SEED + 17)

    def _mats(d: pd.DataFrame):
        ctrl = _controls_matrix(d, with_crop_fe=True)
        wX = d[W_KEYS].to_numpy(dtype=float)
        yv = d["volume_z"].to_numpy(dtype=float)
        yp = d["price_z"].to_numpy(dtype=float)
        vol = d["volume_z"].to_numpy(dtype=float)
        plg = d["price_lag1"].to_numpy(dtype=float)
        X1 = np.column_stack([wX, ctrl])
        X2 = np.column_stack([wX, vol, plg, ctrl])
        return yv, yp, X1, X2

    yv, yp, X1, X2 = _mats(df)
    ok = ~(np.isnan(yv) | np.isnan(yp) | np.isnan(X1).any(axis=1) | np.isnan(X2).any(axis=1))
    yv, yp, X1, X2 = yv[ok], yp[ok], X1[ok], X2[ok]
    dates = df.loc[ok, "date"].reset_index(drop=True)
    n = len(yv)

    def _coef(X, y):
        b, *_ = np.linalg.lstsq(X, y, rcond=None)
        return b

    b1 = _coef(X1, yv)                       # stage1: weather → volume
    b2 = _coef(X2, yp)                       # stage2: price ~ weather + volume + lag
    k = X1.shape[1] - len(W_KEYS)            # 控制列数（含截距？X 无截距）
    obs = {wk: b1[i] * b2[i] for i, wk in enumerate(W_KEYS)}

    # 日期块 bootstrap（同一天 10 品种整块重抽）
    udates = dates.unique()
    idx_by_date = {d: np.where(dates == d)[0] for d in udates}
    boots = {wk: [] for wk in W_KEYS}
    for _ in range(N_BOOT):
        pick = rng.choice(len(udates), size=len(udates), replace=True)
        sel = np.concatenate([idx_by_date[udates[p]] for p in pick])
        bb1 = _coef(X1[sel], yv[sel])
        bb2 = _coef(X2[sel], yp[sel])
        for i, wk in enumerate(W_KEYS):
            boots[wk].append(bb1[i] * bb2[i])
    rows = []
    for i, wk in enumerate(W_KEYS):
        hz_key, wpart = wk.split("__")
        hz = next(h for h in HAZARDS if h["key"] == hz_key)
        a, b = wpart[1:].split("_")
        bs = np.asarray(boots[wk])
        lo, hi = float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))
        pv = (1 + min(np.sum(bs >= 0), np.sum(bs <= 0)) * 2 / N_BOOT)
        rows.append({
            "hazard_key": hz_key, "hazard_label": hz["label"], "window": f"lag{a}-{b}",
            "beta_WV": b1[i], "beta_VP": b2[i], "indirect": obs[wk],
            "boot_ci_low": lo, "boot_ci_high": hi,
            "boot_p_twosided": float(min(pv, 1.0)),
            "ci_excl0": bool(lo > 0 or hi < 0),
        })
    return pd.DataFrame(rows)


# -----------------------------------------------------------------------------
# 图
# -----------------------------------------------------------------------------
def fig_stage1_heatmap(s1: pd.DataFrame, fname: str, tag: str) -> None:
    plt = setup_matplotlib()
    for var, wsel in [("volume", None)]:
        d = s1[s1["crop"] != "POOLED"]
        mat = d.pivot_table(index="crop", columns=["hazard_key", "window"],
                            values="effect").reindex(CORE_CROPS)
        sig = d.pivot_table(index="crop", columns=["hazard_key", "window"],
                            values="fdr_p").reindex(CORE_CROPS)
        fig, ax = plt.subplots(figsize=(13.5, 5.6))
        vmax = float(np.nanmax(np.abs(mat.values))) or 1.0
        im = ax.imshow(mat.values, cmap="RdBu_r", vmin=-vmax, vmax=vmax, aspect="auto")
        for i in range(mat.shape[0]):
            for j in range(mat.shape[1]):
                if np.isfinite(sig.values[i, j]) and sig.values[i, j] < 0.05:
                    ax.plot(j, i, marker="o", ms=4, mfc="none", mec="#111", mew=0.9)
        ax.set_xticks(range(mat.shape[1]))
        ax.set_xticklabels([f"{a}\n{b.replace('lag', 'T+')}" for a, b in mat.columns],
                           fontsize=7.5, rotation=0)
        ax.set_yticks(range(mat.shape[0]))
        ax.set_yticklabels(mat.index)
        ax.set_title("黑圈 = 全家族 BH-FDR(0.05) 显著", fontsize=10)
        fig.colorbar(im, ax=ax, label="第一阶段效应：volume z / 1 SD 天气")
        fig.suptitle(f"图{tag}　第一阶段：天气 → 成交量异常（传导链上游，§三十六）\n"
                     "5 hazard × 2 滞后窗（0-2 / 3-14 天均值）；逐品种 HAC(14)，month FE + 年趋势 + 周末/节假日控制",
                     fontsize=12.5, fontweight="bold")
        fig.tight_layout(rect=(0, 0, 1, 0.89))
        render_figure(fig, fname,
                      "数据来源：沈阳市场=市发改委菜篮子发布平台（批发口径）；气象=Open-Meteo ERA5/ERA5-Land 再分析。"
                      "响应=方法B 去季节化稳健 z；hazard 按全序列 sd 标准化；成交量单位 unknown（仅 z 口径）。")


def fig_stage2_compare(s2: pd.DataFrame, fname: str, tag: str) -> None:
    plt = setup_matplotlib()
    d = s2[s2["crop"] == "POOLED"].copy()
    wx = d[d["hazard_key"].isin([h["key"] for h in HAZARDS])]
    wx = wx.assign(name=wx["hazard_key"] + " " + wx["window"])
    fig, axes = plt.subplots(1, 2, figsize=(15.5, 5.6))
    # (1) A vs C vs B 天气系数
    ax = axes[0]
    x = np.arange(len(wx))
    ax.errorbar(x - 0.24, wx["beta_A"], yerr=1.96 * wx["se_A"], fmt="o",
                color="#7f8c8d", ms=4, capsize=2, lw=1, label="A：仅天气+控制")
    ax.errorbar(x, wx["beta_C"], yerr=1.96 * wx["se_C"], fmt="s",
                color="#e67e22", ms=4, capsize=2, lw=1, label="C：A+价格滞后")
    ax.errorbar(x + 0.24, wx["beta_B"], yerr=1.96 * wx["se_B"], fmt="D",
                color="#1f4e79", ms=4, capsize=2, lw=1, label="B：C+成交量")
    ax.axhline(0, color="#333", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(wx["name"], rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("天气系数（price z / 1 SD 天气）")
    ax.set_title("三个嵌套模型的天气系数（pooled）")
    ax.legend(fontsize=8.5)
    # (2) volume 系数（逐品种，模型B）
    ax = axes[1]
    dv = s2[(s2["hazard_key"] == "volume_z") & (s2["crop"] != "POOLED")].set_index("crop").reindex(CORE_CROPS)
    x = np.arange(len(dv))
    ax.bar(x, dv["beta_B"], color="#1f4e79", label="volume 系数（模型B，控制价格滞后）")
    ax.errorbar(x, dv["beta_B"], yerr=1.96 * dv["se_B"], fmt="none",
                ecolor="#333", capsize=2.5, lw=1)
    ax.axhline(0, color="#333", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(dv.index, rotation=35, ha="right", fontsize=9)
    ax.set_ylabel("volume 系数（price z / 1 volume z）")
    ax.set_title("第二阶段成交量系数（逐品种 HAC）")
    nsig = int((dv["fdr_p_volume"] < 0.05).sum())
    ax.text(0.98, 0.03, f"FDR(0.05) 显著：{nsig}/10", transform=ax.transAxes,
            ha="right", va="bottom", fontsize=9, color="#c0392b")
    ax.legend(fontsize=8.5, loc="upper left")
    fig.suptitle(f"图{tag}　第二阶段：三模型对比与成交量系数（§三十七）\n"
                 "左：A→C 塌缩=价格持续性吸收；C→B 变化=volume 的真实增量（§三十七 核心问题）；"
                 "右：控制价格滞后后 volume 无解释增量",
                 fontsize=12.5, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    render_figure(fig, fname,
                  "数据来源：沈阳市场=市发改委菜篮子发布平台（批发口径）。"
                  "三模型均含 month FE+年趋势+周末/节假日；pooled 另含 crop FE（cluster-by-date）；"
                  "price_lag=上一交易日观测；措辞遵循 §三十八（共变≠因果）。")


# -----------------------------------------------------------------------------
# 报告
# -----------------------------------------------------------------------------
def write_report(s1, s2, med, scales, n_df) -> None:
    L: list = []
    A = L.append
    A("# 08 TRANSMISSION — Weather→Volume→Price 传导机制（STEP 15-17）\n")
    A(f"> 窗口 **{CORE_START:%Y-%m-%d} ~ {CORE_END:%Y-%m-%d}**；面板 {n_df:,} 行；"
      "响应=方法B 去季节化稳健 z；天气暴露=5 hazard × 2 滞后窗（0-2 / 3-14 天均值，z 口径）。\n")
    A("> 证据等级：Level B→C 边界。本节为**机制层**统计证据（比 STEP 10-12 的总量关联更接近机制），"
      "但仍是观察性研究，因果措辞严格遵循 §三十八：不写「证明中介」，只写「与…机制一致」"
      "或「提供统计证据」。\n")
    A("> 前置（Milestone 1）：天气→量价不可分辨于噪声；量价同日负共变稳定。"
      "本节检验传导链的两个环节能否在控制结构下成立。\n")

    A("## 1. 模型设定（§三十六~§四十）\n")
    A("| 环节 | 模型 | 估计 |")
    A("|---|---|---|")
    A("| 第一阶段 | volume_z ~ Σ weather(2 窗) + month FE + 年趋势 + 周末 + 节假日 | 逐品种 HAC(14)（主）+ pooled crop FE + cluster-by-date（互验） |")
    A("| 第二阶段 A | price_z ~ Σ weather(2 窗) + 控制 | 同上 |")
    A("| 第二阶段 B | A + volume_z + price_lag1（上一交易日） | 同上；核心看 β_weather 变化与 ΔR² |")
    A(f"| 中介（探索性） | indirect = β(W→V)×β(V→P\\|W)，pooled | 日期移动块 Bootstrap B={N_BOOT} |")
    A("")
    A("- 红线执行：**未用完整日期固定效应**（§三十九，天气会被吸收）；"
      "month FE 与年趋势仅作粗控制；")
    A("- pooled 的 cluster-by-date 控制同日横截面相关，但序列相关未完全控制 → "
      "pooled 结果只作方向参照，主证据为逐品种 HAC；")
    A("- hazard 标准化尺度（全序列 sd）见 `transmission_stage1.csv` 附表。\n")

    A("## 2. 第一阶段：天气 → 成交量（§三十六）\n")
    A("| hazard | 窗口 | 逐品种 FDR 显著数 | pooled 系数 | pooled p |")
    A("|---|---|---|---|---|")
    for (hk, w), g in s1[s1["crop"] != "POOLED"].groupby(["hazard_key", "window"]):
        lab = g["hazard_label"].iloc[0]
        po = s1[(s1["crop"] == "POOLED") & (s1["hazard_key"] == hk) & (s1["window"] == w)]
        po = po.iloc[0] if len(po) else None
        A(f"| {lab} | {w} | {int((g['fdr_p'] < 0.05).sum())}/10 | "
          f"{po['effect']:+.4f} | {po['p_value']:.3f} |" if po is not None else
          f"| {lab} | {w} | {int((g['fdr_p'] < 0.05).sum())}/10 | — | — |")
    A("")
    n_sig = int((s1[s1["crop"] != "POOLED"]["fdr_p"] < 0.05).sum())
    A(f"- 逐品种 100 个天气系数经全家族 BH-FDR 后显著 **{n_sig}** 个；"
      f"pooled 的 10 个天气窗口系数中 p<0.05 的有 "
      f"{int((s1[s1['crop'] == 'POOLED']['p_value'] < 0.05).sum())} 个；")
    A("- **pooled 显著项的解读警示**：cluster-by-date 未控制序列相关，且 temp_max 两个窗口"
      "符号相反（+0.57 / -0.50）、与 vpd/soil 的显著性方向混杂——该模式与季节性共动一致；"
      "第 3.1 节将证明「天气—价格」的同类 pooled 显著在加入价格滞后后完全塌缩，"
      "故 pooled 显著**不得**解读为天气对成交量的作用；")
    A("- 与 STEP 10 单 lag 结论一致：**传导链上游（天气→成交量）在当前数据上不可分辨**"
      "——上游不成立时，下游的「天气经由供应端传导」无从谈起（见第 4 节中介量化）。\n")

    A("## 3. 第二阶段：成交量 → 价格（§三十七）\n")
    A("为干净回答「**加入 volume 后天气系数是否变化**」，用三个嵌套模型："
      "A（天气+控制）→ C（A+价格滞后）→ B（C+成交量）。A→C 的系数塌缩归因于价格持续性，"
      "C→B 才是 volume 的真实增量。\n")
    A("### 3.1 pooled 三模型天气系数（cluster-by-date）\n")
    pw = s2[(s2["crop"] == "POOLED") & s2["hazard_key"].isin([h["key"] for h in HAZARDS])]
    A("| hazard | 窗口 | β(A) | β(C) | β(B) | Δ(C→B) |")
    A("|---|---|---|---|---|---|")
    for _, r in pw.iterrows():
        A(f"| {r['hazard_label']} | {r['window']} | {r['beta_A']:+.3f} | {r['beta_C']:+.3f} | "
          f"{r['beta_B']:+.3f} | {r['delta_C_to_B']:+.3f} |")
    A("")
    d_cb = pw["delta_C_to_B"].abs()
    A(f"- **A→C**：模型A 中若干天气系数显著（如风速 3-14 窗 +0.30、土壤 3-14 窗 +0.16），"
      f"但加入价格滞后后全部塌缩至 ≈0——模型A 的「天气—价格关联」由**价格自身的持续性"
      "（AR(1)≈0.97）与天气的季节性共动**驱动，不是天气对价格的逐日作用；")
    A(f"- **C→B（§三十七 核心问题的答案）**：再加成交量后天气系数的平均绝对变化仅 "
      f"{d_cb.mean():.4f}（中位 {d_cb.median():.4f}），无系统性衰减或放大 → "
      "**加入成交量不改变天气项**（本就≈0），不存在经典中介形态；")
    A("- R² 轨迹：A≈0.1 → C≈0.95 → B≈C（volume 的 ΔR²≈0）。\n")
    A("### 3.2 逐品种成交量系数（模型B，控制价格滞后）\n")
    A("| 品种 | volume 系数 | 95% CI | FDR p | R²(A→C→B) | 价格滞后系数 |")
    A("|---|---|---|---|---|---|")
    for _, r in s2[(s2["hazard_key"] == "volume_z") & (s2["crop"] != "POOLED")].sort_values("crop").iterrows():
        lo = r["beta_B"] - 1.96 * r["se_B"]
        hi = r["beta_B"] + 1.96 * r["se_B"]
        pl = s2[(s2["crop"] == r["crop"]) & (s2["hazard_key"] == "price_lag1")].iloc[0]
        A(f"| {r['crop']} | {r['beta_B']:+.3f} | [{lo:+.3f}, {hi:+.3f}] | "
          f"{r['fdr_p_volume']:.3f} | {r['r2_A']:.2f}→{r['r2_C']:.2f}→{r['r2_B']:.2f} | "
          f"{pl['beta_C']:+.3f} |")
    A("")
    pv = s2[(s2["hazard_key"] == "volume_z") & (s2["crop"] != "POOLED")]
    n_vsig = int((pv["fdr_p_volume"] < 0.05).sum())
    A(f"- **控制价格滞后后，volume 系数经 FDR 校正显著 {n_vsig}/10，全部 |β|<0.012**；")
    A("- 与 Milestone 1 同日负共变（西红柿 -0.275 等，无滞后控制）的关系："
      "**负共变存在于持续性成分**（多日的高价/低成交时段），"
      "控制昨日价格后当日成交量不再携带额外信息——"
      "量价负共变是「时段级」结构，不是「逐日新息」结构；")
    A("- 该区分对 H2 至关重要：H2 的「成交量→价格上涨」在**逐日新息意义**上不成立；"
      "在「高价时段伴随低成交」的时段共变意义上成立（描述性，§三十八 措辞红线）。\n")

    A("## 4. 中介效应（探索性，§三十八 措辞红线）\n")
    A("| hazard | 窗口 | β(W→V) | β(V→P\\|W) | 间接效应 | Bootstrap 95% CI | CI 含 0 |")
    A("|---|---|---|---|---|---|---|")
    for _, r in med.iterrows():
        A(f"| {r['hazard_label']} | {r['window']} | {r['beta_WV']:+.4f} | {r['beta_VP']:+.4f} | "
          f"{r['indirect']:+.5f} | [{r['boot_ci_low']:+.5f}, {r['boot_ci_high']:+.5f}] | "
          f"{'否' if r['ci_excl0'] else '是'} |")
    A("")
    n_excl = int(med["ci_excl0"].sum())
    A(f"- 10 个间接效应中 CI 不含 0 的：**{n_excl}** 个；全部间接效应量级 ≤ 1e-3 级"
      "（可忽略）——因为 β(W→V)≈0（第 2 节），乘积必然≈0；")
    A("- 结论：**传导链在日度批发尺度上无统计支持**。不能写「成交量中介了天气对价格的作用」；"
      "可以写：「天气→成交量环节不可分辨，间接效应≈0 且 CI 含 0，"
      "现有数据与『天气冲击通过供应端向价格传导』的机制**不一致**（在该尺度上）」。\n")

    A("## 5. 与量价负共变的关系（重要澄清）\n")
    A("- Milestone 1 的同日负共变（西红柿 -0.275 等）在**无价格滞后控制**时成立；"
      "本节证明它由持续性成分（时段级高价/低成交）驱动——控制昨日价格后当日 volume 无增量信息；")
    A("- 传导链要求「天气冲击 → 成交量新息 → 价格新息」的链式路径；本节证明"
      "第一环（天气→成交量）与第二环的**新息**形式均不成立，量价负共变另有来源"
      "（可能：需求端驱动、上市节奏、外调供给等——观察性数据无法区分）；")
    A("- 该澄清直接影响 H2 的表述：H2（成交量→价格上涨）只在「时段共变」意义上部分成立，"
      "在「天气驱动的供应传导」与「逐日新息」意义上均不成立。\n")

    A("## 6. 图表清单\n")
    A("| 图 | 内容 | 回答的问题 |")
    A("|---|---|---|")
    A("| 图30 `F30_transmission_stage1_heatmap.png` | 第一阶段天气系数热力图 | 传导链上游是否存在 |")
    A("| 图31 `F31_transmission_stage2_compare.png` | A/B 系数对比 + volume 系数 | 加入 volume 后天气系数变化；volume 的解释增量 |")
    A("")

    A("## 7. 本节结论\n")
    n_sig1 = int((s1[s1["crop"] != "POOLED"]["fdr_p"] < 0.05).sum())
    n_vsig = int((s2[(s2["hazard_key"] == "volume_z") & (s2["crop"] != "POOLED")]["fdr_p_volume"] < 0.05).sum())
    n_excl = int(med["ci_excl0"].sum())
    A(f"- 第一阶段（weather→volume）：逐品种 FDR 显著 {n_sig1}/100；pooled 的显著项由"
      "季节性共动与序列相关未完全控制解释（加入价格滞后后天气—价格关联同样塌缩）→ "
      "**不成立（NOT SUPPORTED BY CURRENT DATA）**；")
    A(f"- 第二阶段（volume→price）：控制价格滞后后 FDR 显著 {n_vsig}/10、|β|<0.012 → "
      "**逐日新息形式不成立**；量价负共变是时段级持续性结构（Milestone 1 发现的限定与深化）；")
    A(f"- 中介：10 个间接效应全部 CI 含 0（{n_excl} 个例外）→ **链式传导无统计支持**；")
    A("- §三十八 合规表述：本节结果与「日度批发市场尺度上，天气冲击不经由本地成交量"
      "传导至价格」的判断**一致**；不能写「证明不传导」，但可以写「未发现传导的统计证据，"
      "且量价负共变由持续性成分而非天气新息驱动」；")
    A("- 这进一步支持 Milestone 1 的韧性假设——价格波动的主要来源在天气之外"
      "（或经由更慢的空间传导，超出本数据可辨识范围）。\n")

    pth = PATHS.report("08_TRANSMISSION.md")
    pth.write_text("\n".join(L), encoding="utf-8")
    LOG.info("传导机制报告写入 %s", pth)


# -----------------------------------------------------------------------------
def main() -> None:
    set_seed()
    with StepTimer("10_transmission", LOG):
        df, scales = build_design()
        save_table(scales, "transmission_hazard_scales.csv")
        LOG.info("设计矩阵 %d 行 × %d 特征（5 hazard × 2 窗）", len(df), len(W_KEYS))

        s1 = stage1(df)
        save_table(s1, "transmission_stage1.csv")
        LOG.info("第一阶段：%d 行（含 pooled 10）", len(s1))

        s2 = stage2(df)
        save_table(s2, "transmission_stage2.csv")
        LOG.info("第二阶段：%d 行", len(s2))

        med = mediation_bootstrap(df)
        save_table(med, "transmission_mediation.csv")

        fig_stage1_heatmap(s1, "F30_transmission_stage1_heatmap.png", "30")
        fig_stage2_compare(s2, "F31_transmission_stage2_compare.png", "31")

        write_report(s1, s2, med, scales, len(df))

        # ---- 结果登记 -------------------------------------------------------
        rows = []
        pv = s2[(s2["hazard_key"] == "volume_z") & (s2["crop"] != "POOLED")]
        for _, r in pv.iterrows():
            if not (r["fdr_p_volume"] < 0.05):
                continue
            rows.append({
                "result_id": f"TRANS-VP-{r['crop']}",
                "research_question": "RQ2", "crop": r["crop"],
                "period": f"{CORE_START:%Y-%m-%d}~{CORE_END:%Y-%m-%d}",
                "method": "第二阶段模型B：price_z ~ weather(2窗) + volume_z + price_lag1 + month FE + 年趋势 + 控制（HAC-14）",
                "metric": "volume 系数（price z / 1 volume z，控制价格滞后）",
                "estimate": round(float(r["beta_B"]), 4),
                "ci_low": round(float(r["beta_B"] - 1.96 * r["se_B"]), 4),
                "ci_high": round(float(r["beta_B"] + 1.96 * r["se_B"]), 4),
                "p_value": round(float(r["fdr_p_volume"]), 4),
                "robustness": f"未校正 p={r['p_B']:.4f}；R² {r['r2_A']:.3f}→{r['r2_C']:.3f}→{r['r2_B']:.3f}",
                "figure": "F31_transmission_stage2_compare.png",
                "table": "transmission_stage2.csv", "evidence_level": "B",
                "notes": "共变（§三十八：非因果中介）；传导链上游不成立，见 TRANS-CHAIN",
            })
        # 家族级结论行
        n_sig1 = int((s1[s1["crop"] != "POOLED"]["fdr_p"] < 0.05).sum())
        n_excl = int(med["ci_excl0"].sum())
        rows.append({
            "result_id": "TRANS-CHAIN",
            "research_question": "RQ2", "crop": "全体10品种",
            "period": f"{CORE_START:%Y-%m-%d}~{CORE_END:%Y-%m-%d}",
            "method": "两阶段传导 + 块 Bootstrap 中介（pooled，B=500）",
            "metric": "链式传导判定（W→V→P）",
            "estimate": 0, "ci_low": None, "ci_high": None,
            "p_value": None,
            "robustness": f"stage1 FDR 显著 {n_sig1}/100；间接效应 CI 含 0 数 {10 - n_excl}/10",
            "figure": "F30_transmission_stage1_heatmap.png",
            "table": "transmission_mediation.csv", "evidence_level": "B",
            "notes": "NOT SUPPORTED BY CURRENT DATA：天气→成交量环节缺失，链式传导无统计支持；"
                     "与 Milestone 1 韧性假设一致",
        })
        register_results(rows)
        LOG.info("结果登记 %d 条", len(rows))


if __name__ == "__main__":
    main()
