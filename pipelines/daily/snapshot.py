# -*- coding: utf-8 -*-
"""Daily Snapshot：机器可读、版本化、带契约校验、可被前端直接消费。

    data/processed/daily/snapshots/daily/<date>.json   每日历史快照（保留，可幂等更新）
    data/processed/daily/snapshots/latest.json         指向最新（失败/非法时不推进）
    data/processed/daily/monitor/status.json           监控状态

关键原则：
  - 数据日期必须真实：latest_data_date 反映来源真实最新价格日期，不写成运行日（§17）；
  - 抓取失败不得污染旧数据：不复制昨日价格，标 FAILED 且不覆盖 latest.json（§21 §27）；
  - 原子写入：任何写入先写临时文件再原子替换（§20）；
  - 契约校验：非法 Snapshot 不得替换 latest.json（§50）；
  - 版本真实：model_version 读 Final RUN_META，不硬编码（§51）。
"""
from __future__ import annotations

import hashlib
from typing import Any

import pandas as pd

from . import config as C
from . import io_utils as IO
from .final_adapter import (
    LEVELS, MS_FINAL, MS_LEGACY, MS_PARTIAL, MS_UNAVAILABLE,
)

SNAPSHOT_DAILY_DIR = C.SNAPSHOT_DIR / "daily"
LATEST_JSON = C.SNAPSHOT_DIR / "latest.json"

# 契约：顶层必需字段
REQUIRED_TOP = ["schema_version", "daily_pipeline_version", "data_version", "model_version",
                "generated_at", "date", "city", "status", "latest_data_date",
                "data_freshness", "crawl_status", "crops", "sources"]
# 契约：单作物必需字段（§48）
REQUIRED_CROP = ["crop", "latest_price", "change_1d", "change_7d", "change_30d",
                 "historical_percentile", "hri", "market_risk", "daily_signal",
                 "confidence", "warnings", "data_freshness", "source"]
VALID_STATUS = {"complete", "partial", "failed"}
VALID_FRESHNESS = {C.FRESH, C.DELAYED, C.STALE, C.MISSING}


class SnapshotContractError(RuntimeError):
    """Snapshot 不符合契约 → 不得替换 latest.json。"""


# ---------------------------------------------------------------- 版本 / 指纹
def data_version() -> str:
    """Daily 数据内容版本：对业务列做稳定哈希。

    刻意不使用文件字节哈希——parquet 字节可能因写出细节变化，而业务内容未变。
    """
    p = C.PROCESSED_DAILY_DIR / "daily_market_price.parquet"
    if not p.exists():
        return "unknown"
    try:
        cols = ["date", "city", "market", "crop_raw", "crop_standard", "price",
                "unit_raw", "price_level", "model_comparable", "quality_status"]
        df = pd.read_parquet(p, columns=[c for c in cols])
        df = df.sort_values(["date", "price_level", "crop_raw"], kind="mergesort")
        h = hashlib.sha256()
        h.update(",".join(df.columns).encode())
        h.update(pd.util.hash_pandas_object(df, index=False).values.tobytes())
        return h.hexdigest()[:16]
    except Exception:  # noqa: BLE001
        return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def snapshot_hash(snap: dict) -> str:
    """快照内容哈希（业务内容，不含 generated_at/monitor）。"""
    import json
    core = {k: v for k, v in snap.items()
            if k not in ("generated_at", "updated_at", "monitor")}
    return hashlib.sha256(json.dumps(core, ensure_ascii=False, sort_keys=True,
                                     default=str).encode()).hexdigest()[:16]


def load_monitor() -> dict:
    d = IO.read_json_safe(C.MONITOR_JSON, {}) or {}
    base = {"consecutive_failures": 0, "last_success_date": None, "last_success_at": None,
            "last_attempt_at": None, "last_failure_reason": None, "latest_data_date": None,
            "crawl_status": None, "snapshot_status": None, "records_fetched": 0,
            "records_accepted": 0, "records_rejected": 0, "model_status": None,
            "daily_pipeline_version": C.DAILY_PIPELINE_VERSION, "timezone": IO.TZ_NAME}
    base.update(d)
    return base


def save_monitor(state: dict) -> None:
    IO.atomic_write_json(C.MONITOR_JSON, state)


def load_previous_snapshot(target_date: str) -> dict | None:
    """取 target_date 之前最近一次历史快照。"""
    if not SNAPSHOT_DAILY_DIR.exists():
        return None
    files = sorted(SNAPSHOT_DAILY_DIR.glob("*.json"))
    prev = [f for f in files if f.stem < target_date]
    if not prev:
        return None
    return IO.read_json_safe(prev[-1])


# ---------------------------------------------------------------- 契约校验
def validate_snapshot(snap: dict) -> list[str]:
    errs: list[str] = []
    for k in REQUIRED_TOP:
        if k not in snap:
            errs.append(f"缺顶层字段 {k}")
    if snap.get("status") not in VALID_STATUS:
        errs.append(f"非法 status={snap.get('status')}")
    if snap.get("data_freshness") not in VALID_FRESHNESS:
        errs.append(f"非法 data_freshness={snap.get('data_freshness')}")
    if not isinstance(snap.get("crops"), list):
        errs.append("crops 必须是数组")
    for i, c in enumerate(snap.get("crops") or []):
        for k in REQUIRED_CROP:
            if k not in c:
                errs.append(f"crops[{i}] 缺字段 {k}")
        if c.get("daily_signal") is not None and c["daily_signal"] not in LEVELS + ["UNKNOWN"]:
            errs.append(f"crops[{i}] 非法 daily_signal={c.get('daily_signal')}")
        if c.get("data_freshness") not in VALID_FRESHNESS:
            errs.append(f"crops[{i}] 非法 data_freshness={c.get('data_freshness')}")
    return errs


# ---------------------------------------------------------------- 构建
def _crop_entries(latest_features: pd.DataFrame, assessments: dict,
                  target_date: str) -> list[dict]:
    entries = []
    for _, row in latest_features.sort_values("crop").iterrows():
        crop = row["crop"]
        ca = assessments.get(crop)
        age = (pd.Timestamp(target_date) - pd.Timestamp(row["date"])).days \
            if pd.notna(row["date"]) else None
        hri = ca.hri if ca and ca.hri else {}
        mr = ca.market_risk if ca and ca.market_risk else {}
        conf = ca.confidence if ca and ca.confidence else {}
        entries.append({
            "crop": crop,
            "unit": "元/公斤",
            "price_level": C.MODEL_PRICE_LEVEL,
            "data_date": str(pd.Timestamp(row["date"]).date()),
            "latest_price": None if pd.isna(row["latest_price"]) else round(float(row["latest_price"]), 4),
            "change_1d": None if pd.isna(row["change_1d"]) else round(float(row["change_1d"]), 6),
            "change_7d": None if pd.isna(row["change_7d"]) else round(float(row["change_7d"]), 6),
            "change_30d": None if pd.isna(row["change_30d"]) else round(float(row["change_30d"]), 6),
            "historical_percentile": None if pd.isna(row["historical_percentile"])
            else round(float(row["historical_percentile"]), 4),
            "rolling_volatility": None if pd.isna(row["rolling_volatility"])
            else round(float(row["rolling_volatility"]), 6),
            "recent_runup_14d": None if pd.isna(row["recent_runup_14d"])
            else round(float(row["recent_runup_14d"]), 6),
            "consecutive_rise_days": int(row["consecutive_rise_days"] or 0),
            "hri": hri.get("value"),
            "hri_level": hri.get("level"),
            "market_risk": mr.get("value"),
            "market_risk_level": mr.get("level"),
            "daily_signal": None if ca is None else ca.daily_signal,
            "confidence": conf.get("overall_confidence"),
            "confidence_detail": conf or None,
            "price_scenario": None if ca is None else ca.price,
            "final_status": None if ca is None else ca.final_status,
            "model_status": None if ca is None else ca.model_status,
            "capability": None if ca is None else ca.capability,
            "warnings": [] if ca is None else list(ca.final_warnings),
            "source": row.get("source"),
            "data_freshness": C.freshness_for_age(age),
            "qc_status": C.QC_OK,
        })
    return entries


def build(target_date: str, city: str = C.PRIMARY_CITY,
          crawl_status: str = "OK", crawl_detail: list[dict] | None = None,
          adapter_meta: dict | None = None,
          assessments: dict | None = None,
          counts: dict | None = None,
          write: bool = True) -> dict:
    """生成 Daily Snapshot。crawl_status ∈ {OK, PARTIAL, FAILED, SKIPPED}。"""
    import warnings
    warnings.filterwarnings("ignore")
    from . import features as FT
    from . import market_signal as MS

    C.ensure_dirs()
    counts = counts or {}
    monitor = load_monitor()
    now = IO.now_str()

    feat = FT.build(write=True)
    latest = FT.latest_by_crop(feat, as_of=target_date) if not feat.empty else pd.DataFrame()
    data_date = str(pd.Timestamp(latest["date"].max()).date()) if not latest.empty else None

    meta = adapter_meta or {}
    prev_snapshot = load_previous_snapshot(target_date)

    # 市场信号（无用户场景 → 只输出市场状态与变化，不生成种植推荐）
    signal = MS.build(latest, assessments or {}, data_date, prev_snapshot, write=write) \
        if not latest.empty else {"basis": MS.BASIS, "crops": [], "changes": []}

    age_days = (pd.Timestamp(target_date) - pd.Timestamp(data_date)).days if data_date else None
    freshness = C.freshness_for_age(age_days)
    prev_data_date = (prev_snapshot or {}).get("latest_data_date")
    data_advanced = data_date is not None and (prev_data_date is None or data_date > prev_data_date)

    model_status = meta.get("model_status", MS_UNAVAILABLE)

    # 状态判定
    if crawl_status == "FAILED" or data_date is None:
        status = "failed"
    elif freshness == C.FRESH and model_status in (MS_FINAL, MS_LEGACY):
        status = "complete"
    else:
        status = "partial"

    entries = _crop_entries(latest, assessments or {}, target_date) if data_date else []
    crops_with_signal = sum(1 for c in entries if c["daily_signal"] not in (None, "UNKNOWN"))

    snap: dict[str, Any] = {
        "schema_version": C.SCHEMA_VERSION,
        "daily_pipeline_version": C.DAILY_PIPELINE_VERSION,
        "data_version": data_version(),
        "model_version": meta.get("model_version", "UNKNOWN"),
        "model_data_version": meta.get("data_version", "UNKNOWN"),
        "generated_at": now,
        "timezone": IO.TZ_NAME,
        "date": target_date,
        "city": city,
        "status": status,
        "updated_at": now,
        "latest_data_date": data_date,
        "previous_data_date": prev_data_date,
        "data_advanced": data_advanced,
        "data_freshness": freshness,
        "data_age_days": age_days,
        "crawl_status": crawl_status,
        "crawl_detail": crawl_detail or [],
        "model": meta,
        "sources": _sources(),
        "crops": entries,
        "crops_with_signal": crops_with_signal,
        "market_signal": signal,
        "recommendation": None,
        "recommendation_note": ("无用户场景（面积/预算/成本/亩产/风险偏好）→ "
                                "不输出种植推荐；仅输出市场状态与信号变化。"),
        "notes": _notes(freshness, crawl_status, data_date, target_date, model_status,
                       meta.get("degradation")),
    }

    # 契约校验
    errs = validate_snapshot(snap)
    snap["contract_valid"] = not errs
    snap["contract_errors"] = errs
    snap["snapshot_hash"] = snapshot_hash(snap)

    if write:
        if errs:
            # 非法快照：不写 dated 文件、不推进 latest.json（§50）
            monitor.update({"last_attempt_at": now, "snapshot_status": "INVALID",
                            "crawl_status": crawl_status,
                            "consecutive_failures": int(monitor.get("consecutive_failures", 0)) + 1,
                            "last_failure_reason": "contract_invalid: " + "; ".join(errs[:3])})
            save_monitor(monitor)
            raise SnapshotContractError(f"Snapshot 契约校验失败：{errs[:5]}")

        SNAPSHOT_DAILY_DIR.mkdir(parents=True, exist_ok=True)

        # 更新监控状态（先算好，便于一并写入快照）
        if crawl_status == "FAILED" or data_date is None:
            monitor["consecutive_failures"] = int(monitor.get("consecutive_failures", 0)) + 1
            monitor["last_failure_reason"] = (
                (crawl_detail or [{}])[0].get("error") if crawl_detail else "no_data") or "no_data"
        else:
            monitor["consecutive_failures"] = 0
            monitor["last_failure_reason"] = None
            monitor["last_success_at"] = now
            monitor["last_success_date"] = target_date
        if data_date and (monitor.get("latest_data_date") is None
                          or data_date >= monitor["latest_data_date"]):
            monitor["latest_data_date"] = data_date
        monitor.update({
            "last_attempt_at": now,
            "crawl_status": crawl_status,
            "snapshot_status": status,
            "records_fetched": int(counts.get("records_fetched", 0)),
            "records_accepted": int(counts.get("records_accepted", 0)),
            "records_rejected": int(counts.get("records_rejected", 0)),
            "model_status": model_status,
            "daily_pipeline_version": C.DAILY_PIPELINE_VERSION,
            "timezone": IO.TZ_NAME,
        })
        snap["monitor"] = monitor

        # latest.json 仅在成功/部分成功、且日期不倒退时推进
        prev_latest_date = None
        if LATEST_JSON.exists():
            prev_latest_date = (IO.read_json_safe(LATEST_JSON, {}) or {}).get("date")
        forward = prev_latest_date is None or target_date >= prev_latest_date
        if not forward:
            snap["notes"].append(
                f"backfill：{target_date} 早于 latest.json 的 {prev_latest_date}，未回退 latest.json。")

        IO.atomic_write_json(SNAPSHOT_DAILY_DIR / f"{target_date}.json", snap)
        if status != "failed" and forward:
            IO.atomic_write_json(LATEST_JSON, snap)
        save_monitor(monitor)

    return snap


def _sources() -> list[dict]:
    return [{
        "source_id": C.SOURCE_ID,
        "name": C.SOURCE_NAME,
        "url": C.SOURCE_URL,
        "api": C.SOURCE_API,
        "price_level": C.MODEL_PRICE_LEVEL,
        "city": C.PRIMARY_CITY,
        "market": C.MARKET_TYPES["1"]["market_cn"],
        "frequency": "daily",
        "timezone": C.SOURCE_TIMEZONE,
        "model_comparable": True,
        "raw_layout": "data/raw/daily/shenyang_clz/<date>/mt<n>.json",
        "volume_unit": C.VOLUME_UNIT,
        "volume_unit_verified": False,
    }]


def _notes(freshness: str, crawl_status: str, data_date: str | None,
           target_date: str, model_status: str, degradation: str | None = None) -> list[str]:
    notes = []
    if data_date and data_date != target_date:
        notes.append(f"数据实际截至 {data_date}，运行日期 {target_date}；"
                     f"来源在 {target_date} 尚未发布当日价格（非错误）。"
                     "前端应显示真实数据日期，不得标为当日价格。")
    if freshness in (C.DELAYED, C.STALE):
        notes.append(f"freshness={freshness}：价格日期落后运行日期。")
    if crawl_status == "FAILED":
        notes.append("抓取失败：未写入今日价格，保留上一有效数据日期，不伪造今日数据。")
    if model_status == MS_UNAVAILABLE:
        notes.append("Final Model 不可用：未静默替换旧模型；HRI/Market Risk/Signal 为空，"
                     "价格/变化/freshness 仍为真实值。")
    elif model_status == MS_PARTIAL:
        notes.append("Final Model 部分可用：部分作物/指标缺失，status=partial（不假装正常）。")
    elif model_status == MS_LEGACY:
        notes.append("LEGACY_FALLBACK：当前为旧信号，不得当作 Final Model 结果。")
    if degradation:
        notes.append(f"模型降级：{degradation}")
    return notes