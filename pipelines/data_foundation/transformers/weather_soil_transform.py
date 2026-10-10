"""扩展气象变量与土壤分层转换为事实表（手册第 8、9 节）。

- 土壤：ERA5-Land hourly（0-7 / 7-28 / 28-100cm 含水量 + 0-7cm 土温）→ 日聚合
- 扩展气象：气压 / 露点 / 降雪 / 雪深 / 云量 / VPD / 阵风 → 日表
一律标记 data_type = reanalysis。
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW_W = ROOT / "data/raw" / "weather"
RAW_S = ROOT / "data/raw" / "soil"
MARTS = ROOT / "city_data/reference/marts"
MARTS.mkdir(parents=True, exist_ok=True)

EXTRA_MAP = {
    "pressure_msl_mean": "pressure_msl",
    "surface_pressure_mean": "surface_pressure",
    "dew_point_2m_mean": "dew_point",
    "snowfall_sum": "snowfall",
    "snow_depth_mean": "snow_depth",
    "cloud_cover_mean": "cloud_cover",
    "vapour_pressure_deficit_max": "vpd_max",
    "wind_gusts_10m_max": "wind_gust_max",
}


def build_extra_daily() -> pd.DataFrame:
    frames = []
    for f in RAW_W.glob("openmeteo_extra_*.json"):
        city = f.name.split("_")[2]
        d = json.loads(f.read_text(encoding="utf-8")).get("daily", {})
        if not d:
            continue
        df = pd.DataFrame({"date": pd.to_datetime(pd.Series(d["time"])).dt.date})
        for k, v in EXTRA_MAP.items():
            if k in d:
                df[v] = d[k]
        df["city"] = city
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out["data_type"] = "reanalysis"
    out["weather_source"] = "open-meteo-era5-reanalysis"
    return out.sort_values(["city", "date"])


def build_soil_daily() -> pd.DataFrame:
    frames = []
    for f in sorted(RAW_S.glob("openmeteo_soil_*.json")):
        parts = f.stem.split("_")
        city, year = parts[2], parts[3]
        d = json.loads(f.read_text(encoding="utf-8")).get("hourly", {})
        if not d or "time" not in d:
            continue
        df = pd.DataFrame({"ts": pd.to_datetime(pd.Series(d["time"]))})
        for k in ("soil_moisture_0_to_7cm", "soil_moisture_7_to_28cm",
                  "soil_moisture_28_to_100cm", "soil_temperature_0_to_7cm"):
            if k in d:
                df[k] = d[k]
        df["date"] = df["ts"].dt.date
        g = df.groupby("date").mean(numeric_only=True).reset_index()
        g["city"] = city
        g["year"] = year
        frames.append(g)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out = out.rename(columns={
        "soil_moisture_0_to_7cm": "soil_water_layer_1",
        "soil_moisture_7_to_28cm": "soil_water_layer_2",
        "soil_moisture_28_to_100cm": "soil_water_layer_3",
        "soil_temperature_0_to_7cm": "soil_temperature",
    })
    out["data_type"] = "reanalysis_era5_land"
    out["source"] = "Open-Meteo Archive API / ERA5-Land"
    out["aggregation_method"] = "hourly_mean_to_daily"
    return out.drop(columns=["year"]).sort_values(["city", "date"])


def main() -> None:
    ex = build_extra_daily()
    if not ex.empty:
        ex.to_parquet(MARTS / "fact_weather_extra_daily.parquet", index=False)
        ex.to_csv(MARTS / "fact_weather_extra_daily.csv", index=False, encoding="utf-8-sig")
        print(f"[OK] fact_weather_extra_daily {len(ex)} 行，变量 {ex.shape[1]-4} 个")
        print("   城市:", dict(ex["city"].value_counts()))

    soil = build_soil_daily()
    if not soil.empty:
        soil.to_parquet(MARTS / "fact_soil_daily.parquet", index=False)
        soil.to_csv(MARTS / "fact_soil_daily.csv", index=False, encoding="utf-8-sig")
        print(f"[OK] fact_soil_daily {len(soil)} 行")
        print("   城市:", dict(soil["city"].value_counts()))
        print(f"   日期范围: {soil['date'].min()} ~ {soil['date'].max()}")
        print(f"   土壤含水量缺失: {int(soil['soil_water_layer_1'].isna().sum())}")


if __name__ == "__main__":
    main()
