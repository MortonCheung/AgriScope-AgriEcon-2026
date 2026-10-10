"""paths.py — 六城研究流水线唯一路径来源。

只读输入：data/model_ready/snapshots（城市数据包）、data/processed、data/model_ready
研究输出：data/research/<city>/<module>/ 与 data/research/cross_city/
"""
from __future__ import annotations

from pathlib import Path

# AgriScope/pipelines/research/lib/paths.py -> repo root
_LIB = Path(__file__).resolve().parent          # .../research/lib
RESEARCH_PIPE = _LIB.parent                      # .../research
AGRISCOPE = RESEARCH_PIPE.parents[1]             # .../AgriScope
ROOT = AGRISCOPE.parent                          # 大数据分析/

# 只读输入（迁移后：城市数据包位于根 data/model_ready/snapshots）
SNAP = ROOT / "data" / "model_ready" / "snapshots" / "v1" / "city_data"
PROCESSED = ROOT / "data" / "processed"
MODEL_READY = ROOT / "data" / "model_ready"

# 研究输出
RESEARCH = ROOT / "data" / "research"

# 配置
CONFIG = RESEARCH_PIPE / "config"

CITIES_ALL = ["shenyang", "chaoyang", "dalian", "dandong", "jinzhou", "tieling"]
CITIES_FIVE = ["chaoyang", "dalian", "dandong", "jinzhou", "tieling"]


def city_data_dir(city: str) -> Path:
    return SNAP / city / "data"


def city_out_dir(city: str, module: str) -> Path:
    """研究输出目录（自动建 tables/figures/metrics）。"""
    base = RESEARCH / city / module
    for sub in ("tables", "figures", "metrics"):
        (base / sub).mkdir(parents=True, exist_ok=True)
    return base


def cross_city_dir(module: str) -> Path:
    base = RESEARCH / "cross_city" / module
    for sub in ("tables", "figures", "metrics"):
        (base / sub).mkdir(parents=True, exist_ok=True)
    return base