"""Regression checks for economically material evaluation/inference boundaries."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from long_horizon import v2


def history(days=500):
    dates=pd.date_range("2022-01-01",periods=days)
    return pd.DataFrame({"date":dates,"crop":"土豆","price_per_kg":2+np.sin(np.arange(days)/31)*.2})


def test_windows_have_exact_calendar_width_and_are_future():
    c=v2.target_spec("harvest_centered_14",120)
    p=v2.target_spec("harvest_post_14",120)
    assert (c["start_offset"],c["end_exclusive_offset"],c["calendar_days"])==(113,127,14)
    assert (p["start_offset"],p["end_exclusive_offset"],p["calendar_days"])==(120,134,14)
    assert v2.target_spec("harvest_centered_7",30)["calendar_days"]==7
    with pytest.raises(ValueError):v2.target_spec("harvest_post_14",210)


def test_observed_labels_are_exact_and_tail_is_not_partial():
    h=history(250)
    spec=v2.target_spec("harvest_post_14",120)
    d=v2.add_targets(v2.build_base_features(h),spec)
    assert d.loc[0,"actual"]==pytest.approx(h.iloc[120:134].price_per_kg.mean())
    assert pd.isna(d.loc[117,"actual"])
    assert d.loc[0,"target_observations"]==14
    sparse=h.drop(index=range(120,131))
    sd=v2.add_targets(v2.build_base_features(sparse),spec)
    assert pd.isna(sd.loc[0,"actual"])


def test_training_labels_and_evaluation_do_not_cross_phase_boundaries():
    spec=v2.target_spec("harvest_post_14",120)
    d=v2.add_targets(v2.build_base_features(history(800)),spec)
    cutoff=pd.Timestamp("2022-12-31")
    selected=d[v2.training_mask(d,cutoff)]
    assert selected.label_end.max()<=cutoff
    assert selected.date.max()<=cutoff-pd.Timedelta(133,"D")
    phase={"start":"2023-01-01","end":"2023-12-31"}
    evaluated=d[v2.evaluation_mask(d,phase)]
    assert evaluated.label_end.max()<=pd.Timestamp(phase["end"])


def test_future_mutation_cannot_change_pit_features_or_seasonal_baseline():
    h=history(600)
    spec=v2.target_spec("harvest_post_14",120)
    a=v2.add_seasonal_features(v2.build_base_features(h),spec)
    changed=h.copy();changed.loc[500:,"price_per_kg"]=10000
    b=v2.add_seasonal_features(v2.build_base_features(changed),spec)
    pd.testing.assert_frame_equal(a.iloc[:500],b.iloc[:500])
    prefix=v2.add_seasonal_features(v2.build_base_features(h.iloc[:500]),spec)
    pd.testing.assert_series_equal(a.iloc[499][v2.FEATURES],prefix.iloc[-1][v2.FEATURES])


def test_method_selection_cannot_look_at_audit_or_calibration():
    m=pd.DataFrame([{"method":method,"phase":phase,"WAPE":score} for method,score in [("last_value",20),("linear",15)] for phase in ["development","tuning"]])
    expected=v2.select_method(m)
    poison=pd.DataFrame([{"method":"last_value","phase":"retrospective_audit_reused","WAPE":0},{"method":"linear","phase":"calibration","WAPE":1000}])
    assert v2.select_method(pd.concat([m,poison]))==expected


def test_trivial_gain_never_passes_and_reused_data_is_not_untouched():
    dates=pd.date_range("2026-01-01",periods=40)
    p=pd.DataFrame({"date":dates,"actual":100.,"prediction":108.377,"anchor_price":100.,"phase":"retrospective_audit_reused"})
    b=p.copy();b["prediction"]=108.38
    g=v2.gate_result(p,b,{"q10":.8,"q90":1.2},v2.target_spec("harvest_post_14",90))
    assert not g["gate_pass"]
    assert g["absolute_gain"]==pytest.approx(.003)
    assert "NO_MEANINGFUL_GAIN" in g["reason"]
    assert g["untouched_metric"] is None and g["final_effective_n"]==0


def test_small_block_count_does_not_produce_confidence_interval():
    p=pd.DataFrame({"date":pd.date_range("2026-01-01",periods=30),"actual":2.,"prediction":1.8,"anchor_price":2.})
    assert v2.paired_bootstrap(p,p,120)["gain_ci_low_pp"] is None


def test_inference_never_fits_and_discloses_fallback(monkeypatch):
    class MissingModel:
        def fit(self,*args):raise AssertionError("inference trained")
        def predict(self,*args):return np.array([np.nan])
    e={"key":"土豆|120|harvest_market_price","target_definition":"harvest_post_14","method":"linear",
       "fallback":"last_value","production_status":"SCENARIO_ONLY","confidence":"low",
       "range":{"q10":.8,"q90":1.2},"fallback_range":{"q10":.7,"q90":1.3},"retrospective_effective_n":1,
       "reason":"NO_UNTOUCHED_EVIDENCE"}
    bundle={"entries":[e],"_models":{e["key"]:MissingModel()},"registry_version":"test"}
    result=v2.predict_at(bundle,history(),"土豆",120,"harvest_market_price")
    assert result["fallback_used"] and result["actual_method"]=="last_value"
    assert result["range_type"]=="scenario_range" and result["status"]=="SCENARIO_ONLY"
    assert result["low"]<result["point"]<result["high"]


def test_duplicate_daily_observations_must_be_normalized_upstream():
    h=history(100)
    with pytest.raises(ValueError,match="duplicate"):
        v2.build_base_features(pd.concat([h,h.iloc[:1]]))


def test_sample_accounting_separates_target_windows_and_horizon_exposure():
    d=v2.add_targets(v2.build_base_features(history(1800)),v2.target_spec("harvest_post_14",120))
    accounting=v2.sample_accounting(d,v2.target_spec("harvest_post_14",120),120,"harvest_market_price")
    assert (accounting.nonoverlap_samples>=accounting.effective_test_samples).all()
    assert (accounting.actual_independent_test_samples==0).all()
    assert (accounting.final_effective_n==0).all()


def test_evaluation_and_inference_share_invalid_value_fallback(monkeypatch):
    class InvalidModel:
        def fit(self,*args):return self
        def predict(self,frame):return np.full(len(frame),-1.)
    monkeypatch.setattr(v2,"factories",lambda:{"linear":lambda:InvalidModel()})
    spec=v2.target_spec("harvest_post_14",30)
    d=v2.add_seasonal_features(v2.add_targets(v2.build_base_features(history(1000)),spec),spec)
    p,m,failures=v2.evaluate(d,30,"harvest_market_price",phases=v2.PHASES[:1])
    candidate=p[p.method=="linear"]
    assert len(candidate) and not failures
    assert candidate.fallback_used.all()
    assert (candidate.actual_method=="last_value").all()
    assert np.array_equal(candidate.prediction,candidate.anchor_price)
    assert m[m.method=="linear"].fallback_n.iloc[0]==len(candidate)


def test_decision_replay_only_compares_complete_common_crop_date_pool():
    rows=[]
    crops=["土豆","西红柿"]
    dates=pd.to_datetime(["2026-01-01","2026-01-02"])
    for dt in dates:
        for i,crop in enumerate(crops):
            for method in ["linear","last_value","seasonal_naive"]:
                if dt==dates[1] and crop==crops[1] and method=="seasonal_naive":continue
                rows.append({"date":dt,"crop":crop,"method":method,"horizon":60,"target_type":"harvest_market_price",
                             "phase":"retrospective_audit_reused","actual":2.2+i,"anchor_price":2.+i,"prediction":2.1+i})
            rows.append({"date":dt,"crop":crop,"method":"same_season_mean","horizon":30,"target_type":"cycle_market_average",
                         "phase":"retrospective_audit_reused","actual":2.1+i,"anchor_price":2.+i,"prediction":2.05+i})
    registry=pd.DataFrame([{"crop":crop,"horizon":60,"target_type":"harvest_market_price","method":"linear",
                            "baseline_method":"last_value","target_definition":"harvest_post_14"} for crop in crops])
    hist=pd.DataFrame({"date":[dates[0]]*2,"crop":crops,"price_per_kg":[2.,3.]})
    replay,summary=v2.decision_replay(pd.DataFrame(rows),registry,hist)
    assert replay.date.nunique()==1 and replay.date.iloc[0]==dates[0]
    assert set(replay.policy)=={"statistical_long","selected_simple_baseline","seasonal_baseline","short_only_30d_seasonal_proxy","random_expected","random_seed17"}
    assert (summary.actual_independent_samples==0).all()
