#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
采集沈北新区逐小时降水/气温/土壤湿度（Open-Meteo ERA5 / ERA5-Land 再分析）。
- 数据性质：再分析（reanalysis），不是气象站实测。来源标注必须写明。
- 输出：02_raw/weather/openmeteo_hourly_沈北新区_<year>.json（逐年分块）
- 站点坐标：42.003513, 123.53712（沈北新区行政中心代表点，与既有 AgriScope 沈北天气同源）
"""
import json
import os
import time
import urllib.parse
import urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "02_raw", "weather")
os.makedirs(OUT, exist_ok=True)

LAT, LON = 42.003513, 123.53712
TZ = "Asia/Shanghai"


def get(url, retries=5):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AgriScope-Research/1.0"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa
            last = e
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"failed: {last}")


def fetch_chunk(start, end, tag):
    params = {
        "latitude": LAT,
        "longitude": LON,
        "start_date": start,
        "end_date": end,
        "hourly": "precipitation,temperature_2m,relative_humidity_2m,wind_speed_10m",
        "timezone": TZ,
    }
    url = "https://archive-api.open-meteo.com/v1/archive?" + urllib.parse.urlencode(params)
    d = get(url)
    d["_meta"] = {
        "source": "Open-Meteo Archive API (ERA5 / ERA5-Land reanalysis)",
        "data_nature": "reanalysis_not_station_observation",
        "requested_start": start,
        "requested_end": end,
        "variable": "hourly precipitation(mm), temperature_2m(C), relative_humidity_2m(%), wind_speed_10m(km/h)",
        "point": {"lat": LAT, "lon": LON, "label": "沈北新区行政中心代表点"},
    }
    path = os.path.join(OUT, f"openmeteo_hourly_沈北新区_{tag}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    n = len(d.get("hourly", {}).get("time", []))
    print(f"[ok] {tag}: {start}..{end} -> {n} hourly rows -> {path}")
    return n


def main():
    total = 0
    for y in range(2015, 2026):
        total += fetch_chunk(f"{y}-01-01", f"{y}-12-31", str(y))
    total += fetch_chunk("2026-01-01", "2026-09-14", "2026")
    print(f"TOTAL hourly rows = {total}")


if __name__ == "__main__":
    main()
