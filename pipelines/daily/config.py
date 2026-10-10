# -*- coding: utf-8 -*-
"""Daily 流水线配置：路径 / 版本 / 来源定义 / 作物清单 / 口径规则。

硬约束（与治理口径严格一致）：
  - ROOT 由本文件位置推导（可用 AGRISCOPE_ROOT 覆盖），禁止硬编码 Mac 路径；
  - 正式支持作物清单来自 **Final Model capability**（capabilities.SHENYANG_CROPS），
    不写死；
  - price_level 分类沿用 data/metadata/governance 既有口径；
  - 业务日期/时间戳统一 Asia/Shanghai。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

# ---------------------------------------------------------------- 路径
ROOT = Path(os.environ.get("PROJECT_ROOT") or next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())).resolve()
DATA_DIR = ROOT / "data"
RAW_DAILY_DIR = DATA_DIR / "raw" / "daily"              # 每日原始证据（新增，不动旧 raw）
PROCESSED_DAILY_DIR = DATA_DIR / "processed" / "daily"
SNAPSHOT_DIR = PROCESSED_DAILY_DIR / "snapshots"
LOG_DIR = PROCESSED_DAILY_DIR / "logs"
MONITOR_JSON = PROCESSED_DAILY_DIR / "monitor" / "status.json"
LOCK_PATH = PROCESSED_DAILY_DIR / ".run.lock"
# Daily 自己持有的 Final Model 输入快照工作区（冻结模型 + 实时输入），不写入 models/
FINAL_INPUT_DIR = PROCESSED_DAILY_DIR / "final_input"

GOV_DIR = DATA_DIR / "metadata" / "governance"
MODEL_READY_DIR = DATA_DIR / "model_ready"
MODELS_DIR = ROOT / "models"

# 模型训练用的 canonical 价格表（只读，绝不改写）
CANONICAL_MARKET_DAILY = MODEL_READY_DIR / "shenyang_core" / "market_daily.parquet"
MODEL_SRC = ROOT / "AgriScope" / "pipelines" / "modeling" / "src"   # decision_engine 包所在目录

# Final Model 冻结产物（只读；迁移后新布局）
FINAL_REPORTS_DIR = MODELS_DIR / "reports" / "final"
FINAL_SNAPSHOT_DIR = DATA_DIR / "model_ready" / "snapshots" / "final_v1"
FINAL_RUN_META = FINAL_REPORTS_DIR / "FINAL_RUN_META.json"
FINAL_OUTPUT_SCHEMA = FINAL_REPORTS_DIR / "FINAL_MODEL_OUTPUT_SCHEMA.json"
FINAL_MODELS_DIR = MODELS_DIR / "short_term" / "final"

# ---------------------------------------------------------------- 版本
DAILY_PIPELINE_VERSION = "1.1.0"     # 本轮封版版本（排错用）
SCHEMA_VERSION = "1.1.0"             # Daily Snapshot schema（前端契约）
SOURCE_PARSER_VERSION = "daily-1.1.0"

# ---------------------------------------------------------------- 城市 / 口径
PRIMARY_CITY = "沈阳"

# 治理口径的 price_level 八类（严禁混用）
PRICE_LEVELS = ["wholesale", "market_average", "retail", "retail_market",
                "supermarket", "farm_gate", "purchase", "other"]

# 价格模型实际使用的口径（Daily 只有同口径才能进入 HRI / 推荐）
MODEL_PRICE_LEVEL = "wholesale"

# ---------------------------------------------------------------- 数据质量状态
QC_OK = "OK"
QC_SUSPECT = "SUSPECT"          # 异常但未确认，不进入 Daily Signal / 模型输入
QC_REJECTED = "REJECTED"
QC_DUPLICATE = "DUPLICATE"

# ---------------------------------------------------------------- Freshness
# 定义基于**来源真实数据日期**，而非脚本运行日期（§17）
FRESH = "FRESH"
DELAYED = "DELAYED"
STALE = "STALE"
MISSING = "MISSING"

FRESH_MAX_AGE = 0               # 数据日期 == 运行日期
DELAYED_MAX_AGE = 2             # 滞后 1~2 天（含周末/节假日空档）
STALE_MAX_AGE = 7               # 滞后 3~7 天
# > STALE_MAX_AGE 记为 MISSING


def freshness_for_age(age_days: int | None) -> str:
    if age_days is None:
        return MISSING
    if age_days <= FRESH_MAX_AGE:
        return FRESH
    if age_days <= DELAYED_MAX_AGE:
        return DELAYED
    if age_days <= STALE_MAX_AGE:
        return STALE
    return MISSING


# ---------------------------------------------------------------- 数据源定义
SOURCE_ID = "SRC-SY-CLZ"
SOURCE_NAME = "沈阳市发展和改革委员会 沈阳菜篮子信息发布平台"
SOURCE_URL = "https://fgw.shenyang.gov.cn/wjgz/clzxxfbpt/"
SOURCE_API = os.environ.get("AGRISCOPE_SY_API", "https://www.lnsyjgjc.com/api/showList")
SOURCE_REFERER = "https://www.lnsyjgjc.com/api/daily"
SOURCE_TIMEZONE = "Asia/Shanghai"

# marketType -> (price_level, 中文市场名, 是否与模型口径可比)
MARKET_TYPES = {
    "1": {"price_level": "wholesale", "market_cn": "批发价格", "model_comparable": True},
    "2": {"price_level": "supermarket", "market_cn": "超市零售", "model_comparable": False},
    "3": {"price_level": "retail_market", "market_cn": "集市零售", "model_comparable": False},
}

# 批发口径每个交易日的期望作物数（Final capability = 10）
# 用于 schema drift fail-loud：结构变化导致数量异常时不得静默判为成功。
EXPECTED_WHOLESALE_CROPS = 10

# 单位换算表（仅做数学可验证的换算，禁止猜测）
UNIT_TO_KG = {
    "元/500g": 2.0, "元/500克": 2.0, "元/斤": 2.0,
    "元/kg": 1.0, "元/公斤": 1.0, "元/千克": 1.0,
}

# volume（成交量）：接口未标注单位 → 一律 UNKNOWN，不参与任何定量计算（§12）
VOLUME_UNIT = "UNKNOWN"
VOLUME_SOURCE_UNIT_UNVERIFIED = True

# 采集参数
HTTP_TIMEOUT = int(os.environ.get("AGRISCOPE_HTTP_TIMEOUT", "30"))
HTTP_RETRIES = int(os.environ.get("AGRISCOPE_HTTP_RETRIES", "3"))
HTTP_SLEEP = float(os.environ.get("AGRISCOPE_HTTP_SLEEP", "0.8"))

# ---------------------------------------------------------------- 作物清单
def supported_crops(city: str = PRIMARY_CITY) -> list[str]:
    """正式支持作物：以 **Final Model capability** 为唯一权威来源。

    读取失败才回退到内置常量，并打印警告（不静默）。
    """
    try:
        import sys
        if str(MODEL_SRC) not in sys.path:
            sys.path.insert(0, str(MODEL_SRC))
        from decision_engine.final import capabilities as CAP  # noqa: PLC0415
        cap = CAP.city_capability(city)
        crops = list(cap.get("crops") or [])
        if crops:
            return sorted(crops)
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] 读取 Final capability 失败({type(exc).__name__}: {exc})，回退内置作物清单")
    return ["土豆", "西红柿", "黄瓜", "韭菜", "青椒", "尖椒", "茄子", "芹菜", "芸豆", "甘蓝"]


def final_versions() -> dict:
    """从 Final RUN_META 读取真实 model_version / data_version（禁止硬编码）。"""
    meta = {}
    try:
        meta = json.loads(FINAL_RUN_META.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        meta = {}
    return {
        "model_version": meta.get("model_version") or "UNKNOWN",
        "data_version": meta.get("data_version") or "UNKNOWN",
        "code_fingerprint": meta.get("code_fingerprint"),
        "final_generated_at": meta.get("generated_at"),
    }


def crop_mapping() -> dict[str, str]:
    """治理层 crop_raw -> crop_standard 映射（exact 规则）。"""
    import csv
    out: dict[str, str] = {}
    p = GOV_DIR / "CROP_MAPPING.csv"
    if p.exists():
        with p.open(encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                raw, std = (row.get("raw_name") or "").strip(), (row.get("standard_name") or "").strip()
                if raw and std:
                    out.setdefault(raw, std)
    return out


def ensure_dirs() -> None:
    for d in (RAW_DAILY_DIR, PROCESSED_DAILY_DIR, SNAPSHOT_DIR, LOG_DIR,
              PROCESSED_DAILY_DIR / "monitor", FINAL_INPUT_DIR):
        d.mkdir(parents=True, exist_ok=True)