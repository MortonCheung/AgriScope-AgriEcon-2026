#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Data Foundation v1 · P9 冻结快照（不复制大数据，只记元数据）"""
from __future__ import annotations
import csv, hashlib, json
from pathlib import Path
import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
# 结构收口后：原 data_foundation 拆分为 data/{processed,model_ready,metadata,reports}
SCAN_LAYERS = [ROOT / "data" / "processed", ROOT / "data" / "model_ready",
               ROOT / "data" / "metadata", ROOT / "data" / "reports"]
SNAP = ROOT / "data" / "metadata" / "snapshots" / "foundation_v1"
SNAP.mkdir(parents=True, exist_ok=True)
AD = "2026-10-04"


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def main():
    rows = []
    files = []
    for layer in SCAN_LAYERS:
        files += [p for p in sorted(layer.rglob("*")) if p.is_file()]
    for p in files:
        if "snapshots" in str(p):
            continue
        if p.suffix.lower() not in (".parquet", ".csv", ".json"):
            continue
        rec = {"file": str(p.relative_to(ROOT)), "type": p.suffix.lstrip("."),
               "size_bytes": p.stat().st_size, "sha256": sha(p), "rows": "", "columns": "", "date_range": "", "source": "data"}
        try:
            if p.suffix == ".parquet":
                df = pd.read_parquet(p); rec["rows"] = len(df); rec["columns"] = len(df.columns)
            elif p.suffix == ".csv":
                df = pd.read_csv(p, dtype=str, low_memory=False); rec["rows"] = len(df); rec["columns"] = len(df.columns)
        except Exception:
            pass
        rows.append(rec)
    with (SNAP / "FOUNDATION_V1_MANIFEST.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["file", "type", "size_bytes", "sha256", "rows", "columns", "date_range", "source"])
        w.writeheader(); w.writerows(rows)
    summary = {"version": "AGRISCOPE_DATA_FOUNDATION_V1", "frozen_at": AD, "n_files": len(rows),
               "n_parquet": sum(1 for r in rows if r["type"] == "parquet"),
               "total_rows": sum(int(r["rows"]) for r in rows if str(r["rows"]).isdigit())}
    (SNAP / "FOUNDATION_V1_SNAPSHOT.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] snapshot: {len(rows)} files, parquet={summary['n_parquet']}, total_rows={summary['total_rows']}")


if __name__ == "__main__":
    main()
