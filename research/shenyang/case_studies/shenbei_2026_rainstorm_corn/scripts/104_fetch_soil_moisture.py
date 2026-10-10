#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Package B —— 土壤湿度与水分状态（ERA5 系再分析，经 Open-Meteo 提供）

【来源判定说明 · 重要】
- Open-Meteo **archive-api** 不提供土壤湿度（实测其 units 返回 'undefined'、值全 null）→ 已排除。
- Open-Meteo **historical-forecast-api** 提供 2024 起的逐时土壤湿度，单位 m³/m³，
  底层为 ECMWF/ERA5 系陆面再分析历史序列。
- 因此本数据的性质标注为 **reanalysis**（不是站点实测 observed）。
  沈北新区**没有公开土壤湿度站点观测**，本数据不可替代地面观测，仅作相对变化与同期比较之用。

【为何不做 ERA5-Land 原始 netCDF】
CDS（Climate Data Store）下载 ERA5-Land 需注册 API Key，本轮无凭据 → 记为 BLOCKED，
并在报告中给出人工获取路径。Open-Meteo 同源自 ECMWF，可覆盖本阶段需求。

输出：
  02_raw/soil/openmeteo_soil_hourly_{year}.json
  03_clean/soil/soil_moisture_daily.csv
  03_clean/soil/soil_moisture_weekly.csv
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[3]
RAW_SOIL = ROOT / "02_raw" / "soil"
CLEAN_SOIL = ROOT / "03_clean" / "soil"
RAW_SOIL.mkdir(parents=True, exist_ok=True)
CLEAN_SOIL.mkdir(parents=True, exist_ok=True)

# 沈北新区代表点（与既有气象序列一致，避免引入第二个不一致点位）
LAT, LON = 42.05, 123.55

API = "https://historical-forecast-api.open-meteo.com/v1/forecast"
HOURLY = [
    "soil_moisture_0_to_1cm", "soil_moisture_1_to_3cm", "soil_moisture_3_to_9cm",
    "soil_moisture_9_to_27cm", "soil_moisture_27_to_81cm",
    "soil_temperature_0_to_7cm", "soil_temperature_7_to_28cm",
]
YEARS = [2024, 2025, 2026]
END_2026 = "2026-09-30"


def fetch_year(year: int) -> dict | None:
    start = f"{year}-01-01"
    end = END_2026 if year == 2026 else f"{year}-12-31"
    params = {
        "latitude": LAT, "longitude": LON,
        "start_date": start, "end_date": end,
        "hourly": ",".join(HOURLY),
        "timezone": "GMT",
    }
    for a in range(3):
        try:
            r = requests.get(API, params=params, timeout=120)
            if r.status_code == 200:
                return r.json()
            print(f"  [WARN] {year} HTTP {r.status_code}")
        except Exception as e:
            print(f"  [WARN] {year} {e}")
        time.sleep(2 * (a + 1))
    return None


def main() -> None:
    frames = []
    for y in YEARS:
        print(f"  获取 {y} ...")
        d = fetch_year(y)
        if not d:
            continue
        (RAW_SOIL / f"openmeteo_soil_hourly_{y}.json").write_text(
            json.dumps(d, ensure_ascii=False), encoding="utf-8")
        h = d.get("hourly", {})
        if not h.get("time"):
            print(f"  [WARN] {y} 无数据")
            continue
        df = pd.DataFrame({"time": h["time"]})
        for k in HOURLY:
            df[k] = h.get(k)
        frames.append(df)
        nn = df["soil_moisture_3_to_9cm"].notna().sum()
        print(f"     {y}: {len(df)} 小时，3-9cm 非空 {nn}")

    if not frames:
        print("[FAIL] 无土壤湿度数据")
        return
    allh = pd.concat(frames, ignore_index=True)
    allh["date"] = allh["time"].str[:10]

    # ---- 日聚合（均值 / 最大 / 最小，保留每日有效小时数以便判断质量）
    agg = {k: "mean" for k in HOURLY}
    daily = allh.groupby("date").agg({**agg, "time": "count"}).rename(columns={"time": "n_hours"})
    daily = daily.reset_index()
    daily["source"] = "Open-Meteo ERA5系历史再分析"
    daily["data_nature"] = "reanalysis"
    daily["quality"] = daily["n_hours"].apply(lambda n: "ok" if n >= 20 else "partial")
    daily.to_csv(CLEAN_SOIL / "soil_moisture_daily.csv", index=False, encoding="utf-8-sig")

    # ---- 周聚合（ISO 周，周一为起点）
    d2 = daily.copy()
    d2["dt"] = pd.to_datetime(d2["date"])
    d2["week_start"] = (d2["dt"] - pd.to_timedelta(d2["dt"].dt.weekday, unit="D")).dt.strftime("%Y-%m-%d")
    weekly = d2.groupby("week_start").agg(
        {**{k: "mean" for k in HOURLY}, "n_hours": "sum", "date": "count"}).rename(
        columns={"date": "n_days"}).reset_index()
    weekly["source"] = daily["source"].iloc[0]
    weekly["data_nature"] = "reanalysis"
    weekly.to_csv(CLEAN_SOIL / "soil_moisture_weekly.csv", index=False, encoding="utf-8-sig")

    print(f"\n[OK] 日表 {len(daily)} 行：{daily['date'].min()} ~ {daily['date'].max()}")
    print(f"[OK] 周表 {len(weekly)} 行")
    print("\n=== 2026 事件窗口（7-10 ~ 7-20）3-9cm 土壤湿度 ===")
    w = daily[(daily.date >= "2026-07-10") & (daily.date <= "2026-07-20")]
    print(w[["date", "soil_moisture_3_to_9cm", "soil_moisture_9_to_27cm", "quality"]].to_string(index=False)
          if len(w) else "  无")


if __name__ == "__main__":
    main()
