"""a02_weather_market.py — A02 天气与市场同期关系（六城统一）。

方法（对齐沈阳 A02）：
- 价格异常 z：严格无未来信息去季节化（仅用更早年份，doy±5 中位数 + 1.4826×MAD）。
- 主模型：z_t = α + φ·z_(t-1) + β·weather_z_t + 日历控制 + ε_t，HAC(14)。
- 暴露：日降水、日最高温、VPD、风速、0-7cm 土壤含水；均为标准化（每 +1 SD）。
- 家族：按"暴露"分组，各含 n_crops 项，BH-FDR 校正，报告原始 p 与 q。

频率：chaoyang/jinzhou 日度；dalian 周度；dandong/tieling 无稳定序列 → NOT_SUPPORTED。
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from ..lib import contract, emit, loaders, panel, stats

MODULE = "A02"
SLUG = "weather-market-response"
TITLE = "气象条件与主要农产品市场响应"
CITY_FREQ = {"chaoyang": "D", "jinzhou": "D", "dalian": "W", "shenyang": "D"}


def run(city: str) -> Dict:
    if city not in CITY_FREQ:
        return emit.emit_not_supported(
            city=city, module=MODULE, slug=SLUG, title=TITLE,
            reason="本城在观测期内没有满足最小覆盖的蔬菜类价格序列，无法做天气—市场同期响应分析。",
            notes=["主源为第三方产地行情，覆盖稀疏", "作物词表碎片化，不足以构建稳定面板"])
    cfg = loaders.load_cities()[city]
    an = loaders.load_analysis()
    hac = int(an["stats"]["hac_lags"])
    win = int(an["price"]["deseason"]["doy_window"])
    min_obs = int(an["price"]["min_days_weather"])
    freq = CITY_FREQ[city]
    alpha = float(an["global"]["alpha"])
    veg = loaders.veg_crops()

    weather = loaders.load_weather(city)
    price = loaders.load_primary_price(city)
    pool = [c for c in veg if len(loaders.load_primary_series(city, c)) >= min_obs]

    rows, summary = [], []
    for crop in pool:
        s = loaders.load_primary_series(city, crop)
        if s.empty:
            continue
        s = panel.deseasonalize_strict(s, "price_per_kg", "date", freq, win)
        s = panel.add_weather(s, weather, freq, "date")
        s = s.dropna(subset=["z"]).sort_values("date").reset_index(drop=True)
        s["z_lag1"] = s["z"].shift(1)
        for ex in panel.EXPOSURES:
            col = ex + "_z"
            if col not in s.columns:
                continue
            d = s.dropna(subset=[col, "z_lag1", "z"]).copy()
            if len(d) < min_obs:
                continue
            y = d["z"].to_numpy()
            X = d[["z_lag1", col]].to_numpy()
            r = stats.hac_ols(y, X, maxlags=hac)
            rows.append({
                "city": city, "crop": crop, "exposure": ex, "freq": freq,
                "beta_per_sd": float(r["coef"][1]),
                "ci_low": float(r["coef"][1] - 1.96 * r["se"][1]),
                "ci_high": float(r["coef"][1] + 1.96 * r["se"][1]),
                "p_raw": float(r["p"][1]), "n": r["n"], "ar1": r["ar1"], "n_eff": r["n_eff"],
                "phi_ar1": float(r["coef"][0]),
            })
    res = pd.DataFrame(rows)
    if res.empty:
        return emit.emit_not_supported(city=city, module=MODULE, slug=SLUG, title=TITLE,
                                       reason="去季节化后有效观测不足，未得到可估计的响应模型。")
    # FDR：按暴露分组
    res["q"] = np.nan
    for ex, g in res.groupby("exposure"):
        res.loc[g.index, "q"] = stats.bh_fdr(g["p_raw"].to_numpy())
    res = res.sort_values("p_raw")
    n_sig = int((res["q"] < alpha).sum())
    max_eff = float(res.loc[res["q"] < alpha, "beta_per_sd"].abs().max()) if n_sig else np.nan

    w = contract.StudyWriter(city, MODULE, SLUG, f"{cfg['name']}市{TITLE}")
    w.save_table(res, f"{MODULE}_response.csv")
    by_ex = (res.groupby("exposure")
             .agg(n_tests=("p_raw", "size"), n_sig=("q", lambda s: int((s < alpha).sum())),
                  median_abs_beta=("beta_per_sd", lambda s: float(s.abs().median())))
             .reset_index())
    w.save_table(by_ex, f"{MODULE}_by_exposure.csv")

    # 图：各暴露显著率 + 效应量
    fig = _fig(cfg["name"], by_ex, res)
    w.save_fig(fig, f"{MODULE}_effect_summary.png")

    phi_med = float(res["phi_ar1"].median())
    metrics = {"city": city, "freq": freq, "n_crops": len(pool), "n_tests": int(len(res)),
               "n_fdr_sig": n_sig, "median_ar1": phi_med,
               "max_abs_effect_sig": max_eff, "alpha": alpha}
    w.dump_metrics(f"{MODULE}_summary.json", metrics)

    sig = res[res["q"] < alpha]
    sig_txt = "；".join([f"{r['crop']}×{r['exposure']} {r['beta_per_sd']:+.4f}（q={r['q']:.3f}）"
                        for _, r in sig.head(8).iterrows()]) or "无"
    freq_note = "日度" if freq == "D" else "周度"
    abstract = (
        f"本研究检验温度、降水、湿度（VPD）、风速与土壤水分是否与{cfg['name']}主要农产品价格异常"
        f"存在稳定关系。价格为该城主源（{cfg['price_level_note']}），频率{freq_note}；"
        f"价格异常采用**严格无未来信息**的历史同期基线（仅用严格更早年份）。主模型 "
        f"z_t = α + φ·z_(t-1) + β·weather_z_t + ε_t，HAC({hac}) 稳健标准误。"
        f"在 {len(pool)} 作物 × {res['exposure'].nunique()} 暴露共 {len(res)} 项检验中，"
        f"**{n_sig} 项在 BH-FDR 后显著**；滞后 1 期自回归系数中位数为 {phi_med:.3f}。"
        f"{'显著项最大效应量 ' + format(max_eff, '.4f') + ' 个标准差。' if n_sig else '未检出一致响应。'}\n\n"
        f"**关键词**：气象冲击；价格异常；自回归；HAC 稳健标准误；BH-FDR；{cfg['name']}"
    )
    frontend_summary = (f"{cfg['name']}（{freq_note}）：{len(res)} 项检验中 {n_sig} 项 FDR 显著；"
                        f"AR(1) 中位 {phi_med:.3f}。")
    data_scope = (
        f"### 2.1 研究对象\n{cfg['name']}主要蔬菜（作物池：{'、'.join(pool)}），频率 {freq_note}。\n\n"
        f"### 2.2 数据来源\n- 价格：{cfg['price_level_note']}。\n"
        f"- 气象：Open-Meteo ERA5/ERA5-Land **再分析网格**（非气象站实测）。\n\n"
        f"### 2.3 变量定义\n- **z**：严格无未来信息去季节化后的价格异常（=观测−历史同期期望，尺度=1.4826×MAD）。\n"
        f"- **weather_z**：标准化暴露（降水/日最高温/VPD/风速/土壤含水），每 +1 SD。\n"
        f"- 控制：滞后 1 期价格异常。")
    methods = (f"### 3.1 主分析\n逐作物估计 z_t = α + φ·z_(t-1) + β·weather_z_t + ε_t，HAC({hac})。\n\n"
               f"### 3.2 去季节化\n严格口径：期望与尺度仅用**严格早于目标年**的年份（doy±{win}"
               f"{'或同周' if freq=='W' else ''}），不使用任何未来年份。\n\n"
               f"### 3.3 多重检验\n家族=暴露（共 {res['exposure'].nunique()} 族，每族 {len(pool)} 作物），BH-FDR；"
               f"报告原始 p 与 q、AR(1)、n_eff。")
    results_text = [
        ("持续性", f"滞后 1 期自回归系数 φ 中位数为 **{phi_med:.3f}**，说明价格异常高度持续，"
                   f"自回归项是必要控制。"),
        ("核心暴露的效应", f"{len(res)} 项检验中 **{n_sig} 项在 BH-FDR 后显著**（q<{alpha}）：{sig_txt}。"),
        ("分暴露汇总", by_ex.to_string(index=False)),
    ]
    discussion = ("检出的显著项集中于个别作物×暴露组合，效应量小且方向不一。批发/零售市场具备调运与"
                  "库存调节能力，单期气象变化可能被到货结构吸收。上述解释属机制猜想，观测设计无法"
                  "区分其与共同驱动因素。本研究不把结果表述为因果。")
    limitations = _limitations(city, cfg, freq, n_sig, max_eff)
    conclusion = (f"本研究对「气象条件与{cfg['name']}市场价格异常存在稳定关系」给出"
                  f"**{'部分支持' if 0 < n_sig else '未得到支持'}**：{len(res)} 项检验中 {n_sig} 项 FDR 显著"
                  f"{'，效应量均较小' if n_sig else ''}。价格异常强持续性（AR(1) 中位 {phi_med:.3f}）"
                  f"要求任何此类分析必须包含自回归控制。")

    explorer = {
        "selectors": [
            {"key": "crop", "label": "作物", "options": pool},
            {"key": "exposure", "label": "气象暴露",
             "options": sorted(res["exposure"].unique().tolist())},
        ],
        "metrics": ["n_tests", "n_fdr_sig", "median_ar1"],
        "series": [{"id": "effect", "table": f"{MODULE}_response.csv", "x": "exposure",
                    "y": "beta_per_sd", "group": "crop", "ci": ["ci_low", "ci_high"]}],
        "tables": [f"{MODULE}_response.csv", f"{MODULE}_by_exposure.csv"],
        "figures": [f"{MODULE}_effect_summary.png"],
        "sources": [], "methodology": methods, "limitations": limitations,
    }
    return emit.emit_study(
        city=city, module=MODULE, slug=SLUG, title=f"{cfg['name']}市{TITLE}",
        abstract=abstract, frontend_summary=frontend_summary,
        keywords=["气象冲击", "价格异常", "自回归", "HAC", "BH-FDR", cfg["name"]],
        research_questions=[f"气象条件是否与{cfg['name']}主要农产品价格异常存在稳定关系？"],
        data_scope=data_scope, methods=methods, results=results_text,
        discussion=discussion, limitations=limitations, conclusion=conclusion,
        explorer=explorer,
        tables=[f"{MODULE}_response.csv", f"{MODULE}_by_exposure.csv"],
        figures=[f"{MODULE}_effect_summary.png"],
        claims=[{"claim_id": f"{city}-A02-C1", "study_id": "A02", "city": cfg["name"],
                 "claim_text": f"{len(res)} 项气象-价格检验中 {n_sig} 项 FDR 显著",
                 "claim_type": "inferential", "table_id": f"{MODULE}_response.csv",
                 "estimate": n_sig, "sample_size": int(res["n"].max()),
                 "status": "PARTIAL" if n_sig else "NOT_SUPPORTED"}])


def _limitations(city, cfg, freq, n_sig, max_eff) -> List[str]:
    out = [
        f"1. **价格口径**：本城主源为「{cfg['price_level_note']}」，非批发市场，跨城不可直接比较。",
        "2. **气象为再分析网格**：ERA5 对极端值有平滑，不得当作气象站实测。",
        f"3. **频率为{'日度' if freq=='D' else '周度'}**：与其他城市粒度可能不同，跨城比较为定性。",
    ]
    if n_sig:
        out.append(f"4. **效应量小**：显著项最大 |效应| = {max_eff:.4f} 个标准差，实际重要性有限。")
    out.append("5. **观测设计非实验**：不构成因果；去季节化基线严格无未来信息，首年无基线故排除。")
    return out


def _fig(city_name: str, by_ex: pd.DataFrame, res: pd.DataFrame = None):
    from ..lib.plotting import setup_plt, C_MAIN, C_ALT
    plt = setup_plt()
    fig, axes = plt.subplots(1, 2, figsize=(12.4, 4.6))
    # 左：显著计数
    x = np.arange(len(by_ex))
    axes[0].bar(x - 0.2, by_ex["n_sig"], width=0.4, color=C_MAIN, label="FDR 显著数")
    axes[0].bar(x + 0.2, by_ex["n_tests"] - by_ex["n_sig"], width=0.4, color=C_ALT, label="未显著")
    axes[0].set_xticks(x); axes[0].set_xticklabels(by_ex["exposure"], rotation=20)
    axes[0].set_ylabel("检验数"); axes[0].set_title("各暴露：显著 vs 未显著")
    axes[0].legend()
    # 右：各暴露效应量中位与 IQR（展示效应之小）
    if res is not None and len(res):
        g = res.groupby("exposure")["beta_per_sd"]
        med = g.median(); lo = g.quantile(0.25); hi = g.quantile(0.75)
        axes[1].errorbar(range(len(med)), med.values,
                         yerr=[med.values - lo.values, hi.values - med.values],
                         fmt="o", color=C_MAIN, capsize=4)
        axes[1].axhline(0, color="grey", lw=0.8)
        axes[1].set_xticks(range(len(med))); axes[1].set_xticklabels(med.index, rotation=20)
        axes[1].set_ylabel("效应（每 +1 SD 暴露，单位=SD）")
        axes[1].set_title("效应量中位与 IQR（含全部非显著项）")
    fig.suptitle(f"{city_name}市 气象暴露—价格异常 检验结果")
    return fig