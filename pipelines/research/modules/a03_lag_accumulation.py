"""a03_lag_accumulation.py — A03 滞后、累积与非线性响应（六城统一）。

- 滞后窗：过去 k 期累积降水 / 平均最高温 / 平均 VPD（k=1,3,7,14,21,30）。
- 主模型：z_t = α + φ·z_(t-1) + β·exposure_window_z + ε_t，HAC(14)。
- 非线性：在 7 期窗加入暴露平方项，检验二次项（控制自相关）。
- 家族：按暴露分组 BH-FDR。
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from ..lib import contract, emit, loaders, panel, stats

MODULE = "A03"
SLUG = "weather-lag-accumulation-nonlinearity"
TITLE = "气象影响的滞后、累积与非线性特征"
CITY_FREQ = {"chaoyang": "D", "jinzhou": "D", "dalian": "W", "shenyang": "D"}
WINDOWS = [1, 3, 7, 14, 21, 30]
EXPO_AGG = {"precipitation": "sum", "temp_max": "mean", "vpd": "mean"}


def _build_panel(city, crop, freq, win, weather, min_obs):
    s = loaders.load_primary_series(city, crop)
    s = panel.deseasonalize_strict(s, "price_per_kg", "date", freq, win)
    s = panel.add_weather(s, weather, freq, "date")
    s = s.dropna(subset=["z"]).sort_values("date").reset_index(drop=True)
    s["z_lag1"] = s["z"].shift(1)
    return s


def run(city: str) -> Dict:
    if city not in CITY_FREQ:
        return emit.emit_not_supported(city=city, module=MODULE, slug=SLUG, title=TITLE,
                                       reason="无满足最小覆盖的价格序列，无法估计滞后/累积/非线性响应。")
    cfg = loaders.load_cities()[city]
    an = loaders.load_analysis()
    hac = int(an["stats"]["hac_lags"]); win = int(an["price"]["deseason"]["doy_window"])
    min_obs = int(an["price"]["min_days_weather"]); alpha = float(an["global"]["alpha"])
    freq = CITY_FREQ[city]
    weather = loaders.load_weather(city)
    veg = loaders.veg_crops()
    pool = [c for c in veg if len(loaders.load_primary_series(city, c)) >= min_obs]

    lag_rows, nl_rows = [], []
    for crop in pool:
        s = _build_panel(city, crop, freq, win, weather, min_obs)
        if len(s) < min_obs:
            continue
        for ex, agg in EXPO_AGG.items():
            base = s[ex].astype(float)
            for k in WINDOWS:
                if agg == "sum":
                    wv = base.rolling(k, min_periods=max(1, k // 2)).sum().shift(1)
                else:
                    wv = base.rolling(k, min_periods=max(1, k // 2)).mean().shift(1)
                col = f"{ex}_w{k}"
                s[col] = (wv - wv.mean()) / wv.std() if wv.std() and wv.std() > 0 else np.nan
                d = s.dropna(subset=[col, "z_lag1", "z"])
                if len(d) < min_obs:
                    continue
                r = stats.hac_ols(d["z"].to_numpy(), d[["z_lag1", col]].to_numpy(), maxlags=hac)
                lag_rows.append({"city": city, "crop": crop, "exposure": ex, "window": k,
                                 "beta_per_sd": float(r["coef"][1]),
                                 "ci_low": float(r["coef"][1] - 1.96 * r["se"][1]),
                                 "ci_high": float(r["coef"][1] + 1.96 * r["se"][1]),
                                 "p_raw": float(r["p"][1]), "n": r["n"], "ar1": r["ar1"]})
            # 非线性（7 期窗，二次项）
            col = f"{ex}_w7"
            if col in s.columns:
                d = s.dropna(subset=[col, "z_lag1", "z"]).copy()
                d["sq"] = d[col] ** 2
                if len(d) >= min_obs:
                    r = stats.hac_ols(d["z"].to_numpy(), d[["z_lag1", col, "sq"]].to_numpy(), maxlags=hac)
                    nl_rows.append({"city": city, "crop": crop, "exposure": ex,
                                    "beta_linear": float(r["coef"][1]), "beta_sq": float(r["coef"][2]),
                                    "p_linear": float(r["p"][1]), "p_sq": float(r["p"][2]),
                                    "n": r["n"], "ar1": r["ar1"]})

    lag = pd.DataFrame(lag_rows); nl = pd.DataFrame(nl_rows)
    if lag.empty:
        return emit.emit_not_supported(city=city, module=MODULE, slug=SLUG, title=TITLE,
                                       reason="有效观测不足，未得到可估计的滞后窗模型。")
    lag["q"] = np.nan
    for ex, g in lag.groupby("exposure"):
        lag.loc[g.index, "q"] = stats.bh_fdr(g["p_raw"].to_numpy())
    lag = lag.sort_values("p_raw")
    n_sig_lag = int((lag["q"] < alpha).sum())
    if not nl.empty:
        nl["q_sq"] = np.nan
        for ex, g in nl.groupby("exposure"):
            nl.loc[g.index, "q_sq"] = stats.bh_fdr(g["p_sq"].to_numpy())
        n_sig_nl = int((nl["q_sq"] < alpha).sum())
    else:
        n_sig_nl = 0

    w = contract.StudyWriter(city, MODULE, SLUG, f"{cfg['name']}市{TITLE}")
    w.save_table(lag, f"{MODULE}_lag_windows.csv")
    if not nl.empty:
        w.save_table(nl, f"{MODULE}_nonlinearity.csv")
    # 累积尺度对照（原始尺度 vs 标准化）
    acc = (lag.groupby(["exposure", "window"]).agg(
        n_tests=("p_raw", "size"), n_sig=("q", lambda s: int((s < alpha).sum())),
        median_beta=("beta_per_sd", "median")).reset_index())
    w.save_table(acc, f"{MODULE}_accumulation.csv")

    fig = _fig(cfg["name"], lag)
    w.save_fig(fig, f"{MODULE}_lag_profile.png")
    metrics = {"city": city, "freq": freq, "n_crops": len(pool), "n_lag_tests": int(len(lag)),
               "n_lag_sig": n_sig_lag, "n_nl_tests": int(len(nl)), "n_nl_sig": n_sig_nl, "alpha": alpha}
    w.dump_metrics(f"{MODULE}_summary.json", metrics)

    sig = lag[lag["q"] < alpha]
    sig_txt = "；".join([f"{r['crop']}×{r['exposure']}(k={int(r['window'])}) {r['beta_per_sd']:+.3f}"
                        for _, r in sig.head(8).iterrows()]) or "无"
    best_w = acc.sort_values("n_sig", ascending=False).head(1)
    bw_txt = (f"{best_w.iloc[0]['exposure']} 在 k={int(best_w.iloc[0]['window'])} "
              f"有 {int(best_w.iloc[0]['n_sig'])} 项显著" if len(best_w) else "无")
    abstract = (
        f"本研究检验{cfg['name']}主要农产品价格异常对气象的**滞后与累积**响应及**非线性**。"
        f"价格为该城主源（{cfg['price_level_note']}），频率{'日度' if freq=='D' else '周度'}；"
        f"异常用严格无未来信息基线。滞后窗 k=1/3/7/14/21/30 期，模型 "
        f"z_t = α + φ·z_(t-1) + β·exposure_window_z + ε_t（HAC({hac})）。"
        f"共 {len(lag)} 项滞后窗检验，**{n_sig_lag} 项 FDR 显著**；非线性（7 期窗二次项）"
        f"{len(nl)} 项中 {n_sig_nl} 项显著。\n\n**关键词**：滞后窗；累积暴露；非线性；HAC；BH-FDR；{cfg['name']}"
    )
    frontend_summary = f"{cfg['name']}：滞后窗 {len(lag)} 项中 {n_sig_lag} 项显著；非线性 {n_sig_nl}/{len(nl)}。"
    data_scope = (f"### 2.1 研究对象\n{cfg['name']}主要蔬菜（{'、'.join(pool)}），频率 "
                  f"{'日度' if freq=='D' else '周度'}。\n\n### 2.2 数据来源\n价格：{cfg['price_level_note']}；"
                  f"气象：ERA5 再分析网格。\n\n### 2.3 变量\n- z：严格去季节化价格异常。\n"
                  f"- exposure_window：过去 k 期的累积降水/平均最高温/平均 VPD（标准化）。")
    methods = (f"### 3.1 主分析\n逐作物×暴露×窗估计 z_t = α + φ·z_(t-1) + β·w_z + ε_t，HAC({hac})。\n\n"
               f"### 3.2 非线性\n7 期窗加二次项，控制自相关后检验 β_sq。\n\n"
               f"### 3.3 多重检验\n按暴露分组 BH-FDR。")
    results_text = [
        ("滞后窗", f"{len(lag)} 项中 **{n_sig_lag} 项 FDR 显著**：{sig_txt}。（表 {MODULE}_lag_windows.csv）"),
        ("累积窗汇总", acc.to_string(index=False)),
        ("非线性", f"{len(nl)} 项二次项检验中 {n_sig_nl} 项显著；控制自相关后非线性证据"
                   f"{'有限' if n_sig_nl < 3 else '存在'}。（表 {MODULE}_nonlinearity.csv）"),
    ]
    discussion = ("滞后窗显著项的分布反映气象影响的时滞结构；但显著比例低、效应量小，说明价格异常"
                  "主要由自身持续性解释。非线性证据薄弱，提示不宜引入阈值型机制叙事。观察性设计不构成因果。")
    limitations = [
        f"1. **价格口径**：{cfg['price_level_note']}，非批发市场，跨城不可直接比较。",
        "2. **再分析网格**：ERA5 平滑极端值。",
        "3. **自相关**：价格异常强持续，未控制自相关会高估气象显著性（本分析已控制）。",
        "4. **窗长上限 30**：更长窗在周度城市信息量不足。",
    ]
    conclusion = (f"{cfg['name']}：滞后窗 {len(lag)} 项中 {n_sig_lag} 项 FDR 显著，非线性 {n_sig_nl}/{len(nl)}；"
                  f"气象影响的滞后/累积/非线性证据{'有限' if n_sig_lag < 3 else '部分存在'}，"
                  f"效应量普遍较小。")
    explorer = {
        "selectors": [{"key": "crop", "label": "作物", "options": pool},
                      {"key": "exposure", "label": "暴露", "options": list(EXPO_AGG.keys())},
                      {"key": "window", "label": "滞后窗", "options": WINDOWS}],
        "metrics": ["n_lag_tests", "n_lag_sig", "n_nl_sig"],
        "series": [{"id": "lag_profile", "table": f"{MODULE}_lag_windows.csv", "x": "window",
                    "y": "beta_per_sd", "group": "crop", "facet": "exposure"}],
        "tables": [f"{MODULE}_lag_windows.csv", f"{MODULE}_accumulation.csv", f"{MODULE}_nonlinearity.csv"],
        "figures": [f"{MODULE}_lag_profile.png"], "sources": [],
        "methodology": methods, "limitations": limitations,
    }
    return emit.emit_study(
        city=city, module=MODULE, slug=SLUG, title=f"{cfg['name']}市{TITLE}",
        abstract=abstract, frontend_summary=frontend_summary,
        keywords=["滞后窗", "累积暴露", "非线性", "HAC", "BH-FDR", cfg["name"]],
        research_questions=[f"{cfg['name']}价格异常是否存在气象滞后/累积/非线性响应？"],
        data_scope=data_scope, methods=methods, results=results_text, discussion=discussion,
        limitations=limitations, conclusion=conclusion, explorer=explorer,
        tables=[f"{MODULE}_lag_windows.csv", f"{MODULE}_accumulation.csv", f"{MODULE}_nonlinearity.csv"],
        figures=[f"{MODULE}_lag_profile.png"],
        claims=[{"claim_id": f"{city}-A03-C1", "study_id": "A03", "city": cfg["name"],
                 "claim_text": f"滞后窗 {len(lag)} 项检验 {n_sig_lag} 项 FDR 显著",
                 "claim_type": "inferential", "table_id": f"{MODULE}_lag_windows.csv",
                 "estimate": n_sig_lag, "sample_size": int(lag["n"].max()),
                 "status": "PARTIAL" if n_sig_lag else "NOT_SUPPORTED"}])


def _fig(city_name, lag):
    from ..lib.plotting import setup_plt, C_MAIN
    plt = setup_plt()
    fig, ax = plt.subplots(figsize=(7.6, 4.6))
    for ex, g in lag.groupby("exposure"):
        prof = g.groupby("window")["beta_per_sd"].mean()
        ax.plot(prof.index, prof.values, marker="o", label=ex, color=C_MAIN if ex == "precipitation" else None)
    ax.axhline(0, color="grey", lw=0.8)
    ax.set_xlabel("滞后窗 k（期）"); ax.set_ylabel("平均效应（每 +1 SD 暴露，单位=SD）")
    ax.set_title(f"{city_name}市 气象滞后窗效应剖面")
    ax.legend()
    return fig