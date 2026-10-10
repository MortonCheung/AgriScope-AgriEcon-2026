# -*- coding: utf-8 -*-
"""把 monorepo 根 data/research 的研究资产发布为前端研究产品契约（runtime/research/product）。

设计原则（见项目架构规范「标准数据流」）：
  研发态：monorepo 根 data/research 保存六城与跨城市研究**完整原始产物**（唯一源，只读）；
  发布态：由本脚本挑选前端真正消费的最小集合写入 runtime/research/product/，
          并生成轻量总索引 runtime/research/research_catalog.json。
  **表/图采用超集复制**：article.json 声明的之外，模块目录下全部 tables/*.csv 与
  figures/*.png 一并发布，以确保前端策展树（如 shenyang-tree.json）引用的表/图
  也能命中，避免 404；研究源里不存在的文件不做任何伪造。
  runtime/research 下只保留「产品件」（product/ + research_catalog.json），
  不再保留任何研究原始副本；原始源始终只有 data/research 一份。
本脚本只读取源目录、只复制/生成不删除；幂等，可反复执行。

产物（对每个城市目录，含 cross_city）：
  product/<city>/manifest.json      产品清单
  product/<city>/articles/<id>.json 逐字节原样复制自模块 article.json
  product/<city>/sources.json       由 sources/source_registry.csv 转 JSON
  product/<city>/tables/<file>      模块目录内全部表格（平铺，**超集**）
  product/<city>/figures/<file>     模块目录内全部图（平铺，**超集**）
  product/<city>/sync-report.json   本次同步审计报告
  product/<city>/references.md      来源清单（源存在则原样复制，否则据 registry 生成）
  research_catalog.json             全城市轻量总索引（不含正文）

用法：
    cd AgriScope && python3 pipelines/publishing/publish_research.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
from pathlib import Path


def project_root() -> Path:
    """向上查找同时含 AgriScope/、data/、models/ 的 monorepo 根。"""
    env = os.environ.get("PROJECT_ROOT")
    if env:
        return Path(env).resolve()
    for p in Path(__file__).resolve().parents:
        if (p / "AgriScope").is_dir() and (p / "data").is_dir() and (p / "models").is_dir():
            return p
    raise RuntimeError("无法定位 monorepo 根目录")


ROOT = project_root()
AGRISCOPE = ROOT / "AgriScope"
# 研究源：monorepo 根 data/research（完整、只读）；不再从 runtime 内的副本读取。
SOURCE_ROOT = ROOT / "data" / "research"
# 发布落点：AgriScope/runtime/research（只放产品件，不放研究原始副本）。
RUNTIME_RESEARCH = AGRISCOPE / "runtime" / "research"
OUT_ROOT = RUNTIME_RESEARCH / "product"
CATALOG_PATH = RUNTIME_RESEARCH / "research_catalog.json"

GENERATED_BY = "AgriScope/pipelines/publishing/publish_research.py"

CITY_NAMES = {
    "shenyang": "沈阳",
    "chaoyang": "朝阳",
    "jinzhou": "锦州",
    "dalian": "大连",
    "dandong": "丹东",
    "tieling": "铁岭",
    "cross_city": "跨城市",
}
# 只处理这 7 个城市（从真实目录扫描后按此顺序输出）
CITY_ORDER = ["shenyang", "chaoyang", "jinzhou", "dalian", "dandong", "tieling", "cross_city"]

# sources.json 每条固定键；CSV 缺失列留空，不编造
SOURCE_FIELDS = [
    "source_id", "title", "publisher", "authors", "type", "url",
    "data_period", "published_date", "accessed_at", "source_grade", "verification_status",
]
# 各城市 source_registry.csv 表头不完全一致，按语义别名映射
FIELD_ALIASES = {
    "source_id": ["source_id"],
    "title": ["title", "source_name"],
    "publisher": ["publisher", "institution", "org"],
    "authors": ["authors", "author"],
    "type": ["type", "source_type"],
    "url": ["url", "public_url", "source_url"],
    "data_period": ["data_period"],
    "published_date": ["published_date", "publish_date"],
    "accessed_at": ["accessed_at", "access_date"],
    "source_grade": ["source_grade", "quality_grade"],
    "verification_status": ["verification_status", "status"],
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, data) -> None:
    """先写临时文件再 os.replace，保证原子写与幂等。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / (path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / (path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def copy_overwrite(src: Path, dst: Path) -> None:
    """先写临时文件再 os.replace 的逐字节复制（覆盖）。"""
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.parent / (dst.name + ".tmp")
    shutil.copyfile(src, tmp)
    os.replace(tmp, dst)


def copy_verbatim(src: Path, dst: Path) -> str:
    """逐字节复制；同名同内容跳过；同名不同内容报错退出，避免静默覆盖。"""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.is_file():
        if sha256(src) == sha256(dst):
            return "same"
        raise SystemExit(f"[publish_research] 冲突：{dst} 已存在且内容与源 {src} 不同")
    copy_overwrite(src, dst)
    return "copied"


def module_entries(city: str, city_dir: Path):
    """返回 [(article_path, tables_dir, figures_dir)]，按模块 id 升序。

    普通城市：A01…A09 模块目录；
    cross_city：根 article.json（单篇）+ synthesis/article.json。
    """
    entries = []
    if city == "cross_city":
        root_article = city_dir / "article.json"
        if root_article.is_file():
            entries.append((root_article, city_dir / "tables", city_dir / "figures"))
        syn = city_dir / "synthesis"
        if (syn / "article.json").is_file():
            entries.append((syn / "article.json", syn / "tables", syn / "figures"))
    else:
        for d in sorted(p for p in city_dir.iterdir() if p.is_dir()):
            name = d.name
            if len(name) == 3 and name[0] == "A" and name[1:].isdigit():
                art = d / "article.json"
                if art.is_file():
                    entries.append((art, d / "tables", d / "figures"))
    return entries


def load_sources(city_dir: Path):
    """读取 sources/source_registry.csv，转为固定键的 JSON 数组。"""
    csv_path = city_dir / "sources" / "source_registry.csv"
    if not csv_path.is_file():
        return []
    rows = []
    with csv_path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            rec = {}
            for field in SOURCE_FIELDS:
                value = ""
                for alias in FIELD_ALIASES[field]:
                    v = row.get(alias)
                    if v not in (None, ""):
                        value = v
                        break
                rec[field] = value
            rows.append(rec)
    return rows


def load_article(article_path: Path):
    with article_path.open(encoding="utf-8") as f:
        return json.load(f)


def build_references_md(city_name: str, rows) -> str:
    lines = [f"# {city_name}研究来源清单",
             "> 由 source_registry.csv 生成，未做任何补充或改写。"]
    for r in rows:
        lines.append(f'- [{r["source_id"]}] {r["title"]} — {r["url"]}')
    return "\n".join(lines) + "\n"


def list_files(directory: Path):
    """模块目录下存在的文件名集合（不递归子目录）。"""
    if not directory.is_dir():
        return set()
    return {p.name for p in directory.iterdir() if p.is_file()}


def copy_module_assets(tables_dir: Path, figures_dir: Path, out_dir: Path) -> None:
    """把模块目录下**全部** tables/*.csv 与 figures/*.png 复制为产品件（超集）。

    article.json 声明的表/图之外，同样复制模块目录中存在的其它表/图——例如前端
    策展树引用、但 article 未声明的表（如沈阳 A01_trend.csv）。这样前端任何合法
    引用都能在 product 命中，消除 404。研究源里不存在的文件不复制、不伪造；
    cross_city 根与 synthesis 的同名同内容文件由 copy_verbatim 幂等跳过。
    """
    if tables_dir.is_dir():
        for src in sorted(tables_dir.glob("*.csv")):
            copy_verbatim(src, out_dir / "tables" / src.name)
    if figures_dir.is_dir():
        for src in sorted(figures_dir.glob("*.png")):
            copy_verbatim(src, out_dir / "figures" / src.name)


def published_module(city_dir: Path, source: Path, tables_dir: Path, figures_dir: Path,
                     out_dir: Path, referenced_tables: set, referenced_figures: set):
    """复制单个模块文章/表格/图，返回该模块的产物元数据。"""
    article = load_article(source)
    module_id = article.get("id")
    table_files = [t.get("file") for t in (article.get("tables") or [])
                   if isinstance(t, dict) and t.get("file")]
    figure_files = [f.get("file") for f in (article.get("figures") or [])
                    if isinstance(f, dict) and f.get("file")]

    # article.json 逐字节原样复制
    copy_overwrite(source, out_dir / "articles" / f"{module_id}.json")

    # 记录 article 声明的表/图（用于 sync-report 的「存在但未引用」与「引用但缺失」口径）
    referenced_tables.update(table_files)
    referenced_figures.update(figure_files)

    # 超集复制：模块目录下全部表/图（不止 article 声明）
    copy_module_assets(tables_dir, figures_dir, out_dir)

    return {
        "id": module_id,
        "slug": article.get("slug"),
        "title": article.get("title"),
        "file": f"articles/{module_id}.json",
        "n_sections": len(article.get("sections") or []),
        "n_sources": len(article.get("source_ids") or []),
        "status": article.get("status"),
        "table_files": table_files,
        "figure_files": figure_files,
        "tables_dir": tables_dir,
        "figures_dir": figures_dir,
        "frontend_summary": article.get("frontend_summary") or article.get("abstract") or None,
        "explorer_available": "explorer" in article,
        "source_ids": list(article.get("source_ids") or []),
    }


def publish_city(cid: str, source_root: Path, out_root: Path) -> dict:
    city_dir = source_root / cid
    city_name = CITY_NAMES[cid]
    out_dir = out_root / cid
    out_dir.mkdir(parents=True, exist_ok=True)

    modules = []
    present_tables, present_figures = set(), set()
    referenced_tables, referenced_figures = set(), set()

    for article_path, tables_dir, figures_dir in module_entries(cid, city_dir):
        modules.append(published_module(city_dir, article_path, tables_dir, figures_dir,
                                        out_dir, referenced_tables, referenced_figures))
        present_tables |= list_files(tables_dir)
        present_figures |= list_files(figures_dir)

    sources = load_sources(city_dir)

    # manifest.json
    manifest = {
        "city": city_name,
        "project": f"{cid}_research_product",
        "n_articles": len(modules),
        "articles": [
            {
                "id": m["id"],
                "slug": m["slug"],
                "title": m["title"],
                "file": m["file"],
                "n_sections": m["n_sections"],
                "n_sources": m["n_sources"],
                "status": m["status"],
            }
            for m in modules
        ],
        "n_sources": len(sources),
        "generated_by": GENERATED_BY,
        "article_end_marker_required": True,
        "no_substring_summary": True,
    }
    write_json(out_dir / "manifest.json", manifest)

    # sources.json
    write_json(out_dir / "sources.json", sources)

    # references.md：源存在则原样复制，否则据 registry 生成纯事实清单
    ref_src = city_dir / "references.md"
    if ref_src.is_file():
        copy_overwrite(ref_src, out_dir / "references.md")
    else:
        write_text(out_dir / "references.md", build_references_md(city_name, sources))

    # sync-report.json
    tables_missing, figures_missing = [], []
    for m in modules:
        for name in m["table_files"]:
            if not (m["tables_dir"] / name).is_file():
                tables_missing.append(name)
        for name in m["figure_files"]:
            if not (m["figures_dir"] / name).is_file():
                figures_missing.append(name)

    sync_report = {
        "generatedBy": GENERATED_BY,
        "sourceRoot": str(source_root.relative_to(ROOT)),
        "outRoot": str(out_root.relative_to(ROOT)),
        "articles": [
            {
                "id": m["id"],
                "title": m["title"],
                "sections": m["n_sections"],
                "sources": m["n_sources"],
                "figures": m["figure_files"],
                "tables": m["table_files"],
            }
            for m in modules
        ],
        "counts": {
            "articles": len(modules),
            "sources": len(sources),
            # 实际写入 product 的表/图数量（超集：含 article 未声明但存在/被前端引用的文件）
            "figuresCopied": len(list_files(out_dir / "figures")),
            "tablesCopied": len(list_files(out_dir / "tables")),
        },
        "assets": {
            "figuresReferencedButMissing": sorted(figures_missing),
            "tablesReferencedButMissing": sorted(tables_missing),
            "tablesPresentButUnreferenced": sorted(present_tables - referenced_tables),
            "figuresPresentButUnreferenced": sorted(present_figures - referenced_figures),
        },
        "exportContracts": {
            "article_end_marker_required": True,
            "no_substring_summary": True,
        },
    }
    write_json(out_dir / "sync-report.json", sync_report)

    print(f"  [OK] {cid:<10} city={city_name}  modules={len(modules)}  sources={len(sources)}  "
          f"tables={sync_report['counts']['tablesCopied']}  figures={sync_report['counts']['figuresCopied']}")

    return {
        "city": cid,
        "city_name": city_name,
        "n_modules": len(modules),
        "n_sources": len(sources),
        "modules": modules,
    }


def main() -> int:
    print(f"[publish_research] ROOT   = {ROOT}")
    print(f"[publish_research] SOURCE = {SOURCE_ROOT.relative_to(ROOT)}  (研究源，完整只读)")
    print(f"[publish_research] OUT    = {OUT_ROOT.relative_to(ROOT)}")

    cities = [c for c in CITY_ORDER if (SOURCE_ROOT / c).is_dir()]
    catalog_cities = []
    total_modules = 0

    for cid in cities:
        city_meta = publish_city(cid, SOURCE_ROOT, OUT_ROOT)
        total_modules += city_meta["n_modules"]
        catalog_cities.append(city_meta)

    # 轻量总索引（不含正文）
    catalog = {
        "schema_version": "1.0",
        "generated_by": GENERATED_BY,
        "n_cities": len(catalog_cities),
        "n_modules": total_modules,
        "cities": [
            {
                "city": cm["city"],
                "city_name": cm["city_name"],
                "modules": [
                    {
                        "module_id": m["id"],
                        "title": m["title"],
                        "status": m["status"],
                        "summary": m["frontend_summary"],
                        "article_path": f"product/{cm['city']}/{m['file']}",
                        "explorer_available": m["explorer_available"],
                        "tables": m["table_files"],
                        "figures": m["figure_files"],
                        "sources": m["source_ids"],
                    }
                    for m in cm["modules"]
                ],
                "n_modules": cm["n_modules"],
                "n_sources": cm["n_sources"],
            }
            for cm in catalog_cities
        ],
    }
    write_json(CATALOG_PATH, catalog)
    print(f"[publish_research] catalog written: {len(catalog_cities)} cities, "
          f"{total_modules} modules -> {CATALOG_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())