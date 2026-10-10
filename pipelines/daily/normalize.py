# -*- coding: utf-8 -*-
"""Daily 标准化层 + 质量检查（QC）。

    daily raw  ->  daily normalized（口径与模型严格一致：wholesale / price_per_kg）

不写入任何既有正式历史表；输出独立 Daily 主表：
    data/processed/daily/daily_market_price.parquet / .csv
    data/processed/daily/qc_daily.csv
    data/processed/daily/normalize_report.json

原始证据来源（全部只读）：
    data/raw/daily/shenyang_clz/<date>/mt<n>.json     （本流水线新增）
    data/raw/prices/shenyang_clz/<date>_mt<n>.json    （既有已验证采集器）
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from . import io_utils as IO

_DT = datetime  # alias

# QC 阈值（异常跳变）
JUMP_UPPER = 3.0     # 较上一观测日涨幅 > 3x  -> SUSPECT
JUMP_LOWER = 1 / 3.0  # 较上一观测日跌幅 > 3x  -> SUSPECT

OUT_CSV = C.PROCESSED_DAILY_DIR / "daily_market_price.csv"
OUT_PARQUET = C.PROCESSED_DAILY_DIR / "daily_market_price.parquet"
QC_CSV = C.PROCESSED_DAILY_DIR / "qc_daily.csv"
REPORT_JSON = C.PROCESSED_DAILY_DIR / "normalize_report.json"

COLUMNS = [
    "date", "city", "market", "crop_raw", "crop_standard", "price", "unit_raw",
    "unit_standard", "price_per_kg", "price_level", "model_comparable", "volume",
    "volume_unit", "volume_unit_unverified", "source_id", "source_name", "source_url",
    "published_at", "crawl_time", "raw_file", "parser_version", "quality_status",
    "qc_flags", "note",
]


# ---------------------------------------------------------------- 原始证据读取
def _iter_new_raw():
    base = C.RAW_DAILY_DIR / "shenyang_clz"
    if not base.exists():
        return
    for day_dir in sorted(base.iterdir()):
        if not day_dir.is_dir():
            continue
        for f in sorted(day_dir.glob("mt*.json")):
            yield day_dir.name, f.stem.replace("mt", ""), f


def _iter_legacy_raw():
    base = C.DATA_DIR / "raw" / "prices" / "shenyang_clz"
    if not base.exists():
        return
    for f in sorted(base.glob("*_mt*.json")):
        stem = f.stem                       # e.g. 2026-09-21_mt1
        date_part, mt = stem.split("_mt")
        yield date_part, mt, f


def _per_kg(price: float, unit: str):
    factor = C.UNIT_TO_KG.get((unit or "").replace(" ", ""))
    return None if factor is None else price * factor


def _published_at(epoch_ms) -> str | None:
    """来源 epoch 毫秒 → 北京时间字符串（显式 Asia/Shanghai，不依赖系统时区）。"""
    return IO.epoch_ms_to_tz_str(epoch_ms)


def _evidence_crawl_time(path: Path, mt: str) -> str:
    """原始证据的抓取时间（保证重复解析得到相同结果）。

    优先：新布局 metadata.json 中归档的 crawl_time；
    其次：旧布局原始文件 mtime（北京时间）；
    最后：当前时间。
    """
    meta_file = path.parent / "metadata.json"
    if meta_file.exists():
        meta = IO.read_json_safe(meta_file, {}) or {}
        ct = (meta.get(f"mt{mt}") or {}).get("crawl_time")
        if ct:
            return str(ct)
    try:
        import datetime as _dt
        ts = _dt.datetime.fromtimestamp(path.stat().st_mtime, tz=IO.TZ)
        return ts.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:  # noqa: BLE001
        return IO.now_str()


def _read_source(date: str, mt: str, path: Path, crawl_time: str | None = None) -> list[dict]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    spec = C.MARKET_TYPES.get(mt, {})
    rows = []
    for it in obj.get("data") or []:
        unit = (it.get("unit") or "").strip()
        price_raw = it.get("price")
        try:
            price = float(price_raw)
        except (TypeError, ValueError):
            price = None
        rows.append({
            "date": date,
            "city": C.PRIMARY_CITY,
            "market": spec.get("market_cn", ""),
            "crop_raw": (it.get("productName") or "").strip(),
            "grade": (it.get("grade") or "").strip(),
            "price": price,
            "unit_raw": unit,
            "unit_standard": "元/公斤",
            "price_per_kg": _per_kg(price, unit) if price is not None else None,
            "price_level": spec.get("price_level", "other"),
            "model_comparable": bool(spec.get("model_comparable", False)),
            # volume（成交量）：接口未标注单位 → 一律 UNKNOWN，且 source_unit_unverified=true；
            # 禁止参与定量模型 / 跨日数量比较 / 供应强度计算（§12）
            "volume": None if not spec.get("model_comparable") else it.get("volume"),
            "volume_unit": C.VOLUME_UNIT if spec.get("model_comparable") else None,
            "volume_unit_unverified": bool(C.VOLUME_SOURCE_UNIT_UNVERIFIED)
            if spec.get("model_comparable") else None,
            "source_id": C.SOURCE_ID,
            "source_name": C.SOURCE_NAME,
            "source_url": C.SOURCE_URL,
            "published_at": _published_at(it.get("dates")),
            "crawl_time": crawl_time or _evidence_crawl_time(path, mt),
            "raw_file": str(path.relative_to(C.ROOT)),
            "parser_version": C.SOURCE_PARSER_VERSION,
        })
    return rows


def load_raw_records(include_legacy: bool = True) -> pd.DataFrame:
    """汇总所有原始证据 → 未去重、未 QC 的原始行。"""
    rows = []
    for date, mt, path in _iter_new_raw():
        rows += _read_source(date, mt, path)
    # 旧布局（data/raw/prices/shenyang_clz）仅用于历史 seed，见 seed_legacy_raw()，
    # 避免与新布局重复计入。
    return pd.DataFrame(rows)


def seed_legacy_raw() -> pd.DataFrame:
    """把既有已验证采集器的原始 JSON（批发 mt1）纳入 Daily 历史基线。

    仅读取，不修改旧文件；用于让 Daily 主表具备完整历史以便算分位/滚动统计。
    """
    rows = []
    for date, mt, path in _iter_legacy_raw():
        if mt != "1":
            continue  # 模型口径 = wholesale，历史基线只取批发
        rows += _read_source(date, mt, path)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- QC
def run_qc(df: pd.DataFrame, crops: list[str]) -> pd.DataFrame:
    """逐行质量检查。quality_status ∈ {OK, SUSPECT, REJECTED, DUPLICATE}。"""
    if df.empty:
        return df
    d = df.copy()
    d["qc_flags"] = ""
    mapping = C.crop_mapping()

    def _add(idx, flag):
        cur = d.at[idx, "qc_flags"]
        d.at[idx, "qc_flags"] = f"{cur};{flag}" if cur else flag

    status = pd.Series(C.QC_OK, index=d.index)

    # 1) 空值 / 缺核心字段
    for idx, r in d.iterrows():
        flags = []
        if not r["crop_raw"]:
            flags.append("EMPTY_CROP")
        if r["price"] is None or (isinstance(r["price"], float) and np.isnan(r["price"])):
            flags.append("EMPTY_PRICE")
        elif r["price"] <= 0:
            flags.append("NON_POSITIVE_PRICE")
        if r["price_per_kg"] is None or (isinstance(r["price_per_kg"], float) and np.isnan(r["price_per_kg"])):
            flags.append("UNIT_UNKNOWN")
        if r["price_level"] not in C.PRICE_LEVELS:
            flags.append("BAD_PRICE_LEVEL")
        # 作物映射
        std = mapping.get(r["crop_raw"], r["crop_raw"])
        if std not in crops and r["model_comparable"]:
            flags.append("CROP_NOT_SUPPORTED")
        # 日期正确性：published_at 的日期必须与请求日期一致（防抓到旧页面）
        pub = r["published_at"]
        if pub and not str(pub).startswith(str(r["date"])):
            flags.append("STALE_PAGE")
        for fl in flags:
            _add(idx, fl)
        hard = {"EMPTY_CROP", "EMPTY_PRICE", "NON_POSITIVE_PRICE", "UNIT_UNKNOWN",
                "BAD_PRICE_LEVEL", "STALE_PAGE"}
        if hard & set(flags):
            status.at[idx] = C.QC_REJECTED
        elif flags:
            status.at[idx] = C.QC_SUSPECT

    # 2) 重复（同 date+market+crop_raw）
    dup_key = ["date", "price_level", "crop_raw"]
    dup_mask = d.duplicated(subset=dup_key, keep="first")
    status[dup_mask] = C.QC_DUPLICATE
    for idx in d.index[dup_mask]:
        _add(idx, "DUPLICATE_ROW")

    # 3) 异常跳变（对同 crop_standard + price_level 的上一观测日）
    ok = d[status.isin([C.QC_OK, C.QC_SUSPECT])].copy()
    ok["_dt"] = pd.to_datetime(ok["date"])
    ok = ok.sort_values(["crop_raw", "_dt"])
    for (crop, lvl), sub in ok.groupby(["crop_raw", "price_level"], sort=False):
        prev = None
        for idx, r in sub.iterrows():
            p = r["price_per_kg"]
            if prev is not None and p and prev > 0:
                ratio = p / prev
                if ratio > JUMP_UPPER or ratio < JUMP_LOWER:
                    _add(idx, f"PRICE_JUMP_x{ratio:.2f}")
                    if status.at[idx] == C.QC_OK:
                        status.at[idx] = C.QC_SUSPECT
            if p and p > 0:
                prev = p

    d["quality_status"] = status
    d["crop_standard"] = d["crop_raw"].map(lambda x: mapping.get(x, x))
    return d


# ---------------------------------------------------------------- 主流程
def build(include_legacy_seed: bool = True, write: bool = True) -> dict:
    """生成 Daily 标准化主表。返回统计报告 dict。"""
    C.ensure_dirs()
    crops = C.supported_crops()
    frames = [load_raw_records()]
    seed = seed_legacy_raw() if include_legacy_seed else pd.DataFrame()
    raw = pd.concat([f for f in frames + [seed] if not f.empty], ignore_index=True) \
        if not (frames[0].empty and seed.empty) else pd.DataFrame()

    if raw.empty:
        report = {"status": "NO_RAW", "rows": 0}
        if write:
            REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report

    qc = run_qc(raw, crops)
    # 排序 + 只保留定义列
    qc["_dt"] = pd.to_datetime(qc["date"])
    qc = qc.sort_values(["_dt", "price_level", "crop_raw"]).drop(columns=["_dt"])
    for c in COLUMNS:
        if c not in qc.columns:
            qc[c] = None
    out = qc[COLUMNS].copy()
    for num in ("price", "price_per_kg", "volume"):
        out[num] = pd.to_numeric(out[num], errors="coerce")

    accepted = out[out["quality_status"].isin([C.QC_OK, C.QC_SUSPECT])].copy()
    if write:
        IO.atomic_write_parquet(out, OUT_PARQUET)
        IO.atomic_write_csv(out, OUT_CSV)
        IO.atomic_write_csv(qc[qc["quality_status"] != C.QC_OK][COLUMNS + ["qc_flags"]], QC_CSV)

    report = {
        "status": "OK",
        "generated_at": IO.now_str(),
        "timezone": IO.TZ_NAME,
        "rows_total": int(len(out)),
        "rows_accepted": int(len(accepted)),
        "by_status": out["quality_status"].value_counts().to_dict(),
        "by_level": out["price_level"].value_counts().to_dict(),
        "date_min": str(out["date"].min()),
        "date_max": str(out["date"].max()),
        "crops": sorted(out[out["model_comparable"]]["crop_standard"].dropna().unique().tolist()),
        "supported_crops": crops,
        "qc_flagged": int((out["quality_status"] != C.QC_OK).sum()),
        "volume_unit": C.VOLUME_UNIT,
        "volume_unit_unverified": bool(C.VOLUME_SOURCE_UNIT_UNVERIFIED),
        "volume_note": "成交量单位来源未标注 → UNKNOWN，不参与模型/跨日比较/供应强度",
    }
    if write:
        IO.atomic_write_json(REPORT_JSON, report)
    return report


# ---------------------------------------------------------------- 与 canonical 一致性核对
def consistency_vs_canonical() -> dict:
    """Daily(wholesale) 与模型训练 canonical 表在重叠区间的一致性核对（只报告，不改数据）。"""
    if not OUT_PARQUET.exists() or not C.CANONICAL_MARKET_DAILY.exists():
        return {"status": "NOT_AVAILABLE"}
    daily = pd.read_parquet(OUT_PARQUET)
    daily = daily[(daily["price_level"] == C.MODEL_PRICE_LEVEL) &
                  (daily["quality_status"].isin([C.QC_OK, C.QC_SUSPECT]))]
    daily = daily[["date", "crop_standard", "price_per_kg"]].copy()

    can = pd.read_parquet(C.CANONICAL_MARKET_DAILY)
    lvl_col = "price_level_canonical" if "price_level_canonical" in can.columns else "price_level"
    can = can[can[lvl_col] == C.MODEL_PRICE_LEVEL]
    can = can.rename(columns={"observation_date": "date"})[["date", "crop_standard", "price_per_kg"]]
    can["price_per_kg"] = pd.to_numeric(can["price_per_kg"], errors="coerce")
    can["date"] = can["date"].astype(str).str.slice(0, 10)
    daily["date"] = daily["date"].astype(str).str.slice(0, 10)

    m = daily.merge(can, on=["date", "crop_standard"], how="inner", suffixes=("_daily", "_canonical"))
    if m.empty:
        return {"status": "NO_OVERLAP"}
    diff = (m["price_per_kg_daily"] - m["price_per_kg_canonical"]).abs()
    return {
        "status": "OK",
        "overlap_rows": int(len(m)),
        "max_abs_diff": float(diff.max()),
        "n_mismatch_gt_1e-6": int((diff > 1e-6).sum()),
        "daily_only_rows": int(len(daily) - len(m)),
        "canonical_only_rows": int(len(can) - len(m)),
    }