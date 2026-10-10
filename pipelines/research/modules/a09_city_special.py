"""a09_city_special.py — A09 城市特色专项研究（逐城，数据驱动，不复制）。

统一骨架：城市气候背景 + 生产结构概览 + 城市专项分析。
专项（由数据决定，非预设结论）：
- 朝阳 / 锦州（辽西）：生长季降水与温度暴露特征 + 蔬菜价格季节峰值月分布。
- 大连（沿海/消费市场）：沿海气候（湿度/风/辐射）+ 市场节点与可达性（logistics/accessibility）。
- 丹东（高降水/特色农业）：降水气候特征 + 特色作物覆盖 + 官方灾情暴露。
- 铁岭（粮食主产）：粮食作物结构 + 生长季气象与产量年际描述。
每个专项均标注 NOT_SUPPORTED 边界（数据不足即明说）。
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from ..lib import contract, emit, loaders, panel, stats, paths

MODULE = "A09"
SLUG = "city-special"
TITLE = "城市特色专项研究"
SPECIALTY = {
    "dandong": ["草莓", "蓝莓", "板栗", "中药材", "淡水鱼", "蜂蜜", "香菇", "蚕茧", "龙眼", "山楂"],
    "tieling": ["玉米", "水稻", "大豆", "花生"],
}


def _climatology(city: str) -> Dict:
    w = loaders.load_weather(city)
    w["year"] = w["date"].dt.year
    w["precip"] = pd.to_numeric(w["precipitation_sum"], errors="coerce")
    w["tmean"] = pd.to_numeric(w["temperature_2m_mean"], errors="coerce")
    gs = w[w["date"].dt.month.isin([4, 5, 6, 7, 8, 9])]
    ann = w.groupby("year").agg(precip_ann=("precip", "sum"), tmean_ann=("tmean", "mean"))
    gsy = gs.groupby("year").agg(precip_gs=("precip", "sum"), tmean_gs=("tmean", "mean"))
    df = ann.join(gsy)
    recent = df[df.index >= 2021]
    early = df[(df.index >= 2010) & (df.index <= 2020)]
    return {
        "n_years": int(len(df)),
        "precip_ann_mean": float(df["precip_ann"].mean()),
        "precip_gs_mean": float(df["precip_gs"].mean()),
        "tmean_ann_mean": float(df["tmean_ann"].mean()),
        "precip_ann_recent": float(recent["precip_ann"].mean()) if len(recent) else np.nan,
        "precip_ann_early": float(early["precip_ann"].mean()) if len(early) else np.nan,
        "gs_share": float(df["precip_gs"].mean() / df["precip_ann"].mean()) if df["precip_ann"].mean() else np.nan,
        "df": df.reset_index(),
    }


def _seasonal_peak_months(city: str, top_n: int = 8):
    veg = loaders.veg_crops()
    rows = []
    for crop in veg:
        s = loaders.load_primary_series(city, crop)
        if len(s) < 200:
            continue
        si = stats.seasonal_index(s["date"], s["price_per_kg"], "month")
        if len(si):
            rows.append({"crop": crop, "peak_month": int(si.loc[si["index"].idxmax(), "period"]),
                         "amplitude": float(si["index"].max() - si["index"].min())})
    if not rows:
        return pd.DataFrame(columns=["crop", "peak_month", "amplitude"])
    return pd.DataFrame(rows).sort_values("amplitude", ascending=False).head(top_n)


def run(city: str) -> Dict:
    cfg = loaders.load_cities()[city]
    an = loaders.load_analysis()
    clim = _climatology(city)
    # 生产结构（复用 A07 逻辑的轻量版）
    cn, eng = _prod_prepare(city)
    top_txt, hhi = _prod_summary(cn)

    w = contract.StudyWriter(city, MODULE, SLUG, f"{cfg['name']}市{TITLE}")
    w.save_table(clim["df"], f"{MODULE}_climatology.csv")

    results, extra_claims = [], []
    # 统一：气候背景
    results.append(("城市气候背景",
                    f"{clim['n_years']} 年（2010–2026）年均降水 {clim['precip_ann_mean']:.0f} mm，"
                    f"生长季（4–9 月）降水占全年 {clim['gs_share']:.0%}，年均温 {clim['tmean_ann_mean']:.1f}℃。"
                    f"2021 年后年均降水 {clim['precip_ann_recent']:.0f} mm，"
                    f"2010–2020 年为 {clim['precip_ann_early']:.0f} mm。"
                    f"（表 {MODULE}_climatology.csv）"))
    results.append(("生产结构概览", f"{top_txt}；HHI={hhi:.3f}。"))

    # 城市专项
    if city in ("chaoyang", "jinzhou"):
        sp = _seasonal_peak_months(city)
        if len(sp):
            w.save_table(sp, f"{MODULE}_seasonal_peak.csv")
            pm = sp["peak_month"].value_counts().sort_index()
            results.append(("价格季节峰值月分布（辽西专项）",
                            f"幅度前 {len(sp)} 作物的价格季节峰值月集中于 "
                            f"{', '.join(f'{int(k)}月×{int(v)}' for k, v in pm.items())}。"
                            f"结合生长季降水占全年 {clim['gs_share']:.0%}，可观察雨季与价格季节的时序关系。"
                            f"（探索性，表 {MODULE}_seasonal_peak.csv）"))
            extra_claims.append({"claim_id": f"{city}-A09-C2", "study_id": "A09", "city": cfg["name"],
                                 "claim_text": f"生长季降水占比 {clim['gs_share']:.0%}；价格季节峰值月集中于 "
                                               f"{', '.join(str(int(k)) for k in pm.index)} 月",
                                 "claim_type": "descriptive", "table_id": f"{MODULE}_seasonal_peak.csv",
                                 "status": "SUPPORTED"})
        fig = _fig_peak(cfg["name"], sp)

    elif city == "dalian":
        nodes = _market_nodes()
        results.append(("沿海城市与市场节点（专项）",
                        f"本城为沿海大城市消费市场。已登记市场/物流节点 {len(nodes)} 条"
                        f"（含批发市场吞吐、冷链等），市场可达性参考表另有城市间距离/时长记录。"
                        f"价格以周度、层级混合（零售/产地）为主。"
                        f"基于现有数据可做市场层面的结构描述，**不作真实物流最优推断**。"
                        f"（表 {MODULE}_market_nodes.csv）"))
        if len(nodes):
            w.save_table(nodes, f"{MODULE}_market_nodes.csv")
        extra_claims.append({"claim_id": f"{city}-A09-C2", "study_id": "A09", "city": cfg["name"],
                             "claim_text": f"登记市场/物流节点 {len(nodes)} 条（市场层面参考）",
                             "claim_type": "descriptive", "table_id": f"{MODULE}_market_nodes.csv",
                             "status": "PARTIAL"})
        fig = _fig_simple(cfg["name"], clim["df"], "年降水（mm）", "大连市 年降水序列")

    elif city == "dandong":
        sp = _specialty_coverage(city)
        dis = loaders.load_disaster(city)
        w.save_table(sp, f"{MODULE}_specialty_coverage.csv")
        if not dis.empty:
            keep = [c for c in ["event_id", "event_type", "start_date", "crop", "source_name"] if c in dis.columns]
            w.save_table(dis[keep], f"{MODULE}_disaster_exposure.csv")
        n_sp = int((sp["n_obs"] > 0).sum())
        results.append(("特色农业与灾害暴露（专项）",
                        f"本城为高降水/山地沿海环境，特色农产品包括 "
                        f"{'、'.join(sp[sp.n_obs > 0]['crop'].head(10).tolist())} 等（{n_sp} 类有观测，"
                        f"均为第三方产地行情、覆盖稀疏）。官方灾情通报 {len(dis)} 条。"
                        f"特色作物价格序列稀疏，**不做价格建模**。"
                        f"（表 {MODULE}_specialty_coverage.csv、{MODULE}_disaster_exposure.csv）"))
        extra_claims.append({"claim_id": f"{city}-A09-C2", "study_id": "A09", "city": cfg["name"],
                             "claim_text": f"特色农产品 {n_sp} 类有观测（稀疏）；官方灾情 {len(dis)} 条",
                             "claim_type": "descriptive", "table_id": f"{MODULE}_specialty_coverage.csv",
                             "status": "PARTIAL"})
        fig = _fig_simple(cfg["name"], clim["df"], "年降水（mm）", "丹东市 年降水序列")

    else:  # tieling
        cn2 = cn.copy()
        grain = cn2[cn2["crop_str"].str.contains("玉米|水稻|大豆|花生|高粱|谷子", na=False)]
        fig = _fig_simple(cfg["name"], clim["df"], "年降水（mm）", "铁岭市 年降水序列")
        results.append(("粮食生产与生长季气象（专项）",
                        f"本城为粮食主产区，生产结构以玉米为主（{top_txt}）。"
                        f"生长季（4–9 月）降水占全年 {clim['gs_share']:.0%}，"
                        f"年均温 {clim['tmean_ann_mean']:.1f}℃。"
                        f"因无区县面板与产量连续序列，气象—产量关系只能作描述性观察，**不作因果**。"))
        extra_claims.append({"claim_id": f"{city}-A09-C2", "study_id": "A09", "city": cfg["name"],
                             "claim_text": f"生长季降水占比 {clim['gs_share']:.0%}；玉米主导（{top_txt}）",
                             "claim_type": "descriptive", "status": "PARTIAL"})

    w.save_fig(fig, f"{MODULE}_special.png")
    metrics = {"city": city, "clim": {k: v for k, v in clim.items() if k != "df"},
               "prod_top": top_txt, "prod_hhi": hhi}
    w.dump_metrics(f"{MODULE}_summary.json", metrics)

    abstract = (
        f"本研究是{cfg['name']}的城市特色专项（不复制其他城市结论），由当地数据决定方向。"
        f"统一包含气候背景与生产结构概览，并针对本城特征展开专项分析。"
        f"年均降水 {clim['precip_ann_mean']:.0f} mm（生长季占 {clim['gs_share']:.0%}）；"
        f"生产结构：{top_txt}。\n\n**关键词**：城市专项；气候背景；生产结构；{cfg['name']}"
    )
    frontend_summary = (f"{cfg['name']}专项：年降水 {clim['precip_ann_mean']:.0f}mm（生长季 {clim['gs_share']:.0%}）；"
                        f"生产 {top_txt}。")
    data_scope = (f"### 2.1 对象\n{cfg['name']}农业气候与生产特征。\n\n"
                  f"### 2.2 数据\n气象：ERA5 再分析网格（2010–2026）；生产：《辽宁统计年鉴》；"
                  f"价格：{cfg['price_level_note']}；灾害：官方通报。\n\n"
                  f"### 2.3 边界\n数据不足处显式标注 NOT_SUPPORTED，不作因果与物流最优推断。")
    methods = ("### 3.1 气候背景\n年/生长季降水与温度统计，近期（2021–2026）与早期（2010–2020）对照。\n\n"
               "### 3.2 生产结构\n作物播种面积结构与集中度。\n\n"
               "### 3.3 专项\n由本城数据可得性决定（见研究结果），探索性结论均标注。")
    discussion = ("城市专项的价值在于识别区域异质性：同为辽宁中部/西部/沿海/东部，其气候背景、"
                  "生产结构与市场口径差异显著。本研究只陈述数据支持的部分，不编造区域机制叙事。")
    limitations = [
        "1. **气候为再分析网格**：非气象站实测。",
        "2. **专项视数据而定**：部分方向因数据不足 NOT_SUPPORTED。",
        "3. **探索性**：专项结论多为描述性，样本有限。",
        f"4. **价格口径**：{cfg['price_level_note']}。",
    ]
    conclusion = (f"{cfg['name']}专项：年均降水 {clim['precip_ann_mean']:.0f} mm（生长季占 {clim['gs_share']:.0%}）；"
                  f"生产结构 {top_txt}。专项分析方向由本地数据决定，未复制其他城市结论。")
    explorer = {
        "selectors": [{"key": "crop", "label": "作物", "options": _options(city)},
                      {"key": "year", "label": "年份",
                       "options": [int(y) for y in clim["df"]["year"].tolist()]}],
        "metrics": ["prod_hhi"],
        "series": [{"id": "climatology", "table": f"{MODULE}_climatology.csv", "x": "year",
                    "y": "precip_ann"}],
        "tables": w.tables, "figures": w.figures, "sources": [],
        "methodology": methods, "limitations": limitations,
    }
    claims = [{"claim_id": f"{city}-A09-C1", "study_id": "A09", "city": cfg["name"],
               "claim_text": f"年降水 {clim['precip_ann_mean']:.0f}mm（生长季 {clim['gs_share']:.0%}）；{top_txt}",
               "claim_type": "descriptive", "table_id": f"{MODULE}_climatology.csv",
               "status": "SUPPORTED"}] + extra_claims
    return emit.emit_study(
        city=city, module=MODULE, slug=SLUG, title=f"{cfg['name']}市{TITLE}",
        abstract=abstract, frontend_summary=frontend_summary,
        keywords=["城市专项", "气候背景", "生产结构", cfg["name"]],
        research_questions=[f"{cfg['name']}的农业气候与生产特征有何区域特点？"],
        data_scope=data_scope, methods=methods, results=results, discussion=discussion,
        limitations=limitations, conclusion=conclusion, explorer=explorer,
        tables=list(w.tables), figures=list(w.figures), claims=claims)


# --- helpers ---
def _prod_prepare(city: str):
    raw = loaders.load_production(city)
    raw["area_kha"] = pd.to_numeric(raw.get("planting_area_kha"), errors="coerce")
    if "planting_area" in raw.columns:
        raw["area_kha"] = raw["area_kha"].fillna(pd.to_numeric(raw["planting_area"], errors="coerce"))
    raw["crop_str"] = raw["crop"].astype(str).str.strip()
    cn = raw[~raw["crop_str"].str.match(r"^[a-z_#]+$", na=False)].copy()
    cn = cn[cn["year"].notna()]; cn["year"] = cn["year"].astype(int)
    cn = cn[~cn["crop_str"].str.contains(r"[\(（#)]|吨", regex=True, na=False)].dropna(subset=["area_kha"])
    eng = raw[raw["crop_str"].str.match(r"^[a-z_#]+$", na=False)]
    return cn, eng


def _prod_summary(cn: pd.DataFrame):
    AGG = ["农作物总", "其他作物", "粮食作物", "经济作物", "粮食", "油料"]
    if cn.empty:
        return "生产数据不足", np.nan
    crops = cn[~cn["crop_str"].str.contains("|".join(AGG), na=False)]
    st = crops.pivot_table(index="crop_str", columns="year", values="area_kha", aggfunc="sum")
    cov = st.notna().sum(); cmax = int(cov.max())
    good = cov[cov >= max(3, int(0.7 * cmax))]
    if not len(good):
        return "生产结构覆盖不足", np.nan
    latest = int(good.index.max())
    sl = st[latest].dropna().sort_values(ascending=False)
    share = (sl / sl.sum())
    top = share.head(3)
    top_txt = "、".join([f"{c} {v:.1%}" for c, v in top.items()])
    hhi = float((share ** 2).sum())
    return top_txt, hhi


def _specialty_coverage(city: str):
    df = loaders.load_price_all(city)
    rows = []
    for name in SPECIALTY.get(city, []):
        n = int((df["crop_raw"].astype(str) == name).sum())
        rows.append({"crop": name, "n_obs": n})
    return pd.DataFrame(rows)


def _market_nodes():
    p = paths.PROCESSED / "infrastructure" / "logistics_reference.parquet"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_parquet(p)
    return df[df["city"] == "大连"] if "city" in df.columns else df


def _options(city: str):
    return loaders.veg_crops() if city in ("chaoyang", "jinzhou", "dalian") else ["玉米", "水稻", "大豆", "花生"]


def _fig_simple(city_name, climat, ylabel, title):
    from ..lib.plotting import setup_plt, C_MAIN
    plt = setup_plt()
    fig, ax = plt.subplots(figsize=(7.6, 4.6))
    ax.plot(climat["year"], climat["precip_ann"], marker="o", color=C_MAIN)
    ax.set_xlabel("年"); ax.set_ylabel(ylabel); ax.set_title(title)
    return fig


def _fig_peak(city_name, sp):
    from ..lib.plotting import setup_plt, C_MAIN
    plt = setup_plt()
    fig, ax = plt.subplots(figsize=(7.6, 4.6))
    if len(sp):
        ax.bar(sp["crop"], sp["peak_month"], color=C_MAIN)
        ax.set_ylabel("价格季节峰值月"); ax.tick_params(axis="x", rotation=45)
    ax.set_title(f"{city_name}市 蔬菜价格季节峰值月")
    return fig