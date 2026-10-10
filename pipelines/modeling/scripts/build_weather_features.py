# -*- coding: utf-8 -*-
"""一键重建：气象/土壤特征（六城）→ data/features/weather_features_*.parquet"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from decision_engine.features.weather_features import build_all  # noqa: E402

if __name__ == "__main__":
    build_all()