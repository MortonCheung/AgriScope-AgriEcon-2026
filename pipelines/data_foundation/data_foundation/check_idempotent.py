#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Data Foundation · §50 幂等性校验
对关键输出计算 sha256 + 行数，输出 manifest 供两次运行比对。
用法：python3 check_idempotent.py out.csv
"""
import hashlib, sys, csv
from pathlib import Path
import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
TARGETS = []
for sub in ["processed", "model_ready", "metadata/quality", "metadata/requirements", "metadata/governance", "metadata/inventory"]:
    TARGETS += sorted((ROOT / "data" / sub).rglob("*.parquet"))
    TARGETS += sorted((ROOT / "data" / sub).rglob("*.csv"))


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data/metadata/snapshots/idempotent_manifest.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for p in TARGETS:
        try:
            h = hashlib.sha256(p.read_bytes()).hexdigest()
        except Exception:
            h = ""
        n = ""
        try:
            n = len(pd.read_parquet(p)) if p.suffix == ".parquet" else len(pd.read_csv(p, dtype=str, low_memory=False))
        except Exception:
            n = ""
        rows.append({"file": str(p.relative_to(ROOT)), "sha256": h, "rows": n})
    with out.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["file", "sha256", "rows"]); w.writeheader(); w.writerows(rows)
    print(f"[OK] {out} ：{len(rows)} 个文件")


if __name__ == "__main__":
    main()
