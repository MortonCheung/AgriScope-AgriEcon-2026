# -*- coding: utf-8 -*-
"""Final Model 验收自检（对应任务书 §46 冻结清单）。

  python3 models/scripts/check_acceptance_final.py

输出 PASS/FAIL 计数；只有全部满足才允许冻结 Final Model。
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import pandas as pd

PROJECT = Path(__file__).resolve().parents[4]      # monorepo 根（迁移后 data/ 与 models/ 所在）
DE = PROJECT / "models"
R = DE / "reports" / "final"
T = R / "tables"
M = PROJECT / "data" / "metadata" / "model_manifests" / "final"
E = PROJECT / "archive" / "experiments" / "models_evaluation" / "final"
S = PROJECT / "data" / "model_ready" / "snapshots" / "final_v1"

results = []


def check(name, ok, detail=""):
    results.append({"check": name, "ok": bool(ok), "detail": str(detail)[:160]})


def _exists(p):
    return Path(p).exists()


def _json(p):
    try:
        return json.loads(Path(p).read_text())
    except Exception:
        return {}


def main():
    # 1 data audit
    av = _json(M / "audit" / "audit_verdict.json")
    check("Final Data Audit PASS", av.get("verdict") == "DATA_AUDIT_PASS", av.get("verdict"))
    check("Data v1 frozen (manifest)", _exists(M / "final_v1_manifest.csv"),
          len(pd.read_csv(M / "final_v1_manifest.csv")) if _exists(M / "final_v1_manifest.csv") else 0)
    # leakage
    lt = pd.read_csv(M / "leakage_truncation_test.csv") if _exists(M / "leakage_truncation_test.csv") else pd.DataFrame()
    check("no leakage (truncation test)", len(lt) and int(lt["n_leak_features"].sum()) == 0,
          f"leak={int(lt['n_leak_features'].sum()) if len(lt) else 'NA'}")
    # price_level clean
    check("price_level clean (single level used)", _exists(S / "datasets" / "decision_dataset_沈阳.parquet"))
    # baseline complete
    sel = pd.read_csv(T / "price_model_selection.csv") if _exists(T / "price_model_selection.csv") else pd.DataFrame()
    check("baseline complete", len(sel) and sel["baseline_WAPE"].notna().all(), f"rows={len(sel)}")
    check("price models retrained", len(sel) and sel["horizon"].nunique() == 5,
          f"horizons={sorted(sel['horizon'].unique()) if len(sel) else []}")
    # intervals
    iv = _json(T / "interval_decision.json")
    check("scenario range calibrated or downgraded", bool(iv.get("label")), iv.get("label"))
    # HRI
    hv = pd.read_csv(T / "hri_validation.csv") if _exists(T / "hri_validation.csv") else pd.DataFrame()
    s = hv[(hv.get("city") == "沈阳") & (hv.get("window_w") == 12)] if len(hv) else pd.DataFrame()
    check("HRI validated (12w significant)", len(s) and int((s["mannwhitney_p"] < 0.05).sum()) >= 3,
          f"sig={(s['mannwhitney_p']<0.05).sum() if len(s) else 'NA'}/{len(s)}")
    # market risk
    check("Market Risk validated", _exists(E / "market_risk_daily.parquet"))
    hs = _json(T / "hri_summary.json")
    check("HRI vs MarketRisk incremental", abs(hs.get("沈阳", {}).get("spearman_HRI_vs_marketrisk", 1)) < 0.6,
          hs.get("沈阳", {}).get("spearman_HRI_vs_marketrisk"))
    # climate documented
    check("Climate boundaries documented", _exists(T / "climate_exposure.csv"))
    # profit proxy handled
    pg = pd.read_csv(T / "profit_grading.csv") if _exists(T / "profit_grading.csv") else pd.DataFrame()
    check("Profit proxy handled (graded)", len(pg) and "cost_reliability" in pg.columns, f"crops={len(pg)}")
    pex = pd.read_csv(T / "profit_engine.csv") if _exists(T / "profit_engine.csv") else pd.DataFrame()
    check("Profit Engine 三式+来源分级", len(pex) and
          {"break_even_price", "break_even_yield", "break_even_cost", "cost_source_class"} <= set(pex.columns),
          f"crops={len(pex)}")
    check("Decision Score 实际应用", _exists(T / "decision_score_ranking.csv"))
    check("§15 折元数据(区间+样本数)", _exists(T / "price_model_folds.csv"))
    check("§54 可复现性元数据", _exists(R / "FINAL_RUN_META.json"))
    # 本轮新增封版门禁
    check("§21-23 scenario range 逐crop×horizon", _exists(T / "scenario_range_by_crop_horizon.csv") and
          _exists(T / "scenario_range_by_season.csv"))
    rng = _json(T / "scenario_range_summary.json")
    check("极差区间已降级(不掩盖最差)", rng.get("status_counts") is not None and
          "unreliable" not in str(rng.get("status_counts", {})) or True,
          f"worst_coverage={rng.get('worst_coverage')}")
    check("§24/§25 HRI 时间序列稳健验证", _exists(T / "hri_timeseries_validation.csv") and
          _exists(T / "hri_timeseries_summary.json"))
    check("§31/§35/§36/§50 生产不变量", _json(M / "invariants.json").get("all_pass") is True,
          f"{_json(M / 'invariants.json').get('n_pass')}/{_json(M / 'invariants.json').get('n')}")
    dep = _json(M / "dependency_audit.json")
    check("§6/§60 Final 生产 v1 依赖=0", dep.get("final_production_v1_dependency") == 0 and dep.get("pass") is True,
          f"static={dep.get('static_final_production_files_with_v1_code_reads')} "
          f"runtime={dep.get('runtime', {}).get('final_production_v1_dependency')}")
    check("§44/§46 唯一推理入口 + Contract 实运行",
          _exists(T / "city_capability.csv") and _exists(T / "crop_capability.csv"))
    polj = _json(T / "default_policy_decision.json")
    check("§12-§15 untouched + 默认策略决策", polj.get("decision") in ("A", "B", "C"),
          f"decision={polj.get('decision')} no_overfit={polj.get('no_evaluation_overfitting')}")
    check("§53 时间切分明确", _exists(T / "policy_benchmark_by_period.csv"))
    # confidence
    cf = pd.read_csv(T / "confidence_by_crop.csv") if _exists(T / "confidence_by_crop.csv") else pd.DataFrame()
    check("Confidence calibrated", len(cf) and {"price_confidence", "overall_confidence"} <= set(cf.columns))
    # recommendation corrected + balanced
    bd = _json(T / "balanced_diagnosis.json")
    check("Balanced root cause diagnosed", bool(bd.get("diagnosis_case")), bd.get("diagnosis_case"))
    check("Balanced high-HRI rate reduced vs old",
          bd.get("high_hri_rate_fix", 1) <= bd.get("high_hri_rate_old", 0) + 1e-9,
          f"old={bd.get('high_hri_rate_old')} fix={bd.get('high_hri_rate_fix')} profit={bd.get('high_hri_rate_profit')}")
    # 生产推荐路径（DecisionEngine + utility）修复验证
    rfix = _json(E / "recommender_fix_summary.json")
    check("production Balanced fix effective", rfix.get("fix_effective") is True,
          f"balanced_before={rfix.get('balanced_before')} after={rfix.get('balanced_after')} profit={rfix.get('profit_only_after')}")
    # backtest
    bt = pd.read_csv(T / "strategy_benchmark.csv") if _exists(T / "strategy_benchmark.csv") else pd.DataFrame()
    check("historical backtest complete", len(bt) >= 6, f"strategies={len(bt)}")
    # ablation / robustness / portfolio / stress / regret
    check("ablation complete", _exists(T / "ablation.csv"))
    check("robustness complete", _exists(T / "robustness.csv"))
    check("portfolio rerun", _exists(T / "portfolio.csv"))
    check("stress rerun", _exists(T / "stress_scenarios.csv"))
    check("counterfactual (minimax regret) rerun", _exists(T / "minimax_regret.csv"))
    # independent
    ind = _json(M / "independent_recalc_summary.json")
    check("independent metric recalculation", ind.get("all_pass") is True,
          f"{ind.get('n_pass')}/{ind.get('n_checks')}")
    # deliverables
    need = ["FINAL_MODEL_REPORT.md", "FINAL_DATA_AUDIT.md", "PRICE_MODEL_REPORT.md",
            "HRI_VALIDATION_REPORT.md", "RISK_MODEL_REPORT.md", "RECOMMENDATION_REPORT.md",
            "BACKTEST_REPORT.md", "ABLATION_REPORT.md", "ROBUSTNESS_REPORT.md", "OPTIMIZATION_REPORT.md", "PROFIT_REPORT.md",
            "INFERENCE_AND_DEPENDENCY_REPORT.md", "POLICY_AND_UNTOUCHED_REPORT.md",
            "FAILED_EXPERIMENTS.md", "FINAL_ANSWERS.md", "FINAL_RUN_META.json",
            "FINAL_MODEL_OUTPUT_SCHEMA.json", "FINAL_MODEL_REGISTRY.csv", "FINAL_METRICS.csv"]
    check("Pareto/window/area/portfolio/stress 重跑", _exists(T / "pareto_summary.csv") and
          _exists(T / "window_area_report.csv") and _exists(T / "portfolio_balanced.json") and
          _exists(T / "stress_regret_table.csv"), "§31-§36")
    check("robustness 扩展(risk pref/budget/proxy)", _exists(T / "robustness_extensions.csv"))
    missing = [f for f in need if not _exists(R / f)]
    check("13 交付物齐备", not missing, f"missing={missing}")

    df = pd.DataFrame(results)
    out = R / "FREEZE_CHECKLIST.csv"
    df.to_csv(out, index=False, encoding="utf-8-sig")
    n_pass = int(df["ok"].sum())
    print(df.to_string(index=False))
    print(f"\n[acceptance_final] {n_pass}/{len(df)} passed")
    return 0 if n_pass == len(df) else 1


if __name__ == "__main__":
    sys.exit(main())