# -*- coding: utf-8 -*-
"""Phase 1: Decision Dataset v1 基础层构建（沈阳 10 蔬菜 日频观测面板）。

数据流：
  1) canonical price_observation（元/斤, wholesale）→ price_per_500g / price_per_kg
  2) volume_observations（daily_transaction, volume_unit=unknown → 相对口径）
  3) 严格 join 校验（行数膨胀 / 未匹配 / 重复键）
  4) 日历特征
所有输入来自 decision_engine/data/snapshots/v1（冻结快照）。
"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from decision_engine.common import de_path, ensure_dir  # noqa: E402

CROPS = ["土豆", "西红柿", "黄瓜", "韭菜", "青椒", "尖椒", "茄子", "芹菜", "芸豆", "甘蓝"]
SNAP = de_path("data", "snapshots", "v1")


def load_price() -> pd.DataFrame:
    df = pd.read_csv(SNAP / "city_data/shenyang/data/price_observation.csv", low_memory=False)
    keep = ["city", "crop_standard", "crop_raw", "price_original", "unit_original",
            "price_per_kg", "price_level", "observation_date", "frequency",
            "source_name", "quality_grade"]
    df = df[keep].rename(columns={"crop_standard": "crop"})
    df = df[df["crop"].isin(CROPS)].copy()
    df["date"] = pd.to_datetime(df["observation_date"]).dt.date
    df = df.drop(columns=["observation_date"])
    # 单位统一：canonical 原始 = 元/斤（500g）
    df["price_raw"] = df["price_original"].astype(float)
    df["price_raw_unit"] = df["unit_original"]
    df["price_per_500g"] = df["price_raw"]           # 元/500g
    df["price_kg_check"] = np.abs(df["price_per_kg"] - df["price_per_500g"] * 2.0) < 1e-6
    df = df.rename(columns={"price_per_kg": "price_per_kg_canonical"})
    df["price_per_kg"] = df["price_per_500g"] * 2.0  # 元/kg（收益模块统一口径）
    df = df.drop(columns=["price_level"]) if "price_level" in df.columns else df
    return df.sort_values(["crop", "date"]).reset_index(drop=True)


def load_volume() -> pd.DataFrame:
    df = pd.read_csv(SNAP / "city_data/shenyang/data/volume_observations.csv", low_memory=False)
    df = df[df["volume_type"] == "daily_transaction"].copy()
    df["frequency"] = df["frequency"].astype(str).str.strip()
    df = df[df["crop"].isin(CROPS)].copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df.rename(columns={"volume": "volume_raw", "volume_unit": "volume_unit_raw"})
    df["volume_semantics"] = "relative_market_activity"  # 单位未知，禁止当作吨
    return df[["date", "crop", "volume_raw", "volume_unit_raw", "volume_semantics", "quality_grade"]]


def join_qc(price: pd.DataFrame, volume: pd.DataFrame) -> pd.DataFrame:
    """join cardinality 校验，返回 QC 记录。"""
    p = price[["date", "crop"]].copy()
    v = volume[["date", "crop"]].copy()
    merged = p.merge(v, on=["date", "crop"], how="outer", indicator=True)
    rec = {
        "price_rows": len(p),
        "volume_rows": len(v),
        "price_dup_keys": int(p.duplicated(["date", "crop"]).sum()),
        "volume_dup_keys": int(v.duplicated(["date", "crop"]).sum()),
        "matched_rows": int((merged["_merge"] == "both").sum()),
        "price_only_rows": int((merged["_merge"] == "left_only").sum()),
        "volume_only_rows": int((merged["_merge"] == "right_only").sum()),
        "row_inflation": int(len(merged) - max(len(p), len(v))),
    }
    return pd.DataFrame([rec])


def add_calendar(df: pd.DataFrame) -> pd.DataFrame:
    d = pd.to_datetime(df["date"])
    df["year"] = d.dt.year
    df["month"] = d.dt.month
    df["week"] = d.dt.isocalendar().week.astype(int)
    df["day_of_year"] = d.dt.dayofyear
    df["quarter"] = d.dt.quarter
    df["season"] = df["month"].map({12: "winter", 1: "winter", 2: "winter",
                                    3: "spring", 4: "spring", 5: "spring",
                                    6: "summer", 7: "summer", 8: "summer",
                                    9: "autumn", 10: "autumn", 11: "autumn"})
    df["sin_doy"] = np.sin(2 * np.pi * df["day_of_year"] / 365.25)
    df["cos_doy"] = np.cos(2 * np.pi * df["day_of_year"] / 365.25)
    df["sin_month"] = np.sin(2 * np.pi * df["month"] / 12)
    df["cos_month"] = np.cos(2 * np.pi * df["month"] / 12)
    return df


def add_volume_features(df: pd.DataFrame) -> pd.DataFrame:
    """成交量相对口径特征（严格 point-in-time）。"""
    df = df.sort_values(["crop", "date"]).reset_index(drop=True)
    g = df.groupby("crop", sort=False)
    # 观测滞后
    df["volume_lag_1"] = g["volume_raw"].shift(1)
    df["volume_lag_7"] = g["volume_raw"].shift(7)
    df["volume_change_1d"] = df["volume_raw"] / df["volume_lag_1"] - 1
    df["volume_change_7d"] = df["volume_raw"] / df["volume_lag_7"] - 1
    df["volume_ma7"] = g["volume_raw"].transform(lambda s: s.rolling(7, min_periods=4).mean())
    df["volume_ma30"] = g["volume_raw"].transform(lambda s: s.rolling(30, min_periods=15).mean())
    # past-only z-score 与分位（expanding，含当前）
    df["volume_zscore"] = g["volume_raw"].transform(
        lambda s: (s - s.expanding(min_periods=30).mean()) /
        s.expanding(min_periods=30).std().replace(0, np.nan))
    df["volume_percentile"] = g["volume_raw"].transform(
        lambda s: s.expanding(min_periods=30).rank(pct=True))
    return df


def build_base() -> tuple[pd.DataFrame, pd.DataFrame]:
    price = load_price()
    volume = load_volume()
    qc = join_qc(price, volume)
    df = price.merge(volume, on=["date", "crop"], how="left", validate="one_to_one")
    assert len(df) == len(price), "join 后行数膨胀！"
    df = add_calendar(df)
    df = add_volume_features(df)
    # 列顺序整理
    front = ["date", "city", "crop", "price_raw", "price_raw_unit", "price_per_500g",
             "price_per_kg", "price_kg_check", "volume_raw", "volume_unit_raw", "volume_semantics"]
    df = df[front + [c for c in df.columns if c not in front]]
    return df, qc


if __name__ == "__main__":
    df, qc = build_base()
    out = ensure_dir(de_path("data", "processed"))
    df.to_parquet(out / "decision_base_v1.parquet", index=False)
    qc.to_csv(ensure_dir(de_path("data", "manifests")) / "join_qc.csv", index=False)
    print(df.shape, "->", out / "decision_base_v1.parquet")
    print(qc.T)