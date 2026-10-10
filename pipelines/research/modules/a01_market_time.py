"""a01_market_time.py — A01 市场价格时间结构与季节性（六城统一方法）。

对每个城市：
- 取该城主源价格（primary_sources），作物经 crop_raw→crop_std 标准化；
- 作物池 = 蔬菜类 且 观测天数 >= min_days_a01；
- 计算月度分布、季节指数与幅度、年度水平、长期趋势（log 价格 ~ t，HAC(14)）、AR(1)、STL 强度；
- 趋势检验家族 n=作物池大小，BH-FDR 校正；
- 产出 tables/figures/metrics/article.json/report.md + 证据链。

数据不支持时（作物池为空）写出 NOT_SUPPORTED_BY_CURRENT_DATA 结论，不强行分析。
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from ..lib import loaders, stats, paths
from ..lib.contract import StudyWriter

MODULE = "A01"
SLUG = "market-time-seasonality"
TITLE = "主要农产品价格的时间结构与季节性特征"


def _trend(series: pd.DataFrame, hac_lags: int) -> Dict:
    """log(price) ~ t（年），HAC 稳健标准误。"""
    d = series.dropna(subset=["price_per_kg"])
    d = d[d["price_per_kg"] > 0]
    if len(d) < 30:
        return {}
    t = (d["date"] - d["date"].min()).dt.days.to_numpy() / 365.25
    y = np.log(d["price_per_kg"].to_numpy())
    r = stats.hac_ols(y, t, maxlags=hac_lags)
    # 年化 % 变化
    coef = float(r["coef"][0]); se = float(r["se"][0])
    return {"ann_pct": 100.0 * (np.exp(coef) - 1.0), "coef": coef, "se": se,
            "ci_low_ann": 100.0 * (np.exp(coef - 1.96 * se) - 1.0),
            "ci_high_ann": 100.0 * (np.exp(coef + 1.96 * se) - 1.0),
            "p": float(r["p"][0]), "r2": r["r2"], "n": r["n"], "ar1": r["ar1"], "n_eff": r["n_eff"]}


def run(city: str) -> Dict:
    cfg = loaders.load_cities()[city]
    an = loaders.load_analysis()
    hac_lags = int(an["stats"]["hac_lags"])
    min_days = int(an["price"]["min_days_a01"])
    veg = loaders.veg_crops()

    price = loaders.load_primary_price(city)
    w = StudyWriter(city, MODULE, SLUG, f"{cfg['name']}市{TITLE}")

    # 作物池
    pool = []
    for crop in veg:
        s = loaders.load_primary_series(city, crop)
        if len(s) >= min_days:
            pool.append(crop)

    if not pool:
        return _not_supported(city, cfg, price, w)

    monthly_rows, si_rows, amp_rows, trend_rows, stl_rows, summary = [], [], [], [], [], []
    for crop in pool:
        s = loaders.load_primary_series(city, crop)
        # 月度中位数与分位
        g = s.set_index("date")["price_per_kg"]
        mo = g.resample("MS").agg(["median", lambda x: x.quantile(0.1), lambda x: x.quantile(0.9), "count"])
        mo.columns = ["median", "p10", "p90", "n"]
        for d, row in mo.iterrows():
            monthly_rows.append({"crop": crop, "month": d.strftime("%Y-%m"), "median": row["median"],
                                 "p10": row["p10"], "p90": row["p90"], "n": int(row["n"])})
        # 季节指数
        si = stats.seasonal_index(s["date"], s["price_per_kg"], freq="month")
        for _, row in si.iterrows():
            si_rows.append({"crop": crop, "month": int(row["period"]), "seasonal_index": row["index"],
                            "mean_price": row["mean"], "n": int(row["count"])})
        amp = float(si["index"].max() - si["index"].min()) if len(si) else np.nan
        amp_rows.append({"crop": crop, "seasonal_amplitude": amp,
                         "si_max": float(si["index"].max()) if len(si) else np.nan,
                         "si_min": float(si["index"].min()) if len(si) else np.nan,
                         "peak_month": int(si.loc[si["index"].idxmax(), "period"]) if len(si) else None,
                         "trough_month": int(si.loc[si["index"].idxmin(), "period"]) if len(si) else None})
        # 趋势
        tr = _trend(s, hac_lags)
        if tr:
            trend_rows.append({"crop": crop, **tr})
        # STL
        wk = s.set_index("date")["price_per_kg"].resample("W").median()
        st = stats.stl_strength(wk, period=int(an["stats"]["stl_period_weekly"]),
                                robust=bool(an["stats"]["stl_robust"]))
        stl_rows.append({"crop": crop, **st})
        summary.append({"crop": crop, "n_days": int(len(s)),
                        "price_median": float(s["price_per_kg"].median()),
                        "seasonal_amplitude": amp})

    trend_df = pd.DataFrame(trend_rows)
    if len(trend_df):
        trend_df["q"] = stats.bh_fdr(trend_df["p"].to_numpy())
        trend_df = trend_df.sort_values("p")
        n_sig = int((trend_df["q"] < float(an["global"]["alpha"])).sum())
    else:
        n_sig = 0

    # 保存
    w.save_table(pd.DataFrame(monthly_rows), f"{MODULE}_monthly.csv")
    w.save_table(pd.DataFrame(si_rows), f"{MODULE}_seasonal_index.csv")
    amp_df = pd.DataFrame(amp_rows).sort_values("seasonal_amplitude", ascending=False)
    w.save_table(amp_df, f"{MODULE}_seasonal_amplitude.csv")
    w.save_table(trend_df, f"{MODULE}_trend.csv")
    w.save_table(pd.DataFrame(stl_rows), f"{MODULE}_stl_strength.csv")

    # 图：季节幅度
    fig = _fig_amplitude(cfg["name"], amp_df)
    w.save_fig(fig, f"{MODULE}_seasonal_amplitude.png")

    median_amp = float(amp_df["seasonal_amplitude"].median()) if len(amp_df) else np.nan
    metrics = {"city": city, "n_crops": len(pool), "crops": pool,
               "median_seasonal_amplitude": median_amp,
               "n_trend_tests": int(len(trend_df)), "n_trend_fdr_sig": n_sig,
               "alpha": float(an["global"]["alpha"])}
    w.dump_metrics(f"{MODULE}_summary.json", metrics)

    _write_article(city, cfg, w, pool, amp_df, trend_df, metrics, n_sig)

    # 证据链
    claims = []
    if len(amp_df):
        top = amp_df.iloc[0]
        claims.append({"claim_id": f"{city}-A01-C1", "study_id": "A01", "city": cfg["name"],
                       "claim_text": f"价格季节指数极差中位数 {median_amp:.3f}（最强 {top['crop']} {top['seasonal_amplitude']:.3f}）",
                       "claim_type": "descriptive", "table_id": f"{MODULE}_seasonal_amplitude.csv",
                       "estimate": median_amp, "sample_size": int(summary[0]["n_days"]) if summary else "",
                       "status": "SUPPORTED"})
    if len(trend_df):
        nt = int(len(trend_df))
        claims.append({"claim_id": f"{city}-A01-C2", "study_id": "A01", "city": cfg["name"],
                       "claim_text": f"{nt} 项趋势检验中 {n_sig} 项 FDR 显著",
                       "claim_type": "inferential", "table_id": f"{MODULE}_trend.csv",
                       "estimate": n_sig, "p_adjusted": "", "sample_size": nt,
                       "status": "PARTIAL" if n_sig < nt else "SUPPORTED"})
    w.append_claims(claims)
    return metrics


def _fig_amplitude(city_name: str, amp_df: pd.DataFrame):
    from ..lib.plotting import setup_plt, FIGSIZE, C_MAIN
    plt = setup_plt()
    fig, ax = plt.subplots(figsize=(max(7.6, 0.5 * len(amp_df) + 3), 4.6))
    ax.bar(amp_df["crop"], amp_df["seasonal_amplitude"], color=C_MAIN)
    ax.set_ylabel("季节指数极差")
    ax.set_title(f"{city_name}市主要农产品价格季节幅度（月季节指数 max-min）")
    ax.tick_params(axis="x", rotation=45)
    return fig


def _write_article(city, cfg, w: StudyWriter, pool, amp_df, trend_df, metrics, n_sig):
    an = loaders.load_analysis()
    from ..lib import contract
    registry = contract.build_source_registry(city)
    src_ids = contract.article_source_ids(city, registry)

    price = loaders.load_primary_price(city)
    dmin = str(price["date"].min().date())
    dmax = str(price["date"].max().date())
    n_obs = len(price)
    from ..lib import panel as panel_lib
    _freq = panel_lib.detect_freq(price)
    freq_word = "日度" if _freq == "D" else "周度"
    unit_word = "观测日" if _freq == "D" else "观测周"
    median_amp = metrics["median_seasonal_amplitude"]
    alpha = float(an["global"]["alpha"])

    top3 = amp_df.head(3)[["crop", "seasonal_amplitude", "peak_month", "trough_month"]].to_dict("records")
    top3_txt = "；".join([f"{r['crop']} {r['seasonal_amplitude']:.3f}（峰值 {int(r['peak_month'])} 月）" for r in top3])
    if len(trend_df):
        sig = trend_df[trend_df["q"] < alpha]
        sig_txt = "、".join([f"{r['crop']} {r['ann_pct']:+.2f}%/年（q={r['q']:.3f}）" for _, r in sig.iterrows()]) or "无"
    else:
        sig_txt = "无（样本不足）"

    abstract = (
        f"本研究回答{cfg['name']}市主要农产品价格如何随时间变化、是否存在季节性与长期趋势。"
        f"数据为该城主价格来源（{cfg['price_level_note']}）的{freq_word}价格，经标准化后进入分析；"
        f"研究窗口 {dmin} 至 {dmax}，主源价格观测 {n_obs} 条，进入作物池的蔬菜类作物 {len(pool)} 种"
        f"（每种 ≥{an['price']['min_days_a01']} 个{unit_word}）。方法包括月度中位数与 P10/P90、季节指数"
        f"（月均值/全期均值）与季节幅度、对数价格对时间趋势的 HAC(14) 回归，以及 STL 稳健分解对照。"
        f"结果显示：价格季节指数极差的中位数为 {median_amp:.3f}（最强：{top3_txt}）；"
        f"{len(trend_df)} 项趋势检验中 {n_sig} 项在 BH-FDR 后显著（{sig_txt}）。\n\n"
        f"**关键词**：价格季节性；长期趋势；HAC 稳健标准误；BH-FDR；{cfg['name']}"
    )
    frontend_summary = (
        f"{cfg['name']} {len(pool)} 种蔬菜价格季节指数极差中位 {median_amp:.3f}；"
        f"{len(trend_df)} 项趋势检验中 {n_sig} 项 FDR 显著。口径：{cfg['price_level_note']}。"
    )
    data_scope = (
        f"### 2.1 研究对象\n{cfg['name']}市主要农产品（蔬菜类）价格。作物池：{'、'.join(pool)}。\n\n"
        f"### 2.2 数据来源\n主价格来源：{cfg['price_level_note']}（详见 sources/source_registry.csv）。"
        f"原始作物字段为 crop_raw，经受控映射进入 crop_std；不使用原 crop_standard 字段。\n\n"
        f"### 2.3 变量定义\n- **price_per_kg**：统一为元/公斤。\n"
        f"- **seasonal_index**：某月均值 / 全期均值。\n"
        f"- **seasonal_amplitude**：季节指数最大值 − 最小值。\n"
        f"- **频率**：{freq_word}（由主源采样间隔判定）。研究窗口 {dmin} ~ {dmax}。"
    )
    methods = (
        f"### 3.1 主分析\n1. 月度中位数与 P10/P90（表 {MODULE}_monthly.csv）。\n"
        f"2. 季节指数与幅度（表 {MODULE}_seasonal_index.csv、{MODULE}_seasonal_amplitude.csv）。\n"
        f"3. 长期趋势：log(price) ~ t（年），Newey-West/HAC({an['stats']['hac_lags']}) 稳健标准误。\n\n"
        f"### 3.2 稳健性\nSTL 稳健分解（周粒度、period={an['stats']['stl_period_weekly']}）计算季节/趋势强度作为独立对照"
        f"（含全序列，仅描述性）。\n\n"
        f"### 3.3 多重检验\n趋势检验家族 = 作物池（{len(trend_df)} 项），BH-FDR 校正，同时报告原始 p 与 q；"
        f"并报告各序列 AR(1) 与 n_eff。"
    )
    sections = [
        {"title": "研究问题与背景",
         "content": f"理解{cfg['name']}主要农产品价格的时间结构，是判断市场是否存在结构性变化、"
                    f"以及后续气象影响分析是否需要控制季节性的前提。本研究提出：价格是否具有季节性？"
                    f"是否存在长期趋势？幅度多大？需要说明边界：不同城市价格层级不同"
                    f"（本城口径：{cfg['price_level_note']}），本研究不做跨城价格水平比较。"},
        {"title": "数据与变量", "content": data_scope},
        {"title": "研究方法", "content": methods},
        {"title": "研究结果",
         "content": f"### 4.1 季节性\n价格季节指数极差中位数为 **{median_amp:.3f}**；幅度最大的作物为 {top3_txt}。"
                    f"（表 {MODULE}_seasonal_amplitude.csv，图 {MODULE}_seasonal_amplitude.png）\n\n"
                    f"### 4.2 长期趋势\n{len(trend_df)} 项趋势检验中 **{n_sig} 项在 BH-FDR 后显著**：{sig_txt}。"
                    f"（表 {MODULE}_trend.csv）\n\n"
                    f"### 4.3 分布与持续性\n各作物价格水平与离散程度见月度表；AR(1) 见趋势表。"},
        {"title": "讨论",
         "content": f"价格季节波动反映蔬菜上市季节与产地转换周期。本城的季节幅度与显著趋势项需结合"
                    f"口径（{cfg['price_level_note']}）解读；机制性解释属猜想，本研究数据无法区分其相对贡献。"},
        {"title": "研究局限",
         "content": _limitations(city, cfg, n_obs, len(pool))},
        {"title": "结论",
         "content": f"在 {dmin}~{dmax} 观测期内，{cfg['name']}主要蔬菜价格季节指数极差中位数为 {median_amp:.3f}；"
                    f"{len(trend_df)} 项趋势检验中 {n_sig} 项 FDR 显著。上述结果仅描述本城在观测期内、"
                    f"本口径（{cfg['price_level_note']}）下的价格结构，不构成对供给结构或本地生产的推断。"},
    ]
    limitations = _limitations(city, cfg, n_obs, len(pool)).split("\n")
    limitations = [l for l in limitations if l.strip()]

    explorer = {
        "selectors": [
            {"key": "crop", "label": "作物", "options": pool},
            {"key": "period", "label": "时间范围", "options": ["全部", "近1年", "近3年"]},
            {"key": "metric", "label": "指标", "options": ["价格中位数", "季节指数", "P10/P90"]},
        ],
        "metrics": ["median_seasonal_amplitude", "n_trend_tests", "n_trend_fdr_sig"],
        "series": [{"id": "monthly_price", "table": f"{MODULE}_monthly.csv", "x": "month", "y": "median",
                    "group": "crop"}],
        "tables": w.tables,
        "figures": w.figures,
        "sources": src_ids,
        "methodology": "log 价格对时间趋势 HAC(14) 回归；季节指数=月均值/全期均值；STL 稳健分解对照；BH-FDR。",
        "limitations": limitations,
    }

    w.write_article(abstract=abstract, frontend_summary=frontend_summary,
                    keywords=["价格季节性", "长期趋势", "HAC 稳健标准误", "BH-FDR", cfg["name"]],
                    research_questions=[f"{cfg['name']}主要农产品价格是否存在季节性与长期趋势？幅度多大？"],
                    data_scope=data_scope, methods=methods, sections=sections,
                    limitations=limitations, conclusion=sections[-1]["content"],
                    source_ids=src_ids, explorer=explorer, status="DRAFT")
    w.write_report(_report_md(w.title, abstract, sections, limitations, src_ids))


def _limitations(city, cfg, n_obs, n_pool) -> str:
    lines = [
        f"1. **价格口径非批发市场**：本城主源为「{cfg['price_level_note']}」，与其他城市层级不可直接比较。",
        "2. **观测期跨度有限**：趋势估计在强自相关（AR(1) 高）条件下对样本区间敏感。",
        "3. **STL 含全序列**：仅作描述性对照，不作为无未来信息口径。",
        "4. **作物标准化边界**：仅对受控映射内的作物分析，未纳入作物不做推断。",
    ]
    if n_pool < 5:
        lines.append(f"5. **可用作物少**：进入作物池仅 {n_pool} 种，季节性结论的稳健性受限。")
    return "\n".join(lines)


def _report_md(title, abstract, sections, limitations, src_ids) -> str:
    parts = [f"# {title}", "", "## 摘要", "", abstract.split("**关键词**")[0].strip(), ""]
    for s in sections:
        parts.append(f"## {s['title']}")
        parts.append("")
        parts.append(s["content"])
        parts.append("")
    parts.append("## 数据来源")
    parts.append("")
    parts.append("来源登记见 `sources/source_registry.csv`：" + "、".join(src_ids))
    return "\n".join(parts)


def _not_supported(city, cfg, price, w: StudyWriter) -> Dict:
    from ..lib import contract
    registry = contract.build_source_registry(city)
    src_ids = contract.article_source_ids(city, registry)
    note = ("本城主价格来源在观测期内**没有**满足最小覆盖阈值的蔬菜类日度/周度序列，"
            "无法进行价格时间结构与季节性分析。")
    sections = [
        {"title": "研究问题与背景", "content": f"拟研究{cfg['name']}主要农产品价格的时间结构与季节性。"},
        {"title": "数据与变量", "content": f"主源：{cfg['price_level_note']}；观测 {len(price)} 条。"},
        {"title": "研究方法", "content": "因可用序列不足，未执行季节性/趋势分析。"},
        {"title": "研究结果", "content": "NOT_SUPPORTED_BY_CURRENT_DATA"},
        {"title": "讨论", "content": note},
        {"title": "研究局限", "content": "主源为第三方产地行情，覆盖稀疏、作物词表碎片化。"},
        {"title": "结论", "content": "NOT_SUPPORTED_BY_CURRENT_DATA"},
    ]
    w.dump_metrics(f"{MODULE}_summary.json", {"city": city, "status": "NOT_SUPPORTED_BY_CURRENT_DATA"})
    explorer = {"status": "NOT_SUPPORTED_BY_CURRENT_DATA", "selectors": [], "metrics": [], "series": [],
                "tables": [], "figures": [], "sources": src_ids,
                "methodology": "数据不支持，未执行分析。",
                "limitations": ["覆盖稀疏", "作物词表碎片化"], "reason": note}
    w.write_article(abstract=note, frontend_summary=f"{cfg['name']}：数据不足，A01 不成立。",
                    keywords=["数据不足", cfg["name"]], research_questions=["价格时间结构与季节性"],
                    data_scope="见 sources/source_registry.csv", methods="未执行",
                    sections=sections, limitations=["覆盖稀疏", "作物词表碎片化"],
                    conclusion="NOT_SUPPORTED_BY_CURRENT_DATA", source_ids=src_ids,
                    explorer=explorer, status="NOT_SUPPORTED")
    w.write_report(_report_md(w.title, note, sections, ["覆盖稀疏"], src_ids))
    return {"city": city, "status": "NOT_SUPPORTED_BY_CURRENT_DATA"}