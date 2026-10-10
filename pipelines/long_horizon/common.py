# -*- coding: utf-8 -*-
"""Long-Horizon 公共：路径 / 常量 / 只读加载冻结数据。"""
from __future__ import annotations

from pathlib import Path
from typing import List

import pandas as pd

from decision_engine.common import ROOT, DE, ensure_dir, sha256_file, write_json, read_json
from decision_engine.final.fcommon import SHENYANG_CROPS, SNAPSHOT_DIR

# ---------------------------------------------------------------- 路径
LH_DIR = DE / "long_horizon"
LH_ARTIFACTS = LH_DIR / "artifacts"          # 程序输出（csv/json/parquet）
LH_REPORTS = LH_DIR / "reports"              # 人读报告（md）
PROJECT_REPORTS = DE / "reports" / "final"   # 与 Final 报告同层（但不改冻结文件）

FINAL_DATASET = SNAPSHOT_DIR / "datasets" / "decision_dataset_沈阳.parquet"
FINAL_WEIGHTS_CUTOFF = "2026-09-14"          # 冻结数据最后一天

# ---------------------------------------------------------------- 常量
CITY = "沈阳"
CROPS: List[str] = list(SHENYANG_CROPS)

# 长期 horizon（30 与现有 Final 重叠，仅作对照锚点）
LONG_HORIZONS = [30, 60, 90, 120, 150, 180]
# 探索级 horizon（OOT 非重叠样本 ≤7，不得作为上线依据）
EXPLORATORY_HORIZONS = [150, 180]
# 「N 附近未来 w 日均价」的尾窗
NEAR_WINDOWS = [7, 14, 30]

ANCHOR_YEARS = [2024, 2025, 2026]            # 与 Final 三折一致的 OOT 年


def now_iso() -> str:
    return pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")


def ensure_lh_dirs() -> None:
    for p in (LH_ARTIFACTS, LH_REPORTS):
        ensure_dir(p)


def load_frozen_dataset() -> pd.DataFrame:
    """只读加载冻结的 Final 决策数据集（含已验证 PIT 特征 + 7/14/30/60/90 目标）。"""
    df = pd.read_parquet(FINAL_DATASET)
    df["date"] = pd.to_datetime(df["date"])
    df = df[df["crop"].isin(CROPS)].copy()
    return df.sort_values(["crop", "date"]).reset_index(drop=True)


def dataset_fingerprint() -> str:
    return sha256_file(FINAL_DATASET)[:16]


def write_json_artifact(obj, name: str) -> Path:
    ensure_lh_dirs()
    p = LH_ARTIFACTS / name
    write_json(obj, p)
    return p


def write_csv_artifact(df: pd.DataFrame, name: str) -> Path:
    ensure_lh_dirs()
    p = LH_ARTIFACTS / name
    df.to_csv(p, index=False, encoding="utf-8-sig")
    return p


def write_report(text: str, name: str) -> Path:
    ensure_lh_dirs()
    p = LH_REPORTS / name
    p.write_text(text, encoding="utf-8")
    return p


__all__ = [
    "ROOT", "DE", "LH_DIR", "LH_ARTIFACTS", "LH_REPORTS", "PROJECT_REPORTS",
    "FINAL_DATASET", "FINAL_WEIGHTS_CUTOFF", "CITY", "CROPS",
    "LONG_HORIZONS", "EXPLORATORY_HORIZONS", "NEAR_WINDOWS", "ANCHOR_YEARS",
    "ensure_lh_dirs", "load_frozen_dataset", "dataset_fingerprint", "now_iso",
    "write_json_artifact", "write_csv_artifact", "write_report",
    "ensure_dir", "write_json", "read_json", "sha256_file",
]