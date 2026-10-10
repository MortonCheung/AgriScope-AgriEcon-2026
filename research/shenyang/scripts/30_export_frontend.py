"""30_export_frontend.py — 前端结构化导出（P6：一篇文章 = 一个物理文件 = 一个 JSON）。

纪律（施工手册 §29-§37）：
  · **禁止**从 MASTER.md 按字符位置切分；
  · **禁止**任何字符串截断（text[:500]、text[start:end]）生成摘要；
    `abstract` 从文章「## 摘要」小节**整段**提取；`frontend_summary` 从文章内
    `<!-- FRONTEND_SUMMARY -->` 显式块读取（逐篇撰写，非 substring）；
  · 每篇文章独立解析、独立 JSON；校验 `<!-- ARTICLE_END:A0X -->` 与 id 一致；
  · 前端来源只输出 public_url / publisher / title / data_year / accessed_at；
    `local_snapshot` 等本地路径**只留在内部 provenance，不导出**。

产出：
  exports/frontend/articles/A01.json ... A09.json
  exports/frontend/sources.json
  exports/frontend/manifest.json
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPORTS = Path("/Users/morton_cheung/Desktop/比赛/大数据分析/shenyang/reports/v2")
OUT = ROOT / "exports" / "frontend"
SRC_REG = ROOT / "sources" / "source_registry.csv"
TABLES = ROOT / "results" / "tables"
FIGURES = ROOT / "results" / "figures"

SLUG = {
    "A01": "market-time-seasonality", "A02": "weather-market-daily-response",
    "A03": "weather-lag-accumulation-nonlinearity", "A04": "extreme-weather-events-case-2026",
    "A05": "crop-heterogeneity-recovery", "A06": "price-volume-transmission-forecast",
    "A07": "district-production-structure", "A08": "district-yield-weather-panel",
    "A09": "synthesis-agrometeorological-risk",
}
SRC_TYPE_MAP = {"DATA_GOV": "official_statistics", "DATA_API": "official_api",
                "ACADEMIC": "academic", "STANDARD": "standard",
                "NEWS_OFFICIAL": "official_news", "METHOD": "methodology"}


def load_sources() -> dict:
    with SRC_REG.open(encoding="utf-8-sig") as fh:
        return {r["source_id"]: r for r in csv.DictReader(fh)}


def section(txt: str, header: str) -> str:
    """整段提取某个 '## header' 小节（到下一个 '## ' 为止），不做字符截断。"""
    m = re.search(rf"^##\s+{re.escape(header)}\s*$", txt, flags=re.M)
    if not m:
        return ""
    rest = txt[m.end():]
    nxt = re.search(r"^##\s+", rest, flags=re.M)
    return (rest[:nxt.start()] if nxt else rest).strip()


def split_sections(txt: str) -> list:
    """按 '## N 标题' 切分为结构化小节（按标题切分，非字符位置切分）。"""
    out = []
    for m in re.finditer(r"^##\s+([0-9]+(?:\.[0-9]+)?)\s+(.+)$", txt, flags=re.M):
        start = m.end()
        nxt = re.search(r"^##\s+", txt[start:], flags=re.M)
        body = (txt[start:start + nxt.start()] if nxt else txt[start:]).strip()
        out.append({"number": m.group(1), "title": m.group(2).strip(), "content": body})
    return out


def main() -> int:
    (OUT / "articles").mkdir(parents=True, exist_ok=True)
    srcmap = load_sources()
    manifest_articles, used_sources = [], set()
    errors = []

    for p in sorted(REPORTS.glob("0[1-9]_*.md")):
        txt = p.read_text(encoding="utf-8")
        m = re.search(r"<!-- ARTICLE_END:(A\d\d) -->", txt)
        if not m:
            errors.append(f"{p.name}: 缺 ARTICLE_END 标记")
            continue
        sid = m.group(1)

        title = ""
        for line in txt.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
        abstract = section(txt, "摘要")
        kw_m = re.search(r"^\*\*关键词\*\*：(.*)$", txt, flags=re.M)
        keywords = [k.strip() for k in kw_m.group(1).split("；")] if kw_m else []
        fs_m = re.search(r"<!-- FRONTEND_SUMMARY -->\n(.*?)\n<!-- /FRONTEND_SUMMARY -->",
                         txt, flags=re.S)
        frontend_summary = fs_m.group(1).strip() if fs_m else ""

        # 引用的表/图（从文章文本中按文件名引用提取；文件必须存在）
        tables = sorted({t for t in re.findall(r"`([A-Za-z0-9_]+\.csv)`", txt)
                         if (TABLES / t).exists()})
        figures = sorted({f for f in re.findall(r"`([A-Za-z0-9_\-]+\.png)`", txt)
                          if (FIGURES / f).exists()})
        # 来源（按 source_id 引用提取）
        sids = sorted(set(re.findall(r"\bSRC-[A-Za-z0-9\u4e00-\u9fff\-]+", txt)))
        expanded = []
        for s in sids:
            if s.endswith("-"):          # 通配符写法（如 SRC-DIST-*）→ 展开为全部匹配来源
                expanded.extend(k for k in srcmap if k.startswith(s))
            else:
                expanded.append(s)
        sids = sorted(set(expanded))
        for s in sids:
            if s not in srcmap:
                errors.append(f"{sid}: 引用了未登记的 source_id {s}")
            else:
                used_sources.add(s)

        obj = {
            "id": sid,
            "slug": SLUG[sid],
            "title": title,
            "abstract": abstract,
            "frontend_summary": frontend_summary,
            "keywords": keywords,
            "research_questions": [],       # 由 research_registry 填充于下方
            "data_scope": {},
            "methods": [],
            "key_findings": [],
            "sections": split_sections(txt),
            "limitations": [ln.strip("- ").strip()
                            for ln in section(txt, "6 研究局限").splitlines() if ln.strip()],
            "conclusion": section(txt, "7 结论"),
            "figures": [{"file": f} for f in figures],
            "tables": [{"file": t} for t in tables],
            "source_ids": sids,
            "status": "ACCEPTED",
        }
        # data_scope / methods 从固定小节提取
        ds = section(txt, "2 数据与变量")
        obj["data_scope"] = {"summary": ds} if ds else {}
        obj["methods"] = [{"summary": section(txt, "3 研究方法")}] if section(txt, "3 研究方法") else []
        # key_findings：从「4 研究结果」按小节标题抽取条目名（内容保留在 sections 中）
        res = section(txt, "4 研究结果")
        obj["key_findings"] = [{"heading": h.strip()}
                               for h in re.findall(r"^###\s+(.+)$", res, flags=re.M)]

        (OUT / "articles" / f"{sid}.json").write_text(
            json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
        manifest_articles.append({"id": sid, "slug": SLUG[sid], "title": title,
                                 "file": f"articles/{sid}.json",
                                 "n_sections": len(obj["sections"]),
                                 "n_sources": len(sids), "status": "ACCEPTED"})

    # research_questions 从 registry 回填
    reg = ROOT / "plan" / "research_registry.csv"
    if reg.exists():
        with reg.open(encoding="utf-8-sig") as fh:
            rq = {r["study_id"]: r["research_question"] for r in csv.DictReader(fh)}
        for a in manifest_articles:
            fp = OUT / a["file"]
            o = json.loads(fp.read_text(encoding="utf-8"))
            if o["id"] in rq:
                o["research_questions"] = [rq[o["id"]]]
            fp.write_text(json.dumps(o, ensure_ascii=False, indent=1), encoding="utf-8")

    # 前端来源（只用公开字段）
    src_out = []
    for s in sorted(used_sources):
        r = srcmap[s]
        src_out.append({
            "source_id": r["source_id"],
            "title": r["title"],
            "publisher": r["publisher"],
            "authors": r.get("authors", ""),
            "type": SRC_TYPE_MAP.get(r["source_type"], r["source_type"]),
            "url": r["public_url"],
            "data_period": r.get("data_period", ""),
            "published_date": r.get("published_date", ""),
            "accessed_at": r.get("accessed_at", ""),
            "source_grade": r.get("source_grade", ""),
            "verification_status": r.get("verification_status", ""),
        })
    (OUT / "sources.json").write_text(json.dumps(src_out, ensure_ascii=False, indent=1),
                                     encoding="utf-8")
    (OUT / "manifest.json").write_text(json.dumps({
        "city": "沈阳", "project": "shenyang_research_v2",
        "n_articles": len(manifest_articles), "articles": manifest_articles,
        "n_sources": len(src_out), "generated_by": "30_export_frontend.py",
        "article_end_marker_required": True, "no_substring_summary": True,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"[OK] 导出文章 {len(manifest_articles)} 篇；来源 {len(src_out)} 条")
    if errors:
        print("[ERRORS]")
        for e in errors:
            print("  ", e)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
