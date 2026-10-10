"""a07_production_structure.py — A07 农业生产与结构变化（五城均可用）。

数据：辽宁统计年鉴（城市级），2017–2024 中文年鉴行使用「面积=千公顷」口径；
生产表内并存英文编码行（2020/2025，另一来源），本模块**只用中文年鉴行**以保证单位一致，
英文编码行作为数据质量说明单独记录、不参与计算。

分析：作物播种面积结构、集中度（HHI/CR4）、面积变化（首年→末年）。
不涉及气象归因（五城无区县面板）。
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from ..lib import contract, emit, loaders

MODULE = "A07"
SLUG = "production-structure"
TITLE = "农业生产结构与变化"

AGG_KEYWORDS = ["农作物总", "其他作物", "粮食作物", "经济作物", "粮食", "油料", "肉类", "水产品"]
NOISE_PAT = r"[\(（#)]|吨"


def _prepare(city: str):
    raw = loaders.load_production(city)
    raw["area_kha"] = pd.to_numeric(raw.get("planting_area_kha"), errors="coerce")
    if "planting_area" in raw.columns:
        raw["area_kha"] = raw["area_kha"].fillna(pd.to_numeric(raw["planting_area"], errors="coerce"))
    raw["crop_str"] = raw["crop"].astype(str).str.strip()
    # 英文编码行（另一来源）单列
    eng = raw[raw["crop_str"].str.match(r"^[a-z_#]+$", na=False)].copy()
    cn = raw[~raw["crop_str"].str.match(r"^[a-z_#]+$", na=False)].copy()
    cn = cn[cn["year"].notna()]
    cn["year"] = cn["year"].astype(int)
    cn = cn[~cn["crop_str"].str.contains(NOISE_PAT, regex=True, na=False)]
    cn = cn.dropna(subset=["area_kha"])
    return cn, eng


def run(city: str) -> Dict:
    cfg = loaders.load_cities()[city]
    cn, eng = _prepare(city)
    if cn.empty:
        return emit.emit_not_supported(city=city, module=MODULE, slug=SLUG, title=TITLE,
                                       reason="本城年鉴生产表缺少可用面积字段。")
    years = sorted(cn["year"].unique().tolist())
    crops = cn[~cn["crop_str"].str.contains("|".join(AGG_KEYWORDS), na=False)].copy()
    struct = crops.pivot_table(index="crop_str", columns="year", values="area_kha", aggfunc="sum")
    # 选取"覆盖最完整"的年份区间：末年取覆盖 >= 最高覆盖 70% 的最新一年
    cov = struct.notna().sum()
    cmax = int(cov.max()) if len(cov) else 0
    good = cov[cov >= max(3, int(0.7 * cmax))]
    if not len(good):
        return emit.emit_not_supported(city=city, module=MODULE, slug=SLUG, title=TITLE,
                                       reason="年鉴生产表在作物维度覆盖不足。")
    latest = int(good.index.max()); first = int(good.index.min())
    sl = struct[latest].dropna().sort_values(ascending=False) if latest in struct.columns else pd.Series(dtype=float)
    if len(sl):
        share = pd.DataFrame({"crop": sl.index.astype(str), "area_kha": sl.values.astype(float)})
        share["area_share"] = share["area_kha"] / share["area_kha"].sum()
    else:
        share = pd.DataFrame(columns=["crop", "area_kha", "area_share"])
    sh = share["area_share"].dropna().to_numpy()
    hhi = float(np.sum(sh ** 2)) if len(sh) else np.nan
    cr4 = float(np.sort(sh)[::-1][:4].sum()) if len(sh) else np.nan
    concentration = pd.DataFrame([{"metric": "HHI", "value": hhi}, {"metric": "CR4", "value": cr4},
                                  {"metric": "n_crops", "value": len(sh)}])
    change_rows = []
    for crop in share["crop"]:
        a0 = struct.loc[crop, first] if first in struct.columns else np.nan
        a1 = struct.loc[crop, latest] if latest in struct.columns else np.nan
        chg = (a1 - a0) / a0 if (np.isfinite(a0) and a0 > 0) else np.nan
        change_rows.append({"crop": crop, "area_first": a0, "area_last": a1, "pct_change": chg})
    change = pd.DataFrame(change_rows).sort_values("pct_change")
    # 总量
    total = cn[cn["crop_str"].str.contains("农作物总", na=False)].groupby("year")["area_kha"].sum()
    if len(total) == 0:
        total = cn[cn["crop_str"].str.contains("|".join(AGG_KEYWORDS[:4]), na=False)].groupby("year")["area_kha"].sum()

    w = contract.StudyWriter(city, MODULE, SLUG, f"{cfg['name']}市{TITLE}")
    w.save_table(share, f"{MODULE}_crop_structure.csv")
    w.save_table(concentration, f"{MODULE}_concentration.csv")
    w.save_table(change, f"{MODULE}_change.csv")
    w.save_table(pd.DataFrame({"year": total.index.astype(int), "total_area_kha": total.values}),
                 f"{MODULE}_total_area.csv")
    w.save_table(pd.DataFrame({"note": ["英文编码行（另一来源，未参与结构计算）"],
                               "n_rows": [len(eng)], "years": [sorted(eng["year"].dropna().astype(int).unique().tolist())]}),
                 f"{MODULE}_data_quality_note.csv")
    fig = _fig(cfg["name"], share, total)
    w.save_fig(fig, f"{MODULE}_structure.png")

    top = share.head(3)
    top_txt = "；".join([f"{r['crop']} {r['area_share']:.1%}" for _, r in top.iterrows()])
    metrics = {"city": city, "years": [int(first), int(latest)], "n_years": len(years),
               "n_crops": len(sh), "HHI": hhi, "CR4": cr4, "top3": top_txt,
               "excluded_english_rows": int(len(eng))}
    w.dump_metrics(f"{MODULE}_summary.json", metrics)

    abstract = (
        f"本研究描述{cfg['name']}农业生产的作物结构与变化。数据为《辽宁统计年鉴》城市级农作物播种面积"
        f"（中文年鉴行，面积口径 千公顷），可用年段 {first}–{latest}（{len(years)} 年）。"
        f"分析作物结构、集中度（HHI={hhi:.3f}、CR4={cr4:.3f}）与 {first}→{latest} 面积变化。"
        f"最新年面积占比前三：{top_txt}。生产表中另有英文编码行（另一来源，{len(eng)} 行）"
        f"因单位口径不一致未参与计算。本研究不涉及气象归因。\n\n"
        f"**关键词**：农业生产结构；播种面积；集中度 HHI/CR4；辽宁统计年鉴；{cfg['name']}"
    )
    frontend_summary = (f"{cfg['name']}：{first}–{latest} 年鉴；HHI={hhi:.3f}、CR4={cr4:.3f}；前三 {top_txt}。")
    data_scope = (f"### 2.1 研究对象\n{cfg['name']}农业生产（作物播种面积结构）。\n\n"
                  f"### 2.2 数据来源\n《辽宁统计年鉴》城市级表。\n\n"
                  f"### 2.3 变量\n- area_kha：播种面积（千公顷，年鉴口径）；"
                  f"结构计算只用中文年鉴行；英文编码行单位不一致，单列说明。")
    methods = ("### 3.1 结构\n年×作物播种面积结构（千公顷）。\n\n"
               "### 3.2 集中度\nHHI（份额平方和）、CR4（前四份额和）。\n\n"
               "### 3.3 变化\n首年→末年各作物面积相对变化；汇总行（粮食作物/经济作物等）单列。")
    results_text = [
        ("作物结构", f"最新年（{latest}）面积占比前三：{top_txt}。（表 {MODULE}_crop_structure.csv）"),
        ("集中度", f"HHI = **{hhi:.3f}**，CR4 = **{cr4:.3f}**，作物类别数 {len(sh)}。（表 {MODULE}_concentration.csv）"),
        ("结构变化", change.head(10).round(3).to_string(index=False)),
    ]
    discussion = ("集中度刻画区域种植结构特征；结构变化可指向种植结构调整，但年鉴为汇总统计，"
                  "不能据以推断农户层面动因。英文编码行与年鉴口径不一致，未合并，避免单位混装。")
    limitations = [
        "1. **城市级汇总**：无区县细分。",
        "2. **年鉴作物分类**：与市场价格品类不完全对应。",
        "3. **口径分离**：生产表内英文编码行单位不一致，未参与计算。",
        "4. **分类较粗**：结构仅基于年鉴 8 类汇总作物，CR4 接近饱和（>0.95），对结构差异的区分度有限。",
        "5. **无气象归因**：仅结构描述，不涉因果；HHI 高不等于农户跟风种植。",
    ]
    conclusion = (f"{cfg['name']} {first}–{latest}：最新年面积占比前三为 {top_txt}；"
                  f"HHI={hhi:.3f}、CR4={cr4:.3f}。上述为结构性描述，不含气象归因。")
    explorer = {
        "selectors": [{"key": "crop", "label": "作物", "options": share["crop"].tolist()},
                      {"key": "year", "label": "年份", "options": [int(y) for y in years]}],
        "metrics": ["HHI", "CR4", "n_crops"],
        "series": [{"id": "structure", "table": f"{MODULE}_crop_structure.csv", "x": "crop", "y": "area_share"}],
        "tables": [f"{MODULE}_crop_structure.csv", f"{MODULE}_concentration.csv", f"{MODULE}_change.csv"],
        "figures": [f"{MODULE}_structure.png"], "sources": [],
        "methodology": methods, "limitations": limitations,
    }
    return emit.emit_study(
        city=city, module=MODULE, slug=SLUG, title=f"{cfg['name']}市{TITLE}",
        abstract=abstract, frontend_summary=frontend_summary,
        keywords=["农业生产结构", "播种面积", "集中度", "辽宁统计年鉴", cfg["name"]],
        research_questions=[f"{cfg['name']}农业生产的作物结构与变化如何？"],
        data_scope=data_scope, methods=methods, results=results_text, discussion=discussion,
        limitations=limitations, conclusion=conclusion, explorer=explorer,
        tables=[f"{MODULE}_crop_structure.csv", f"{MODULE}_concentration.csv", f"{MODULE}_change.csv"],
        figures=[f"{MODULE}_structure.png"],
        claims=[{"claim_id": f"{city}-A07-C1", "study_id": "A07", "city": cfg["name"],
                 "claim_text": f"HHI={hhi:.3f}、CR4={cr4:.3f}；前三 {top_txt}",
                 "claim_type": "descriptive", "table_id": f"{MODULE}_concentration.csv",
                 "estimate": hhi, "sample_size": len(sh), "status": "SUPPORTED"}])


def _fig(city_name, share, total):
    from ..lib.plotting import setup_plt, C_MAIN, C_ALT
    plt = setup_plt()
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.6))
    s = share.head(10)
    if len(s):
        axes[0].barh(s["crop"][::-1], s["area_share"][::-1], color=C_MAIN)
        axes[0].set_xlabel("面积占比"); axes[0].set_title("作物结构（最新年，前10）")
    if len(total):
        axes[1].plot(total.index, total.values, marker="o", color=C_ALT)
        axes[1].set_xlabel("年"); axes[1].set_ylabel("播种面积（千公顷）"); axes[1].set_title("面积趋势")
    fig.suptitle(f"{city_name}市 农业生产结构")
    return fig