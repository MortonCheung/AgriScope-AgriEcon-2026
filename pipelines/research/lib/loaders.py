"""loaders.py — 六城统一数据载入 + crop_raw 标准化 + 价格分层。

只读。所有研究模块必须经此层取数，禁止各模块自行拼路径或另立标准。
"""
from __future__ import annotations

from functools import lru_cache
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import yaml

from . import paths


@lru_cache(maxsize=1)
def load_cities() -> Dict:
    return yaml.safe_load((paths.CONFIG / "cities.yaml").read_text(encoding="utf-8"))["cities"]


@lru_cache(maxsize=1)
def load_crops() -> Dict:
    return yaml.safe_load((paths.CONFIG / "crops.yaml").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_analysis() -> Dict:
    return yaml.safe_load((paths.CONFIG / "analysis.yaml").read_text(encoding="utf-8"))


def crop_map() -> Dict[str, str]:
    return {str(k): str(v) for k, v in load_crops()["map"].items()}


def veg_crops() -> List[str]:
    return list(load_crops()["categories"]["vegetable"])


def _standardize_crop(s: pd.Series) -> pd.Series:
    m = crop_map()
    return s.astype(str).str.strip().map(lambda x: m.get(x, None))


# ---------------------------------------------------------------------------
# 价格
# ---------------------------------------------------------------------------
def load_price_all(city: str) -> pd.DataFrame:
    """读入该城全部价格观测，附 crop(=std) 字段。"""
    p = paths.city_data_dir(city) / "price_observation.csv"
    df = pd.read_csv(p, encoding="utf-8-sig", low_memory=False)
    df["date"] = pd.to_datetime(df["observation_date"], errors="coerce")
    df["crop_std"] = _standardize_crop(df["crop_raw"]) if "crop_raw" in df.columns else None
    if "price_per_kg" not in df.columns:
        df["price_per_kg"] = np.nan
    df["price_per_kg"] = pd.to_numeric(df["price_per_kg"], errors="coerce")
    return df


def load_primary_price(city: str, level_filter: bool = False) -> pd.DataFrame:
    """该城主源价格（子串匹配 primary_sources），返回 date/crop_raw/crop_std/price_per_kg/
    price_level/source_name/quality_grade/county。"""
    cfg = load_cities()[city]
    df = load_price_all(city)
    pats = cfg.get("primary_sources", [])
    mask = pd.Series(False, index=df.index)
    for pat in pats:
        mask |= df["source_name"].astype(str).str.contains(pat, na=False)
    sub = df[mask].copy()
    sub = sub.dropna(subset=["date", "price_per_kg"])
    keep = ["date", "crop_raw", "crop_std", "price_per_kg", "price_level",
            "source_name", "quality_grade"]
    keep = [c for c in keep if c in sub.columns]
    if "county" in sub.columns:
        keep += ["county"]
    sub = sub[keep]
    return sub.reset_index(drop=True)


def load_primary_series(city: str, crop_std: str, agg: str = "median") -> pd.DataFrame:
    """该城某标准化作物的日度序列（同日多重记录按 agg 聚合）。"""
    sub = load_primary_price(city)
    s = sub[sub["crop_std"] == crop_std]
    if s.empty:
        return pd.DataFrame(columns=["date", "price_per_kg", "n"])
    g = s.groupby("date")["price_per_kg"].agg(["median", "mean", "count"]).reset_index()
    g = g.rename(columns={"median": "price_per_kg", "count": "n"})[
        ["date", "price_per_kg", "n"]].sort_values("date")
    return g.reset_index(drop=True)


# ---------------------------------------------------------------------------
# 气象 / 土壤
# ---------------------------------------------------------------------------
def _es_kpa(t_c: pd.Series) -> pd.Series:
    """饱和水汽压（kPa），FAO-56。"""
    return 0.6108 * np.exp(17.27 * t_c / (t_c + 237.3))


def load_weather(city: str) -> pd.DataFrame:
    """该城日度气象（ERA5 再分析网格）+ 土壤（ERA5-Land），并派生 VPD。

    注意：ERA5 为再分析网格，非气象站实测。
    """
    w = pd.read_csv(paths.city_data_dir(city) / "weather_daily_era5.csv", encoding="utf-8-sig")
    w["date"] = pd.to_datetime(w["date"])
    w = w.sort_values("date").reset_index(drop=True)
    # VPD（用日均温 + 相对湿度）
    if {"temperature_2m_mean", "relative_humidity_2m_mean"}.issubset(w.columns):
        es = _es_kpa(w["temperature_2m_mean"])
        w["vpd"] = es * (1 - w["relative_humidity_2m_mean"] / 100.0)
    soil_p = paths.city_data_dir(city) / "soil_daily.csv"
    if soil_p.exists():
        s = pd.read_csv(soil_p, encoding="utf-8-sig")
        s["date"] = pd.to_datetime(s["date"])
        s = s.rename(columns={"soil_water_layer_1": "soil_moisture_0_7"})
        cols = ["date"] + [c for c in ["soil_moisture_0_7", "soil_temperature"] if c in s.columns]
        w = w.merge(s[cols], on="date", how="left")
    return w


def weather_daily_index(city: str, start: str, end: str) -> pd.DataFrame:
    w = load_weather(city)
    w = w[(w["date"] >= start) & (w["date"] <= end)].copy()
    w = w.set_index("date").asfreq("D")
    return w


# ---------------------------------------------------------------------------
# 生产（年鉴）/ 物候 / 灾害
# ---------------------------------------------------------------------------
def load_production(city: str) -> pd.DataFrame:
    """该城年鉴生产（长表清洗）：year/crop/planting_area_kha/production_ton/yield_kg_per_ha。"""
    p = paths.PROCESSED / "production" / "production_yearly.parquet"
    df = pd.read_parquet(p)
    df = df[df["city"] == load_cities()[city]["name"]].copy()
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    for c in ["planting_area_kha", "production_ton", "yield_kg_per_ha"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["year", "crop"])
    df["crop"] = df["crop"].astype(str).str.strip()
    return df.reset_index(drop=True)


def load_phenology(city: str) -> pd.DataFrame:
    p = paths.city_data_dir(city) / "phenology_events.csv"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_csv(p, encoding="utf-8-sig", low_memory=False)
    for c in ["start_date", "end_date"]:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    return df


def load_disaster(city: str) -> pd.DataFrame:
    p = paths.city_data_dir(city) / "disaster_events_observed.csv"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_csv(p, encoding="utf-8-sig", low_memory=False)
    for c in ["start_date", "end_date"]:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    return df


def coverage_report(city: str, crop_std: str) -> Dict:
    """单作物覆盖画像（供可行性判断与局限说明）。"""
    s = load_primary_series(city, crop_std)
    if s.empty:
        return {"city": city, "crop": crop_std, "n_days": 0, "status": "NOT_FOUND"}
    gaps = s["date"].diff().dt.days.dropna()
    return {
        "city": city, "crop": crop_std, "n_days": int(len(s)),
        "date_min": str(s["date"].min().date()), "date_max": str(s["date"].max().date()),
        "median_gap_days": float(gaps.median()) if len(gaps) else None,
        "level": (load_primary_price(city)["price_level"].mode().iloc[0]
                  if not load_primary_price(city).empty else None),
    }