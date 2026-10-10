#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Data Foundation v1 · P4 整合层
从 02_standardized/ 派生 03_integrated/：
  city_daily_environment / city_crop_weekly / city_crop_monthly / city_crop_yearly / city_structural_context
所有月度/年度外部量 forward-map 到目标粒度时标注 source_frequency，保证 PIT 可识别。
"""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
STD = ROOT / "data/processed"
INT = ROOT / "data/processed/integrated"
INT.mkdir(parents=True, exist_ok=True)
LOG = []


def rp(sub, name):
    p = STD / sub / f"{name}.parquet"
    return pd.read_parquet(p) if p.exists() else None


def to_num(s):
    return pd.to_numeric(s, errors="coerce")


def build_daily_env():
    wx = rp("climate", "weather_daily")
    soil = rp("climate", "soil_daily")
    ndvi = rp("remote_sensing", "ndvi")
    va = rp("remote_sensing", "vegetation_anomaly")
    p = pd.DataFrame()
    if wx is not None:
        wx = wx.copy()
        wx["date"] = wx["date"].astype(str)
        keep = [c for c in ["city", "date", "temperature_2m_max", "temperature_2m_min", "temperature_2m_mean",
                            "precipitation_sum", "relative_humidity_2m_mean", "wind_speed_10m_max",
                            "shortwave_radiation_sum", "et0_fao_evapotranspiration"] if c in wx.columns]
        p = wx[keep].drop_duplicates(["city", "date"])
    if soil is not None and len(p):
        s = soil.copy(); s["date"] = s["date"].astype(str)
        sc = [c for c in s.columns if c not in ("city", "date")]
        p = p.merge(s[["city", "date"] + sc], on=["city", "date"], how="left", suffixes=("", "_soil"))
    if ndvi is not None and len(p):
        n = ndvi.copy(); n["ym"] = n["period"].astype(str)
        n = n[["city", "ym", "ndvi_mean", "ndvi_p10", "ndvi_p90", "valid_pixel_ratio"]].rename(
            columns={"ndvi_mean": "ndvi_mean", "valid_pixel_ratio": "ndvi_valid_ratio"})
        n["source_frequency_ndvi"] = "monthly"
        p["ym"] = p["date"].str[:7]
        p = p.merge(n, on=["city", "ym"], how="left")
    if va is not None and len(p):
        v = va[["city", "period", "ndvi_anomaly_z", "baseline_same_month"]].rename(columns={"period": "ym"})
        p = p.merge(v, on=["city", "ym"], how="left")
    if len(p):
        p.to_parquet(INT / "city_daily_environment.parquet", index=False)
        LOG.append(f"WRITE city_daily_environment {len(p)} rows cols={len(p.columns)}")


def build_crop_weekly():
    pr = rp("market", "price_observation")
    if pr is None:
        LOG.append("SKIP price panel: no price_observation"); return
    pr = pr.copy()
    pr["price_per_kg"] = to_num(pr["price_per_kg"])
    pr["observation_date"] = pd.to_datetime(pr["observation_date"], errors="coerce")
    pr = pr.dropna(subset=["observation_date", "price_per_kg"])
    pr = pr[pr["crop_standard"].astype(bool)]
    iso = pr["observation_date"].dt.isocalendar()
    pr["iso_year"] = iso.year.astype("int64"); pr["iso_week"] = iso.week.astype("int64")
    g = pr.groupby(["city", "crop_standard", "iso_year", "iso_week"], dropna=False).agg(
        price_mean=("price_per_kg", "mean"), price_median=("price_per_kg", "median"),
        price_min=("price_per_kg", "min"), price_max=("price_per_kg", "max"),
        price_std=("price_per_kg", "std"), price_n=("price_per_kg", "size"),
        price_level=("price_level", lambda x: "|".join(sorted(set(x.dropna().astype(str))))[:80]),
        n_markets=("market_name", "nunique")).reset_index()
    # 省份参考价（周）
    pv = rp("market", "province_price_reference")
    if pv is not None:
        pv = pv.copy()
        pv["price"] = to_num(pv.get("price"))
        pv["iso_year"] = to_num(pv["year"]).astype("Int64")
        pv["iso_week"] = to_num(pv["week"]).astype("Int64")
        pvv = pv.dropna(subset=["iso_year", "iso_week"]).groupby(
            ["crop_standard", "iso_year", "iso_week"], dropna=False)["price"].mean().reset_index()
        pvv.columns = ["crop_standard", "iso_year", "iso_week", "province_price_mean"]
        pvv["iso_year"] = pvv["iso_year"].astype("int64"); pvv["iso_week"] = pvv["iso_week"].astype("int64")
        g["iso_year"] = g["iso_year"].astype("int64"); g["iso_week"] = g["iso_week"].astype("int64")
        g = g.merge(pvv, on=["crop_standard", "iso_year", "iso_week"], how="left")
        g["city_vs_province_spread"] = g["price_mean"] - g["province_price_mean"]
    # 环境周均值
    env = rp("climate", "weather_daily")
    if env is not None:
        env = env.copy(); env["date"] = pd.to_datetime(env["date"], errors="coerce")
        env = env.dropna(subset=["date"])
        iso = env["date"].dt.isocalendar()
        env["iso_year"] = iso.year; env["iso_week"] = iso.week
        agg = {}
        for c in ["temperature_2m_mean", "precipitation_sum", "shortwave_radiation_sum", "wind_speed_10m_max"]:
            if c in env.columns:
                env[c] = to_num(env[c]); agg[c] = "mean"
        ew = env.groupby(["city", "iso_year", "iso_week"]).agg(agg).reset_index()
        ew.columns = ["city", "iso_year", "iso_week"] + [f"w_{k}" for k in agg]
        g = g.merge(ew, on=["city", "iso_year", "iso_week"], how="left")
    g = g.sort_values(["city", "crop_standard", "iso_year", "iso_week"])
    for lag in (1, 2, 4):
        g[f"price_lag_{lag}w"] = g.groupby(["city", "crop_standard"])["price_mean"].shift(lag)
    g.to_parquet(INT / "city_crop_weekly.parquet", index=False)
    LOG.append(f"WRITE city_crop_weekly {len(g)} rows cols={len(g.columns)}")


def build_crop_monthly():
    pr = rp("market", "price_observation")
    if pr is None:
        return
    pr = pr.copy()
    pr["price_per_kg"] = to_num(pr["price_per_kg"])
    d = pd.to_datetime(pr["observation_date"], errors="coerce")
    pr["year"] = d.dt.year; pr["month"] = d.dt.month
    pr = pr.dropna(subset=["year", "price_per_kg"])
    pr = pr[pr["crop_standard"].astype(bool)]
    g = pr.groupby(["city", "crop_standard", "year", "month"]).agg(
        price_mean=("price_per_kg", "mean"), price_median=("price_per_kg", "median"),
        price_n=("price_per_kg", "size")).reset_index()
    ndvi = rp("remote_sensing", "ndvi")
    if ndvi is not None:
        n = ndvi.copy(); n["year"] = to_num(n["year"]); n["month"] = to_num(n["month"])
        n = n[["city", "year", "month", "ndvi_mean", "ndvi_p10", "ndvi_p90", "valid_pixel_ratio"]]
        n["source_frequency_ndvi"] = "monthly"
        g = g.merge(n, on=["city", "year", "month"], how="left")
    g.to_parquet(INT / "city_crop_monthly.parquet", index=False)
    LOG.append(f"WRITE city_crop_monthly {len(g)} rows cols={len(g.columns)}")


def build_crop_yearly():
    area = rp("production", "planting_area_yearly")
    prod = rp("production", "production_yearly")
    out = None
    if area is not None:
        out = area.copy()
    if prod is not None:
        out = prod if out is None else pd.concat([out, prod], ignore_index=True)
    if out is not None:
        out.to_parquet(INT / "city_crop_yearly.parquet", index=False)
        LOG.append(f"WRITE city_crop_yearly {len(out)} rows cols={len(out.columns)}")


def build_structural():
    parts = []
    for sub, name, tag in [("production", "facility_agriculture", "facility"),
                           ("cost", "cost_components", "cost"),
                           ("cost", "crop_cost", "crop_cost"),
                           ("water", "irrigation_water", "irrigation"),
                           ("infrastructure", "cold_chain", "cold_chain"),
                           ("infrastructure", "market_accessibility", "accessibility"),
                           ("disaster", "insurance_claims", "insurance"),
                           ("demand", "population", "population")]:
        df = rp(sub, name)
        if df is not None:
            df = df.copy(); df["_block"] = tag
            parts.append(df)
    if parts:
        out = pd.concat(parts, ignore_index=True)
        out.to_parquet(INT / "city_structural_context.parquet", index=False)
        LOG.append(f"WRITE city_structural_context {len(out)} rows cols={len(out.columns)} (长表: _block 标识来源块)")


def main():
    build_daily_env(); build_crop_weekly(); build_crop_monthly(); build_crop_yearly(); build_structural()
    (ROOT / "data/metadata/quality").mkdir(parents=True, exist_ok=True)
    (ROOT / "data/metadata/quality/build_integrated.log").write_text("\n".join(LOG), encoding="utf-8")
    for l in LOG:
        print(l)


if __name__ == "__main__":
    main()
