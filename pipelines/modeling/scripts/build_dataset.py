# -*- coding: utf-8 -*-
"""
Phase 1 入口：构建 Decision Dataset v1（沈阳 10 蔬菜）。

  python3 decision_engine/scripts/build_dataset.py

输出：
  decision_engine/data/processed/decision_dataset_v1.parquet / .csv
  decision_engine/data/features/price_features_v1.parquet
  decision_engine/data/manifests/join_qc.csv
  decision_engine/data/manifests/feature_dictionary.csv
"""
from __future__ import annotations
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from decision_engine.common import de_path, ensure_dir  # noqa: E402
from decision_engine.data.build_dataset import build_base  # noqa: E402
from decision_engine.features.build_features import (  # noqa: E402
    add_price_features, add_targets, feature_dictionary)


def main():
    base, qc = build_base()
    print(f"[base] rows={len(base)} cols={len(base.columns)}")
    print(qc.T.to_string())

    feats = add_price_features(base)
    print(f"[features] rows={len(feats)} cols={len(feats.columns)}")

    ds = add_targets(feats)
    print(f"[targets] rows={len(ds)} cols={len(ds.columns)}")

    processed = ensure_dir(de_path("data", "processed"))
    features_dir = ensure_dir(de_path("data", "features"))
    manifests = ensure_dir(de_path("data", "manifests"))

    ds.to_parquet(processed / "decision_dataset_v1.parquet", index=False)
    ds.to_csv(processed / "decision_dataset_v1.csv", index=False, encoding="utf-8-sig")
    feats.to_parquet(features_dir / "price_features_v1.parquet", index=False)
    qc.to_csv(manifests / "join_qc.csv", index=False)
    feature_dictionary().to_csv(manifests / "feature_dictionary.csv", index=False, encoding="utf-8-sig")

    # 快速质量摘要
    tcol = "target_mean_price_next_30d"
    print(f"\ntarget 可用率:")
    for c in ["target_mean_price_next_7d", "target_mean_price_next_14d", "target_mean_price_next_30d"]:
        print(f"  {c}: {ds[c].notna().mean():.3f}")
    print(f"\nseasonal_feature_available: {ds['seasonal_feature_available'].mean():.3f}")
    print("outputs -> decision_engine/data/processed/decision_dataset_v1.parquet")


if __name__ == "__main__":
    main()