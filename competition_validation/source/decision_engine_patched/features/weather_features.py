# -*- coding: utf-8 -*-
"""气象/土壤特征（六城日频，point-in-time）。

用途：
  - 气候暴露指数（主用途）；
  - 价格模型 weather ablation（默认不进入正式价格模型）。
基线：气象数据范围 2010-01-01 起，无 1991-2020；使用 2010-2019 固定历史基线
（全部早于价格建模期 2021+，不构成泄漏）。
"""
from __future__ import annotations
from pathlib import Path

import numpy as np
import pandas as pd

from decision_engine.common import de_path

SNAP = de_path("data", "snapshots", "v1")
CITY_FILE = {
    "沈阳": "shenyang", "朝阳": "chaoyang", "锦州": "jinzhou",
    "大连": "dalian", "铁岭": "tieling", "丹东": "dandong",
}
BASE_YEARS = (2010, 2019)   # 固定历史基线窗口（无 1991-2020 数据）


def _consec_days(flag: pd.Series) -> pd.Series:
    """连续 True 天数（含当天），False 归零。"""
    f = flag.astype(int)
    return f.groupby((f == 0).cumsum()).cumsum()


def build_city_weather(city_cn: str) -> pd.DataFrame:
    slug = CITY_FILE[city_cn]
    w = pd.read_csv(SNAP / f"city_data/{slug}/data/weather_daily_era5.csv", low_memory=False)
    w["date"] = pd.to_datetime(w["date"])
    w = w.sort_values("date").reset_index(drop=True)
    df = pd.DataFrame({
        "date": w["date"],
        "city": city_cn,
        "tmax": w["temperature_2m_max"],
        "tmin": w["temperature_2m_min"],
        "tmean": w["temperature_2m_mean"],
        "precip": w["precipitation_sum"],
        "rh": w.get("relative_humidity_2m_mean"),
        "et0": w.get("et0_fao_evapotranspiration"),
    })

    # 累积降水（含当天，<=t）
    for k in [7, 14, 30]:
        df[f"precip_{k}d"] = df["precip"].rolling(k, min_periods=k).sum()
    df["heavy_rain_flag"] = (df["precip"] >= 50).astype(int)
    df["heavy_rain_days_30"] = df["heavy_rain_flag"].rolling(30, min_periods=15).sum()

    # 固定历史基线（2010-2019）：doy 气候态与分位
    base = df[(df["date"].dt.year >= BASE_YEARS[0]) & (df["date"].dt.year <= BASE_YEARS[1])].copy()
    base["doy"] = base["date"].dt.dayofyear
    clim_t = base.groupby("doy")["tmean"].mean()
    clim_p = base.groupby("doy")["precip"].mean()
    p90_tmax = base.groupby("doy")["tmax"].quantile(0.90)
    p95_tmax = base.groupby("doy")["tmax"].quantile(0.95)
    df["doy"] = df["date"].dt.dayofyear
    df["temp_anomaly"] = df["tmean"] - df["doy"].map(clim_t)
    df["precip_anomaly"] = df["precip"] - df["doy"].map(clim_p)
    df["temp_p90_flag"] = (df["tmax"] >= df["doy"].map(p90_tmax)).astype(int)
    df["temp_p95_flag"] = (df["tmax"] >= df["doy"].map(p95_tmax)).astype(int)
    df["rolling_heat_days_7"] = df["temp_p90_flag"].rolling(7, min_periods=3).sum()
    df["rain_p90_flag"] = (df["precip"] >= df["doy"].map(
        base.groupby("doy")["precip"].quantile(0.90))).astype(int)

    # 干旱：连续少雨天数（<1mm）
    df["dry_spell_days"] = _consec_days(df["precip"] < 1.0)

    # 土壤（沈阳来自 supplement；其余五城来自 soil_daily.csv）
    if city_cn == "沈阳":
        soil = pd.read_csv(SNAP / "city_data/reference/decision_engine_supplement/soil_moisture_daily_extended.csv",
                           low_memory=False)
    else:
        soil = pd.read_csv(SNAP / f"city_data/{slug}/data/soil_daily.csv", low_memory=False)
    soil["date"] = pd.to_datetime(soil["date"])
    soil = soil.rename(columns={"soil_water_layer_1": "soil_moisture_0_7",
                                "soil_water_layer_2": "soil_moisture_7_28",
                                "soil_water_layer_3": "soil_moisture_28_100"})
    df = df.merge(soil[["date", "soil_moisture_0_7", "soil_moisture_7_28", "soil_moisture_28_100"]]
                  if "soil_moisture_7_28" in soil.columns else
                  soil[["date", "soil_moisture_0_7"]],
                  on="date", how="left", validate="one_to_one")
    df["soil_moisture_percentile"] = df["soil_moisture_0_7"].expanding(min_periods=90).rank(pct=True)
    df = df.drop(columns=["doy"])
    return df


def build_all() -> dict:
    out = {}
    for city in CITY_FILE:
        df = build_city_weather(city)
        p = de_path("data", "features", f"weather_features_{CITY_FILE[city]}.parquet")
        df.to_parquet(p, index=False)
        out[city] = df
        print(f"[weather] {city}: {df.shape} -> {p.name}")
    return out


if __name__ == "__main__":
    build_all()