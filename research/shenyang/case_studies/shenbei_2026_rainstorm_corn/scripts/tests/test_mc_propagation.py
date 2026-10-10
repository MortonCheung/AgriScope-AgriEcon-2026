#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Monte Carlo 传播单元测试（SYNTHETIC 参数）。"""
import os, sys, importlib.util, numpy as np
BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
spec = importlib.util.spec_from_file_location("p4r_cf", os.path.join(BASE, "scripts", "94_p4r_counterfactual.py"))
m = importlib.util.module_from_spec(spec)
sys.path.insert(0, os.path.join(BASE, "06_models", "prebuild", "M4"))
try:
    spec.loader.exec_module(m)
except SystemExit:
    pass


def test_seed_reproducible():
    a = m.mc_propagation_demo(n=200, seed=1)
    b = m.mc_propagation_demo(n=200, seed=1)
    assert a.equals(b), "固定 seed 必须可复现"
    print("PASS test_seed_reproducible")


def test_sample_stability():
    a = m.mc_propagation_demo(n=500, seed=2)["A"].median()
    b = m.mc_propagation_demo(n=5000, seed=2)["A"].median()
    assert abs(a - b) / max(abs(b), 1e-9) < 0.25, f"样本量增大应稳定: {a} vs {b}"
    print("PASS test_sample_stability", round(a, 2), round(b, 2))


def test_world_ordering():
    d = m.mc_propagation_demo(n=500, seed=3)
    assert d["C"].median() >= d["A"].median() - 1e-6, "C(无应急)应不早于 A"
    assert d["D24"].median() <= d["A"].median() + 1e-6, "D24(提前)应不晚于 A"
    print("PASS test_world_ordering", {k: round(d[k].median(), 1) for k in ["A", "B", "C", "D24", "D48"]})


def test_ranges_physical():
    d = m.mc_propagation_demo(n=500, seed=4)
    assert (d[["A", "B", "C", "D24", "D48"]] >= 0).all().all(), "历时不得为负"
    assert d[["A", "B", "C", "D24", "D48"]].max().max() <= 168 + 1e-6, "不得超过模拟时长"
    print("PASS test_ranges_physical")


if __name__ == "__main__":
    test_seed_reproducible(); test_sample_stability(); test_world_ordering(); test_ranges_physical()
