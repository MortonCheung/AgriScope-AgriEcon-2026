from decision_engine.portfolio import optimizer as PO
from _v2_helpers import cached


def test_portfolio_allocation_bounds():
    _, _, _, plans = cached()
    pf = PO.optimize_crop_portfolio(plans, 60, 300000, "balanced")
    if pf.get("status") != "ok":
        return
    total = sum(a["area_mu"] for a in pf["allocation"])
    assert total <= 60 + 1e-6
    cost = sum(a["area_mu"] * a["cost_per_mu"] for a in pf["allocation"])
    assert cost <= 300000 + 1e-6
    assert pf["idle_area_mu"] >= -1e-6
