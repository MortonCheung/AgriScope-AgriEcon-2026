"""cross_city.py — 跨城市研究（六城比较）。

约束（审计结论）：六城价格层级不同（wholesale/market_average/supermarket/farm_gate 混合），
**不做价格水平比较**，只做结构化/相对化与同步性分析。

包含：
1. 作物结构集中度对比（复用 A07 输出）。
2. 价格季节同步性（共有蔬菜的季节指数剖面相关）。
3. 极端天气韧性对比（复用 A04 事件/安慰剂结果）。
4. 跨城价格联动（周度对数价格的领先/滞后互相关，仅报告可检验对）。
5. 跟风种植风险 / 销售去向 → NOT_SUPPORTED（无生产—价格面板与流向数据）。
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from ..lib import contract, emit, loaders, panel, paths, stats

MODULE = "cross_city"
CITY_FREQ = {"chaoyang": "D", "jinzhou": "D", "dalian": "W", "shenyang": "D"}


def run() -> Dict:
    cities = paths.CITIES_FIVE
    names = {c: loaders.load_cities()[c]["name"] for c in cities}
    out = paths.RESEARCH / "cross_city"
    for sub in ("tables", "figures", "metrics"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    tables: List[str] = []
    figures: List[str] = []

    # 1) 生产结构集中度对比
    conc_rows = []
    for c in cities:
        j = _read_metrics(c, "A07")
        if j:
            conc_rows.append({"city": names[c], "HHI": j.get("HHI"), "CR4": j.get("CR4"),
                              "n_crops": j.get("n_crops"), "years": str(j.get("years")), "top3": j.get("top3")})
    conc = pd.DataFrame(conc_rows)
    conc.to_csv(out / "tables" / f"{MODULE}_production_concentration.csv", index=False, encoding="utf-8-sig")
    tables.append(f"{MODULE}_production_concentration.csv")

    # 2) 价格季节同步性（共有蔬菜）
    common = ["西红柿", "黄瓜", "青椒", "尖椒", "茄子", "芸豆", "土豆", "芹菜", "大白菜", "菜花", "胡萝卜"]
    prof = {}
    for c in cities:
        for crop in common:
            s = loaders.load_primary_series(c, crop)
            if len(s) < 200:
                continue
            si = stats.seasonal_index(s["date"], s["price_per_kg"], "month")
            if len(si) >= 10:
                prof[(names[c], crop)] = si.set_index("period")["index"]
    pairs = []
    keys = list(prof.keys())
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            (c1, k1), (c2, k2) = keys[i], keys[j]
            if k1 != k2 or c1 == c2:
                continue
            a, b = prof[(c1, k1)].align(prof[(c2, k2)], join="inner")
            if len(a) >= 10:
                r = float(np.corrcoef(a.values, b.values)[0, 1])
                fa = CITY_FREQ.get([k for k, v in names.items() if v == c1][0], "?")
                fb = CITY_FREQ.get([k for k, v in names.items() if v == c2][0], "?")
                pairs.append({"crop": k1, "city_a": c1, "city_b": c2, "seasonal_corr": r, "n_months": len(a),
                              "freq_a": fa, "freq_b": fb,
                              "freq_pair": "same" if fa == fb else "mixed"})
    pair_df = pd.DataFrame(pairs)
    if len(pair_df):
        pair_df.to_csv(out / "tables" / f"{MODULE}_seasonal_sync.csv", index=False, encoding="utf-8-sig")
        tables.append(f"{MODULE}_seasonal_sync.csv")
        # 仅同频率对进入主结论；混合频率对单列
        same = pair_df[pair_df["freq_pair"] == "same"]
        by_crop = (same.groupby("crop")["seasonal_corr"]
                   .agg(["mean", "count"]).reset_index().rename(columns={"mean": "mean_corr", "count": "n_pairs"}))
        by_crop.to_csv(out / "tables" / f"{MODULE}_seasonal_sync_by_crop.csv", index=False, encoding="utf-8-sig")
        tables.append(f"{MODULE}_seasonal_sync_by_crop.csv")
        mixed = (pair_df[pair_df["freq_pair"] == "mixed"].groupby("crop")["seasonal_corr"]
                 .agg(["mean", "count"]).reset_index().rename(columns={"mean": "mean_corr_mixed", "count": "n_pairs_mixed"}))
    else:
        by_crop = pd.DataFrame(); mixed = pd.DataFrame()

    # 3) 极端天气韧性对比（A04）
    res_rows = []
    for c in cities:
        j = _read_metrics(c, "A04")
        if j:
            res_rows.append({"city": names[c], "n_event_clusters": j.get("n_event_clusters"),
                             "median_post_z": j.get("median_post_z"), "placebo_p": j.get("placebo_p"),
                             "n_official_disaster": j.get("n_official_disaster")})
        else:
            res_rows.append({"city": names[c], "n_event_clusters": np.nan, "median_post_z": np.nan,
                             "placebo_p": np.nan, "n_official_disaster": np.nan})
    resil = pd.DataFrame(res_rows)
    resil.to_csv(out / "tables" / f"{MODULE}_resilience.csv", index=False, encoding="utf-8-sig")
    tables.append(f"{MODULE}_resilience.csv")

    # 4) 跨城价格联动（周度对数价格，领先/滞后互相关）
    weekly = {}
    for c in cities:
        if c not in CITY_FREQ:
            continue
        for crop in ["西红柿", "黄瓜", "青椒", "茄子", "土豆", "芹菜"]:
            s = loaders.load_primary_series(c, crop)
            if len(s) < 100:
                continue
            s = s.set_index("date")["price_per_kg"].resample("W").median()
            weekly[(names[c], crop)] = np.log(s[s > 0].dropna())
    lead = []
    wk = list(weekly.keys())
    for i in range(len(wk)):
        for j in range(i + 1, len(wk)):
            (c1, k1), (c2, k2) = wk[i], wk[j]
            if k1 != k2 or c1 == c2:
                continue
            a, b = weekly[(c1, k1)].align(weekly[(c2, k2)], join="inner")
            if len(a) < 60:
                continue
            best = None
            for L in range(-6, 7):
                x = a.shift(L)
                m = x.notna() & b.notna()
                if m.sum() < 50:
                    continue
                r = float(np.corrcoef(x[m], b[m])[0, 1])
                if best is None or abs(r) > abs(best[1]):
                    best = (L, r)
            if best:
                lead.append({"crop": k1, "city_a": c1, "city_b": c2, "best_lag_weeks": best[0],
                             "corr_at_best": best[1], "n_weeks": int(len(a))})
    leaddf = pd.DataFrame(lead)
    if len(leaddf):
        leaddf.to_csv(out / "tables" / f"{MODULE}_cross_city_lead_lag.csv", index=False, encoding="utf-8-sig")
        tables.append(f"{MODULE}_cross_city_lead_lag.csv")

    # 图
    fig = _fig(names, conc, resil, by_crop)
    from ..lib.plotting import save_fig
    save_fig(fig, out / "figures" / f"{MODULE}_overview.png")
    figures.append(f"{MODULE}_overview.png")

    # 结论文本
    conc_txt = "；".join([f"{r['city']} HHI={r['HHI']:.3f}" for _, r in conc.iterrows()]) if len(conc) else "无"
    sync_txt = ("；".join([f"{r['crop']} r̄={r['mean_corr']:.2f}({int(r['n_pairs'])}对)"
                          for _, r in by_crop.sort_values("mean_corr", ascending=False).head(5).iterrows()])
                if len(by_crop) else "无足够共有序列")
    resil_txt = ("；".join([f"{r['city']} 安慰剂p={r['placebo_p']:.2f}"
                           for _, r in resil.iterrows() if pd.notna(r["placebo_p"])]) or "无")
    lead_txt = ("；".join([f"{r['crop']} {r['city_a']}→{r['city_b']} lag={int(r['best_lag_weeks'])}w r={r['corr_at_best']:.2f}"
                          for _, r in leaddf.head(6).iterrows()]) if len(leaddf) else "可检验对不足")

    metrics = {"cities": [names[c] for c in cities],
               "n_seasonal_pairs": int(len(pair_df)),
               "production_concentration": conc_rows}
    (out / "metrics" / f"{MODULE}_summary.json").write_text(
        __import__("json").dumps(metrics, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    abstract = (
        f"本研究比较辽宁五城（朝阳/大连/丹东/锦州/铁岭，沈阳为参照）的农业市场与风险特征。"
        f"由于六城价格层级不同（批发/市场均价/超市/产地），**不做价格水平比较**，只做结构化与相对化分析。"
        f"内容：作物结构集中度对比（{conc_txt}）；共有蔬菜的价格季节同步性（{sync_txt}）；"
        f"极端天气韧性对比（{resil_txt}）；跨城价格领先/滞后（{lead_txt}）。"
        f"跟风种植风险与销售去向因缺少生产—价格面板与流通数据而不成立。\n\n"
        f"**关键词**：跨城市；季节同步性；结构集中度；韧性；领先滞后；辽宁六城"
    )
    frontend_summary = (f"六城对比：结构集中度、季节同步性、韧性、领先滞后。"
                        f"季节同步性 {sync_txt[:80]}。")
    data_scope = ("### 2.1 对象\n辽宁六城（含沈阳参照）。\n\n"
                  "### 2.2 数据\n各城价格（口径不同，仅作相对比较）、ERA5 气象、辽宁统计年鉴。\n\n"
                  "### 2.3 边界\n价格水平不可比；跟风种植/销售去向无数据，NOT_SUPPORTED。")
    methods = ("### 3.1 集中度\n各城 HHI/CR4 对比。\n\n"
               "### 3.2 季节同步\n共有蔬菜季节指数剖面的城际相关。\n\n"
               "### 3.3 韧性\n各城事件后响应与安慰剂 p 对比。\n\n"
               "### 3.4 领先滞后\n周度对数价格的多滞后互相关，取绝对值最大者为最优滞后。")
    results = [
        ("作物结构集中度", conc.to_string(index=False) if len(conc) else "无"),
        ("价格季节同步性（仅同频率对）", (by_crop.to_string(index=False) if len(by_crop) else "同频率共有序列不足")
                                       + ("\n（混合频率对已单列于 season_sync.csv 的 freq_pair=mixed，不进入主结论）" if len(pair_df) else "")),
        ("极端天气韧性", resil.to_string(index=False)),
        ("跨城领先/滞后（探索性）", (leaddf.sort_values("corr_at_best", key=lambda s: s.abs(), ascending=False).head(12).to_string(index=False)
                         if len(leaddf) else "可检验对不足")
                           + "\n注意：`best_lag_weeks` 与 `corr_at_best` 是在 −6…+6 共 13 个滞后中按 |相关| 取最大者，"
                             "属**选择性最大化**，会高估相关系数且未做多重比较校正；"
                             "故仅作探索性描述，不构成领先/滞后因果传导证据。"),
        ("数据不支持的议题", "1) **跟风种植风险**：需「价格→次年生产扩张」面板，五城无区县生产与连续种植面积，"
                             "NOT_SUPPORTED。\n2) **销售去向/物流最优**：无货源地与流向数据，NOT_SUPPORTED，"
                             "仅作市场层面参考。"),
    ]
    discussion = ("季节同步性高提示区域市场受共同季节/气候驱动；领先滞后结构若有稳定模式，"
                  "可能反映集散与调运时序，但本数据无法证实机制。价格水平差异使绝对套利类结论不成立。"
                  "关于跟风种植：当前数据只能支持「部分作物存在明显周期同步与较高生产集中度」，"
                  "这构成进一步研究跟风扩种风险的依据，但**不能据此证明农户存在跟风种植**。")
    limitations = [
        "1. **价格层级不可比**：仅相对/结构化比较，不做价格水平比较。",
        "2. **粒度不一**：部分城日度、部分周度。",
        "3. **重叠时间有限**：跨城可检验对受限。",
        "4. **季节同步可检验对极少**：同频率对每种作物仅 1 对（朝阳—锦州，均日度），均值相关无置信区间，"
        "只能作为「存在较强同步」的初步信号，不能量化其稳健性。",
        "5. **领先/滞后为选择性最大化**：13 个滞后中取 |相关| 最大者，未做多重比较校正，仅探索性。",
        "6. **无流通数据**：销售去向与物流最优不成立。",
        "7. **跟风种植不可检验**：缺生产—价格面板，只能报告「周期同步+高集中度」作为进一步研究依据。",
        "8. **季节同步效应量未量化**：以均值相关表示，未给置信区间。",
        "9. **研究级多重比较**：全研究跨模块累计执行逾千项检验，仅模块内做 BH-FDR，未做研究级校正；"
        "因此单项「显著」应视为探索性信号，而非确定性结论。",
    ]
    conclusion = (f"六城对比显示：生产结构均以玉米主导但集中度不同（{conc_txt}）；"
                  f"共有蔬菜季节同步性 {sync_txt}；极端天气韧性（安慰剂 p）{resil_txt}。"
                  f"价格水平与流通类结论不成立。")

    # 直接写 article.json / report.md（无单城 StudyWriter）
    w = contract.StudyWriter(cities[0], "cross_city", "cross-city-liaoning", "辽宁六城农业市场与风险比较研究")
    w.tables = tables
    w.figures = figures
    w.dir = out
    explorer = {
        "selectors": [{"key": "city", "label": "城市", "options": [names[c] for c in cities]},
                      {"key": "crop", "label": "作物", "options": common}],
        "metrics": ["n_seasonal_pairs"],
        "series": [{"id": "sync", "table": f"{MODULE}_seasonal_sync.csv", "x": "city_b",
                    "y": "seasonal_corr", "facet": "crop"}],
        "tables": tables, "figures": figures, "sources": [],
        "methodology": methods, "limitations": limitations,
    }
    from pathlib import Path
    art = {
        "id": "A10", "city": "辽宁六城", "slug": w.slug, "title": w.title,
        "abstract": abstract, "frontend_summary": frontend_summary,
        "keywords": ["跨城市", "季节同步性", "结构集中度", "韧性", "领先滞后"],
        "research_questions": ["辽宁六城农业市场与风险的结构与同步性如何？"],
        "data_scope": {"summary": data_scope}, "methods": [{"summary": methods}],
        "key_findings": [{"heading": h} for h, _ in results],
        "sections": [{"number": str(i + 1), "title": t, "content": c}
                     for i, (t, c) in enumerate([("研究问题与背景", "见摘要"), ("数据与变量", data_scope),
                                                 ("研究方法", methods), ("研究结果", "\n\n".join([f"### {h}\n{c}" for h, c in results])),
                                                 ("讨论", discussion), ("研究局限", "\n".join(limitations)),
                                                 ("结论", conclusion)])],
        "limitations": limitations, "conclusion": conclusion,
        "figures": [{"file": f} for f in figures], "tables": [{"file": t} for t in tables],
        "source_ids": [], "status": "DRAFT", "explorer": explorer,
    }
    (out / "article.json").write_text(__import__("json").dumps(art, ensure_ascii=False, indent=1), encoding="utf-8")
    md = [f"# {w.title}", "", "## 摘要", "", abstract.split("**关键词**")[0].strip(), ""]
    for t, c in results:
        md += [f"## {t}", "", c, ""]
    md += ["## 研究局限", "", "\n".join(limitations), "", "## 结论", "", conclusion, "", "ARTICLE_END"]
    (out / "report.md").write_text("\n".join(md), encoding="utf-8")
    return {"module": MODULE, "status": "DRAFT", "tables": tables, "figures": figures}


def _read_metrics(city: str, module: str):
    import json
    p = paths.RESEARCH / city / module / "metrics" / f"{module}_summary.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return None
    return None


def _fig(names, conc, resil, by_crop):
    from ..lib.plotting import setup_plt, C_MAIN, C_ALT
    plt = setup_plt()
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.4))
    if len(conc):
        axes[0].bar(conc["city"], conc["HHI"], color=C_MAIN)
        axes[0].set_ylabel("HHI"); axes[0].set_title("生产结构集中度")
    if len(by_crop):
        d = by_crop.sort_values("mean_corr", ascending=False)
        axes[1].bar(d["crop"], d["mean_corr"], color=C_ALT)
        axes[1].set_ylabel("季节同步相关(均值)"); axes[1].tick_params(axis="x", rotation=45)
        axes[1].set_title("共有蔬菜季节同步性")
    r = resil.dropna(subset=["placebo_p"])
    if len(r):
        axes[2].bar(r["city"], r["placebo_p"], color=C_MAIN)
        axes[2].axhline(0.05, color="red", ls="--", lw=1)
        axes[2].set_ylabel("安慰剂 p"); axes[2].set_title("极端天气韧性（安慰剂）")
    fig.suptitle("辽宁六城农业市场与风险概览")
    return fig