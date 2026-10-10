#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P2-10 干预变量定量化 → 03_clean/intervention/intervention_quantified.csv
泵能力：8寸(≈200mm口径)潜水泵/轴流泵常见流量区间属工程参考，非沈北设备铭牌 → 记为参数范围 low/mid/high。
"""
import os

import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN = os.path.join(BASE, "03_clean")

# 时间锚点（来源见 03_clean/disaster 与 intervention_timeline）
WARN = pd.Timestamp("2026-07-13 09:10")
RAIN_START = pd.Timestamp("2026-07-12 20:00")
RAIN_PEAK = pd.Timestamp("2026-07-13 05:00")   # ERA5 网格点峰值小时

# 8寸潜水泵/轴流泵常见单机流量工程参考区间（m3/h）——非沈北设备铭牌，仅作不确定参数
PUMP8_LOW, PUMP8_MID, PUMP8_HIGH = 150.0, 300.0, 500.0


def h(t):
    if pd.isna(t):
        return None
    return round((pd.Timestamp(t) - RAIN_START).total_seconds() / 3600.0, 1)


def main():
    rows = [
        # 八间房村：唯一含清晰起止与设备强度的排涝案例
        dict(location="沈北新区新城子街道八间房村/北四家子村", location_level="village",
             warning_time=str(WARN), rain_start_time=str(RAIN_START), rain_peak_time=str(RAIN_PEAK),
             intervention_start="2026-07-14", intervention_end="2026-07-18",
             pump_count=12, pump_diameter="8寸(≈200mm)", pump_capacity="范围待定(见note)",
             affected_area_mu=8000, drained_area_mu=8000,
             source_id="SRC-SYD-2026-0814", confidence="medium",
             note="原文:两台大功率泵车+一台50泵+三组8寸管+一台应急排水车，共12台8寸泵同时作业；"
                  "8000余亩为媒体量级；7-14协调、7-15增援、7-18排净"),
        dict(location="沈北新区兴隆台街道新民村", location_level="village",
             warning_time=str(WARN), rain_start_time=str(RAIN_START), rain_peak_time=str(RAIN_PEAK),
             intervention_start="2026-07-15", intervention_end="2026-07-17",
             pump_count=None, pump_diameter="未披露", pump_capacity="未披露",
             affected_area_mu=None, drained_area_mu=None,
             source_id="SRC-LN-GOV-2026-0717", confidence="high",
             note="官方:多部门联动清障疏渠、抢排积水；无设备/面积数字"),
        dict(location="沈阳市（含沈北）-防汛红色预警与最高一级响应", location_level="city",
             warning_time=str(WARN), rain_start_time=str(RAIN_START), rain_peak_time=str(RAIN_PEAK),
             intervention_start="2026-07-13T09:10", intervention_end="2026-07-14T23:59",
             pump_count=None, pump_diameter=None, pump_capacity=None,
             affected_area_mu=None, drained_area_mu=None,
             source_id="SRC-SY-GOV-2026-0714", confidence="high",
             note="9:10红色预警/最高一级响应；非排涝设备"),
    ]
    df = pd.DataFrame(rows)
    # 时间差（小时）
    df["time_warning_to_action_h"] = df["intervention_start"].apply(
        lambda x: round((pd.Timestamp(x) - WARN).total_seconds() / 3600.0, 1))
    df["time_rain_start_to_action_h"] = df["intervention_start"].apply(
        lambda x: round((pd.Timestamp(x) - RAIN_START).total_seconds() / 3600.0, 1))
    df["time_peak_to_action_h"] = df["intervention_start"].apply(
        lambda x: round((pd.Timestamp(x) - RAIN_PEAK).total_seconds() / 3600.0, 1))
    df["drainage_duration_h"] = df.apply(
        lambda r: round((pd.Timestamp(r["intervention_end"]) - pd.Timestamp(r["intervention_start"])).total_seconds() / 3600.0, 1), axis=1)

    # 泵能力范围（仅当有台数时）
    def cap(r, factor):
        return None if pd.isna(r["pump_count"]) or r["pump_count"] is None else round(r["pump_count"] * factor, 1)
    df["pump_capacity_low_m3h"] = df.apply(lambda r: cap(r, PUMP8_LOW), axis=1)
    df["pump_capacity_mid_m3h"] = df.apply(lambda r: cap(r, PUMP8_MID), axis=1)
    df["pump_capacity_high_m3h"] = df.apply(lambda r: cap(r, PUMP8_HIGH), axis=1)
    df["pump_capacity_basis"] = f"8寸泵单机工程参考区间 {PUMP8_LOW:.0f}/{PUMP8_MID:.0f}/{PUMP8_HIGH:.0f} m3/h(未获沈北设备铭牌)"
    df["parameter_type"] = "engineering_reference_range_not_device_spec"

    out = os.path.join(CLEAN, "intervention", "intervention_quantified.csv")
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print("[P2-10] intervention_quantified rows=", len(df))
    pd.set_option("display.width", 260)
    print(df[["location", "intervention_start", "intervention_end", "pump_count",
              "time_warning_to_action_h", "time_rain_start_to_action_h",
              "time_peak_to_action_h", "drainage_duration_h"]].to_string())


if __name__ == "__main__":
    main()
