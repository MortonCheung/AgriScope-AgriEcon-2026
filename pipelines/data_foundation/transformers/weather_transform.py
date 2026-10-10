"""气象日值 → 城市日值表 + ISO 周表 + 气候异常。

关键原则（手册第 13 节）：**价格周 == 天气周**，统一使用 ISO 周（周一→周日）。

数据源诚实标注：
- Open-Meteo = ERA5 再分析网格点（非观测站）
- NASA POWER = MERRA2 再分析
- weather_source 字段必须标明，不得冒充中国气象局观测站数据
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "weather_fallback"
CURATED = ROOT / "city_data/reference/curated"
MARTS = ROOT / "city_data/reference/marts"
META = ROOT / "data/raw/metadata"
for d in (CURATED, MARTS, META):
    d.mkdir(parents=True, exist_ok=True)

VAR_MAP = {
    "temperature_2m_max": "temp_max",
    "temperature_2m_min": "temp_min",
    "temperature_2m_mean": "temp_mean",
    "precipitation_sum": "precip",
    "relative_humidity_2m_mean": "humidity",
    "wind_speed_10m_max": "wind_max",
    "shortwave_radiation_sum": "sunshine_radiation",
    "et0_fao_evapotranspiration": "et0",
    "soil_moisture_0_to_10cm_mean": "soil_moisture",
}


def iso_of(d: date):
    return d.isocalendar()


def load_daily(city: str, period: str) -> pd.DataFrame | None:
    for f in RAW.glob(f"openmeteo_{city}_{period}_*.json"):
        data = json.loads(f.read_text(encoding="utf-8"))
        daily = data.get("daily", {})
        if not daily:
            return None
        df = pd.DataFrame({VAR_MAP.get(k, k): v for k, v in daily.items() if k in VAR_MAP or k == "time"})
        df = df.rename(columns={"time": "date"})
        df["date"] = pd.to_datetime(df["date"]).dt.date
        df["city"] = city
        return df
    return None


def longest_consecutive_rain(series: pd.Series) -> int:
    best = cur = 0
    for v in series:
        cur = cur + 1 if v >= 0.1 else 0
        best = max(best, cur)
    return best


def build_weekly(daily: pd.DataFrame) -> pd.DataFrame:
    d = daily.copy()
    iso = d["date"].apply(lambda x: x.isocalendar())
    d["iso_year"] = [i[0] for i in iso]
    d["iso_week"] = [i[1] for i in iso]
    d["week_start"] = d["date"].apply(lambda x: x - timedelta(days=x.weekday()))
    d["week_end"] = d["week_start"].apply(lambda x: x + timedelta(days=6))
    d["rain_day"] = (d["precip"] >= 0.1).astype(int)
    d["heavy_rain_25"] = (d["precip"] >= 25).astype(int)
    d["rainstorm_50"] = (d["precip"] >= 50).astype(int)
    d["hot_35"] = (d["temp_max"] >= 35).astype(int)
    d["freezing"] = (d["temp_min"] <= 0).astype(int)

    g = d.groupby(["city", "iso_year", "iso_week", "week_start", "week_end"])
    w = g.agg(
        temp_mean=("temp_mean", "mean"),
        temp_max=("temp_max", "max"),
        temp_min=("temp_min", "min"),
        precip_sum=("precip", "sum"),
        precip_max_daily=("precip", "max"),
        rain_days=("rain_day", "sum"),
        heavy_rain_25mm_days=("heavy_rain_25", "sum"),
        rainstorm_50mm_days=("rainstorm_50", "sum"),
        hot_35c_days=("hot_35", "sum"),
        freezing_days=("freezing", "sum"),
        humidity_mean=("humidity", "mean"),
        wind_mean=("wind_max", "mean"),
        wind_max=("wind_max", "max"),
        sunshine_sum=("sunshine_radiation", "sum"),
        et0_sum=("et0", "sum"),
        observation_days=("date", "count"),
    ).reset_index()

    # 最长连续降雨日数需按日序计算，逐周处理
    lcr = (d.sort_values(["city", "iso_year", "iso_week", "date"])
           .groupby(["city", "iso_year", "iso_week"])["rain_day"]
           .apply(longest_consecutive_rain).reset_index(name="longest_consecutive_rain_days"))
    w = w.merge(lcr, on=["city", "iso_year", "iso_week"], how="left")
    return w


def build_climatology() -> pd.DataFrame:
    """1991—2020 长期基线：按 (city, iso_week) 计算温度与降水的 30 年均值。"""
    frames = []
    for f in RAW.glob("openmeteo_*_baseline_*.json"):
        city = f.name.split("_")[1]
        data = json.loads(f.read_text(encoding="utf-8"))
        daily = data.get("daily", {})
        if not daily:
            continue
        df = pd.DataFrame({
            "date": pd.to_datetime(pd.Series(daily["time"])).dt.date,
            "temp_mean": daily["temperature_2m_mean"],
            "precip": daily["precipitation_sum"],
        })
        iso = df["date"].apply(lambda x: x.isocalendar())
        df["iso_week"] = [i[1] for i in iso]
        df["city"] = city
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    all_df = pd.concat(frames, ignore_index=True)
    clim = (all_df.groupby(["city", "iso_week"])
            .agg(temp_mean_clim=("temp_mean", "mean"),
                 precip_sum_clim=("precip", "mean"),
                 years=("date", "nunique"))
            .reset_index())
    clim["climatology_period"] = "1991-2020"
    return clim


def main() -> None:
    cities = [p["city"] for p in pd.read_csv(META / "cities.csv").to_dict("records")]

    # ---------- 日值 ----------
    daily_all = []
    for c in cities:
        df = load_daily(c, "current")
        if df is None:
            print(f"[WARN] {c} 无日值数据")
            continue
        daily_all.append(df)
        print(f"[OK] {c} 日值 {len(df)} 天")
    daily = pd.concat(daily_all, ignore_index=True)
    daily["weather_source"] = "open-meteo-era5-reanalysis"
    daily.to_parquet(MARTS / "fact_weather_daily.parquet", index=False)
    daily.to_csv(MARTS / "fact_weather_daily.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] fact_weather_daily {len(daily)} 行")

    # ---------- 周值 ----------
    weekly = build_weekly(daily)
    clim = build_climatology()
    if not clim.empty:
        clim.to_csv(CURATED / "weekly_climatology_1991_2020.csv", index=False, encoding="utf-8-sig")
        weekly = weekly.merge(clim[["city", "iso_week", "temp_mean_clim", "precip_sum_clim"]],
                              on=["city", "iso_week"], how="left")
        weekly["temp_anomaly"] = weekly["temp_mean"] - weekly["temp_mean_clim"]
        weekly["precip_anomaly"] = weekly["precip_sum"] - weekly["precip_sum_clim"]
        print(f"[OK] weekly_climatology {len(clim)} 行（1991—2020）")
    else:
        weekly["temp_anomaly"] = None
        weekly["precip_anomaly"] = None
    weekly["weather_source"] = "open-meteo-era5-reanalysis"
    weekly["station_count"] = 1  # 再分析网格点，非观测站
    weekly.to_parquet(MARTS / "fact_weather_weekly.parquet", index=False)
    weekly.to_csv(MARTS / "fact_weather_weekly.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] fact_weather_weekly {len(weekly)} 行")
    print("   城市:", dict(weekly["city"].value_counts()))

    # ---------- 站点主数据（诚实标注为再分析网格）----------
    city_df = pd.read_csv(META / "cities.csv")
    st = city_df[["city", "latitude", "longitude"]].copy()
    st["station_id"] = "OM-" + st["city"]
    st["station_name"] = st["city"] + " ERA5 再分析网格点"
    st["elevation"] = None
    st["district"] = ""
    st["source"] = "open-meteo-era5-reanalysis"
    st["station_type"] = "reanalysis_grid"   # 明确不是地面观测站
    st = st[["station_id", "station_name", "latitude", "longitude",
             "elevation", "city", "district", "station_type", "source"]]
    st.to_csv(META / "weather_stations.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] weather_stations.csv {len(st)} 行（reanalysis_grid）")


if __name__ == "__main__":
    main()
