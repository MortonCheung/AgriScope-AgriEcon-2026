import pandas as pd
from _v2_helpers import REQ, cached
from decision_engine.recommendation import candidates as CG


def test_candidate_generation():
    gen, _, _, _ = cached()
    assert gen["status"] == "ok"
    df = pd.DataFrame(gen["candidates"])
    assert len(df) > 0
    assert df["candidate_id"].is_unique                      # 稳定且唯一
    assert (pd.to_datetime(df["plant_date"]) >= pd.Timestamp(REQ["earliest_plant_date"])).all()
    assert (pd.to_datetime(df["harvest_date"]) <= pd.Timestamp(REQ["latest_harvest_date"])).all()
    assert (df["area_mu"] <= REQ["available_area_mu"]).all()
    assert (df["total_cost"] <= REQ["budget"] + 1e-6).all()
    assert set(df["planting_date_source"]) <= {"observed_calendar", "inferred_window", "regional_reference"}


def test_candidate_determinism():
    a = CG.generate_candidate_plans(**REQ)
    b = CG.generate_candidate_plans(**REQ)
    assert [c["candidate_id"] for c in a["candidates"]] == [c["candidate_id"] for c in b["candidates"]]
