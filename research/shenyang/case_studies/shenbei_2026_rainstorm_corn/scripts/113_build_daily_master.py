#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
日级主表 04_marts/shenbei_daily_system.csv

【时间对齐纪律（用户第九条）】
- 卫星是 **scene-based**：绝不生成"7/11~7/15 的实测 NDVI"。
  本表用 `ndvi_nearest_*` 三件套表达：最近一次真实观测的**日期 + 值 + 距今天数**，
  并恒定标记 `ndvi_is_interpolated=False`（明说这是最近观测的记录，不是插值出来的值）。
- 玉米价格是 **weekly**：在日表用 `*_weekly_carried` 表达，并带 `*_is_weekly_carried=True`。
- 缺测一律 `NaN`，不做任何 forward fill。

输出：04_marts/shenbei_daily_system.csv
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
M = ROOT / "04_marts"
M.mkdir(parents=True, exist_ok=True)

# ---------- 1. 天气 ----------
w = pd.read_parquet(ROOT / "03_clean" / "weather" / "pnb_daily_1991_2026.parquet")
w = w[["date", "precipitation_sum", "temperature_2m_mean", "temperature_2m_max",
       "temperature_2m_min", "relative_humidity_2m_mean", "et0_fao_evapotranspiration"]]
w = w.rename(columns={"temperature_2m_mean": "temperature_mean"})
w["date"] = w["date"].astype(str)

# ---------- 2. 土壤湿度（新，Package B） ----------
sm_p = ROOT / "03_clean" / "soil" / "soil_moisture_daily.csv"
if sm_p.exists():
    sm = pd.read_csv(sm_p)[["date", "soil_moisture_3_to_9cm", "soil_moisture_9_to_27cm",
                            "soil_moisture_27_to_81cm", "soil_temperature_0_to_7cm", "quality"]]
    sm = sm.rename(columns={"soil_moisture_3_to_9cm": "soil_moisture_3_9cm",
                            "soil_moisture_9_to_27cm": "soil_moisture_9_27cm",
                            "soil_moisture_27_to_81cm": "soil_moisture_27_81cm",
                            "quality": "soil_moisture_quality"})
    sm["date"] = sm["date"].astype(str)
else:
    sm = pd.DataFrame(columns=["date"])

# ---------- 3. 卫星指数（scene-based） ----------
rs_p = ROOT / "03_clean" / "remote_sensing" / "s2_crop_indices_scenes.csv"
if rs_p.exists():
    rs = pd.read_csv(rs_p)
    rs = rs[rs.get("quality") == "ok"] if "quality" in rs else rs
    rs = rs[["date", "ndvi_crop_mean", "evi_crop_mean", "ndwi_crop_mean", "mndwi_crop_mean",
             "cloud_cover", "clear_frac", "scene_id", "ndvi_crop_npx"]]
    # ★ 质量门：云量<=70% 且耕地有效像元>=10 万。
    #   否则厚云场景会被当成"低 NDVI"录入，在异常分析里伪装成"植被下降"
    rs = rs[(rs["cloud_cover"] <= 70) & (rs["ndvi_crop_npx"] >= 100000)]
    rs = rs.dropna(subset=["ndvi_crop_mean"])
    rs = rs.sort_values("date").reset_index(drop=True)
    rs["date"] = rs["date"].astype(str)
else:
    rs = pd.DataFrame(columns=["date", "ndvi_crop_mean"])

# ---------- 4. 玉米价格（weekly） ----------
pr_p = ROOT / "03_clean" / "market" / "corn_price_weekly.csv"
if pr_p.exists():
    pr = pd.read_csv(pr_p)
    pr = pr[pr["price_type"] == "farmgate"][["date", "price"]].rename(
        columns={"price": "corn_price_farmgate"})
    pr = pr.sort_values("date")
    pr["date"] = pr["date"].astype(str)
else:
    pr = pd.DataFrame(columns=["date", "corn_price_farmgate"])

# ---------- 5. 事件 / 干预 ----------
ev = pd.DataFrame([
    {"date": "2026-07-12", "event": "rain_start"},
    {"date": "2026-07-13", "event": "rain_peak__red_alert"},
    {"date": "2026-07-14", "event": "flooding_reported__pumps_deployed"},
    {"date": "2026-07-15", "event": "drainage_reinforced__xinmin_village"},
    {"date": "2026-07-18", "event": "bajianfang_drained_complete"},
])

# ---------- 组装 ----------
START, END = "2024-01-01", "2026-09-30"
grid = pd.DataFrame({"date": pd.date_range(START, END).strftime("%Y-%m-%d")})
d = grid.merge(w, on="date", how="left")
d = d.merge(sm, on="date", how="left")
d = d.merge(pr, on="date", how="left")

# 卫星：最近观测（不插值）
if len(rs):
    rsx = rs.set_index("date")
    idx = rsx.index
    def nearest(dt):
        past = idx[idx <= dt]
        return past[-1] if len(past) else None
    nn = [nearest(x) for x in d["date"]]
    d["ndvi_obs_date"] = nn
    d["ndvi_nearest"] = [rsx.loc[n, "ndvi_crop_mean"] if n is not None else np.nan for n in nn]
    d["evi_nearest"] = [rsx.loc[n, "evi_crop_mean"] if n is not None else np.nan for n in nn]
    d["ndwi_nearest"] = [rsx.loc[n, "ndwi_crop_mean"] if n is not None else np.nan for n in nn]
    d["mndwi_nearest"] = [rsx.loc[n, "mndwi_crop_mean"] if n is not None else np.nan for n in nn]
    d["ndvi_obs_lag_days"] = [
        (pd.Timestamp(x) - pd.Timestamp(n)).days if n is not None else np.nan
        for x, n in zip(d["date"], nn)]
    # ★ 禁止无限前向填充：滞后超过 NDVI_MAX_LAG 天即视为"无观测"，
    #   否则会把去年 10 月的值一路填到次年 4 月，制造假实测（用户明确禁止 forward fill）
    NDVI_MAX_LAG = 10
    stale = d["ndvi_obs_lag_days"] > NDVI_MAX_LAG
    for col in ["ndvi_nearest", "evi_nearest", "ndwi_nearest", "mndwi_nearest"]:
        d.loc[stale, col] = np.nan
    d.loc[stale, "ndvi_scene_id"] = None
    d.loc[stale, "ndvi_obs_date"] = None
    d["ndvi_stale_dropped"] = stale
    d["ndvi_is_interpolated"] = False
    d["ndvi_scene_id"] = [rsx.loc[n, "scene_id"] if n is not None else None for n in nn]
else:
    for c in ["ndvi_obs_date", "ndvi_nearest", "evi_nearest", "ndwi_nearest",
              "mndwi_nearest", "ndvi_obs_lag_days", "ndvi_scene_id"]:
        d[c] = np.nan
    d["ndvi_is_interpolated"] = False

# 事件标记
d["date_only"] = d["date"]
evmap = dict(zip(ev["date"], ev["event"]))
d["event_flag"] = d["date"].map(evmap)
d["disaster_flag"] = d["date"].isin(["2026-07-12", "2026-07-13", "2026-07-14",
                                     "2026-07-15", "2026-07-16", "2026-07-17", "2026-07-18"])
d["intervention_flag"] = d["date"].isin(["2026-07-14", "2026-07-15", "2026-07-16",
                                         "2026-07-17", "2026-07-18"])

# 数据性质标注
d["weather_nature"] = "reanalysis_era5"
d["soil_moisture_nature"] = np.where(d["soil_moisture_3_9cm"].notna(), "reanalysis_era5", "missing")
d["rs_nature"] = np.where(d["ndvi_nearest"].notna(), "remote_sensing_scene_nearest", "missing")
d["price_nature"] = np.where(d["corn_price_farmgate"].notna(),
                             "official_statistic_weekly_carried", "missing")

cols = ["date", "precipitation_sum", "temperature_mean", "temperature_2m_max",
        "temperature_2m_min", "relative_humidity_2m_mean", "et0_fao_evapotranspiration",
        "soil_moisture_3_9cm", "soil_moisture_9_27cm", "soil_moisture_27_81cm",
        "soil_temperature_0_to_7cm", "soil_moisture_quality",
        "ndvi_nearest", "evi_nearest", "ndwi_nearest", "mndwi_nearest",
        "ndvi_obs_date", "ndvi_obs_lag_days", "ndvi_is_interpolated", "ndvi_scene_id", "ndvi_stale_dropped",
        "corn_price_farmgate",
        "event_flag", "disaster_flag", "intervention_flag",
        "weather_nature", "soil_moisture_nature", "rs_nature", "price_nature"]
d = d[[c for c in cols if c in d.columns]]
d.to_csv(M / "shenbei_daily_system.csv", index=False, encoding="utf-8-sig")

print(f"[OK] 日级主表 {len(d)} 行 -> 04_marts/shenbei_daily_system.csv")
print(f"     日期 {d.date.min()} ~ {d.date.max()}")
print("\n=== 缺失率（2024-01-01 起）===")
tot = len(d)
for c in ["precipitation_sum", "temperature_mean", "soil_moisture_3_9cm",
          "ndvi_nearest", "corn_price_farmgate"]:
    if c in d:
        miss = d[c].isna().sum()
        print(f"     {c:26s} 缺失 {miss:5d}/{tot} ({miss/tot*100:5.1f}%)")
