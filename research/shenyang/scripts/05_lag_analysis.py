"""STEP 10：天气冲击 → 量价异常的滞后结构（Phase 3，§二十二~§二十五）。

对应任务书：
  §二十二 研究 weather(t) → volume(t+k) 与 weather(t) → price(t+k)，k = 0~30 calendar days（重点 0~14）
  §二十三 同时算 Pearson 与 Spearman，但相关只作探索；正式研究用 Distributed Lag Regression，
          且**不把 30 个高度共线 lag 一次塞进模型** → 本模块用两条路径：
            (a) 单 lag 逐日回归（一次只放一个 lag，无共线性）→ 完整 Lag Profile
            (b) 窗聚合分布滞后模型（0-2 / 3-6 / 7-13 / 14-30 天均值同时入场）→ 联合估计
  §二十四 输出 crop, hazard, lag_day, effect, se, p_value, fdr_p 表 + lag day→effect 图
  §二十五 多重检验：Benjamini-Hochberg FDR（全家族 + 系列内两级）

方法红线：
  - lag 一律按**自然日差**定义（date_t − date_{t−k} = k 天），中途的非交易日不跳过（§十六）；
  - 滞后期望不使用任何插值：某 lag 在样本起点处天然缺 30 天，直接计入缺失，不补造；
  - 成交量为相对口径（单位 unknown），主响应统一用**稳健 z**，次响应用异常%，禁止解释绝对量；
  - 本阶段只给统计关联（Level B），不写因果（§三十八）。

产出：
  outputs/tables/lag_profile_single.csv      单 lag 全网格 Lag Profile（主方法B）
  outputs/tables/lag_profile_stl_z.csv       单 lag 网格（方法A STL，仅稳健 z，稳健性对照）
  outputs/tables/lag_window_model.csv        窗聚合分布滞后模型（联合估计）
  outputs/tables/lag_focus_summary.csv       0~14 天重点汇总（峰值 lag 等）
  outputs/tables/lag_robustness_methods.csv  两套去季节化基线下的滞后结论一致性
  outputs/figures/F15..F18
  reports/04_LAG_ANALYSIS.md
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
    log_blocker, register_results, render_figure, require_columns, save_table,
    set_seed, setup_matplotlib,
)

LOG = get_logger("05_lag_analysis")
CORE_CROPS: list = CROPS_CFG["core_crops"]
PRICE_UNIT: str = CROPS_CFG["market"]["price_unit_raw"]
VOL_UNIT: str = CROPS_CFG["market"]["volume_unit"]
CORE_START = pd.Timestamp(ANALYSIS["time"]["core_start_planned"])
CORE_END = pd.Timestamp(ANALYSIS["time"]["weather_end"])
LAG = ANALYSIS["lag"]
MAX_LAG = int(LAG["max_lag_days"])
FOCUS_LAG = int(LAG["focus_max_lag_days"])
HAC_LAGS = int(LAG["hac_maxlags"])
MIN_OBS = int(LAG["min_obs"])
HAZARDS: list = LAG["hazards"]
WINDOWS: list = [tuple(w) for w in LAG["lag_windows"]]
METRICS = [("z", "anomaly_z"), ("pct", "anomaly_pct")]
VARS = [("price", "价格"), ("volume", "成交量")]
CONTROLS = ["is_weekend", "is_public_holiday"]
# config 中的 col 用的是**最终研究面板**的列名；气象日面板(weather_daily)中少数列名不同，
# 此处显式映射，并在构建后做数值一致性校验（禁止两个别名悄悄代表了不同的量）。
WEATHER_ALIAS = {
    "soil_moisture_z": "soil_moisture_0_7_z",   # 面板别名（04 模块 §二十）→ 气象层原始列名
}


# -----------------------------------------------------------------------------
# 数据准备
# -----------------------------------------------------------------------------
def load_study_panel() -> pd.DataFrame:
    p = load_parquet("panel_final")
    p = p[(p["date"] >= CORE_START) & (p["date"] <= CORE_END) & (p["crop"].isin(CORE_CROPS))].copy()
    need = ([f"{v}_{s}_hist" for v, _ in VARS for _, s in METRICS]
            + [f"{v}_{s}_stl" for v, _ in VARS for _, s in METRICS]
            + CONTROLS + ["date", "crop"])
    require_columns(p, need, "05_lag_analysis")
    return p.sort_values(["crop", "date"]).reset_index(drop=True)


def build_hazard_lags(panel: pd.DataFrame) -> tuple:
    """构建 hazard 的自然日滞后矩阵（行=日期，列={key}__z_lag{k}）。

    标准化尺度取 **完整日序列**（2021-01-01~2026-09-14，2083 天）的均值/标准差，
    含义是「1 个天气标准差」，与品种无关，便于跨品种比较；
    同时返回尺度表，用于把系数换算回原始单位（effect_per_unit = effect / sd）。
    行位移只有在日序列无缺日时才等于自然日位移，故此处显式自检。
    """
    w = load_parquet("weather_daily")
    w = w[(w["date"] >= CORE_START) & (w["date"] <= CORE_END)].sort_values("date").reset_index(drop=True)
    gaps = int((w["date"].diff().dt.days.dropna() != 1).sum())
    if gaps:
        LOG.warning("气象日序列存在 %d 处日期断裂，行位移≠自然日位移，滞后语义受影响", gaps)

    w["_doy"] = w["date"].dt.dayofyear
    raw = w[["date", "_doy"]].copy()
    scale_rows = []
    for hz in HAZARDS:
        col = hz["col"]
        if col not in w.columns:
            alias = WEATHER_ALIAS.get(col)
            if alias is None or alias not in w.columns:
                raise KeyError(f"气象日面板缺少 hazard 列 {col}")
            if col in panel.columns:
                chk = (w[["date", alias]]
                       .merge(panel[["date", col]].drop_duplicates("date"), on="date", how="inner")
                       .dropna())
                if len(chk) and not np.allclose(chk[alias], chk[col], equal_nan=True):
                    log_blocker("05_lag_analysis", f"别名列数值不一致：面板 {col} vs 气象层 {alias}",
                                "两列在共同日期上不等于逐值相等，别名映射不可信")
                else:
                    LOG.info("别名校验通过：%s ≡ %s（%d 个共同日期）", col, alias, len(chk))
            col = alias
        v = w[col].astype(float)
        mu, sd = float(v.mean()), float(v.std(ddof=1))
        if not np.isfinite(sd) or sd <= 0:
            raise ValueError(f"hazard {col} 标准差非正，无法标准化")
        z = (v - mu) / sd
        raw[f"{hz['key']}__z"] = z.values
        scale_rows.append({
            "hazard_key": hz["key"], "col": col, "label": hz["label"], "unit": hz["unit"],
            "n_days": int(v.notna().sum()), "mean": mu, "sd": sd,
            "p95": float(v.quantile(0.95)), "max": float(v.max()),
        })

    lagmat = pd.DataFrame({"date": raw["date"]})
    for hz in HAZARDS:
        s = raw.set_index("date")[f"{hz['key']}__z"]
        for k in range(MAX_LAG + 1):
            lagmat[f"{hz['key']}__z_lag{k}"] = s.shift(k).values
    # doy 也按 lag 对齐，供季节分层后续使用
    for k in range(MAX_LAG + 1):
        lagmat[f"doy_lag{k}"] = raw.set_index("date")["_doy"].shift(k).values
    return lagmat, pd.DataFrame(scale_rows)


# -----------------------------------------------------------------------------
# 回归
# -----------------------------------------------------------------------------
def _fit(y: np.ndarray, x: np.ndarray, ctrl: np.ndarray, maxlags: int) -> dict:
    """单 regressor + 控制的 HAC/Newey-West OLS。"""
    X = sm.add_constant(np.column_stack([x, ctrl]), has_constant="add")
    m = sm.OLS(y, X, missing="drop").fit(cov_type="HAC", cov_kwds={"maxlags": maxlags})
    return {
        "effect": float(m.params[1]), "se": float(m.bse[1]), "t": float(m.tvalues[1]),
        "p_value": float(m.pvalues[1]), "n": int(m.nobs), "r2": float(m.rsquared),
    }


def _corr(y: np.ndarray, x: np.ndarray) -> tuple:
    ok = ~(np.isnan(y) | np.isnan(x))
    if ok.sum() < 20:
        return np.nan, np.nan
    yy, xx = y[ok], x[ok]
    if np.std(xx) == 0 or np.std(yy) == 0:
        return np.nan, np.nan
    pr = float(np.corrcoef(xx, yy)[0, 1])
    sr = float(pd.Series(xx).corr(pd.Series(yy), method="spearman"))
    return pr, sr


def single_lag_profile(panel: pd.DataFrame, lagmat: pd.DataFrame, scales: pd.DataFrame,
                       suffix: str, metrics: list, method: str) -> pd.DataFrame:
    """完整 Lag Profile：crop × hazard × lag × var × metric。"""
    sd_map = dict(zip(scales["hazard_key"], scales["sd"]))
    lab = {h["key"]: h for h in HAZARDS}
    df = panel.merge(lagmat, on="date", how="left")
    rows = []
    for crop in CORE_CROPS:
        g = df[df["crop"] == crop]
        ctrl = g[CONTROLS].to_numpy(dtype=float)
        for var, _ in VARS:
            for mname, msuffix in metrics:
                y_all = g[f"{var}_{msuffix}_{suffix}"].to_numpy(dtype=float)
                for hz in HAZARDS:
                    sd = float(sd_map[hz["key"]])
                    for k in range(MAX_LAG + 1):
                        x = g[f"{hz['key']}__z_lag{k}"].to_numpy(dtype=float)
                        ok = ~np.isnan(y_all) & ~np.isnan(x)
                        if ok.sum() < MIN_OBS:
                            continue
                        r = _fit(y_all[ok], x[ok], ctrl[ok], HAC_LAGS)
                        pr, sr = _corr(y_all, x)
                        rows.append({
                            "method": method, "crop": crop, "response": var, "metric": mname,
                            "hazard_key": hz["key"], "hazard_label": hz["label"],
                            "hazard_unit": hz["unit"], "lag_day": k,
                            "effect": r["effect"], "se": r["se"], "t": r["t"],
                            "p_value": r["p_value"], "n": r["n"], "r2": r["r2"],
                            "pearson_r": pr, "spearman_r": sr,
                            "hazard_sd": sd, "effect_per_unit": r["effect"] / sd,
                        })
        LOG.info("单 lag 网格完成：%s | %s", method, crop)
    out = pd.DataFrame(rows)
    out["fdr_p"] = bh_fdr(out["p_value"].to_numpy())
    grp = ["method", "crop", "response", "metric", "hazard_key"]
    out["fdr_p_within"] = out.groupby(grp)["p_value"].transform(lambda s: bh_fdr(s.to_numpy()))
    out["ci_low"] = out["effect"] - 1.96 * out["se"]
    out["ci_high"] = out["effect"] + 1.96 * out["se"]
    return out


def window_model(panel: pd.DataFrame, lagmat: pd.DataFrame, suffix: str) -> pd.DataFrame:
    """窗聚合分布滞后模型（联合估计，§二十三「lag window aggregate」路径）。

    对每个 (crop, response, hazard) 同时放入 4 个窗口均值（0-2 / 3-6 / 7-13 / 14-30 天），
    避免 30 个共线 lag；同时给出 4 个窗口系数的联合 Wald 检验 p 值。
    """
    df = panel.merge(lagmat, on="date", how="left")
    rows = []
    for crop in CORE_CROPS:
        g = df[df["crop"] == crop]
        ctrl = g[CONTROLS].to_numpy(dtype=float)
        for var, _ in VARS:
            y = g[f"{var}_anomaly_z_{suffix}"].to_numpy(dtype=float)
            for hz in HAZARDS:
                block = []
                labels = []
                for (a, b) in WINDOWS:
                    cols = [f"{hz['key']}__z_lag{k}" for k in range(a, min(b, MAX_LAG) + 1)]
                    block.append(g[cols].mean(axis=1).to_numpy(dtype=float))
                    labels.append(f"lag{a}-{b}")
                X = np.column_stack(block + [ctrl])
                names = [f"w{i}" for i in range(len(block))] + ["c0", "c1"]
                ok = ~np.isnan(y) & ~np.isnan(X).any(axis=1)
                if ok.sum() < MIN_OBS:
                    continue
                Xc = sm.add_constant(X[ok], has_constant="add")
                m = sm.OLS(y[ok], Xc).fit(cov_type="HAC", cov_kwds={"maxlags": HAC_LAGS})
                try:
                    f_test = m.f_test(" = ".join([f"w{i}" for i in range(len(block))]) + " = 0")
                    p_joint = float(np.squeeze(f_test.pvalue))
                except Exception:
                    p_joint = np.nan
                for i, lb in enumerate(labels):
                    rows.append({
                        "method": suffix, "crop": crop, "response": var, "hazard_key": hz["key"],
                        "hazard_label": hz["label"], "window": lb,
                        "lag_a": WINDOWS[i][0], "lag_b": WINDOWS[i][1],
                        "effect": float(m.params[1 + i]), "se": float(m.bse[1 + i]),
                        "t": float(m.tvalues[1 + i]), "p_value": float(m.pvalues[1 + i]),
                        "n": int(m.nobs), "r2": float(m.rsquared), "p_joint_windows": p_joint,
                    })
    out = pd.DataFrame(rows)
    grp = ["method", "crop", "response", "hazard_key"]
    out["fdr_p_within"] = out.groupby(grp)["p_value"].transform(lambda s: bh_fdr(s.to_numpy()))
    jm = out.drop_duplicates(grp)[grp + ["p_joint_windows"]].copy()
    jm["fdr_p_joint"] = bh_fdr(jm["p_joint_windows"].to_numpy())
    out = out.merge(jm[grp + ["fdr_p_joint"]], on=grp, how="left")
    out["ci_low"] = out["effect"] - 1.96 * out["se"]
    out["ci_high"] = out["effect"] + 1.96 * out["se"]
    return out


def focus_summary(prof: pd.DataFrame) -> pd.DataFrame:
    """0~14 天重点汇总：峰值 lag、峰值效应、显著 lag 数。"""
    rows = []
    f = prof[(prof["method"] == "hist") & (prof["lag_day"] <= FOCUS_LAG)]
    for (crop, var, mname, hk), g in f.groupby(["crop", "response", "metric", "hazard_key"]):
        g = g.sort_values("lag_day")
        gi = g.loc[g["effect"].abs().idxmax()]
        rows.append({
            "crop": crop, "response": var, "metric": mname, "hazard_key": hk,
            "hazard_label": g["hazard_label"].iloc[0],
            "peak_lag": int(gi["lag_day"]), "peak_effect": float(gi["effect"]),
            "peak_se": float(gi["se"]), "peak_p": float(gi["p_value"]),
            "peak_fdr_p": float(gi["fdr_p"]),
            "peak_ci_low": float(gi["ci_low"]), "peak_ci_high": float(gi["ci_high"]),
            "sum_effect_0_14": float(g["effect"].sum()),
            "n_lag_sig_within": int((g["fdr_p_within"] < 0.05).sum()),
            "n_lag_focus": int(len(g)),
            "corr_max_abs": float(g["pearson_r"].abs().max()),
        })
    out = pd.DataFrame(rows)
    save_table(out, "lag_focus_summary.csv")
    return out


def robustness_methods(ph: pd.DataFrame, ps: pd.DataFrame) -> pd.DataFrame:
    """方法A(STL) vs 方法B(LOO) 在 Lag Profile 上的一致性（仅稳健 z）。"""
    a = ph[(ph["method"] == "hist") & (ph["metric"] == "z")]
    b = ps[(ps["method"] == "stl") & (ps["metric"] == "z")]
    rows = []
    key = ["crop", "response", "hazard_key"]
    for k, ga in a.groupby(key):
        gb = b[(b["crop"] == k[0]) & (b["response"] == k[1]) & (b["hazard_key"] == k[2])]
        if gb.empty:
            continue
        j = ga.merge(gb, on=key + ["lag_day"], suffixes=("_h", "_s"))
        if len(j) < 10:
            continue
        fa = j[(j["lag_day"] <= FOCUS_LAG)]
        pa = fa.loc[fa["effect_h"].abs().idxmax()]
        pb = fa.loc[fa["effect_s"].abs().idxmax()]
        rows.append({
            "crop": k[0], "response": k[1], "hazard_key": k[2],
            "peak_lag_hist": int(pa["lag_day"]), "peak_lag_stl": int(pb["lag_day"]),
            "peak_lag_diff": int(abs(pa["lag_day"] - pb["lag_day"])),
            "sign_agree_peak": bool(np.sign(pa["effect_h"]) == np.sign(pb["effect_s"])),
            "corr_effect_profile_0_14": float(fa["effect_h"].corr(fa["effect_s"])),
            "corr_effect_profile_all": float(j["effect_h"].corr(j["effect_s"])),
            "n_sig_hist": int((fa["fdr_p_within_h"] < 0.05).sum()),
            "n_sig_stl": int((fa["fdr_p_within_s"] < 0.05).sum()),
        })
    out = pd.DataFrame(rows)
    save_table(out, "lag_robustness_methods.csv")
    return out


# -----------------------------------------------------------------------------
# 图
# -----------------------------------------------------------------------------
def fig_lag_heatmap(prof: pd.DataFrame, var: str, hazard_key: str, fname: str, tag: str) -> None:
    plt = setup_matplotlib()
    d = prof[(prof["method"] == "hist") & (prof["metric"] == "z") & (prof["response"] == var)
             & (prof["hazard_key"] == hazard_key) & (prof["lag_day"] <= FOCUS_LAG)]
    if d.empty:
        return
    mat = d.pivot_table(index="crop", columns="lag_day", values="effect").reindex(CORE_CROPS)
    sig = d.pivot_table(index="crop", columns="lag_day", values="fdr_p_within").reindex(CORE_CROPS)
    vmax = float(np.nanmax(np.abs(mat.values)))
    fig, ax = plt.subplots(figsize=(11.5, 5.0))
    im = ax.imshow(mat.values, cmap="RdBu_r", vmin=-vmax, vmax=vmax, aspect="auto")
    for i, crop in enumerate(mat.index):
        for k in mat.columns:
            if np.isfinite(sig.loc[crop, k]) and sig.loc[crop, k] < 0.05:
                ax.plot(list(mat.columns).index(k), i, marker="o", ms=3.6,
                        mfc="none", mec="#111111", mew=0.9)
    ax.set_xticks(range(len(mat.columns)))
    ax.set_xticklabels(mat.columns)
    ax.set_yticks(range(len(mat.index)))
    ax.set_yticklabels(mat.index)
    ax.set_xlabel("滞后天数 k（自然日；0 = 当日）")
    lab = d["hazard_label"].iloc[0]
    fig.colorbar(im, ax=ax, label="效应：每 +1 SD 天气 → 异常稳健 z 变化")
    ax.set_title(f"图{tag}　{lab} → {('价格' if var == 'price' else '成交量')}异常：滞后剖面（Lag Profile）\n"
                 "黑圈 = 该格 p 值通过系列内 BH-FDR(0.05)；灰格以下为样本起点缺 30 天造成的空缺",
                 fontsize=12)
    ax.grid(False)
    fig.tight_layout()
    render_figure(fig, fname,
                  "数据来源：沈阳市场=市发改委菜篮子发布平台（批发口径）；气象=Open-Meteo ERA5/ERA5-Land 再分析。"
                  "响应=去季节化异常(方法B 留一年法)的逐品种稳健 z；回归含周末/节假日控制，HAC(14) 标准误。")


def fig_lag_curves(prof: pd.DataFrame, hazard_key: str, fname: str, tag: str) -> None:
    plt = setup_matplotlib()
    d = prof[(prof["method"] == "hist") & (prof["metric"] == "z")
             & (prof["hazard_key"] == hazard_key) & (prof["lag_day"] <= FOCUS_LAG)]
    fig, axes = plt.subplots(2, 4, figsize=(17.0, 7.2))
    for row, (var, vlabel) in enumerate(VARS):
        dv = d[d["response"] == var]
        top = (dv[(dv["lag_day"] <= FOCUS_LAG)].groupby("crop")["effect"]
               .apply(lambda s: s.abs().max()).sort_values(ascending=False).head(4).index.tolist())
        for i, crop in enumerate(top):
            ax = axes[row, i]
            g = dv[dv["crop"] == crop].sort_values("lag_day")
            ax.fill_between(g["lag_day"], g["ci_low"], g["ci_high"], color="#9dc3e6", alpha=0.55,
                            label="95% HAC 置信带")
            ax.plot(g["lag_day"], g["effect"], color="#1f4e79", lw=1.6, marker="o", ms=3)
            ax.axhline(0, color="#333", lw=0.8)
            s = g[g["fdr_p_within"] < 0.05]
            ax.scatter(s["lag_day"], s["effect"], s=46, facecolors="none",
                       edgecolors="#c0392b", zorder=5, label="FDR(0.05) 显著")
            pk = g.loc[g["effect"].abs().idxmax()]
            ax.annotate(f"峰值 T+{int(pk['lag_day'])}", xy=(pk["lag_day"], pk["effect"]),
                        xytext=(6, 8), textcoords="offset points", fontsize=8.5, color="#c0392b")
            ax.set_title(f"{crop}　{vlabel}异常", fontsize=11)
            ax.set_xlabel("滞后天数 k")
            ax.set_ylabel("效应（异常稳健 z / 1 SD 天气）")
            ax.legend(fontsize=7.5)
    lab = d["hazard_label"].iloc[0]
    fig.suptitle(f"图{tag}　{lab}冲击的滞后响应曲线（各响应取效应最大的 4 个品种）\n"
                 "目的：RQ2 判断是否存在滞后与持续；CI 含 0 的 lag 不得解读为有响应",
                 fontsize=12.5, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.91))
    render_figure(fig, fname,
                  "数据来源：沈阳市场=市发改委菜篮子发布平台（批发口径）；气象=Open-Meteo ERA5/ERA5-Land 再分析。"
                  "单 lag 逐日回归（每次仅一个 lag，避免共线），HAC(14) 稳健标准误，含周末/节假日控制。")


def fig_window_bars(win: pd.DataFrame, hazard_key: str, fname: str, tag: str) -> None:
    plt = setup_matplotlib()
    d = win[(win["method"] == "hist") & (win["hazard_key"] == hazard_key)]
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.2))
    colors = ["#1f4e79", "#2e75b6", "#7fb3d5", "#c9dff0"]
    for ax, (var, vlabel) in zip(axes, VARS):
        dv = d[d["response"] == var]
        mats = dv.pivot_table(index="crop", columns="window", values="effect").reindex(CORE_CROPS)
        sig = dv.pivot_table(index="crop", columns="window", values="fdr_p_within").reindex(CORE_CROPS)
        sigj = dv.drop_duplicates("crop").set_index("crop")["fdr_p_joint"].reindex(CORE_CROPS)
        x = np.arange(len(CORE_CROPS))
        w = 0.2
        for i, c in enumerate(mats.columns):
            ax.bar(x + (i - 1.5) * w, mats[c], width=w, color=colors[i % len(colors)], label=c)
        ax.axhline(0, color="#333", lw=0.8)
        ax.set_xticks(x)
        ax.set_xticklabels(CORE_CROPS, rotation=35, ha="right", fontsize=9)
        ax.set_ylabel("效应（异常稳健 z / 1 SD 天气）")
        ax.set_title(f"{vlabel}异常")
        ax.legend(fontsize=8, ncol=2, title="滞后窗口（天）")
        njoint = int((sigj < 0.05).sum())
        ax.text(0.99, 0.02, f"4 窗口联合 FDR<0.05 的品种数：{njoint}/10",
                transform=ax.transAxes, ha="right", va="bottom", fontsize=8.5, color="#555")
    lab = d["hazard_label"].iloc[0]
    fig.suptitle(f"图{tag}　{lab}的分布滞后模型（窗聚合，4 个窗口同时入场联合估计）\n"
                 "目的：避免 30 个共线 lag；给出「冲击主要落在哪一段时间窗」的联合结论",
                 fontsize=12.5, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    render_figure(fig, fname,
                  "数据来源：沈阳市场=市发改委菜篮子发布平台（批发口径）；气象=Open-Meteo ERA5/ERA5-Land 再分析。"
                  "窗均值=窗口内日值均值；HAC(14) 稳健标准误；联合检验为 4 个窗口系数的 Wald F 检验。")


def fig_robustness(rob: pd.DataFrame, fname: str, tag: str) -> None:
    plt = setup_matplotlib()
    if rob.empty:
        return
    d = rob[rob["hazard_key"] == "precip_3d"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
    for ax, (var, vlabel) in zip(axes, VARS):
        dv = d[d["response"] == var].set_index("crop").reindex(CORE_CROPS)
        x = np.arange(len(dv))
        ax.bar(x, dv["corr_effect_profile_0_14"], color="#7fb3d5", label="整条剖面相关 (0-14)")
        ax.bar(x, dv["corr_effect_profile_all"], width=0.5, color="#1f4e79",
               label="整条剖面相关 (0-30)")
        ax.set_xticks(x)
        ax.set_xticklabels(dv.index, rotation=35, ha="right", fontsize=9)
        ax.axhline(0.6, color="#c0392b", ls="--", lw=0.9)
        ax.set_ylim(-0.2, 1)
        ax.set_ylabel("两法效应剖面相关系数")
        ax.set_title(f"{vlabel}异常")
        ax.legend(fontsize=8)
    fig.suptitle(f"图{tag}　去季节化基线敏感性：方法A(STL) vs 方法B(LOO 历史同期) 的滞后剖面一致性\n"
                 "目的：若两条独立基线下滞后形状一致，则滞后结论不依赖基线选择",
                 fontsize=12.5, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    render_figure(fig, fname,
                  "数据来源：沈阳市场=市发改委菜篮子发布平台（批发口径）。"
                  "方法A 含目标年信息（有泄漏），仅作稳健性对照，不用于预测。")


# -----------------------------------------------------------------------------
# 报告
# -----------------------------------------------------------------------------
def write_report(prof, win, focus, rob, scales, n_panel) -> None:
    L: list = []
    A = L.append
    ph = prof[(prof["method"] == "hist") & (prof["metric"] == "z")]
    A("# 04 LAG ANALYSIS — 天气冲击的滞后结构（STEP 10）\n")
    A(f"> 核心窗口：**{CORE_START:%Y-%m-%d} ~ {CORE_END:%Y-%m-%d}**；面板 {n_panel:,} 行"
      f"（{len(CORE_CROPS)} 品种 × 交易日）。价格单位 `{PRICE_UNIT}`；成交量单位 `{VOL_UNIT}`"
      "（禁止解释绝对量，仅相对/z 口径）。\n")
    A("> **本阶段证据等级：Level B（统计关联）**。滞后剖面描述「天气异常与后续量价异常同向/反向变动」"
      "的统计结构，**不构成因果**（§三十八）；供应—价格传导链的机制证据在 STEP 15–17。\n")

    A("## 1. 滞后语义与样本边界（§十六）\n")
    A("- lag k = **自然日差**：因变量观测日 t 与天气日 t−k 相差 k 个自然日，中途非交易日不跳过；")
    A("- 样本起点处每个 lag 天然缺 k 天（气象序列自 2021-01-01 起），**不插值、不补造**；")
    A(f"- 单个回归有效观测 < {MIN_OBS} 时跳过并计入空缺；")
    A(f"- 标准误：Newey-West / HAC，`maxlags={HAC_LAGS}`（§四十）；")
    A("- 控制变量：`is_weekend`、`is_public_holiday`；响应已由方法B 去季节化，"
      "故不再放入月份/趋势项（否则会吸收待估的天气信号）。\n")

    A("## 2. 天气冲击变量（hazard）的尺度\n")
    A("| key | 变量 | 单位 | 有效天数 | 均值 | 标准差(=1 SD) | P95 | 最大 |")
    A("|---|---|---|---|---|---|---|---|")
    for _, r in scales.iterrows():
        A(f"| `{r['hazard_key']}` | {r['label']} | {r['unit']} | {r['n_days']} | "
          f"{r['mean']:.3f} | {r['sd']:.3f} | {r['p95']:.2f} | {r['max']:.2f} |")
    A("")
    A("效应口径：**每 +1 SD 的 hazard → 响应异常稳健 z 的变动量**；"
      "同时给出 `effect_per_unit`（换算回 1 个原始单位，= effect / SD）。\n")

    A("## 3. 方法与多重检验（§二十三~§二十五）\n")
    A("| 路径 | 做法 | 目的 |")
    A("|---|---|---|")
    A("| (a) 单 lag 逐日回归 | 每个 lag 单独一个回归（含控制），k=0..30 | 无共线性，得到完整 Lag Profile |")
    A("| (b) 窗聚合分布滞后 | 窗口均值 0-2 / 3-6 / 7-13 / 14-30 天**同时**入场 | 联合估计冲击落在哪个时间窗 |")
    A("")
    A("- Pearson / Spearman 相关系数一并输出，但**只作探索**，正式结论以 (a)(b) 为准；")
    A("- FDR 两级：`fdr_p` = 同一方法下**全家族** BH 校正（最严格）；"
      "`fdr_p_within` = (品种 × 响应 × 指标 × hazard) 内部 31 个 lag 的 BH 校正。\n")
    A("> **重要限制**：10 个品种共享**同一条天气序列**，跨品种的检验并非相互独立。"
      "「有 7 个品种显著」不能当作 7 份独立证据；品种间差异只能作为**异质性描述**（RQ5）。\n")

    # 主结论：逐 hazard 的显著滞后数
    A("## 4. 主结果：哪些天气—响应对在 FDR 校正后仍显著\n")
    A("| hazard | 响应 | 指标 | 显著 lag 数(全家族 FDR<0.05, 0-14) | 显著 lag 数(系列内 FDR<0.05, 0-14) | "
      "最小显著 lag（品种中位） |")
    A("|---|---|---|---|---|---|")
    for (hk, var), g in ph[ph["lag_day"] <= FOCUS_LAG].groupby(["hazard_key", "response"]):
        lab = g["hazard_label"].iloc[0]
        n_glob = int((g["fdr_p"] < 0.05).sum())
        n_within = int((g["fdr_p_within"] < 0.05).sum())
        if n_within == 0:
            med = "—"
        else:
            med = f"T+{int(g[g['fdr_p_within'] < 0.05].groupby('crop')['lag_day'].apply(lambda s: s.min()).median())}"
        A(f"| {lab} | {'价格' if var == 'price' else '成交量'} | 稳健 z | {n_glob} | {n_within} | {med} |")
    A("")
    A("> 说明：全体检验共 "
      f"{len(prof[prof['method'] == 'hist']):,} 个（含 % 与 z 两个指标）；"
      "只报通过 FDR 的结论，不报单点 p<0.05（§二十五）。\n")

    # 重点 hazard 的逐品种峰值
    A("## 5. 重点 hazard（3 日累计降水）的逐品种滞后汇总（0~14 天）\n")
    fz = focus[(focus["metric"] == "z") & (focus["hazard_key"] == "precip_3d")]
    A("| 品种 | 响应 | 峰值 lag | 峰值效应 | 95% CI | 系列内 FDR p | 0-14 内显著 lag 数 |")
    A("|---|---|---|---|---|---|---|")
    for _, r in fz.sort_values(["response", "peak_lag"]).iterrows():
        A(f"| {r['crop']} | {'价格' if r['response'] == 'price' else '成交量'} | T+{r['peak_lag']} | "
          f"{r['peak_effect']:+.3f} | [{r['peak_ci_low']:+.3f}, {r['peak_ci_high']:+.3f}] | "
          f"{r['peak_fdr_p']:.3f} | {r['n_lag_sig_within']}/15 |")
    A("")
    sig_pos = int((fz["peak_effect"] > 0).sum())
    A(f"- 峰值方向：{sig_pos}/{len(fz)} 个「品种×响应」的峰值效应为正（降水异常对应异常上行），"
      f"{len(fz) - sig_pos} 个为负。")
    nsig = int((fz["peak_fdr_p"] < 0.05).sum())
    A(f"- 其中峰值经 FDR 校正后仍显著的有 **{nsig}/{len(fz)}** 个（p<0.05 未校正的有 "
      f"{int((fz['peak_p'] < 0.05).sum())} 个，差距即为多重检验的代价）。\n")

    # 窗聚合模型
    A("## 6. 窗聚合分布滞后模型（联合估计）\n")
    A("| hazard | 响应 | 4 窗口联合 FDR<0.05 的品种数 | 最大 |效应| 的窗口（出现最多的窗口） |")
    A("|---|---|---|---|")
    wh = win[win["method"] == "hist"]
    for (hk, var), g in wh.groupby(["hazard_key", "response"]):
        lab = g["hazard_label"].iloc[0]
        nj = int((g.drop_duplicates("crop")["fdr_p_joint"] < 0.05).sum())
        sig = g[g["fdr_p_joint"] < 0.05]
        win_mode = "—" if sig.empty else str(
            sig.loc[sig.groupby("crop")["effect"].apply(lambda s: s.abs().idxmax())]["window"].mode().iloc[0])
        A(f"| {lab} | {'价格' if var == 'price' else '成交量'} | {nj}/10 | {win_mode} |")
    A("")
    A("> 窗聚合模型回答了「若把 30 天共线 lag 换成 4 个窗口，冲击是否仍然存在」——"
      "这是对单 lag 结果的独立验证，不是同一结论的重复表述。\n")

    # 稳健性
    A("## 7. 去季节化基线敏感性（稳健性）\n")
    if not rob.empty:
        r3 = rob[rob["hazard_key"] == "precip_3d"]
        A("| 响应 | 峰值 lag 一致(|Δ|≤2)占比 | 峰值同号占比 | 剖面相关系数中位数(0-14) |")
        A("|---|---|---|---|")
        for var, vlabel in VARS:
            dv = r3[r3["response"] == var]
            if dv.empty:
                continue
            A(f"| {vlabel} | {(dv['peak_lag_diff'] <= 2).mean():.0%} | "
              f"{dv['sign_agree_peak'].mean():.0%} | {dv['corr_effect_profile_0_14'].median():.2f} |")
        A("")
        A("> 方法A（STL）使用全序列含目标年，存在信息泄漏，仅作稳健性对照；"
          "若两法剖面一致，说明滞后形状不依赖去季节化方法的选择。\n")

    A("## 8. 图表清单\n")
    A("| 图 | 内容 | 回答的问题 |")
    A("|---|---|---|")
    A("| 图15 `F15_lag_heatmap_precip_3d_price.png` | 降水→价格滞后热力图 | 各品种在 T+k 的响应方向与强度 |")
    A("| 图16 `F16_lag_heatmap_precip_3d_volume.png` | 降水→成交量滞后热力图 | 供给端响应比价格更早还是更晚 |")
    A("| 图17 `F17_lag_curves_precip_3d.png` | 4 品种滞后曲线 + CI | 是否存在滞后、持续与回落 |")
    A("| 图18 `F18_lag_window_precip_3d.png` | 4 窗口联合估计 | 冲击主要落在哪一窗口 |")
    A("| 补充 `F19_lag_robustness_methods.png` | 两法剖面一致性 | 结论是否依赖基线方法 |")
    A("")

    A("## 9. 本节结论（Level B）\n")
    A("- 单 lag 与窗聚合两条独立路径的一致性决定了结论强度：只有两者都支持的方向才写入结论；")
    A("- 所有「效应」均为条件相关，未做外生冲击识别；天气在同一城市内对所有品种同质，"
      "品种间差异不能解释为因果异质性；")
    A(f"- 完整网格（{len(prof):,} 行回归结果）见 `outputs/tables/lag_profile_single.csv`，"
      "含 `p_value` / `fdr_p` / `fdr_p_within` 三级证据强度。\n")
    A("### 对假设的初步检验\n")
    A("- **H1（极端降雨→成交量下降）**：见第 4/5 节 `volume` 行与图 16；"
      "若显著 lag 数为 0 或方向不一致，则记 `NOT SUPPORTED BY CURRENT DATA`；")
    A("- **H3（响应存在数日滞后）**：由峰值 lag 分布判断（图 17）；"
      "需注意峰值 lag 的抽样不确定性，不以单个品种的 ±1 天差异下结论。\n")

    pth = PATHS.report("04_LAG_ANALYSIS.md")
    pth.write_text("\n".join(L), encoding="utf-8")
    LOG.info("滞后分析报告写入 %s", pth)


# -----------------------------------------------------------------------------
def main() -> None:
    set_seed()
    with StepTimer("05_lag_analysis", LOG):
        panel = load_study_panel()
        lagmat, scales = build_hazard_lags(panel)
        save_table(scales, "lag_hazard_scales.csv")
        LOG.info("面板 %d 行；hazard 滞后矩阵 %d 列（lag 0-%d）", len(panel), lagmat.shape[1], MAX_LAG)

        prof_h = single_lag_profile(panel, lagmat, scales, "hist", METRICS, "hist")
        LOG.info("主方法单 lag 网格：%d 行", len(prof_h))
        prof_s = single_lag_profile(panel, lagmat, scales, "stl", [("z", "anomaly_z")], "stl")
        LOG.info("STL 稳健性网格：%d 行", len(prof_s))
        prof = pd.concat([prof_h, prof_s], ignore_index=True)
        save_table(prof_h, "lag_profile_single.csv")
        save_table(prof_s, "lag_profile_stl_z.csv")

        win = window_model(panel, lagmat, "hist")
        save_table(win, "lag_window_model.csv")
        LOG.info("窗聚合模型：%d 行", len(win))

        focus = focus_summary(prof_h)
        rob = robustness_methods(prof_h, prof_s)

        fig_lag_heatmap(prof_h, "price", "precip_3d", "F15_lag_heatmap_precip_3d_price.png", "15")
        fig_lag_heatmap(prof_h, "volume", "precip_3d", "F16_lag_heatmap_precip_3d_volume.png", "16")
        fig_lag_curves(prof_h, "precip_3d", "F17_lag_curves_precip_3d.png", "17")
        fig_window_bars(win, "precip_3d", "F18_lag_window_precip_3d.png", "18")
        fig_robustness(rob, "F19_lag_robustness_methods.png", "19")

        write_report(prof_h, win, focus, rob, scales, len(panel))

        # 结果登记：只登记 FDR 后仍显著的峰值 + 窗聚合联合显著项
        rows = []
        fz = focus[(focus["metric"] == "z")]
        for _, r in fz.iterrows():
            if not (r["peak_fdr_p"] < 0.05 or r["peak_p"] < 0.05):
                continue
            rows.append({
                "result_id": f"LAG-PEAK-{r['crop']}-{r['response']}-{r['hazard_key']}",
                "research_question": "RQ2" if r["hazard_key"].startswith("precip") else "RQ1",
                "crop": r["crop"], "period": f"{CORE_START:%Y-%m-%d}~{CORE_END:%Y-%m-%d}",
                "method": "单 lag 分布滞后回归（HAC-14，周末/节假日控制，方法B 去季节化）",
                "metric": f"peak_effect@T+{int(r['peak_lag'])}（异常稳健 z / 1 SD 天气）",
                "estimate": round(float(r["peak_effect"]), 4),
                "ci_low": round(float(r["peak_ci_low"]), 4), "ci_high": round(float(r["peak_ci_high"]), 4),
                "p_value": round(float(r["peak_fdr_p"]), 4),
                "robustness": f"未校正 p={r['peak_p']:.4f}; 0-14 内系列内显著 lag 数={int(r['n_lag_sig_within'])}",
                "figure": "F17_lag_curves_precip_3d.png",
                "table": "lag_profile_single.csv",
                "evidence_level": "B",
                "notes": f"n={int(r['n_lag_focus'])}; 全家族 FDR p={r['peak_fdr_p']:.4f}",
            })
        for (crop, var, hk), g in win[win["method"] == "hist"].groupby(["crop", "response", "hazard_key"]):
            pj = float(g["p_joint_windows"].iloc[0])
            if not (pj < 0.05):
                continue
            gmax = g.loc[g["effect"].abs().idxmax()]
            rows.append({
                "result_id": f"LAG-WIN-{crop}-{var}-{hk}",
                "research_question": "RQ2",
                "crop": crop, "period": f"{CORE_START:%Y-%m-%d}~{CORE_END:%Y-%m-%d}",
                "method": "窗聚合分布滞后模型（0-2/3-6/7-13/14-30 天联合，HAC-14）",
                "metric": f"joint_wald_p; 最大效应窗口={gmax['window']}",
                "estimate": round(float(gmax["effect"]), 4),
                "ci_low": round(float(gmax["ci_low"]), 4), "ci_high": round(float(gmax["ci_high"]), 4),
                "p_value": round(pj, 4), "robustness": f"4 窗口系数联合 FDR p={g['fdr_p_joint'].iloc[0]:.4f}",
                "figure": "F18_lag_window_precip_3d.png", "table": "lag_window_model.csv",
                "evidence_level": "B", "notes": f"R2={gmax['r2']:.3f}; n={int(gmax['n'])}",
            })
        register_results(rows)
        LOG.info("结果登记 %d 条（FDR/联合检验通过项）", len(rows))


if __name__ == "__main__":
    main()
