#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M4 单调性测试（可独立运行）。"""
import os, sys, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "06_models", "prebuild", "M4"))
from m4_water_balance import simulate

def test_pump_capacity_monotone():
    d = [simulate(pump_capacity_m3h=c)["end_h"] for c in [0, 1800, 3600, 6000]]
    assert all(np.diff(d) <= 1e-6), f"泵能力↑不应使历时增加: {d}"
    print("PASS test_pump_capacity_monotone", d)

def test_rain_monotone_peak():
    d = [simulate(rain_mm_per_h=r)["peak_mm"] for r in [1, 4, 8, 16]]
    assert all(np.diff(d) >= -1e-6), f"降雨↑不应降低峰值: {d}"
    print("PASS test_rain_monotone_peak", d)

if __name__ == "__main__":
    test_pump_capacity_monotone(); test_rain_monotone_peak()
