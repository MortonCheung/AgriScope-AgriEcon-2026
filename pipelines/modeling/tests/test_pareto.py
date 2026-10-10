import numpy as np
import pandas as pd
from decision_engine.optimization import pareto as PA


def test_pareto_mask_synthetic():
    df = pd.DataFrame({
        "profit_baseline": [10, 9, 5, 8, 5], "profit_pessimistic": [5, 4, 4, 8, 4],
        "confidence_score": [80, 85, 60, 70, 60], "HRI": [50, 40, 30, 60, 60],
        "market_risk": [50, 45, 30, 55, 55], "climate_risk": [20, 20, 20, 20, 25]})
    m = PA.pareto_mask(df)
    assert len(m) == 5
    assert m.sum() >= 1
    # idx=4 在所有目标上被 idx=0 支配（利润/下行/置信更差，风险更高）
    assert not m[4]


def test_pareto_front_columns():
    from _v2_helpers import cached
    _, _, ok, _ = cached()
    from decision_engine.optimization import utility as U
    f = PA.compute_pareto_frontier(U.utility_report(ok))
    assert "pareto_style" in f.columns
    assert set(f["pareto_style"]) <= {"best_return", "best_downside", "lowest_risk", "balanced"}
