#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M4 简化水量平衡（PREBUILD / SYNTHETIC）。State(t+dt)=State(t)+(P+Inflow-Inf-NatDrain-Pump)*dt"""
import numpy as np


def pump_rate_mm_per_h(pump_capacity_m3h, area_m2):
    """泵排水能力折算为面雨量当量 (mm/h)。"""
    return pump_capacity_m3h / area_m2 * 1000.0


def simulate(rain_mm_per_h=2.0, rain_end_h=24.0, duration_h=168, dt=0.25, area_m2=5.33e6,
             k_inf_mm_h=1.0, k_nat_per_h=0.02, init_storage_mm=120.0,
             pump_capacity_m3h=3600.0, intervention_start_h=28.0, intervention_end_h=None,
             s_threshold_mm=0.5, wetness_factor=1.0):
    """返回 dict(peak_mm, end_h, series_mm)。SYNTHETIC 参数必须外部给定。"""
    k_inf = k_inf_mm_h * (1.0 / wetness_factor)      # 前期越湿，入渗越慢
    pump = pump_rate_mm_per_h(pump_capacity_m3h, area_m2) if pump_capacity_m3h else 0.0
    n = int(duration_h / dt)
    S = init_storage_mm
    peak = S
    series = []
    for i in range(n):
        t = i * dt
        rain = rain_mm_per_h if t < rain_end_h else 0.0
        inf = k_inf * (1.0 if S > 0 else 0.0)
        nat = k_nat_per_h * max(0.0, S - s_threshold_mm) * dt * 60.0 / 60.0  # ≈ k*(S-thr)
        nat = k_nat_per_h * max(0.0, S - s_threshold_mm)
        p = 0.0
        if pump > 0 and t >= intervention_start_h and (intervention_end_h is None or t <= intervention_end_h):
            p = min(pump, max(0.0, S) / dt)              # 不抽成负
        dS = (rain - inf - nat - p) * dt
        S = max(0.0, S + dS)
        peak = max(peak, S)
        series.append(S)
    # 排净时间：S 首次 <= 阈值且此后保持
    end_h = None
    for i in range(len(series) - 1, -1, -1):
        if series[i] > s_threshold_mm:
            end_h = (i + 1) * dt
            break
    if end_h is None:
        end_h = 0.0
    return dict(peak_mm=float(peak), end_h=float(end_h), series=np.array(series))
