#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Step8 验证：对 03_clean / 04_marts 关键产出做统一质量审计。"""
import os

import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rows = []


def audit(path, name, timecol=None, unit=""):
    if not os.path.exists(path):
        rows.append(dict(dataset=name, path=os.path.relpath(path, BASE), rows="MISSING"))
        return
    if path.endswith(".parquet"):
        d = pd.read_parquet(path)
    else:
        d = pd.read_csv(path)
    info = dict(dataset=name, path=os.path.relpath(path, BASE), rows=len(d),
                cols=len(d.columns), unit=unit,
                dup_rows=int(d.duplicated().sum()),
                missing_rate=round(float(d.isna().mean().mean()), 4))
    if timecol and timecol in d.columns:
        t = pd.to_datetime(d[timecol], errors="coerce")
        info["time_min"] = str(t.min())
        info["time_max"] = str(t.max())
    rows.append(info)


C = os.path.join(BASE, "03_clean")
M = os.path.join(BASE, "04_marts")
audit(os.path.join(C, "agriculture", "corn_annual_pnb.csv"), "沈北玉米年序列", "year", "ha/t/kg每ha")
audit(os.path.join(C, "agriculture", "pnb_grain_rice_soy.csv"), "沈北粮食水稻大豆", "year")
audit(os.path.join(C, "weather", "pnb_hourly.parquet"), "沈北逐小时气象", "time", "mm/C/%/km·h")
audit(os.path.join(C, "weather", "pnb_daily_1991_2026.parquet"), "沈北日值气象", "date", "mm/C")
audit(os.path.join(C, "disaster", "disaster_event_timeline.csv"), "灾情事件时间线", "datetime_start")
audit(os.path.join(C, "intervention", "intervention_timeline.csv"), "干预时间线", "datetime_start")
audit(os.path.join(C, "phenology", "corn_phenology_2026.csv"), "玉米物候", "start")
audit(os.path.join(M, "REAL_WORLD_TIMELINE_2026.csv"), "现实世界时间轴", "datetime")
audit(os.path.join(M, "corn_annual_baseline.csv"), "玉米年度基线", "year")
audit(os.path.join(M, "rainfall_event_features.csv"), "暴雨事件特征", "date", "mm")

out = pd.DataFrame(rows)
out.to_csv(os.path.join(BASE, "logs", "data_quality_audit.csv"), index=False, encoding="utf-8-sig")
print(out.to_string())
