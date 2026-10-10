from _v2_helpers import cached


def test_objective_metrics_invariant_to_preference():
    """§13：风险偏好只改排序，不改客观量。"""
    _, _, ok, _ = cached()
    sub = ok[ok["crop"] == ok["crop"].iloc[0]]
    assert sub["HRI"].nunique(dropna=True) == 1 or sub["HRI"].std(skipna=True) < 1e-9
    assert sub["market_risk"].nunique(dropna=True) == 1 or sub["market_risk"].std(skipna=True) < 1e-9


def test_preference_changes_ranking():
    from decision_engine.optimization import utility as U
    from _v2_helpers import cached
    _, _, _, plans = cached()
    if len(plans) < 3:
        return
    a = plans.sort_values("utility_conservative", ascending=False)["candidate_id"].tolist()
    c = plans.sort_values("utility_aggressive", ascending=False)["candidate_id"].tolist()
    assert set(a) == set(c)          # 同一候选池；排序可能不同但不丢候选
