# -*- coding: utf-8 -*-
"""Final Model 阶段一键编排。

  python3 models/scripts/run_final.py [--steps all|fast]

顺序：
  audit → freeze(含 dataset) → leakage → price models → intervals → risk(HRI/Market) →
  score(Climate/Profit/Confidence) → backtest(策略/诊断) → experiments(消融/鲁棒/组合/压力) →
  independent → report
"""
from __future__ import annotations
import argparse
import sys
import time
from pathlib import Path

DE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DE / "src"))


def _run(label, fn):
    t0 = time.time()
    print(f"\n[final] >>> {label}", flush=True)
    try:
        out = fn()
        print(f"[final] <<< {label} ({time.time()-t0:.0f}s) -> {str(out)[:200]}", flush=True)
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"[final] !!! {label} FAILED: {type(e).__name__}: {e}", flush=True)
        raise


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", default="all")
    a = ap.parse_args()

    from decision_engine.final import (audit, build, leakage, models, intervals, risk, score,
                                       profit, capabilities, artifacts, backtest, policy,
                                       hri_stats, experiments, optimize, recommender_check,
                                       invariants, audit_paths, independent, report)

    _run("audit", lambda: (audit.run_audit(), audit.build_model_data_map())[0])
    def _freeze_and_build():
        man = build.freeze_data()
        dsets = build.build_all()
        return {"frozen_tables": int(len(man)), "datasets": {k: int(len(v)) for k, v in dsets.items()}}
    _run("freeze+dataset", _freeze_and_build)
    _run("leakage", leakage.run)
    _run("price_models", lambda: models.run(cities=("沈阳", "朝阳")))
    _run("intervals", intervals.run)
    _run("scenario_range(逐crop×horizon×season)", lambda: __import__("decision_engine.final.range_", fromlist=["calibrate"]).calibrate("沈阳"))
    _run("risk(HRI/Market)", risk.run)
    _run("hri_timeseries_validation(§24/§25)", lambda: (hri_stats.run("沈阳"), hri_stats.run("朝阳"))[0])
    _run("score(Climate/Confidence)", score.run)
    _run("capabilities(§47/§48/§49)", capabilities.write_capabilities)
    _run("final_model_artifacts", artifacts.build_artifacts)
    _run("backtest(strategies+diagnosis)", lambda: (backtest.build_panel(), backtest.diagnosis(backtest.build_panel()), backtest.run_backtest())[-1])
    _run("policy(untouched/默认策略§12-§15)", policy.run)
    _run("experiments(ablation/robust/portfolio/stress/regret)", experiments.run)
    _run("optimize(pareto/window/area/portfolio/stress/§42)", optimize.run)
    _run("profit_engine(§26)+decision_score(§28)", profit.run)   # 依赖 optimize 产出的候选池
    _run("production recommender fix check", recommender_check.run)
    _run("invariants(§31/§35/§36/§50)", invariants.run)
    _run("dependency_audit(v1=0)", audit_paths.run)
    _run("independent_recheck", independent.run)
    _run("reports", lambda: len(report.write_reports()))
    print("\n[final] 全部完成")


if __name__ == "__main__":
    main()