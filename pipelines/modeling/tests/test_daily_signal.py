from decision_engine.monitoring import daily_signal as DS


def test_signal_fields_and_levels():
    s = DS.daily_signal("沈阳", "西红柿", "2026-09-14")
    assert s["status"] == "ok"
    assert 0 <= s["current_price_percentile"] <= 1
    assert s["warning_level"] in {"NORMAL", "WATCH", "HIGH", "VERY_HIGH", "UNKNOWN"}
    assert "signal_change_1d" in s and "signal_change_7d" in s
    assert s["thresholds"]["HRI"]["p90"] >= s["thresholds"]["HRI"]["p75"]


def test_warning_table_and_thresholds():
    t = DS.warning_table("沈阳", ["西红柿", "黄瓜"], "2026-09-14")
    assert len(t) == 2
    thr = DS.warning_thresholds("沈阳", "西红柿")
    assert thr["HRI"]["p95"] >= thr["HRI"]["p90"]
