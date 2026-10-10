#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M4 世界排序测试：无泵 >= 现实 >= 提前（排净时间）。"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "06_models", "prebuild", "M4"))
from m4_water_balance import simulate

def test_world_ordering():
    real = simulate(pump_capacity_m3h=3600, intervention_start_h=28)["end_h"]
    none = simulate(pump_capacity_m3h=0, intervention_start_h=28)["end_h"]
    d24 = simulate(pump_capacity_m3h=3600, intervention_start_h=4.8)["end_h"]
    assert none >= real - 1e-6, (none, real)
    assert d24 <= real + 1e-6, (d24, real)
    print("PASS test_world_ordering", {"C_none": none, "A_real": real, "D_early": d24})

if __name__ == "__main__":
    test_world_ordering()
