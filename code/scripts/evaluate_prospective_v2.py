#!/usr/bin/env python3
"""Evaluate pre-issued future forecasts against the frozen Gate; never promote a Registry."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "pipelines", ROOT / "pipelines" / "modeling",
             ROOT / "pipelines" / "modeling" / "src"):
    sys.path.insert(0, str(path))
from pipelines.long_horizon.run_long_horizon_job import load_runtime_history, digest
from long_horizon.v2 import load_bundle, target_spec, add_targets, build_base_features, exposure_rows, CONFIG


def _finite_positive(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and np.isfinite(value) and value > 0


def _wape(actual, prediction):
    return float(100*np.abs(actual-prediction).sum()/np.abs(actual).sum())


def _component(observed, threshold, passed, enough=True):
    return {"observed": observed, "threshold": threshold, "passed": bool(passed and enough),
            "status": "INSUFFICIENT" if not enough else "PASS" if passed else "FAIL"}


def gate_components(group, entry):
    """Use paired origins and the pre-locked engineering thresholds, without tuning."""
    cfg = CONFIG["practical_gate"]
    paired = group[group.baseline.map(_finite_positive)].copy()
    blocks = exposure_rows(paired, int(group.exposure_spacing_days.iloc[0]))
    n = len(blocks)
    y, p, b = (blocks[column].to_numpy(float) for column in ("actual", "prediction", "baseline"))
    model_wape = _wape(y,p) if n else None
    baseline_wape = _wape(y,b) if n else None
    gain = baseline_wape-model_wape if n else None
    relative = gain/baseline_wape if n and baseline_wape>0 else None
    ci_low = ci_high = None
    if n >= 4:
        rng = np.random.default_rng(CONFIG["random_seed"])
        draws = rng.integers(0,n,size=(cfg["bootstrap_repetitions"],n))
        gains = 100*(np.abs(y[draws]-b[draws]).sum(axis=1)-np.abs(y[draws]-p[draws]).sum(axis=1))/np.abs(y[draws]).sum(axis=1)
        ci_low,ci_high = (float(x) for x in np.percentile(gains,[2.5,97.5]))
    periods=[]
    for period,g in paired.groupby(paired.date.dt.to_period("Q")):
        yy,pp,bb=(g[column].to_numpy(float) for column in ("actual","prediction","baseline"))
        period_gain=_wape(yy,bb)-_wape(yy,pp)
        periods.append({"period":str(period),"paired_origins":len(g),"absolute_gain_pp":period_gain})
    winning=float(np.mean([x["absolute_gain_pp"]>0 for x in periods])) if periods else None
    worst=float(-min(x["absolute_gain_pp"] for x in periods)) if periods else None
    period_n=len(periods)
    interval=blocks[blocks.low.map(_finite_positive)&blocks.high.map(_finite_positive)]
    coverage=float(((interval.actual>=interval.low)&(interval.actual<=interval.high)).mean()) if len(interval) else None
    cal_n=int(entry.get("calibration_effective_n",entry.get("range",{}).get("calibration_effective_n",0)))
    complete=len(paired)==len(group)
    c={
        "paired_baseline_availability":_component(len(paired),len(group),complete),
        "minimum_final_exposure_blocks":_component(n,cfg["min_final_exposure_blocks"],n>=cfg["min_final_exposure_blocks"],n>0),
        "minimum_absolute_gain":_component(gain,cfg["absolute_gain_pp"],gain is not None and gain>=cfg["absolute_gain_pp"],n>0),
        "minimum_relative_gain":_component(relative,cfg["relative_gain_fraction"],relative is not None and relative>=cfg["relative_gain_fraction"],relative is not None),
        "minimum_periods":_component(period_n,cfg["min_periods"],period_n>=cfg["min_periods"],period_n>0),
        "stability":_component(winning,cfg["winning_period_fraction"],winning is not None and winning>=cfg["winning_period_fraction"],period_n>=cfg["min_periods"]),
        "worst_period":_component(worst,cfg["worst_period_degradation_pp"],worst is not None and worst<=cfg["worst_period_degradation_pp"],period_n>=cfg["min_periods"]),
        "paired_gain_ci":_component({"low_pp":ci_low,"high_pp":ci_high},cfg["paired_gain_ci_lower_gt"],ci_low is not None and ci_low>cfg["paired_gain_ci_lower_gt"],n>=4),
        "calibration_exposure_blocks":_component(cal_n,cfg["calibration_exposure_blocks"],cal_n>=cfg["calibration_exposure_blocks"],cal_n>0),
        "interval_availability":_component(len(interval),n,len(interval)==n and n>0,n>0),
        "independent_interval_coverage":_component(coverage,[cfg["coverage_min"],cfg["coverage_max"]],coverage is not None and cfg["coverage_min"]<=coverage<=cfg["coverage_max"],len(interval)>=cfg["min_final_exposure_blocks"]),
    }
    point_keys=["paired_baseline_availability","minimum_final_exposure_blocks","minimum_absolute_gain","minimum_relative_gain","minimum_periods","stability","worst_period","paired_gain_ci"]
    point_pass=all(c[k]["passed"] for k in point_keys)
    interval_pass=all(c[k]["passed"] for k in ["minimum_final_exposure_blocks","calibration_exposure_blocks","interval_availability","independent_interval_coverage"])
    insufficient=n<cfg["min_final_exposure_blocks"] or period_n<cfg["min_periods"] or not complete
    status="INSUFFICIENT_PROSPECTIVE_EVIDENCE" if insufficient else "POINT_GATE_PASSED" if point_pass else "POINT_GATE_FAILED"
    return {"status":status,"matured_origins":len(group),"paired_origins":len(paired),
            "nonoverlap_exposure_blocks":n,"baseline_method":entry.get("baseline_method"),
            "WAPE":model_wape,"baseline_WAPE":baseline_wape,"absolute_gain_pp":gain,"relative_gain_fraction":relative,
            "MAE":float(np.abs(y-p).mean()) if n else None,
            "sMAPE":float(100*np.mean(2*np.abs(y-p)/(np.abs(y)+np.abs(p)))) if n else None,
            "bias":float((p-y).mean()) if n else None,
            "paired_ci_low_pp":ci_low,"paired_ci_high_pp":ci_high,"period_metrics":periods,
            "independent_interval_coverage":coverage,"nominal_coverage":cfg["nominal_coverage"],
            "point_gate_pass":point_pass,"prediction_interval_gate_pass":interval_pass,
            "all_gate_components_pass":point_pass and interval_pass,"gate_components":c,
            "production_promotion":False,
            "interval_semantics":"scenario_range until independent interval Gate and explicit release review"}


def evaluate_snapshots(bundle, history, snapshots):
    """Pure evaluator used by CLI and boundary tests; no model or Registry writes."""
    rows=[];lookup={};skipped={};earliest=pd.Timestamp(bundle["prospective_origin_not_before"])
    registered={entry["key"]:entry for entry in bundle["entries"]}
    def skip(reason):skipped[reason]=skipped.get(reason,0)+1
    for snap in snapshots:
        if snap.get("method_registry_version")!=bundle["method_registry_version"] or snap.get("evaluation_config_hash")!=bundle["config_hash"]:
            skip("VERSION_MISMATCH");continue
        if digest({k:v for k,v in snap.items() if k not in ("snapshot_hash","generated_at")})!=snap.get("snapshot_hash"):
            raise ValueError("Prospective snapshot checksum mismatch")
        issuance=snap.get("issuance_protocol",{})
        if issuance.get("version")!="prospective_issuance_v1":
            skip("ISSUANCE_PROTOCOL_MISSING");continue
        if issuance.get("max_origin_age_days")!=1:
            raise ValueError("Prospective issuance protocol age mismatch")
        published=pd.Timestamp(snap["generated_at"]).tz_convert("Asia/Shanghai").tz_localize(None)
        for e in snap.get("entries",[]):
            origin=pd.Timestamp(e["anchor_observation_date"])
            if origin<earliest or not e.get("available"):
                skip("ORIGIN_NOT_ELIGIBLE");continue
            age=(published.normalize()-origin).days
            if age<0 or age>1:
                skip("PUBLICATION_NOT_AT_ORIGIN");continue
            key=f"{e['crop']}|{e['horizon']}|{e['target_type']}"
            if key not in registered:raise ValueError("Prospective Registry key mismatch")
            entry=registered[key]
            if key not in lookup:
                spec=target_spec(entry["target_definition"],int(entry["horizon"]))
                realised=add_targets(build_base_features(history[history.crop==entry["crop"]]),spec)
                lookup[key]=(spec,realised)
            spec,realised=lookup[key]
            window=e["target_window"]
            start=origin+pd.Timedelta(days=spec["start_offset"])
            end=origin+pd.Timedelta(days=spec["end_exclusive_offset"])
            if (window["definition"]!=spec["name"] or window["start_offset"]!=spec["start_offset"] or
                window["end_offset_exclusive"]!=spec["end_exclusive_offset"] or
                window.get("start_date")!=str(start.date()) or window.get("end_date_exclusive")!=str(end.date())):
                raise ValueError("Prospective target definition/date mismatch")
            if published>=start:
                skip("PUBLICATION_AFTER_TARGET_STARTED");continue
            if not _finite_positive(e.get("point_forecast")):
                raise ValueError("Prospective invalid forecast point")
            if e.get("baseline_method")!=entry.get("baseline_method"):
                raise ValueError("Prospective baseline method mismatch")
            lo,hi=e.get("range_low"),e.get("range_high")
            if lo is not None or hi is not None:
                if not _finite_positive(lo) or not _finite_positive(hi) or not lo<=e["point_forecast"]<=hi:
                    raise ValueError("Prospective invalid forecast range")
            label=realised[realised.date==origin]
            if label.empty or not np.isfinite(label.actual.iloc[0]):
                skip("TARGET_NOT_MATURED_OR_QC_REJECTED");continue
            rows.append({"crop":e["crop"],"horizon":e["horizon"],"target_type":e["target_type"],"date":origin,
                         "actual":float(label.actual.iloc[0]),"prediction":e["point_forecast"],"baseline":e.get("baseline_point"),
                         "low":lo,"high":hi,"snapshot_hash":snap["snapshot_hash"],"published_at":published,
                         "origin_age_days":age,"exposure_spacing_days":spec["exposure_spacing_days"]})
    summaries=[];table=pd.DataFrame(rows)
    if not table.empty:
        table=table.sort_values(["published_at","snapshot_hash"],kind="stable").drop_duplicates(["crop","horizon","target_type","date"])
        for key,g in table.groupby(["crop","horizon","target_type"]):
            entry=registered[f"{key[0]}|{key[1]}|{key[2]}"]
            summaries.append({**dict(zip(["crop","horizon","target_type"],key)),**gate_components(g,entry)})
    return {"status":"PROSPECTIVE_OBSERVATIONS_AVAILABLE" if summaries else "PROSPECTIVE_LABELS_NOT_MATURED",
            "method_registry_version":bundle["method_registry_version"],"config_hash":bundle["config_hash"],
            "origin_not_before":str(earliest.date()),"matured_forecasts":len(table),"raw_archived_forecasts":len(rows),
            "duplicate_archived_forecasts":len(rows)-len(table),"skipped":skipped,"groups":summaries,
            "production_promotion":False,"gate":CONFIG["practical_gate"],
            "note":"Exposure blocks are conservative counts, not proof of statistical independence. Gate observations never change methods/windows/thresholds or promote a Registry."}


def main():
    bundle=load_bundle();history,_=load_runtime_history()
    snapshots=[json.loads(path.read_text()) for path in sorted((ROOT/"data/processed/long_horizon/snapshots/history").rglob("*.json"))]
    result=evaluate_snapshots(bundle,history,snapshots)
    (ROOT/"LONG_HORIZON_PROSPECTIVE_STATUS.json").write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
    print(json.dumps(result,ensure_ascii=False,allow_nan=False))


if __name__=="__main__":main()
