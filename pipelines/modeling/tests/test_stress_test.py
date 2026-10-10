from decision_engine.counterfactual import stress as ST
from _v2_helpers import cached


def test_required_shocks_present():
    _, ev, _, plans = cached()
    st = ST.stress_plan(plans.iloc[0].to_dict(), engine=ev.engine)
    names = {s["shock"] for s in st["scenarios"]}
    for expect in ["price_-10%", "price_-20%", "cost_+10%", "cost_+20%",
                   "yield_-10%", "yield_-20%", "harvest_delay_+7d", "harvest_delay_+14d",
                   "climate_risk_+15", "market_risk_+15"]:
        assert expect in names, expect


def test_price_shock_direction():
    _, ev, _, plans = cached()
    st = ST.stress_plan(plans.iloc[0].to_dict(), engine=ev.engine)
    d = {s["shock"]: s for s in st["scenarios"] if s.get("status") == "ok"}
    assert d["price_-20%"]["profit_delta"] < d["price_-10%"]["profit_delta"] < 0
    assert d["price_+10%"]["profit_delta"] > 0


def test_robust_and_minimax():
    _, ev, _, plans = cached()
    rb = ST.robust_plan_selection(plans.head(3).to_dict("records"), engine=ev.engine)
    assert rb["status"] == "ok"
    assert rb["minimax_regret_plan"]["max_regret"] is not None
    assert all(r["max_regret"] >= -1e-6 for r in rb["table"])
