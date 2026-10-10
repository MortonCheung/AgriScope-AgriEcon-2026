import numpy as np
import pandas as pd
from decision_engine.optimization import utility as U


def test_weights_sum_to_one():
    for pref, w in U.PREFERENCE_WEIGHTS.items():
        assert abs(sum(w.values()) - 1.0) < 1e-9, pref
        assert set(w) == {"ret", "down", "conf", "market", "herding", "climate"}


def test_utility_in_range_and_ranks():
    from _v2_helpers import cached
    _, _, _, plans = cached()
    assert plans["utility_score"].between(-1, 1).all()
    assert plans["utility_score"].notna().all()
    for pref in U.PREFERENCE_WEIGHTS:
        assert plans[f"utility_{pref}"].between(-1, 1).all()


def test_weight_sensitivity_stable():
    from _v2_helpers import cached
    _, _, _, plans = cached()
    ws = U.weight_sensitivity(plans, "balanced", n_draws=30)
    assert ws["spearman_mean"] > 0.9
    assert "topk_overlap_mean" in ws
