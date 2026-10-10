#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Data Foundation v1 · P1 全量盘点
扫描全项目数据资产 → 01_inventory/
产出：ALL_FILES / ALL_TABLES / FILE_SHA256 / DUPLICATE_FILES / DUPLICATE_TABLES /
      SCHEMA_CONFLICTS / SOURCE_CONFLICTS / LEGACY_ASSETS
只读，不修改任何被扫描文件。
"""
from __future__ import annotations
import csv, hashlib, json, os, re, sys
from pathlib import Path
from collections import defaultdict, Counter

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
OUT = ROOT / "data" / "metadata" / "inventory"
OUT.mkdir(parents=True, exist_ok=True)

SCAN_ROOTS = ["data/raw", "data/raw/retained_source/city_data", "data/processed", "data/model_ready", "data/metadata",
              "data/reports", "AgriScope/pipelines/data_foundation", "archive", "models", "reference", "AgriScope"]
EXCLUDE_DIR = {"node_modules", ".git", ".next", "dist", "build", "__pycache__",
               ".pytest_cache", ".venv", "venv", ".cache", "catboost_info"}
EXCLUDE_NAME = {".DS_Store", ".gitkeep", ".gitignore", "Thumbs.db", "package-lock.json"}

TABULAR = {"csv", "tsv", "xls", "xlsx", "parquet", "json", "jsonl", "geojson"}
CATEGORY_KEYS = [
    ("price", "price"), ("volume", "volume"), ("supply", "supply"), ("weather", "weather"),
    ("climate", "climate"), ("soil", "soil"), ("production", "production"), ("area", "production"),
    ("cost", "cost"), ("input", "cost"), ("disaster", "disaster"), ("flood", "disaster"),
    ("pest", "pest"), ("disease", "pest"), ("policy", "policy"), ("demand", "demand"),
    ("population", "demand"), ("cpi", "demand"), ("ndvi", "remote_sensing"), ("evi", "remote_sensing"),
    ("remote", "remote_sensing"), ("insurance", "insurance"), ("irrigation", "water"),
    ("water", "water"), ("cold", "infrastructure"), ("market", "infrastructure"),
    ("logistic", "infrastructure"), ("herding", "evidence"), ("calendar", "calendar"),
    ("phenolog", "calendar"), ("agronom", "calendar"), ("crop", "production"),
]


def classify_category(p: str) -> str:
    s = p.lower()
    for k, v in CATEGORY_KEYS:
        if k in s:
            return v
    return "other"


def classify_layer(p: str) -> str:
    p = p.replace("\\", "/")
    if p.startswith("data/raw/"):
        return "raw"
    if p.startswith("archive/"):
        return "legacy"
    if p.startswith("models/"):
        return "model_workspace"
    if p.startswith("AgriScope/") or p.startswith("reference/"):
        return "frontend"
    if p.startswith("AgriScope/pipelines/data_foundation/"):
        return "tooling"
    if p.startswith("decision_audit/"):
        return "audit"
    if p.startswith("city_data/"):
        parts = p.split("/")
        if len(parts) >= 4 and parts[2] == "data":
            return "canonical"
        if "decision_engine_supplement_v3" in p:
            return "supplement_v3"
        if "decision_engine_supplement_v2" in p:
            return "supplement_v2"
        if "decision_engine_supplement/" in p:
            return "supplement_v1"
        if "final_foundation" in p:
            return "foundation_prev"
        if "/marts/" in p:
            return "marts"
        if "/curated/" in p:
            return "curated"
        if "/staging/" in p:
            return "staging"
        if "/reports/" in p:
            return "reports"
        if "/registries/" in p:
            return "registries"
        if "/research/" in p:
            return "research"
        if "/workspace/" in p:
            return "workspace"
        return "city_other"
    return "other"


def sha256_of(fp: Path, cap: int = 400 * 1024 * 1024):
    h = hashlib.sha256()
    try:
        if fp.stat().st_size > cap:
            return "SKIP_TOO_LARGE"
        with fp.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return "READ_ERROR"


def read_table(p: Path, ext: str):
    """返回 (rows, columns)。失败返回 (None, None)。"""
    try:
        if ext == "csv":
            with p.open(encoding="utf-8-sig", errors="replace", newline="") as fh:
                rd = csv.reader(fh)
                hdr = next(rd, None)
                n = sum(1 for _ in rd)
            return n, (hdr or [])
        if ext == "tsv":
            with p.open(encoding="utf-8-sig", errors="replace") as fh:
                lines = fh.readlines()
            hdr = lines[0].rstrip("\n").split("\t") if lines else []
            return max(0, len(lines) - 1), hdr
        if ext == "parquet":
            import pyarrow.parquet as pq
            md = pq.read_metadata(str(p))
            sch = pq.read_schema(str(p))
            return md.num_rows, list(sch.names)
        if ext in ("xls", "xlsx"):
            import pandas as pd
            xl = pd.ExcelFile(p)
            sheets = xl.sheet_names
            if not sheets:
                return 0, []
            df = xl.parse(sheets[0], nrows=2000)
            return f"{len(sheets)}sheets", [f"sheet:{sheets[0]}"] + [str(c) for c in df.columns[:60]]
        if ext in ("json", "jsonl", "geojson"):
            if p.stat().st_size > 20 * 1024 * 1024:
                return None, None
            if ext == "jsonl":
                n = sum(1 for _ in p.open(encoding="utf-8", errors="replace"))
                return n, []
            d = json.loads(p.read_text(encoding="utf-8", errors="replace"))
            if isinstance(d, list):
                keys = list(d[0].keys())[:60] if d and isinstance(d[0], dict) else []
                return len(d), [str(k) for k in keys]
            if isinstance(d, dict):
                return 1, [str(k) for k in list(d.keys())[:60]]
    except Exception:
        return None, None
    return None, None


def main():
    all_files, tables, sha_rows = [], [], []
    for r in SCAN_ROOTS:
        base = ROOT / r
        if not base.exists():
            continue
        for dp, dns, fns in os.walk(base):
            dns[:] = [d for d in dns if d not in EXCLUDE_DIR]
            for fn in fns:
                if fn in EXCLUDE_NAME:
                    continue
                fp = Path(dp) / fn
                rel = str(fp.relative_to(ROOT))
                ext = fp.suffix.lower().lstrip(".")
                try:
                    st = fp.stat()
                    size, mt = st.st_size, int(st.st_mtime)
                except Exception:
                    size, mt = -1, 0
                sha = sha256_of(fp) if size >= 0 else "READ_ERROR"
                layer, cat = classify_layer(rel), classify_category(rel)
                all_files.append({"file_path": rel, "file_name": fn, "file_type": ext,
                                  "size_bytes": size, "mtime": mt, "source_layer": layer,
                                  "logical_category": cat})
                sha_rows.append({"file_path": rel, "file_sha256": sha, "size_bytes": size})
                if ext in TABULAR:
                    n, cols = read_table(fp, ext)
                    tables.append({"file_path": rel, "file_type": ext, "rows": n,
                                   "n_columns": (len(cols) if cols is not None else None),
                                   "columns": ("|".join(cols)[:2000] if cols else ""),
                                   "source_layer": layer, "logical_category": cat,
                                   "file_sha256": sha})
        print(f"  scanned {r}: cumulative files={len(all_files)}", flush=True)

    def write(name, rows, cols):
        with (OUT / name).open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow(r)
        print(f"[OK] {name}  {len(rows)} 行")

    write("ALL_FILES.csv", all_files,
          ["file_path", "file_name", "file_type", "size_bytes", "mtime", "source_layer", "logical_category"])
    write("ALL_TABLES.csv", tables,
          ["file_path", "file_type", "rows", "n_columns", "columns", "source_layer", "logical_category", "file_sha256"])
    write("FILE_SHA256.csv", sha_rows, ["file_path", "file_sha256", "size_bytes"])

    # 重复文件（按 sha256，排除空/失败）
    by_sha = defaultdict(list)
    for r in sha_rows:
        if r["file_sha256"] not in ("READ_ERROR", "SKIP_TOO_LARGE") and r["size_bytes"] > 0:
            by_sha[r["file_sha256"]].append(r["file_path"])
    dup_files = []
    for sha, paths in by_sha.items():
        if len(paths) > 1:
            paths_sorted = sorted(paths, key=len)
            for p in paths_sorted[1:]:
                dup_files.append({"sha256": sha, "keeper": paths_sorted[0], "duplicate": p,
                                  "n_copies": len(paths), "size_bytes": next(x["size_bytes"] for x in sha_rows if x["file_path"] == p)})
    write("DUPLICATE_FILES.csv", dup_files, ["sha256", "keeper", "duplicate", "n_copies", "size_bytes"])

    # 近似重复表：schema(columns) + rows 相同，按 (n_columns, rows, columns_hash)
    sig = defaultdict(list)
    for t in tables:
        if t["columns"]:
            ch = hashlib.sha256(t["columns"].encode()).hexdigest()[:16]
            sig[(ch, str(t["rows"]))].append(t["file_path"])
    dup_tables = []
    for (ch, rw), paths in sig.items():
        if len(paths) > 1:
            ps = sorted(paths, key=len)
            for p in ps[1:]:
                dup_tables.append({"schema_rows_sig": f"{ch}|{rw}", "keeper": ps[0], "near_duplicate": p, "n_copies": len(paths)})
    write("DUPLICATE_TABLES.csv", dup_tables, ["schema_rows_sig", "keeper", "near_duplicate", "n_copies"])

    # schema 冲突：同一 file_name（不含目录）在不同层出现，且列集合不同
    by_name = defaultdict(list)
    for t in tables:
        if t["columns"]:
            by_name[Path(t["file_path"]).name].append(t)
    schema_conf = []
    for nm, ts in by_name.items():
        colsets = {frozenset(t["columns"].split("|")) for t in ts}
        if len(colsets) > 1:
            schema_conf.append({"file_name": nm, "n_variants": len(colsets),
                                "n_files": len(ts), "layers": ",".join(sorted({t["source_layer"] for t in ts})),
                                "paths": " ; ".join(t["file_path"] for t in ts[:6])})
    write("SCHEMA_CONFLICTS.csv", schema_conf, ["file_name", "n_variants", "n_files", "layers", "paths"])

    # legacy 资产
    leg = [r for r in all_files if r["source_layer"] == "legacy"]
    write("LEGACY_ASSETS.csv", leg, ["file_path", "file_name", "file_type", "size_bytes", "mtime", "source_layer", "logical_category"])

    # 层/类别统计
    print("\n=== 按 source_layer ===")
    for k, v in Counter(r["source_layer"] for r in all_files).most_common():
        print(f"  {k}: {v}")
    print("=== 按 logical_category (top15) ===")
    for k, v in Counter(r["logical_category"] for r in all_files).most_common(15):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
