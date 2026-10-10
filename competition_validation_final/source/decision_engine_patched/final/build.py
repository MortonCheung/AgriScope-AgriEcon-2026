# -*- coding: utf-8 -*-
"""F1/F2: 冻结 Final 数据快照 + 构建 Final 决策数据集（严格来自 data/model_ready/）。

核心原则：
  - 正式模型只能读取 Final 快照（本模块从 data/model_ready/ 复制 + 哈希冻结）；
  - 与旧 models/data/snapshots/v1 明确隔离（OLD BASELINE vs FINAL DATA）；
  - 特征全部 point-in-time；禁止未来窗口/centered rolling/全样本分位回填。
"""
from __future__ import annotations
import glob
import os
import shutil
from typing import Dict, Tuple

import numpy as np
import pandas as pd

from decision_engine.common import sha256_file
from decision_engine.features.build_features import add_price_features, add_targets
from decision_engine.final.fcommon import (MODEL_READY, SNAPSHOT_DIR, MANIFEST_DIR,
                                           SHENYANG_CROPS, ensure_dir, md5_of_frame,
                                           now_stamp, DATA_VERSION)

DATE_COLS = ["date", "observation_date", "period", "start_date", "end_date"]


def _date_range(df: pd.DataFrame) -> str:
    for c in DATE_COLS:
        if c in df.columns:
            s = pd.to_datetime(df[c], errors="coerce")
            if s.notna().any():
                return f"{s.min().date()}~{s.max().date()}"
    return "-"


def freeze_data() -> pd.DataFrame:
    """把 data/model_ready/ 冻结为 models/data/snapshots/final_v1/model_ready/。"""
    dst_root = SNAPSHOT_DIR / "model_ready"
    if dst_root.exists():
        shutil.rmtree(dst_root)
    ensure_dir(dst_root)
    files = sorted(glob.glob(str(MODEL_READY / "**" / "*.parquet"), recursive=True))
    rows = []
    csv_files = sorted(glob.glob(str(MODEL_READY / "**" / "*.csv"), recursive=True))
    for f in files:
        rel = os.path.relpath(f, MODEL_READY)
        d = dst_root / rel
        ensure_dir(d.parent)
        shutil.copy2(f, d)
        df = pd.read_parquet(f)
        rows.append({
            "table": rel, "rows": len(df), "cols": df.shape[1],
            "date_range": _date_range(df),
            "sha256": sha256_file(f), "content_md5": md5_of_frame(df),
            "frozen_at": now_stamp(), "source": "data/model_ready",
        })
    man = pd.DataFrame(rows)
    ensure_dir(MANIFEST_DIR)
    man.to_csv(MANIFEST_DIR / "final_v1_manifest.csv", index=False, encoding="utf-8-sig")
    for f in csv_files:
        rel = os.path.relpath(f, MODEL_READY)
        d = dst_root / rel; ensure_dir(d.parent); shutil.copy2(f, d)
    return man


def shenyang_base() -> pd.DataFrame:
    """沈阳 base：来自 Final 快照的 market_daily（wholesale 单一层）。"""
    src = SNAPSHOT_DIR / "model_ready/shenyang_core/market_daily.parquet"
    df = pd.read_parquet(src)
    df = df[df["crop_standard"].isin(SHENYANG_CROPS)].copy()
    df = df[df["price_level_canonical"] == "wholesale"].copy()
    df["price_per_kg"] = pd.to_numeric(df["price_per_kg"], errors="coerce").astype(float)
    df["date"] = pd.to_datetime(df["observation_date"]).dt.date
    df = df.dropna(subset=["price_per_kg"]).drop_duplicates(["date", "crop_standard"])
    df = df.rename(columns={"crop_standard": "crop"})
    df = df.sort_values(["crop", "date"]).reset_index(drop=True)
    d = pd.to_datetime(df["date"])
    df["year"] = d.dt.year; df["month"] = d.dt.month
    df["week"] = d.dt.isocalendar().week.astype(int)
    df["day_of_year"] = d.dt.dayofyear; df["quarter"] = d.dt.quarter
    df["season"] = df["month"].map({12: "winter", 1: "winter", 2: "winter",
                                    3: "spring", 4: "spring", 5: "spring",
                                    6: "summer", 7: "summer", 8: "summer",
                                    9: "autumn", 10: "autumn", 11: "autumn"})
    df["sin_doy"] = np.sin(2 * np.pi * df["day_of_year"] / 365.25)
    df["cos_doy"] = np.cos(2 * np.pi * df["day_of_year"] / 365.25)
    df["sin_month"] = np.sin(2 * np.pi * df["month"] / 12)
    df["cos_month"] = np.cos(2 * np.pi * df["month"] / 12)
    return df[["date", "city", "crop", "price_per_kg", "year", "month", "week",
               "day_of_year", "quarter", "season", "sin_doy", "cos_doy",
               "sin_month", "cos_month"]].reset_index(drop=True)


def chaoyang_base(crops=None) -> pd.DataFrame:
    """朝阳 base：只用 market_average 单一层（发改委全市均价主源）。"""
    crops = crops or SHENYANG_CROPS
    src = SNAPSHOT_DIR / "model_ready/chaoyang_extended/market_daily.parquet"
    df = pd.read_parquet(src)
    df = df[(df["crop_standard"].isin(crops)) &
            (df["price_level_canonical"] == "market_average")].copy()
    df["price_per_kg"] = pd.to_numeric(df["price_per_kg"], errors="coerce").astype(float)
    df["date"] = pd.to_datetime(df["observation_date"]).dt.date
    df = df.dropna(subset=["price_per_kg"]).drop_duplicates(["date", "crop_standard"])
    df = df.rename(columns={"crop_standard": "crop"}).sort_values(["crop", "date"]).reset_index(drop=True)
    d = pd.to_datetime(df["date"])
    df["year"] = d.dt.year; df["month"] = d.dt.month
    df["week"] = d.dt.isocalendar().week.astype(int)
    df["day_of_year"] = d.dt.dayofyear; df["quarter"] = d.dt.quarter
    df["season"] = df["month"].map({12: "winter", 1: "winter", 2: "winter",
                                    3: "spring", 4: "spring", 5: "spring",
                                    6: "summer", 7: "summer", 8: "summer",
                                    9: "autumn", 10: "autumn", 11: "autumn"})
    df["sin_doy"] = np.sin(2 * np.pi * df["day_of_year"] / 365.25)
    df["cos_doy"] = np.cos(2 * np.pi * df["day_of_year"] / 365.25)
    df["sin_month"] = np.sin(2 * np.pi * df["month"] / 12)
    df["cos_month"] = np.cos(2 * np.pi * df["month"] / 12)
    return df[["date", "city", "crop", "price_per_kg", "year", "month", "week",
               "day_of_year", "quarter", "season", "sin_doy", "cos_doy",
               "sin_month", "cos_month"]].reset_index(drop=True)


def add_mean_targets(df: pd.DataFrame, horizons=(60, 90)) -> pd.DataFrame:
    """补充 60/90 天「未来窗口均价」目标（日历天窗口，窗口须完整落在数据范围内）。"""
    d = df.sort_values(["crop", "date"]).reset_index(drop=True).copy()
    dd = pd.to_datetime(d["date"])
    last = dd.max()
    for h in horizons:
        col = f"target_mean_price_next_{h}d"
        vals = np.full(len(d), np.nan)
        for crop, sub in d.groupby("crop", sort=False):
            sub = sub.sort_values("date")
            dates = pd.to_datetime(sub["date"]).values.astype("datetime64[D]")
            prices = sub["price_per_kg"].values.astype(float)
            idx = sub.index.values
            for j, dt in enumerate(dates):
                if dt + np.timedelta64(h, "D") > np.datetime64(last.date(), "D"):
                    continue
                lo = np.searchsorted(dates, dt, side="right")
                hi = np.searchsorted(dates, dt + np.timedelta64(h, "D"), side="right")
                if hi > lo:
                    vals[idx[j]] = prices[lo:hi].mean()
        d[col] = vals
    return d


def build_dataset_for(city: str) -> pd.DataFrame:
    base = shenyang_base() if city == "沈阳" else chaoyang_base()
    feats = add_price_features(base)
    ds = add_targets(feats)
    ds = add_mean_targets(ds, (60, 90))
    return ds


def build_all() -> Dict[str, pd.DataFrame]:
    ensure_dir(SNAPSHOT_DIR / "datasets")
    out = {}
    for city in ["沈阳", "朝阳"]:
        ds = build_dataset_for(city)
        ds.to_parquet(SNAPSHOT_DIR / "datasets" / f"decision_dataset_{city}.parquet", index=False)
        out[city] = ds
    return out


if __name__ == "__main__":
    man = freeze_data()
    print("frozen tables:", len(man), "| total rows:", int(man["rows"].sum()))
    ds = build_all()
    for c, d in ds.items():
        print(f"[{c}] dataset rows={len(d)} cols={len(d.columns)} crops={d['crop'].nunique()}")
    b = shenyang_base()
    print("沈阳 base:", b.shape, b["crop"].nunique(), b["date"].min(), b["date"].max())
    print("沈阳 每作物观测数:", b.groupby("crop").size().to_dict())