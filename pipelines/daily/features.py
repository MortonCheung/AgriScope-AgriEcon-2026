# -*- coding: utf-8 -*-
"""Daily 特征构建：latest / change_1d / 7d / 30d / 历史分位 / 波动 / run-up / 连涨。

硬约束（§16-§17）：所有滚动统计与历史分位**只使用 <= 当前日期**的数据
（expanding / trailing window），绝不引入未来信息。

输入：data/processed/daily/daily_market_price.parquet（wholesale，模型口径）
输出：data/processed/daily/features_daily.parquet / .csv
"""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from . import config as C
from . import io_utils as IO

FEATURES_PARQUET = C.PROCESSED_DAILY_DIR / "features_daily.parquet"
FEATURES_CSV = C.PROCESSED_DAILY_DIR / "features_daily.csv"

FEATURE_COLUMNS = [
    "date", "city", "crop", "latest_price", "change_1d", "change_7d", "change_30d",
    "historical_percentile", "rolling_volatility", "recent_runup_14d",
    "consecutive_rise_days", "n_obs_to_date", "source",
]


def _model_series() -> pd.DataFrame:
    """模型口径（wholesale）的日价格序列，SUSPECT 不进入信号但保留可比价格。"""
    df = pd.read_parquet(C.PROCESSED_DAILY_DIR / "daily_market_price.parquet")
    df = df[(df["price_level"] == C.MODEL_PRICE_LEVEL) &
            (df["quality_status"] == C.QC_OK)].copy()
    df["date"] = pd.to_datetime(df["date"])
    df["price_per_kg"] = pd.to_numeric(df["price_per_kg"], errors="coerce")
    df = df.dropna(subset=["price_per_kg"])
    # 同 date+crop 若仍有多行（不同解析），取 median 以稳定
    g = (df.groupby(["date", "crop_standard"])
         .agg(price_per_kg=("price_per_kg", "median"),
              source=("source_id", "first")).reset_index()
         .rename(columns={"crop_standard": "crop"}))
    return g.sort_values(["crop", "date"]).reset_index(drop=True)


def _asof_change(sub: pd.DataFrame, days: int) -> np.ndarray:
    """对每个观测日，取 date-`days` 时点（当日或之前最近一次）的价格，算涨跌幅。

    sub 必须已按 date 升序。使用 searchsorted，严格只看过去，无未来信息。
    """
    dates = sub["date"].values.astype("datetime64[D]")
    px = sub["price_per_kg"].values.astype(float)
    target = dates - np.timedelta64(days, "D")
    idx = np.searchsorted(dates, target, side="right") - 1
    base = np.full(len(px), np.nan)
    ok = idx >= 0
    base[ok] = px[idx[ok]]
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(base > 0, px / base - 1.0, np.nan)


def compute_features(series: pd.DataFrame | None = None) -> pd.DataFrame:
    series = _model_series() if series is None else series
    if series.empty:
        return pd.DataFrame(columns=FEATURE_COLUMNS)

    frames = []
    for crop, sub in series.groupby("crop", sort=True):
        s = sub.sort_values("date").reset_index(drop=True).copy()
        px = s["price_per_kg"]
        s["latest_price"] = px
        s["change_1d"] = px.pct_change()
        s["change_7d"] = _asof_change(s, 7)
        s["change_30d"] = _asof_change(s, 30)
        # 历史分位：past-only expanding（>=30 个观测后才有意义）
        s["historical_percentile"] = px.expanding(min_periods=30).rank(pct=True)
        # 近期波动率：30 个观测的收益率标准差
        s["rolling_volatility"] = px.pct_change().rolling(30, min_periods=15).std()
        # 近期 run-up：相对过去 14 个观测最低点的涨幅
        roll_min = px.rolling(14, min_periods=5).min()
        s["recent_runup_14d"] = px / roll_min.replace(0, np.nan) - 1.0
        # 连涨天数
        up = (px.diff() > 0).astype(int)
        s["consecutive_rise_days"] = up.groupby((up == 0).cumsum()).cumsum()
        s["n_obs_to_date"] = np.arange(1, len(s) + 1)
        s["source"] = s["source"]
        s["city"] = C.PRIMARY_CITY
        frames.append(s)

    feat = pd.concat(frames, ignore_index=True)
    for c in ("change_1d", "change_7d", "change_30d", "rolling_volatility",
              "recent_runup_14d", "historical_percentile", "latest_price"):
        feat[c] = pd.to_numeric(feat[c], errors="coerce").round(6)
    return feat[FEATURE_COLUMNS]


def build(write: bool = True) -> pd.DataFrame:
    C.ensure_dirs()
    feat = compute_features()
    if write and not feat.empty:
        IO.atomic_write_parquet(feat, FEATURES_PARQUET)
        IO.atomic_write_csv(feat, FEATURES_CSV)
    return feat


def latest_by_crop(feat: pd.DataFrame | None = None,
                   as_of: str | None = None) -> pd.DataFrame:
    """截至 as_of（含）每个作物的最新一行特征。"""
    feat = build(write=False) if feat is None else feat
    if feat.empty:
        return feat
    d = feat if as_of is None else feat[feat["date"] <= pd.Timestamp(as_of)]
    return d.sort_values("date").groupby("crop", sort=True).tail(1).reset_index(drop=True)