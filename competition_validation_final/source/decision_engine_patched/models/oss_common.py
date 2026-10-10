# -*- coding: utf-8 -*-
"""开源评估公共工具：统一 Benchmark CSV 累加。"""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import pandas as pd

from decision_engine.common import de_path, ensure_dir

OSS_DIR = de_path("evaluation", "open_source")
BENCH_CSV = OSS_DIR / "OPEN_SOURCE_MODEL_BENCHMARK.csv"
COLS = ["library", "model", "version", "city", "crop", "target", "route",
        "MAE", "RMSE", "sMAPE", "WAPE", "coverage", "interval_width",
        "runtime_sec", "artifact_size_mb", "status", "reason", "updated_at"]


def upsert_benchmark(rows: List[Dict]) -> pd.DataFrame:
    """按 (library, model, city, crop, target, route) upsert。"""
    ensure_dir(OSS_DIR)
    new = pd.DataFrame(rows)
    if BENCH_CSV.exists():
        old = pd.read_csv(BENCH_CSV)
        old = old[~old.set_index(["library", "model", "city", "crop", "target", "route"]).index.isin(
            new.set_index(["library", "model", "city", "crop", "target", "route"]).index)]
        out = pd.concat([old, new], ignore_index=True)
    else:
        out = new
    for c in COLS:
        if c not in out.columns:
            out[c] = None
    out["updated_at"] = datetime.now().isoformat(timespec="seconds")
    out = out[COLS + [c for c in out.columns if c not in COLS]]
    out.to_csv(BENCH_CSV, index=False, encoding="utf-8-sig")
    print(f"[oss] benchmark rows={len(out)} -> {BENCH_CSV}")
    return out


def pkg_version(name: str) -> str:
    try:
        import importlib
        return getattr(importlib.import_module(name), "__version__", "unknown")
    except Exception:
        return "not_installed"