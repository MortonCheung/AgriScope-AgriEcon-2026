import pandas as pd
from decision_engine.portfolio.risk import portfolio_metrics


def test_hhi_bounds_and_penalty():
    rows = {"A": {"area_mu": 10, "profit_baseline": 100, "profit_pessimistic": 50,
                  "profit_optimistic": 150, "cost_per_mu": 10, "HRI": 50,
                  "market_risk": 50, "climate_risk": 20, "confidence_score": 80},
            "B": {"area_mu": 10, "profit_baseline": 100, "profit_pessimistic": 50,
                  "profit_optimistic": 150, "cost_per_mu": 10, "HRI": 50,
                  "market_risk": 50, "climate_risk": 20, "confidence_score": 80}}
    even = portfolio_metrics({"A": 10, "B": 10}, rows)
    conc = portfolio_metrics({"A": 20}, rows)
    assert abs(even["hhi"] - 0.5) < 1e-9
    assert conc["hhi"] == 1.0
    assert conc["concentration_penalty"] >= even["concentration_penalty"]
    assert even["risk_adjusted_market"] <= (even["portfolio_market_risk"] * (1 + 0.5))
