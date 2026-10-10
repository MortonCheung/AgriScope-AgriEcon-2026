#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Data Foundation · P7 路径依赖审计（任务书 §31/§32）
扫描活跃代码/文档中对旧路径的引用：city_data/ 、reference/marts 、supplement
产出：01_inventory/PATH_DEPENDENCY_AUDIT.csv
"""
from __future__ import annotations
import re, os
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
OUT = ROOT / "data" / "metadata" / "inventory" / "PATH_DEPENDENCY_AUDIT.csv"
EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".md", ".yaml", ".yml"}
SKIP_DIRS = {"node_modules", ".git", ".pytest_cache", "__pycache__", "archive", ".workbuddy",
             "AutogluonModels", "catboost_info", ".ipynb_checkpoints"}
PATTERNS = {
    "data/raw/retained_source/city_data": re.compile(r"city_data/"),
    "marts": re.compile(r"reference/marts"),
    "supplement": re.compile(r"supplement(_v\d)?"),
}


def main():
    rows = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            p = Path(dirpath) / fn
            if p.suffix.lower() not in EXTS:
                continue
            rel = str(p.relative_to(ROOT))
            try:
                txt = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for i, line in enumerate(txt.splitlines(), 1):
                for name, pat in PATTERNS.items():
                    if pat.search(line):
                        rows.append({"source_file": rel, "line_no": i, "pattern": name,
                                     "line": line.strip()[:200]})
    import csv
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["source_file", "line_no", "pattern", "line"])
        w.writeheader(); w.writerows(rows)
    from collections import Counter
    c = Counter(r["pattern"] for r in rows)
    f = Counter(r["source_file"].split("/")[0] for r in rows)
    print("引用总数:", len(rows))
    print("按模式:", dict(c))
    print("按顶层目录:", dict(f))
    print("涉及文件数:", len(set(r["source_file"] for r in rows)))


if __name__ == "__main__":
    main()
