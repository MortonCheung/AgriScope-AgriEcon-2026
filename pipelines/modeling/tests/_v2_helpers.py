# -*- coding: utf-8 -*-
"""v2 测试共用夹具：一次性构建候选/评估/方案，避免重复计算。"""
import functools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from decision_engine.optimization import ranking as RK  # noqa: E402
from decision_engine.optimization import utility as U  # noqa: E402
from decision_engine.recommendation import candidates as CG  # noqa: E402
from decision_engine.recommendation.evaluate_candidates import CandidateEvaluator  # noqa: E402

REQ = dict(city="沈阳", available_area_mu=60, budget=300000,
           earliest_plant_date="2027-03-01", latest_harvest_date="2027-10-31",
           risk_preference="balanced", max_candidates=160)


@functools.lru_cache(maxsize=1)
def cached():
    gen = CG.generate_candidate_plans(**REQ)
    ev = CandidateEvaluator()
    df = ev.evaluate_many(gen["candidates"], verbose=False)
    ok = df[df["evaluable"]].copy()
    plans = RK.collapse_area_variants(ok, 0.25 * REQ["budget"])
    plans = U.utility_report(plans)
    return gen, ev, ok, plans


@functools.lru_cache(maxsize=1)
def cached_recommendation():
    from decision_engine.recommendation.recommender import recommend_plans
    return recommend_plans(**REQ, mode="compare_both", run_stress=True)
