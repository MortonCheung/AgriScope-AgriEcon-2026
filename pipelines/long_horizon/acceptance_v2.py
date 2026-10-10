"""Read-only V2 acceptance, including independent metric/sample recomputation."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import v2

# 交付物迁移后分散在多处：根 data/research/long_horizon、models/registry、archive、runtime
_DELIVERY_DIRS = [
    v2.ROOT / "data" / "research" / "long_horizon",
    v2.ROOT / "models" / "registry",
    v2.ARTIFACTS.parent.parent,
    v2.ROOT / "archive" / "agent_reports",
]


def _deliverable(name):
    for d in _DELIVERY_DIRS:
        p = d / name
        if p.is_file():
            return p
    return v2.ROOT / name


def run() -> dict:
    checks = []

    def check(name, condition):
        checks.append({"check": name, "pass": bool(condition)})

    bundle = v2.load_bundle()
    reg = pd.read_csv(_deliverable("LONG_HORIZON_V2_REGISTRY.csv"))
    account = pd.read_csv(_deliverable("LONG_HORIZON_SAMPLE_ACCOUNTING.csv"))
    met = pd.read_csv(_deliverable("LONG_HORIZON_V2_METRICS.csv"))
    p = pd.read_parquet(v2.ARTIFACTS/"predictions.parquet")
    history = v2._normalize(pd.read_parquet(v2.DATA_PATH))
    crops = history.crop.nunique()
    check("registry has unique crop/horizon/target", len(reg)==crops*len(v2.HORIZONS)*2 and not reg.duplicated(["crop","horizon","target_type"]).any())
    check("all historical evidence conservatively scenario", reg.production_status.isin(["SCENARIO_ONLY","EXPLORATORY_SCENARIO_ONLY"]).all())
    check("long horizons exploratory", (reg[reg.horizon>=150].production_status=="EXPLORATORY_SCENARIO_ONLY").all())
    check("no fabricated untouched metric", reg.untouched_metric.isna().all() and (reg.final_effective_n==0).all())
    check("confidence considers lack of untouched evidence", (reg.confidence=="low").all())
    check("no scenario range mislabeled interval", (reg.range_type=="scenario_range").all())
    check("accounting rows complete", len(account)==len(reg)*len(v2.PHASES))
    check("accounting counts ordered", (account.calendar_candidates>=account.observed_candidates).all() and (account.observed_candidates>=account.nonoverlap_samples).all() and (account.nonoverlap_samples>=account.effective_test_samples).all())
    check("no multiplied independent crop samples", (account.actual_independent_test_samples==0).all())
    check("all sample metrics share config", (reg.config_hash==v2.CONFIG_HASH).all())
    check("all required model families evaluated", set((*v2.BASELINES,*v2.factories())).issubset(set(met.method)))
    check("price outputs finite and positive", np.isfinite(p.prediction).all() and (p.prediction>0).all())
    check("target selection excludes calibration and audit", json.loads((v2.ARTIFACTS/"target_selection_lock.json").read_text())["selection_data"]=="development+tuning only")
    for phase in v2.PHASES:
        phase_m=met[met.phase==phase["name"]]
        end=pd.to_datetime(phase_m.max_training_label_end)
        check(f"purged train {phase['name']}", (end<=pd.Timestamp(phase["train_end"])).all())
        phase_p=p[p.phase==phase["name"]]
        check(f"test outcome contained {phase['name']}", (phase_p.label_end<=pd.Timestamp(phase["end"])).all())
    errors=[]
    for (crop,h,target,method,phase),g in p.groupby(["crop","horizon","target_type","method","phase"]):
        expected=100*float((g.actual-g.prediction).abs().sum())/float(g.actual.abs().sum())
        old=met[(met.crop==crop)&(met.horizon==h)&(met.target_type==target)&(met.method==method)&(met.phase==phase)]
        if len(old)!=1 or not np.isclose(expected,float(old.iloc[0].WAPE),rtol=1e-10,atol=1e-10):
            errors.append((crop,h,target,method,phase))
    check("WAPE independently recomputed from saved predictions",not errors)
    sample_errors=[]
    features=v2.build_base_features(history)
    for h in v2.HORIZONS:
        for target in v2.TARGET_TYPES:
            name="cycle_market_average" if target=="cycle_market_average" else bundle["harvest_definition"]
            spec=v2.target_spec(name,h)
            ds=v2.add_targets(features,spec)
            fresh=v2.sample_accounting(ds,spec,h,target)
            old=account[(account.horizon==h)&(account.target==target)].sort_values(["crop","fold"])
            fresh=fresh.sort_values(["crop","fold"])
            cols=["calendar_candidates","observed_candidates","nonoverlap_samples","effective_test_samples","train_rows"]
            if not np.array_equal(old[cols].to_numpy(),fresh[cols].to_numpy()):
                sample_errors.append((h,target))
    check("sample accounting independently recomputed",not sample_errors)
    for target in v2.TARGET_TYPES:
        result=v2.predict_at(bundle,history,str(history.iloc[0].crop),120,target)
        check(f"inference finite interval {target}", np.isfinite([result["low"],result["point"],result["high"]]).all() and result["low"]<=result["point"]<=result["high"])
        check(f"no hidden production claim {target}", result["production_status"]=="SCENARIO_ONLY" and result["final_effective_n"]==0)
    missing=[name for name in ["LONG_HORIZON_V2_TARGET_REPORT.md","LONG_HORIZON_V2_EVALUATION_REPORT.md","HARVEST_WINDOW_REPORT.md","SAMPLE_ACCOUNTING_REPORT.md","PRODUCTION_GATE_REPORT.md","DECISION_LONG_HORIZON_BACKTEST.md"] if not _deliverable(name).exists()]
    check("reports complete",not missing)
    return {"passed":sum(x["pass"] for x in checks),"total":len(checks),"checks":checks,
            "registry_rows":len(reg),"metrics_rows":len(met),"prediction_rows":len(p),"sample_accounting_rows":len(account)}


if __name__=="__main__":
    result=run()
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if result["passed"]!=result["total"]:
        raise SystemExit(1)
