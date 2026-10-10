# -*- coding: utf-8 -*-
"""LLM 层公共：路径 / 稳定哈希 / 规范化 JSON。"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

# 统一 env 加载（系统环境变量优先，backend/.env 兜底）：LLM Provider 只读 os.environ，
# 因此这里必须在任何 provider 读取之前执行；路径按仓库根解析，与 cwd 无关。
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from agriscope_env import load_env  # noqa: E402

load_env()

from decision_engine.common import ROOT, DE, ensure_dir, write_json, read_json  # noqa: E402

LLM_DIR = _REPO_ROOT / "llm"       # 迁移后 llm/ 仍位于 AgriScope 仓内（不随 models/data 迁出）
LLM_ARTIFACTS = LLM_DIR / "artifacts"
LLM_CACHE = LLM_ARTIFACTS / "cache"
LLM_PACKETS = LLM_ARTIFACTS / "packets"
LLM_RESULTS = LLM_ARTIFACTS / "results"
LLM_REPORTS = LLM_DIR / "reports"
PROMPTS_DIR = LLM_DIR / "prompts"

# 单位口径（严禁分叉；与 inference.py 的 CNY/kg 一致）
UNIT = "CNY/kg"
PRICE_LEVEL = "wholesale"


def now_iso() -> str:
    return pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")


def ensure_llm_dirs() -> None:
    for p in (LLM_ARTIFACTS, LLM_CACHE, LLM_PACKETS, LLM_RESULTS, LLM_REPORTS):
        ensure_dir(p)


def _round_floats(obj: Any, ndigits: int = 6) -> Any:
    """递归把 float 归一到固定精度，消除跨进程浮点漂移（determinism 前提）。"""
    if isinstance(obj, float):
        if obj != obj or obj in (float("inf"), float("-inf")):
            return None
        return round(obj, ndigits)
    if isinstance(obj, dict):
        return {k: _round_floats(v, ndigits) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_round_floats(v, ndigits) for v in obj]
    return obj


def canonical_json(obj: Any) -> str:
    """规范化 JSON：键排序、无多余空白、浮点定精度、不写入任何运行时刻。"""
    return json.dumps(_round_floats(obj), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, default=str)


def stable_hash(obj: Any, n: int = 16) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()[:n]


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_csv_artifact(df, name: str) -> Path:
    ensure_llm_dirs()
    p = LLM_ARTIFACTS / name
    df.to_csv(p, index=False, encoding="utf-8-sig")
    return p


def write_report(text: str, name: str) -> Path:
    ensure_llm_dirs()
    p = LLM_REPORTS / name
    p.write_text(text, encoding="utf-8")
    return p


def read_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def prompt_meta(name: str) -> dict:
    p = PROMPTS_DIR / name
    return {"prompt_version": name.replace(".md", ""),
            "prompt_hash": file_hash(p)[:16]}


__all__ = ["ROOT", "DE", "LLM_DIR", "LLM_ARTIFACTS", "LLM_CACHE", "LLM_PACKETS",
           "LLM_RESULTS", "LLM_REPORTS", "PROMPTS_DIR", "UNIT", "PRICE_LEVEL",
           "now_iso", "ensure_llm_dirs", "canonical_json", "stable_hash",
           "file_hash", "read_prompt", "prompt_meta", "write_json", "read_json", "ensure_dir",
           "write_csv_artifact", "write_report"]