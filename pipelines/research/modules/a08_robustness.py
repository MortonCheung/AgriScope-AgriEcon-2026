"""a08_robustness.py — A08 稳健性与可信度（横切）。

不新增研究问题，只对 A01/A02/A04 的关键估计做稳健性检验：
1. A01 趋势：留一年法（LOO）重估，观察显著性与方向稳定性。
2. A02 主效应：对比"含自回归"与"不含自回归"的显著数（说明自相关控制的决定性影响）。
3. A04：引用安慰剂 p 作为事件响应可信度指标。

对无市场类分析的丹东/铁岭 → NOT_SUPPORTED_BY_CURRENT_DATA（无可检验估计）。
"""
from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

from ..lib import contract, emit, loaders, panel, stats

MODULE = "A08"
SLUG = "robustness-credibility"
TITLE = "稳健性与可信度检验"
CITY_FREQ = {"chaoyang": "D", "jinzhou": "D", "dalian": "W", "shenyang": "D"}


def run(city: str) -> Dict:
    if city not in CITY_FREQ:
        return emit.emit_not_supported(city=city, module=MODULE, slug=SLUG, title=TITLE,
                                       reason="本城无市场类分析估计，稳健性检验不适用（NOT_SUPPORTED）。",
                                       notes=["丹东/铁岭无稳定蔬菜价格序列", "A08 依附 A01–A06 的成立度"])
    cfg = loaders.load_cities()[city]
    an = loaders.load_analysis()
    hac = int(an["stats"]["hac_lags"]); win = int(an["price"]["deseason"]["doy_window"])
    min_obs = int(an["price"]["min_days_weather"]); alpha = float(an["global"]["alpha"])
    freq = CITY_FREQ[city]
    weather = loaders.load_weather(city); veg = loaders.veg_crops()
    pool = [c for c in veg if len(loaders.load_primary_series(city, c)) >= min_obs]

    # 1) A01 趋势 LOO
    loo_rows = []
    for crop in pool:
        s = loaders.load_primary_series(city, crop).dropna(subset=["price_per_kg"])
        s = s[s["price_per_kg"] > 0]
        if len(s) < 60:
            continue
        t = (s["date"] - s["date"].min()).dt.days.to_numpy() / 365.25
        y = np.log(s["price_per_kg"].to_numpy())
        full = stats.hac_ols(y, t, maxlags=hac)
        full_sig = float(full["p"][0]) < alpha
        years = s["date"].dt.year.to_numpy()
        signs, sig_flags = [], []
        for Y in np.unique(years):
            m = years != Y
            if m.sum() < 60:
                continue
            r = stats.hac_ols(y[m], t[m], maxlags=hac)
            signs.append(np.sign(r["coef"][0])); sig_flags.append(float(r["p"][0]) < alpha)
        loo_rows.append({"crop": crop, "ann_pct_full": 100 * (np.exp(float(full["coef"][0])) - 1),
                         "full_sig": full_sig,
                         "loo_sign_consistency": float(np.mean(np.array(signs) == np.sign(full["coef"][0]))) if signs else np.nan,
                         "loo_sig_share": float(np.mean(sig_flags)) if sig_flags else np.nan,
                         "n_loo": len(signs)})
    loo = pd.DataFrame(loo_rows)

    # 2) A02 含/不含自回归对比
    cmp_rows = []
    for crop in pool:
        s = panel.deseasonalize_strict(loaders.load_primary_series(city, crop), "price_per_kg", "date",
                                       freq=freq, doy_window=win)
        s = panel.add_weather(s, weather, freq, "date").dropna(subset=["z"]).sort_values("date").reset_index(drop=True)
        s["z_lag1"] = s["z"].shift(1)
        for ex in panel.EXPOSURES:
            col = ex + "_z"
            if col not in s.columns:
                continue
            d = s.dropna(subset=[col, "z_lag1", "z"])
            if len(d) < min_obs:
                continue
            with_ar = stats.hac_ols(d["z"].to_numpy(), d[["z_lag1", col]].to_numpy(), maxlags=hac)
            no_ar = stats.hac_ols(d["z"].to_numpy(), d[[col]].to_numpy(), maxlags=hac)
            cmp_rows.append({"crop": crop, "exposure": ex,
                             "p_with_ar": float(with_ar["p"][1]), "p_no_ar": float(no_ar["p"][0]),
                             "sig_with_ar": float(with_ar["p"][1]) < alpha,
                             "sig_no_ar": float(no_ar["p"][0]) < alpha})
    cmp = pd.DataFrame(cmp_rows)
    n_no = int(cmp["sig_no_ar"].sum()) if len(cmp) else 0
    n_w = int(cmp["sig_with_ar"].sum()) if len(cmp) else 0

    # 3) A04 安慰剂
    placebo = np.nan
    p_metrics = paths_metrics(city, "A04")
    if p_metrics:
        placebo = p_metrics.get("placebo_p", np.nan)

    w = contract.StudyWriter(city, MODULE, SLUG, f"{cfg['name']}市{TITLE}")
    if len(loo):
        w.save_table(loo, f"{MODULE}_a01_trend_loo.csv")
    if len(cmp):
        w.save_table(cmp, f"{MODULE}_a02_ar_comparison.csv")
    summary = pd.DataFrame([
        {"check": "A01 趋势 LOO 符号一致率(中位)",
         "value": float(loo["loo_sign_consistency"].median()) if len(loo) else np.nan},
        {"check": "A02 原始p<0.05计数(含AR)", "value": n_w},
        {"check": "A02 原始p<0.05计数(不含AR)", "value": n_no},
        {"check": "A04 安慰剂 p", "value": placebo},
    ])
    w.save_table(summary, f"{MODULE}_robustness_summary.csv")
    fig = _fig(cfg["name"], loo, cmp)
    w.save_fig(fig, f"{MODULE}_robustness.png")
    sign_med = float(loo["loo_sign_consistency"].median()) if len(loo) else np.nan
    metrics = {"city": city, "n_crops": len(pool),
               "a01_loo_sign_consistency_median": sign_med,
               "a02_sig_with_ar": n_w, "a02_sig_no_ar": n_no, "a04_placebo_p": placebo}
    w.dump_metrics(f"{MODULE}_summary.json", metrics)

    abstract = (
        f"本研究对{cfg['name']}的主要估计做稳健性检验，不新增研究问题。"
        f"包括：（1）A01 趋势的留一年法（LOO）符号一致性；（2）A02 主效应在「含自回归」与"
        f"「不含自回归」下的显著数对比；（3）引用 A04 安慰剂 p。"
        f"A01 趋势 LOO 符号一致率中位 {sign_med:.2f}；A02 原始 p<0.05 计数：含自回归 {n_w} 项、不含自回归 {n_no} 项。\n\n"
        f"**关键词**：稳健性；留一年法；自相关控制；安慰剂；{cfg['name']}"
    )
    frontend_summary = (f"{cfg['name']}：A01 趋势 LOO 符号一致率中位 {sign_med:.2f}；"
                        f"A02 含/不含 AR 显著数 {n_w}/{n_no}。")
    data_scope = (f"### 2.1 对象\n{cfg['name']} A01/A02/A04 的关键估计。\n\n"
                  f"### 2.2 方法\nLOO 重估、含/不含 AR 对照、安慰剂 p。")
    methods = ("### 3.1 趋势稳健性\n逐作物留一年重估趋势，计算符号与显著性稳定度。\n\n"
               "### 3.2 自相关控制\n对比 z_t = α + φ·z_(t-1) + β·w 与 z_t = α + β·w 的显著数。\n\n"
               "### 3.3 安慰剂\n引用 A04 的随机窗口安慰剂 p。")
    results_text = [
        ("A01 趋势稳健性", f"LOO 符号一致率中位 **{sign_med:.2f}**；"
                           f"（表 {MODULE}_a01_trend_loo.csv）"),
        ("A02 自相关控制", f"原始 p<0.05 计数：含自回归 **{n_w}** 项，不含自回归 **{n_no}** 项。"
                           f"方向{'为不含自回归时更多（提示遗漏自相关易致过度显著）' if n_no > n_w else ('为含自回归时更多' if n_w > n_no else '两者相同')}；"
                           f"本城结果只反映该样本，不与沈阳结论直接等同。"
                           f"（表 {MODULE}_a02_ar_comparison.csv）"),
        ("A04 安慰剂", f"事件响应安慰剂 p = {placebo}。"),
    ]
    discussion = ("稳健性检验显示：趋势估计对单年扰动的敏感度见 LOO 符号一致率（越接近 1 越稳健）。"
                  "A02 含/不含自回归的显著计数差异方向在本城为"
                  f"{'不含自回归更多' if n_no > n_w else ('含自回归更多' if n_w > n_no else '两者相同')}——"
                  "该差异只说明自相关控制会改变推断结果，方向并不在各城市保持一致；"
                  "因此主分析统一保留 AR(1) 控制仅作为预注册口径，不代表经验上总是更保守。")
    limitations = ["1. **仅覆盖 A01/A02/A04**：A03/A05/A06 的稳健性未逐一展开。",
                   "2. **LOO 非全模型**：仅对趋势作留一年。", "3. **少样本**：LOO 年数有限。"]
    conclusion = (f"{cfg['name']}稳健性：A01 趋势 LOO 符号一致率中位 {sign_med:.2f}；"
                  f"A02 原始 p<0.05 计数含/不含自回归为 {n_w}/{n_no}。"
                  f"自相关控制会改变推断结果，但改变方向在不同城市并不一致，故不据此断言「控制后更保守」。")
    explorer = {
        "selectors": [{"key": "check", "label": "检验", "options": summary["check"].tolist()}],
        "metrics": ["a01_loo_sign_consistency_median", "a02_sig_with_ar", "a02_sig_no_ar"],
        "series": [{"id": "loo", "table": f"{MODULE}_a01_trend_loo.csv", "x": "crop",
                    "y": "loo_sign_consistency"}],
        "tables": [f"{MODULE}_a01_trend_loo.csv", f"{MODULE}_a02_ar_comparison.csv",
                   f"{MODULE}_robustness_summary.csv"],
        "figures": [f"{MODULE}_robustness.png"], "sources": [],
        "methodology": methods, "limitations": limitations,
    }
    return emit.emit_study(
        city=city, module=MODULE, slug=SLUG, title=f"{cfg['name']}市{TITLE}",
        abstract=abstract, frontend_summary=frontend_summary,
        keywords=["稳健性", "留一年法", "自相关", "安慰剂", cfg["name"]],
        research_questions=[f"{cfg['name']}主要估计在方法扰动下是否稳健？"],
        data_scope=data_scope, methods=methods, results=results_text, discussion=discussion,
        limitations=limitations, conclusion=conclusion, explorer=explorer,
        tables=[f"{MODULE}_a01_trend_loo.csv", f"{MODULE}_a02_ar_comparison.csv",
                f"{MODULE}_robustness_summary.csv"],
        figures=[f"{MODULE}_robustness.png"],
        claims=[{"claim_id": f"{city}-A08-C1", "study_id": "A08", "city": cfg["name"],
                 "claim_text": f"A01 趋势 LOO 符号一致率中位 {sign_med:.2f}；A02 含/不含 AR 显著 {n_w}/{n_no}",
                 "claim_type": "robustness", "table_id": f"{MODULE}_robustness_summary.csv",
                 "estimate": sign_med, "status": "SUPPORTED"}])


def paths_metrics(city: str, module: str):
    import json
    from ..lib import paths
    p = paths.RESEARCH / city / module / "metrics" / f"{module}_summary.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return None
    return None


def _fig(city_name, loo, cmp):
    from ..lib.plotting import setup_plt, C_MAIN, C_ALT
    plt = setup_plt()
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))
    if len(loo):
        axes[0].bar(loo["crop"], loo["loo_sign_consistency"], color=C_MAIN)
        axes[0].set_ylabel("LOO 符号一致率"); axes[0].tick_params(axis="x", rotation=45)
        axes[0].set_title("A01 趋势稳健性")
    if len(cmp):
        axes[1].bar(["含AR", "不含AR"], [int(cmp["sig_with_ar"].sum()), int(cmp["sig_no_ar"].sum())],
                    color=[C_MAIN, C_ALT])
        axes[1].set_ylabel("显著项数"); axes[1].set_title("A02 自相关控制的影响")
    fig.suptitle(f"{city_name}市 稳健性检验")
    return fig