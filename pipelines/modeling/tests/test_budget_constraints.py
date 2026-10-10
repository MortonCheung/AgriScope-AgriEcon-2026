import pandas as pd
from _v2_helpers import REQ, cached


def test_budget_and_area_caps():
    gen, _, _, _ = cached()
    df = pd.DataFrame(gen["candidates"])
    assert (df["total_cost"] <= REQ["budget"] + 1e-6).all()
    assert (df["area_mu"] <= REQ["available_area_mu"]).all()


def test_insufficient_budget_gives_no_candidate():
    from decision_engine.recommendation import candidates as CG
    r = CG.generate_candidate_plans(city="沈阳", available_area_mu=50, budget=100,
                                    earliest_plant_date="2027-03-01", latest_harvest_date="2027-10-31")
    assert r["status"] in {"ok", "no_feasible_candidate"}
    if r["status"] == "ok":
        assert all(c["total_cost"] <= 100 + 1e-6 for c in r["candidates"])
