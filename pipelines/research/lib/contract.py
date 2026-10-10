"""contract.py — 研究产物契约：article.json / report.md / 表图指标 / 证据链 / 来源登记。

对齐沈阳 A01 的 article.json 字段，并扩展 interactive 研究版所需契约：
    explorer = {selectors, metrics, series, tables, figures, sources, methodology, limitations}
供前端"研究中心"直接消费。
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from . import paths, loaders

ARTICLE_END = "ARTICLE_END"

EVENT_COLS = ["claim_id", "study_id", "city", "claim_text", "claim_type", "evidence_id",
              "source_ids", "table_id", "figure_id", "estimate", "ci_low", "ci_high",
              "p_raw", "p_adjusted", "sample_size", "method_id", "status"]


class StudyWriter:
    """单城单研究模块的产物写出器。"""

    def __init__(self, city: str, module: str, slug: str, title: str):
        self.city = city
        self.city_name = loaders.load_cities()[city]["name"]
        self.module = module
        self.slug = slug
        self.title = title
        self.dir = paths.city_out_dir(city, module)
        self.tables: List[str] = []
        self.figures: List[str] = []

    # --- 产物 ---
    def save_table(self, df: pd.DataFrame, name: str) -> Path:
        p = self.dir / "tables" / name
        df.to_csv(p, index=False, encoding="utf-8-sig")
        self.tables.append(name)
        return p

    def save_fig(self, fig, name: str) -> Path:
        from .plotting import save_fig
        p = save_fig(fig, self.dir / "figures" / name)
        self.figures.append(name)
        return p

    def dump_metrics(self, name: str, obj: Dict[str, Any]) -> Path:
        p = self.dir / "metrics" / name
        p.write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        return p

    # --- article.json ---
    def write_article(self, *, abstract: str, frontend_summary: str, keywords: List[str],
                      research_questions: List[str], data_scope: str, methods: str,
                      sections: List[Dict[str, str]], limitations: List[str], conclusion: str,
                      source_ids: List[str], explorer: Optional[Dict] = None,
                      status: str = "DRAFT") -> Path:
        art = {
            "id": self.module,
            "city": self.city_name,
            "slug": self.slug,
            "title": self.title,
            "abstract": abstract,
            "frontend_summary": frontend_summary,
            "keywords": keywords,
            "research_questions": research_questions,
            "data_scope": {"summary": data_scope},
            "methods": [{"summary": methods}],
            "key_findings": [{"heading": s["title"]} for s in sections],
            "sections": [{"number": str(i + 1), "title": s["title"], "content": s["content"]}
                         for i, s in enumerate(sections)],
            "limitations": limitations,
            "conclusion": conclusion,
            "figures": [{"file": f} for f in self.figures],
            "tables": [{"file": t} for t in self.tables],
            "source_ids": source_ids,
            "status": status,
        }
        if explorer:
            art["explorer"] = explorer
        p = self.dir / "article.json"
        p.write_text(json.dumps(art, ensure_ascii=False, indent=1), encoding="utf-8")
        return p

    def write_report(self, markdown: str) -> Path:
        p = self.dir / "report.md"
        p.write_text(markdown.rstrip() + f"\n\n{ARTICLE_END}\n", encoding="utf-8")
        return p

    # --- 证据链 ---
    def append_claims(self, rows: List[Dict[str, Any]]) -> Path:
        p = paths.RESEARCH / self.city / "evidence" / "claim_evidence.csv"
        p.parent.mkdir(parents=True, exist_ok=True)
        old: List[Dict] = []
        if p.exists():
            with p.open(encoding="utf-8-sig") as fh:
                old = [r for r in csv.DictReader(fh) if r.get("claim_id")]
        new_ids = {r["claim_id"] for r in rows}
        old = [r for r in old if r["claim_id"] not in new_ids]
        allr = old + [{k: r.get(k, "") for k in EVENT_COLS} for r in rows]
        with p.open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=EVENT_COLS)
            w.writeheader()
            for r in allr:
                w.writerow({k: r.get(k, "") for k in EVENT_COLS})
        return p


# ---------------------------------------------------------------------------
# 来源登记
# ---------------------------------------------------------------------------
_WEATHER_SRC = {
    "source_name": "Open-Meteo Historical Weather API（ERA5 / ERA5-Land 再分析网格）",
    "source_url": "https://archive-api.open-meteo.com/v1/archive",
    "source_type": "official_api",
    "quality_grade": "A",
    "note": "再分析网格，非气象站实测",
}
_PROD_SRC = {
    "source_name": "辽宁统计年鉴（农作物播种面积/产量/单产，分市）",
    "source_url": "https://tjj.ln.gov.cn/",
    "source_type": "official_statistics",
    "quality_grade": "A",
    "note": "城市级年鉴",
}


def build_source_registry(city: str) -> pd.DataFrame:
    """从该城价格表实际来源 + 气象/生产来源，生成来源登记并写入 research/<city>/sources/。"""
    df = loaders.load_price_all(city)
    rows = []
    use = df.dropna(subset=["source_name"])
    # 按来源名聚合（同一来源的逐条 URL 归并为代表 URL，避免登记爆炸）
    for sname, g in use.groupby("source_name"):
        urls = g["source_url"].dropna().astype(str)
        rep_url = urls.mode().iloc[0] if len(urls) else ""
        rows.append({
            "source_name": sname,
            "source_url": rep_url,
            "source_type": g["source_type"].mode().iloc[0] if g["source_type"].notna().any() else "",
            "quality_grade": g["quality_grade"].mode().iloc[0] if g["quality_grade"].notna().any() else "",
            "n_obs": int(len(g)),
            "date_min": str(g["date"].min().date()) if g["date"].notna().any() else "",
            "date_max": str(g["date"].max().date()) if g["date"].notna().any() else "",
            "price_level": g["price_level"].mode().iloc[0] if g["price_level"].notna().any() else "",
            "note": "",
        })
    for extra in (_WEATHER_SRC, _PROD_SRC):
        rows.append({"source_name": extra["source_name"], "source_url": extra["source_url"],
                     "source_type": extra["source_type"], "quality_grade": extra["quality_grade"],
                     "n_obs": "", "date_min": "", "date_max": "", "note": extra["note"]})
    reg = pd.DataFrame(rows)
    reg["n_obs_num"] = pd.to_numeric(reg["n_obs"], errors="coerce")
    reg = reg.sort_values("n_obs_num", ascending=False, na_position="last").drop(columns=["n_obs_num"]).reset_index(drop=True)
    reg.insert(0, "source_id", [f"SRC-{city[:2].upper()}-{i+1:02d}" for i in range(len(reg))])
    out = paths.RESEARCH / city / "sources"
    out.mkdir(parents=True, exist_ok=True)
    reg.to_csv(out / "source_registry.csv", index=False, encoding="utf-8-sig")
    return reg


def primary_source_ids(city: str, registry: pd.DataFrame) -> List[str]:
    cfg = loaders.load_cities()[city]
    pats = cfg.get("primary_sources", [])
    ids = []
    for _, r in registry.iterrows():
        if any(p in str(r["source_name"]) for p in pats):
            ids.append(r["source_id"])
    return ids


def article_source_ids(city: str, registry: pd.DataFrame,
                       include_standard: bool = True) -> List[str]:
    """文章引用来源 = 主价格来源 +（气象 + 生产）。"""
    ids = primary_source_ids(city, registry)
    if include_standard:
        for _, r in registry.iterrows():
            nm = str(r["source_name"])
            if nm == _WEATHER_SRC["source_name"] or nm == _PROD_SRC["source_name"]:
                ids.append(r["source_id"])
    return list(dict.fromkeys(ids))