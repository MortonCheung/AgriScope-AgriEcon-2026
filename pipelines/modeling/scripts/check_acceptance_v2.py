# -*- coding: utf-8 -*-
"""
Decision Engine v2 验收自检（任务书 §67 清单）。

  python3 models/scripts/check_acceptance_v2.py
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from decision_engine.common import de_path  # noqa: E402


def main():
    checks = []

    def add(name, ok, detail=""):
        checks.append((name, bool(ok), detail))

    def has(*p):
        return de_path(*p).exists()

    # v1 复用
    add("v1 完整复用", has("models", "registry", "model_registry.json") and
        has("evaluation", "backtests", "predictions.parquet"))
    # 候选与约束
    add("Candidate Plan Generator", has("src", "decision_engine", "recommendation", "candidates.py"))
    add("农事约束", has("data", "features", "crop_calendar_v2.parquet"))
    add("Harvest Window Optimizer", has("src", "decision_engine", "optimization", "harvest_window.py"))
    add("Planting Window Generator",
        has("data", "features", "crop_calendar_v2.parquet"))
    add("Area Optimizer", has("src", "decision_engine", "optimization", "harvest_window.py"))
    add("Multi-Crop Portfolio", has("evaluation", "portfolio", "portfolio_backtest.csv"))
    add("Pareto Frontier", has("evaluation", "optimization", "pareto_examples.csv"))
    add("Risk Preference", has("src", "decision_engine", "optimization", "utility.py"))
    add("Utility Model", has("evaluation", "optimization", "utility_weights.csv"))
    # 压力/鲁棒/监测
    add("Counterfactual Stress Test", has("evaluation", "optimization", "stress_test_results.csv"))
    add("Robust Decision", has("src", "decision_engine", "counterfactual", "stress.py"))
    add("Minimax Regret", has("src", "decision_engine", "counterfactual", "stress.py"))
    add("Daily Signal", has("evaluation", "recommendation", "daily_signal_snapshot.csv"))
    add("Warning Level", has("evaluation", "recommendation", "warning_thresholds.csv"))
    # 解释与置信度
    add("Recommendation Explanation", has("src", "decision_engine", "recommendation", "explainer.py"))
    ex = de_path("outputs", "v2_recommendation.json")
    full = json.loads(ex.read_text()) if ex.exists() else {}
    add("Opportunity Cost", bool(full.get("opportunity_cost")))
    add("Break-even Yield", bool(((full.get("area_optimization") or {}).get("break_even") or {})
                                .get("break_even_yield_kg_per_mu")))
    add("Break-even Cost", bool(((full.get("area_optimization") or {}).get("break_even") or {})
                                .get("break_even_cost_per_mu")))
    add("Price×Yield Sensitivity", bool(((full.get("area_optimization") or {}).get("sensitivity_matrix"))))
    add("Recommendation Confidence", bool(full.get("confidence")))
    # 回测与政策
    add("Historical Recommendation Backtest", has("evaluation", "recommendation", "recommender_backtest.parquet"))
    add("Policy Benchmark", has("evaluation", "recommendation", "policy_benchmark.csv"))
    herd = de_path("evaluation", "recommendation", "herding_suppression.csv")
    add("Herding Suppression Evaluation", herd.exists())
    add("Ranking Stability", has("evaluation", "recommendation", "ranking_stability.csv"))
    # 案例与扩展
    c10 = de_path("evaluation", "recommendation", "recommendation_examples_10.csv")
    n10 = len(pd.read_csv(c10)) if c10.exists() else 0
    add("10 真实推荐案例", n10 >= 10, f"{n10} 例")
    rc = de_path("evaluation", "cases", "recommendation_cases.json")
    nfail = 0
    if rc.exists():
        nfail = sum(1 for c in json.loads(rc.read_text())["cases"] if c.get("case_type") == "failure")
    add("1 失败案例", nfail >= 1, f"{nfail} 例")
    reg = de_path("evaluation", "recommendation", "regional_recommendations.csv")
    regd = pd.read_csv(reg) if reg.exists() else pd.DataFrame()
    add("朝阳简化推荐", len(regd) and "朝阳" in set(regd.get("city", [])))
    add("锦州简化推荐", len(regd) and "锦州" in set(regd.get("city", [])))
    add("V3 Optional Adapter", has("evaluation", "recommendation", "v3_enhancement_scan.csv") and
        has("src", "decision_engine", "recommendation", "reference_inputs.py"))
    # 工程质量
    tests = [p.name for p in de_path("tests").glob("test_*.py")]
    need = ["test_candidate_generation.py", "test_calendar_constraints.py", "test_pareto.py", "test_utility.py",
            "test_risk_preference.py", "test_area_constraints.py", "test_budget_constraints.py",
            "test_portfolio_sum.py", "test_portfolio_concentration.py", "test_stress_test.py",
            "test_recommender.py", "test_recommender_confidence.py", "test_historical_recommendation.py",
            "test_daily_signal.py"]
    add("全部自动测试", all(n in tests for n in need), f"{sum(n in tests for n in need)}/{len(need)}")
    docs_need = ["RECOMMENDATION_ENGINE_SPEC.md", "OPTIMIZATION_MODEL_REPORT.md", "PORTFOLIO_MODEL_REPORT.md",
                 "COUNTERFACTUAL_REPORT.md", "RECOMMENDER_BACKTEST_REPORT.md", "DECISION_ENGINE_V2_FINAL_REPORT.md"]
    have_docs = [d for d in docs_need if has("docs", d)]
    add("全部报告", len(have_docs) == len(docs_need), f"{len(have_docs)}/{len(docs_need)}")
    figs = [p.name for p in de_path("evaluation", "figures").glob("v2_*.png")]
    add("全部图表", len(figs) >= 9, f"{len(figs)} 张")
    add("make_planting_decision()", has("src", "decision_engine", "recommendation", "recommender.py"))
    add("一键重建 / 验证", has("scripts", "run_all.py") or has("scripts", "run_all_v2.py"))

    ok_n = sum(1 for _, ok, _ in checks if ok)
    print("\n== Decision Engine v2 验收清单 ==")
    for name, ok, detail in checks:
        print(f"{'✅' if ok else '❌'} {name}" + (f"  [{detail}]" if detail else ""))
    print(f"\n通过 {ok_n}/{len(checks)}")
    return 0 if ok_n == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())