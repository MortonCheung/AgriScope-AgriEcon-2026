"""emit.py — 通用研究产出器（供 A02–A09 复用，减少样板）。

约定：模块只提供"结构化的真实结果文本"，本模块负责组装
report.md / article.json / 证据链，并统一来源引用与交互契约。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from . import contract, loaders, paths


def emit_study(*, city: str, module: str, slug: str, title: str,
               abstract: str, frontend_summary: str, keywords: List[str],
               research_questions: List[str], data_scope: str, methods: str,
               results: List[Tuple[str, str]], discussion: str,
               limitations: List[str], conclusion: str,
               explorer: Optional[Dict] = None,
               claims: Optional[List[Dict]] = None,
               tables: Optional[List[str]] = None,
               figures: Optional[List[str]] = None,
               status: str = "DRAFT") -> Dict:
    """results: [(小节标题, 内容)]，按顺序构成"研究结果"章下的 ###。"""
    w = contract.StudyWriter(city, module, slug, title)
    w.tables = list(tables or [])
    w.figures = list(figures or [])
    registry = contract.build_source_registry(city)
    src_ids = contract.article_source_ids(city, registry)

    result_content = "\n\n".join([f"### {h}\n{c}" for h, c in results])
    sections = [
        {"title": "研究问题与背景", "content": research_questions[0] if research_questions else ""},
        {"title": "数据与变量", "content": data_scope},
        {"title": "研究方法", "content": methods},
        {"title": "研究结果", "content": result_content},
        {"title": "讨论", "content": discussion},
        {"title": "研究局限", "content": "\n".join(limitations)},
        {"title": "结论", "content": conclusion},
    ]
    w.write_article(abstract=abstract, frontend_summary=frontend_summary, keywords=keywords,
                    research_questions=research_questions, data_scope=data_scope, methods=methods,
                    sections=sections, limitations=limitations, conclusion=conclusion,
                    source_ids=src_ids, explorer=explorer, status=status)
    _write_report(w, abstract, sections, src_ids)
    if claims:
        w.append_claims(claims)
    return {"city": city, "module": module, "status": status, "sources": src_ids,
            "tables": list(w.tables), "figures": list(w.figures)}


def emit_not_supported(*, city: str, module: str, slug: str, title: str,
                       reason: str, notes: Optional[List[str]] = None) -> Dict:
    cfg = loaders.load_cities()[city]
    w = contract.StudyWriter(city, module, slug, title)
    registry = contract.build_source_registry(city)
    src_ids = contract.article_source_ids(city, registry, include_standard=False)
    limitations = notes or ["当前城市数据不支持该研究模块"]
    sections = [
        {"title": "研究问题与背景", "content": f"拟研究{cfg['name']}{title}。"},
        {"title": "数据与变量", "content": f"口径：{cfg['price_level_note']}。"},
        {"title": "研究方法", "content": "因数据不支持，未执行分析。"},
        {"title": "研究结果", "content": "NOT_SUPPORTED_BY_CURRENT_DATA"},
        {"title": "讨论", "content": reason},
        {"title": "研究局限", "content": "\n".join(limitations)},
        {"title": "结论", "content": "NOT_SUPPORTED_BY_CURRENT_DATA"},
    ]
    w.dump_metrics(f"{module}_summary.json", {"city": city, "status": "NOT_SUPPORTED_BY_CURRENT_DATA"})
    explorer = {
        "status": "NOT_SUPPORTED_BY_CURRENT_DATA",
        "selectors": [], "metrics": [], "series": [],
        "tables": [], "figures": [], "sources": src_ids,
        "methodology": "数据不支持，未执行分析。",
        "limitations": limitations,
        "reason": reason,
    }
    w.write_article(abstract=reason, frontend_summary=f"{cfg['name']}：{module} 数据不足，不成立。",
                    keywords=["数据不足", cfg["name"]], research_questions=[title],
                    data_scope=f"见 sources/source_registry.csv", methods="未执行",
                    sections=sections, limitations=limitations,
                    conclusion="NOT_SUPPORTED_BY_CURRENT_DATA", source_ids=src_ids,
                    explorer=explorer, status="NOT_SUPPORTED")
    _write_report(w, reason, sections, src_ids)
    return {"city": city, "module": module, "status": "NOT_SUPPORTED_BY_CURRENT_DATA"}


def _write_report(w, abstract, sections, src_ids):
    parts = [f"# {w.title}", "", "## 摘要", "",
             abstract.split("**关键词**")[0].strip(), "",
             "**关键词**：" + (abstract.split("**关键词**")[1].strip() if "**关键词**" in abstract else "")]
    for s in sections:
        parts += ["", f"## {s['title']}", "", s["content"]]
    parts += ["", "## 数据来源", "", "来源登记见 `sources/source_registry.csv`：" + "、".join(src_ids)]
    w.write_report("\n".join(parts))