"""STEP D4 — 区县天气采集与年度气象派生（与既有沈阳天气体系同源）。

天气体系（与 `` 沈阳市场研究**完全一致**，不换源）：
  · 源：Open-Meteo Archive API（ERA5 / ERA5-Land 再分析）
      https://archive-api.open-meteo.com/v1/archive
  · 日核心变量：temperature_2m_max/min/mean, precipitation_sum,
      relative_humidity_2m_mean, wind_speed_10m_max, shortwave_radiation_sum,
      et0_fao_evapotranspiration, soil_moisture_0_to_10cm_mean, sunshine_duration
  · 扩展日变量：pressure_msl_mean, surface_pressure_mean, dew_point_2m_mean,
      snowfall_sum, snow_depth_mean, cloud_cover_mean,
      vapour_pressure_deficit_max, wind_gusts_10m_max
  · 土壤分层：ERA5-Land hourly（0-7/7-28/28-100cm 含水量 + 0-7cm 土温）→ 日聚合
  · 时区 Asia/Shanghai；data_type=reanalysis（**非气象站观测**）

时间范围：2015-01-01 ~ 2025-12-31（覆盖年鉴数据年 2015-2024 与 2025 公报年）。
代表点：district_coordinates.csv（8 个农业区县，区行政中心）。

年度派生（阈值沿用项目 config/analysis.yaml hazard_thresholds，不新造定义）：
  温度：年均温、生长季均温、高温日数(≥35℃)、极端高温日数(≥37℃，本层补充指标)、
        低温日数(日最低≤0℃ 霜冻，config frost_tmin_c)
  降水：年累计、生长季累计、强降水日数(≥50mm 暴雨 / ≥25mm 大雨)、
        最长连续降水日数、最大1/3/5日累计降水
  其他：VPD 均值、ET0 累计、相对湿度均值
  生长季 = config time.growing_season_months（5-9 月）

红线：不插值；缺失即缺失；原始 JSON 全部留档；不把再分析写成气象站实测。

产出：
  data/raw/district_production/district_weather/openmeteo_{district}_{tag}.json
  data/processed/district_weather_daily.parquet
  data/processed/district_weather_yearly.csv
"""
from __future__ import annotations

import json
import ssl
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import ANALYSIS, PATHS, StepTimer, get_logger, save_table  # noqa: E402

MOD = "23_district_weather"
LOG = get_logger(MOD)
RAW = PATHS.project["data_raw_district"] / "district_weather"
PROC = PATHS.project["data_processed"]

START, END = "2015-01-01", "2025-12-31"
OM = "https://archive-api.open-meteo.com/v1/archive"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

CORE_DAILY = ["temperature_2m_max", "temperature_2m_min", "temperature_2m_mean",
              "precipitation_sum", "relative_humidity_2m_mean", "wind_speed_10m_max",
              "shortwave_radiation_sum", "et0_fao_evapotranspiration",
              "soil_moisture_0_to_10cm_mean", "sunshine_duration"]
EXTRA_DAILY = ["pressure_msl_mean", "surface_pressure_mean", "dew_point_2m_mean",
               "snowfall_sum", "snow_depth_mean", "cloud_cover_mean",
               "vapour_pressure_deficit_max", "wind_gusts_10m_max"]
SOIL_HOURLY = ["soil_moisture_0_to_7cm", "soil_moisture_7_to_28cm",
               "soil_moisture_28_to_100cm", "soil_temperature_0_to_7cm"]

CORE_MAP = {
    "temperature_2m_max": "temperature_max", "temperature_2m_min": "temperature_min",
    "temperature_2m_mean": "temperature_mean", "precipitation_sum": "precipitation",
    "relative_humidity_2m_mean": "relative_humidity", "wind_speed_10m_max": "wind_speed",
    "shortwave_radiation_sum": "radiation", "et0_fao_evapotranspiration": "et0",
    "soil_moisture_0_to_10cm_mean": "soil_moisture_0_10", "sunshine_duration": "sunshine_duration",
}
EXTRA_MAP = {
    "pressure_msl_mean": "pressure_msl", "surface_pressure_mean": "surface_pressure",
    "dew_point_2m_mean": "dew_point", "snowfall_sum": "snowfall",
    "snow_depth_mean": "snow_depth", "cloud_cover_mean": "cloud_cover",
    "vapour_pressure_deficit_max": "vpd", "wind_gusts_10m_max": "wind_gust_max",
}
SOIL_MAP = {
    "soil_moisture_0_to_7cm": "soil_moisture_0_7",
    "soil_moisture_7_to_28cm": "soil_moisture_7_28",
    "soil_moisture_28_to_100cm": "soil_moisture_28_100",
    "soil_temperature_0_to_7cm": "soil_temperature",
}

HAZ = ANALYSIS["hazard_thresholds"]
GROW = list(ANALYSIS["time"]["growing_season_months"])
HEAVY_25, STORM_50 = 25.0, float(HAZ["rainstorm_daily_mm"])
HOT_35, EX_HOT_37, FROST = float(HAZ["heat_tmax_c"]), 37.0, float(HAZ["frost_tmin_c"])


def http_json(url: str, timeout: int = 180, retries: int = 5) -> dict:
    import urllib.error
    last = None
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code in (429, 500, 502, 503, 504):
                w = 6 * (a + 1)
                LOG.warning("HTTP %s 退避 %ds", exc.code, w)
                time.sleep(w)
                continue
            raise
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(4)
    raise last


def districts() -> pd.DataFrame:
    d = pd.read_csv(PATHS.artifacts["district_coordinates"], dtype={"admin_code": str})
    return d[d["is_agricultural"] == 1].reset_index(drop=True)


def fetch_all(log) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    for _, r in districts().iterrows():
        ds, lat, lon = r["district"], r["latitude"], r["longitude"]
        # 1) 核心日变量（整段一次）
        out = RAW / f"openmeteo_{ds}_core_{START}_{END}.json"
        if not out.exists():
            p = {"latitude": lat, "longitude": lon, "start_date": START, "end_date": END,
                 "daily": ",".join(CORE_DAILY), "timezone": "Asia/Shanghai"}
            d = http_json(f"{OM}?{urllib.parse.urlencode(p)}")
            out.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            log.info("[OK] %s 核心日变量 %d 天", ds, len(d.get("daily", {}).get("time", [])))
            time.sleep(2)
        else:
            log.info("[SKIP] %s 核心日变量", ds)
        # 2) 扩展日变量（整段一次）
        out = RAW / f"openmeteo_{ds}_extra_{START}_{END}.json"
        if not out.exists():
            p = {"latitude": lat, "longitude": lon, "start_date": START, "end_date": END,
                 "daily": ",".join(EXTRA_DAILY), "timezone": "Asia/Shanghai"}
            d = http_json(f"{OM}?{urllib.parse.urlencode(p)}")
            out.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            log.info("[OK] %s 扩展日变量 %d 天", ds, len(d.get("daily", {}).get("time", [])))
            time.sleep(2)
        else:
            log.info("[SKIP] %s 扩展日变量", ds)
        # 3) 土壤分层（ERA5-Land hourly，逐年）
        for year in range(int(START[:4]), int(END[:4]) + 1):
            s, e = f"{year}-01-01", f"{year}-12-31"
            out = RAW / f"openmeteo_{ds}_soil_{year}.json"
            if out.exists():
                continue
            p = {"latitude": lat, "longitude": lon, "start_date": s, "end_date": e,
                 "hourly": ",".join(SOIL_HOURLY), "models": "era5_land",
                 "timezone": "Asia/Shanghai"}
            try:
                d = http_json(f"{OM}?{urllib.parse.urlencode(p)}")
                out.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
                log.info("[OK] %s 土壤 %d", ds, year)
            except Exception as exc:  # noqa: BLE001
                log.warning("[FAIL] %s 土壤 %d：%s", ds, year, exc)
            time.sleep(1.5)


def build_daily() -> pd.DataFrame:
    frames = []
    for _, r in districts().iterrows():
        ds = r["district"]
        core_f = RAW / f"openmeteo_{ds}_core_{START}_{END}.json"
        if not core_f.exists():
            continue
        dc = json.loads(core_f.read_text(encoding="utf-8")).get("daily", {})
        df = pd.DataFrame({"date": pd.to_datetime(pd.Series(dc["time"]))})
        for k, v in CORE_MAP.items():
            if k in dc:
                df[v] = dc[k]
        ex_f = RAW / f"openmeteo_{ds}_extra_{START}_{END}.json"
        if ex_f.exists():
            de = json.loads(ex_f.read_text(encoding="utf-8")).get("daily", {})
            if "time" in de and len(de["time"]) == len(df):
                for k, v in EXTRA_MAP.items():
                    if k in de:
                        df[v] = de[k]
        # 土壤逐年合并
        soil_parts = []
        for f in sorted(RAW.glob(f"openmeteo_{ds}_soil_*.json")):
            dh = json.loads(f.read_text(encoding="utf-8")).get("hourly", {})
            if not dh or "time" not in dh:
                continue
            s = pd.DataFrame({"ts": pd.to_datetime(pd.Series(dh["time"]))})
            for k in SOIL_HOURLY:
                if k in dh:
                    s[k] = dh[k]
            s["date"] = s["ts"].dt.normalize()
            g = s.groupby("date").mean(numeric_only=True).reset_index()
            soil_parts.append(g)
        if soil_parts:
            soil = pd.concat(soil_parts, ignore_index=True).rename(columns=SOIL_MAP)
            df = df.merge(soil.drop(columns=["ts"], errors="ignore"), on="date", how="left")
        df["district"] = ds
        frames.append(df)
    out = pd.concat(frames, ignore_index=True).sort_values(["district", "date"]).reset_index(drop=True)
    out["weather_source"] = "open-meteo-era5-reanalysis"
    out["data_type"] = "reanalysis"
    return out


def _max_consec(series: pd.Series, thr: float, ge: bool = True) -> int:
    m = (series >= thr) if ge else (series < thr)
    best = cur = 0
    for v in m.to_numpy():
        cur = cur + 1 if v else 0
        best = max(best, cur)
    return best


def _roll_max(series: pd.Series, k: int) -> float:
    if len(series) < k:
        return np.nan
    return float(series.rolling(k, min_periods=k).sum().max())


def yearly_agg(daily: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (ds, yr), g in daily.groupby(["district", daily["date"].dt.year]):
        g = g.sort_values("date")
        gs = g[g["date"].dt.month.isin(GROW)]
        rec = {
            "district": ds, "year": int(yr), "n_days": int(len(g)),
            # 温度
            "temp_mean": g["temperature_mean"].mean(),
            "temp_max_abs": g["temperature_max"].max(),
            "temp_min_abs": g["temperature_min"].min(),
            "growing_season_temp_mean": gs["temperature_mean"].mean(),
            "hot_days": int((g["temperature_max"] >= HOT_35).sum()),
            "hot_days_growing": int((gs["temperature_max"] >= HOT_35).sum()),
            "extreme_hot_days": int((g["temperature_max"] >= EX_HOT_37).sum()),
            "low_temp_days": int((g["temperature_min"] <= FROST).sum()),
            # 降水
            "precip_sum": g["precipitation"].sum(),
            "growing_season_precip": gs["precipitation"].sum(),
            "heavy_rain_days": int((g["precipitation"] >= STORM_50).sum()),
            "heavy_rain_days_growing": int((gs["precipitation"] >= STORM_50).sum()),
            "moderate_rain_days": int((g["precipitation"] >= HEAVY_25).sum()),
            "max_consec_wet_days": _max_consec(g["precipitation"], 0.1),
            "max_consec_dry_days": _max_consec(g["precipitation"], 1.0, ge=False),
            "max_1d_precip": float(g["precipitation"].max()),
            "max_3d_precip": _roll_max(g["precipitation"], 3),
            "max_5d_precip": _roll_max(g["precipitation"], 5),
            "growing_season_max_1d_precip": float(gs["precipitation"].max()) if len(gs) else np.nan,
            "growing_season_max_3d_precip": _roll_max(gs["precipitation"], 3),
            "growing_season_max_5d_precip": _roll_max(gs["precipitation"], 5),
            # 其他
            "humidity_mean": g["relative_humidity"].mean(),
            "growing_season_humidity_mean": gs["relative_humidity"].mean(),
            "vpd_mean": g["vpd"].mean() if "vpd" in g else np.nan,
            "growing_season_vpd_mean": gs["vpd"].mean() if "vpd" in g else np.nan,
            "et0_sum": g["et0"].sum(),
            "growing_season_et0_sum": gs["et0"].sum(),
            "radiation_sum": g["radiation"].sum(),
            "growing_season_radiation_sum": gs["radiation"].sum(),
            "growing_season_soil_moisture_mean": (gs["soil_moisture_0_7"].mean()
                                                  if "soil_moisture_0_7" in gs else np.nan),
            "weather_source": "open-meteo-era5-reanalysis",
        }
        rows.append(rec)
    out = pd.DataFrame(rows).sort_values(["district", "year"]).reset_index(drop=True)
    return out


def main() -> None:
    with StepTimer(MOD, LOG):
        log = LOG
        log.info("区县天气采集（%s ~ %s；8 个农业区县；Open-Meteo ERA5 再分析）", START, END)
        fetch_all(log)
        daily = build_daily()
        p = PATHS.artifacts["district_weather_daily"]
        p.parent.mkdir(parents=True, exist_ok=True)
        daily.to_parquet(p, index=False)
        log.info("已写 %s：%d 行 × %d 列；%s~%s；区县 %d",
                 p.name, len(daily), daily.shape[1],
                 daily["date"].min().date(), daily["date"].max().date(), daily["district"].nunique())
        yr = yearly_agg(daily)
        q = PATHS.artifacts["district_weather_yearly"]
        yr.to_csv(q, index=False, encoding="utf-8-sig")
        save_table(yr, "district_weather_yearly.csv")
        log.info("已写 %s：%d 行；年份 %s", q.name, len(yr), sorted(yr["year"].unique()))
        log.info("生长季 = %s 月", GROW)


if __name__ == "__main__":
    main()
