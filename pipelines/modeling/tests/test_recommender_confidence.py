from _v2_helpers import cached_recommendation


def test_confidence_bounds_and_penalties():
    r = cached_recommendation()
    c = r["confidence"]
    assert 0 <= c["score"] <= 100
    assert c["grade"] in list("ABCD")
    assert "total_penalty" in c
    assert all(v >= 0 for v in c["penalties"].values())
    assert "note" in c


def test_low_separation_lowers_confidence():
    import pandas as pd
    from decision_engine.optimization import ranking as RK
    df = pd.DataFrame({"utility_score": [0.50, 0.4999], "confidence_score": [85, 85]})
    c = RK.recommendation_confidence(df, {"spearman_mean": 0.99}, 85, 0.8, 0.9)
    assert c["top1_minus_top2_utility"] < 0.02
    assert c["note"] is not None
