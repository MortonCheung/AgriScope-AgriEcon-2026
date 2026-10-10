# -*- coding: utf-8 -*-
"""Phase 6: Climate Exposure Index（气候暴露，不是损失/减产模型）。

- 日频暴露：暴雨 / 降水 P90 / 连旱 / 土壤干 / 高温 / 温度异常 的 past-only 分位组合
- 未来种植计划：使用「历史同期（同 DOY 窗口）气候概率」——明确不是未来天气预报
- 严格 as_of 截断：历史回放时只能使用 <= T 的数据
"""
from __future__ import annotations
from datetime import date as _date
from typing import Dict, Optional

import numpy as np
import pandas as pd

from decision_engine.common import de_path
from decision_engine.features.weather_features import CITY_FILE

MIN_PERIODS = 90
WEIGHTS = {"heavy_rain": 0.20, "precip_p90": 0.20, "dry": 0.20,
           "soil_dry": 0.15, "heat": 0.15, "temp_anomaly": 0.10}

_WEATHER_CACHE: Dict[str, pd.DataFrame] = {}


def _load_weather(city: str) -> pd.DataFrame:
    if city not in _WEATHER_CACHE:
        p = de_path("data", "features", f"weather_features_{CITY_FILE[city]}.parquet")
        w = pd.read_parquet(p)
        w["date"] = pd.to_datetime(w["date"])
        _WEATHER_CACHE[city] = w.sort_values("date").reset_index(drop=True)
    return _WEATHER_CACHE[city]


def daily_exposure(city: str) -> pd.DataFrame:
    w = _load_weather(city).copy()
    w["x_heavy_rain"] = w["heavy_rain_flag"] * 100
    w["x_precip_p90"] = w["rain_p90_flag"] * 100
    w["x_dry"] = w["dry_spell_days"].expanding(MIN_PERIODS).rank(pct=True) * 100
    w["x_soil_dry"] = (1 - w["soil_moisture_percentile"]) * 100
    w["x_heat"] = w["temp_p95_flag"] * 100
    w["x_temp_anomaly"] = w["temp_anomaly"].abs().expanding(MIN_PERIODS).rank(pct=True) * 100
    cols = [f"x_{k}" for k in WEIGHTS]
    avail = w[cols].notna()
    w["climate_exposure"] = w[cols].fillna(0).mul(list(WEIGHTS.values()), axis=1).sum(axis=1) / \
        (avail.mul(list(WEIGHTS.values()), axis=1).sum(axis=1).replace(0, np.nan))
    w["climate_component_count"] = avail.sum(axis=1)
    return w


def _doy_mask(doy: np.ndarray, d1: int, d2: int) -> np.ndarray:
    if d1 <= d2:
        return (doy >= d1) & (doy <= d2)
    return (doy >= d1) | (doy <= d2)


def plan_exposure(city: str, plant_date: str | _date, harvest_date: str | _date,
                  as_of: Optional[str | _date] = None) -> Dict:
    """历史同期（plan→harvest DOY 窗口）气候暴露。

    as_of: 历史回放截止日；None = 使用全部可得历史。
    """
    w = daily_exposure(city)          # 含 x_* 组件列（past-only 分位）
    if as_of is not None:
        w = w[w["date"] <= pd.Timestamp(as_of)]
    d1 = pd.Timestamp(plant_date).dayofyear
    d2 = pd.Timestamp(harvest_date).dayofyear
    m = _doy_mask(w["date"].dt.dayofyear.values, d1, d2)
    sub = w[m].copy()
    # 每一年窗口内只保留完整窗口（该年在此 DOY 窗口的天数 >= 应有天数的 60%）
    win_days = int((pd.Timestamp(harvest_date) - pd.Timestamp(plant_date)).days) + 1
    if win_days <= 0:
        win_days += 365
    sums = sub.groupby(sub["date"].dt.year).agg(
        n=("date", "count"),
        heavy_rain=("x_heavy_rain", "mean"),
        precip_p90=("x_precip_p90", "mean"),
        dry=("x_dry", lambda s: float((s >= 75).mean()) * 100 if s.notna().any() else np.nan),
        soil_dry=("x_soil_dry", lambda s: float((s >= 75).mean()) * 100 if s.notna().any() else np.nan),
        heat=("x_heat", "mean"),
        temp_anomaly=("x_temp_anomaly", "mean"),
    )
    sums = sums[sums["n"] >= max(10, 0.6 * min(win_days, 366))]
    comp = {k: (float(sums[k].mean()) if sums[k].notna().any() else np.nan)
            for k in WEIGHTS}
    avail = {k: np.isfinite(v) for k, v in comp.items()}
    wsum = sum(WEIGHTS[k] for k, a in avail.items() if a)
    score = (sum(comp[k] * WEIGHTS[k] for k, a in avail.items() if a) / wsum) if wsum > 0 else np.nan
    return {
        "city": city,
        "window": [str(pd.Timestamp(plant_date).date()), str(pd.Timestamp(harvest_date).date())],
        "doy_window": [d1, d2],
        "years_used": sorted(sums.index.tolist()),
        "n_years": int(len(sums)),
        "components": {k: (round(v, 2) if np.isfinite(v) else None) for k, v in comp.items()},
        "component_weights": {k: (WEIGHTS[k] if avail[k] else 0) for k in WEIGHTS},
        "component_count": int(sum(avail.values())),
        "climate_exposure_score": round(float(score), 2) if np.isfinite(score) else None,
        "basis": "historical_same_period_climatology",
        "is_weather_forecast": False,
        "as_of": str(as_of) if as_of is not None else "data_end",
        "limitation": "暴露≠损失；无分作物灾损标签，不能解释为减产概率",
    }