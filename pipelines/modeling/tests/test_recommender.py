from _v2_helpers import cached_recommendation
from decision_engine.recommendation.recommender import make_planting_decision


def test_recommender_schema_and_topn():
    r = cached_recommendation()
    for k in ["request", "recommended_plan", "alternatives", "pareto_frontier", "portfolio_plan",
              "risk_summary", "stress_test", "confidence", "reasons", "limitations"]:
        assert k in r, k
    assert r["status"] == "ok"
    assert len(r["top_plans"]) >= 1
    labels = {x["label"] for x in r["labels"]}
    assert {"Best Return", "Best Balanced", "Lowest Risk", "Most Robust", "Alternative"} <= labels
    assert r["comparison_reason"]
    p = r["recommended_plan"]
    assert p["price_low"] <= p["price_mid"] <= p["price_high"]
    assert p["area_mu"] <= 60 + 1e-6


def test_make_planting_decision_and_degradation():
    r = make_planting_decision({"city": "大连", "available_area_mu": 50, "budget": 200000,
                                "earliest_plant_date": "2027-03-01", "latest_harvest_date": "2027-09-30"})
    assert r["status"] == "insufficient_market_data"
    assert r["recommended_plan"] is None
