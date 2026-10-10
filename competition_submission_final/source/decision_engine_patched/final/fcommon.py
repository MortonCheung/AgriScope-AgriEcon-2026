# -*- coding: utf-8 -*-
"""Final Model 层公共工具：路径、版本、IO、审计表常量。"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from decision_engine.common import ROOT, DE, ensure_dir, sha256_file, write_json, read_json

# ---------------------------------------------------------------- 版本
MODEL_VERSION = "final_v1"
DATA_VERSION = "final_v1"
SNAPSHOT_DIR = DE / "data" / "snapshots" / "final_v1"
MODEL_READY = ROOT / "data" / "model_ready"
GOV_DIR = ROOT / "data" / "metadata" / "governance"

REPORTS_DIR = DE / "reports" / "final"
MANIFEST_DIR = DE / "data" / "manifests" / "final"
FINAL_MODELS_DIR = DE / "models" / "final"
FINAL_EVAL_DIR = DE / "evaluation" / "final"

# 沈阳 P0：10 种批发蔬菜
SHENYANG_CROPS = ["土豆", "西红柿", "黄瓜", "韭菜", "青椒", "尖椒", "茄子", "芹菜", "芸豆", "甘蓝"]

# price_level 八类（治理口径，严禁混用）
PRICE_LEVELS = ["wholesale", "market_average", "retail", "retail_market",
                "supermarket", "farm_gate", "purchase", "other"]

# 支持的城市分层
CITY_TIERS = {
    "沈阳": "full_model",          # wholesale 单一来源，10 蔬菜稠密
    "朝阳": "extended_model",      # market_average 单一主源（发改委全市均价）
    "锦州": "weak_model",          # 多 level（OCR 转录），仅弱化/降级
    "大连": "insufficient_market_data",
    "铁岭": "insufficient_market_data",
    "丹东": "insufficient_market_data",
}


def ensure_final_dirs() -> None:
    for p in (REPORTS_DIR, MANIFEST_DIR, FINAL_MODELS_DIR, FINAL_EVAL_DIR, SNAPSHOT_DIR):
        ensure_dir(p)


def md5_of_frame(df: pd.DataFrame) -> str:
    """稳定的内容哈希（列排序 + 行排序）。"""
    h = hashlib.md5()
    cols = sorted(df.columns)
    sub = df[cols]
    try:
        sub = sub.sort_values(cols, kind="mergesort")
    except Exception:
        pass
    h.update(",".join(cols).encode("utf-8"))
    h.update(pd.util.hash_pandas_object(sub, index=False).values.tobytes())
    return h.hexdigest()


def load_gov(name: str) -> pd.DataFrame:
    return pd.read_csv(GOV_DIR / name)


def now_stamp() -> str:
    return pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")


def git_fingerprint() -> str:
    """代码指纹：models/src 下所有 .py 的内容哈希。"""
    h = hashlib.sha256()
    files = sorted((DE / "src").rglob("*.py"))
    for f in files:
        h.update(f.name.encode())
        h.update(f.read_bytes())
    return h.hexdigest()[:16]