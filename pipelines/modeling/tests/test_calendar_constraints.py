import pandas as pd
from decision_engine.recommendation import calendar as cal


def test_winter_openfield_warm_crop_rejected():
    r = cal.check_agronomic_feasibility("沈阳", "黄瓜", "2027-01-10", "2027-03-25",
                                        production_system="open_field")
    assert r["feasible"] is False
    assert any("露地" in v for v in r["violations"])


def test_growing_days_bounds():
    bad = cal.check_agronomic_feasibility("沈阳", "西红柿", "2027-05-01", "2027-05-20")
    assert bad["feasible"] is False            # 20 天 << 生育期下限


def test_calendar_levels_and_sources():
    t = cal.build_crop_calendar("沈阳", ["西红柿", "黄瓜"])
    assert set(t["calendar_level"]) <= {"observed_calendar", "regional_reference",
                                        "inferred_from_price_seasonality", "none"}
    assert set(t["constraint_strength"]) <= {"strong", "medium", "weak", "none"}
    ws = cal.feasible_harvest_windows("沈阳", "西红柿", pd.Timestamp("2027-04-01"), pd.Timestamp("2027-08-31"))
    assert ws and all(w["planting_date_source"] for w in ws)
