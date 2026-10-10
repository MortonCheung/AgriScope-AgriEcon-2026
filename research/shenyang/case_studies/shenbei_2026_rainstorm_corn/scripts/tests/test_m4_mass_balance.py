#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M4 质量平衡单元测试（可独立运行）。"""
import os, sys, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "06_models", "prebuild", "M4"))
from m4_water_balance import simulate

def test_non_negative_storage():
    r = simulate(rain_mm_per_h=0.1, duration_h=48, pump_capacity_m3h=6000, init_storage_mm=5)
    assert (r["series"] >= -1e-9).all(), "storage 不得为负"
    print("PASS test_non_negative_storage")

def test_zero_pump_equals_no_pump_term():
    r0 = simulate(rain_mm_per_h=1.0, pump_capacity_m3h=0)
    r1 = simulate(rain_mm_per_h=1.0, pump_capacity_m3h=0, intervention_start_h=1000)
    assert abs(r0["end_h"] - r1["end_h"]) < 1e-9
    print("PASS test_zero_pump_equals_no_pump_term")

if __name__ == "__main__":
    test_non_negative_storage(); test_zero_pump_equals_no_pump_term()
