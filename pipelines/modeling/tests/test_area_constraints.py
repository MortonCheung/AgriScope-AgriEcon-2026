import numpy as np
from decision_engine.optimization import harvest_window as HW
from _v2_helpers import cached


def test_area_recommended_within_tolerance():
    _, _, ok, _ = cached()
    crop = ok["crop"].iloc[0]
    sub = ok[ok["crop"] == crop]
    res = HW.optimize_area(sub, 60, 300000, float(sub.iloc[0]["cost_per_mu"]),
                           float(sub.iloc[0]["expected_yield_per_mu"]), 50000, "balanced")
    assert res["status"] == "ok"
    assert res["recommended_area_mu"] <= 60 + 1e-9
    assert res["recommended_area_mu"] >= 1
    if res["recommended_area_feasible"]:
        assert res["worst_case_loss_at_recommended"] <= 50000 + 1e-6


def test_break_even_identities():
    be = HW.break_even_analysis(5000, 4000, 2.0)
    assert abs(be["break_even_price"] - 1.25) < 1e-9
    assert abs(be["break_even_yield_kg_per_mu"] - 2500) < 1e-6
    assert abs(be["break_even_cost_per_mu"] - 8000) < 1e-6


def test_price_yield_matrix_loss_ratio():
    m = HW.price_yield_matrix(5000, 4000, 1.0, 60, (-0.2, 0.2), (-0.2, 0.2))
    assert 0 <= m["loss_region_ratio"] <= 1
    assert len(m["profit_matrix"]) == len(m["yield_axis"])
