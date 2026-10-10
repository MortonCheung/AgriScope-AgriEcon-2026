#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Data Foundation v1 · 一键重建
python3 AgriScope/pipelines/data_foundation/run_all.py
只读既有数据 → 盘点 → 维度 → 标准化 → 整合 → QC → 需求 → 冲突 → 缺口补充 → model-ready → 快照
"""
import subprocess, sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
STEPS = [
    ("盘点 inventory", "build_inventory.py"),
    ("年鉴解析 yearbook", "parse_yearbook_sy.py"),
    ("年鉴QC qc_yearbook", "qc_yearbook.py"),
    ("公报解析 bulletins", "parse_bulletins.py"),
    ("定点补数 gapfill_final", "gapfill_final.py"),
    ("维度主数据 dimensions", "build_dimensions.py"),
    ("标准化 standardized", "build_standardized.py"),
    ("语义治理 annotate", "annotate_governance.py"),
    ("整合 integrated", "build_integrated.py"),
    ("缺口补充 gapfill", "build_gapfill.py"),
    ("来源冲突 conflicts", "build_source_conflicts.py"),
    ("质量与覆盖 QC", "run_qc.py"),
    ("需求矩阵 requirements", "build_requirements.py"),
    ("model-ready", "build_model_ready.py"),
    ("旧层迁移审计 legacy", "audit_legacy_layers.py"),
    ("冻结快照 snapshot", "build_snapshot.py"),
]


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    for name, script in STEPS:
        if only and only not in script:
            continue
        print(f"\n=== {name} ===", flush=True)
        r = subprocess.run([sys.executable, str(ROOT / "AgriScope/pipelines/data_foundation" / script)], cwd=str(ROOT))
        if r.returncode != 0:
            print(f"[FAIL] {script} rc={r.returncode}")
    print("\n[OK] run_all 完成")


if __name__ == "__main__":
    main()
