# -*- coding: utf-8 -*-
"""
Phase 11 产物：Pareto 示例 / 压力测试结果 / 组合回测 / 每日信号快照 / V3 增强扫描。

  python3 decision_engine/scripts/build_optimization_v2.py [--city 沈阳] [--area 100] [--budget 500000]

输出：
  evaluation/optimization/pareto_examples.csv
  evaluation/optimization/stress_test_results.csv
  evaluation/optimization/utility_weights.csv
  evaluation/portfolio/portfolio_backtest.csv
  evaluation/recommendation/daily_signal_snapshot.csv
  evaluation/recommendation/warning_thresholds.csv
  evaluation/recommendation/v3_enhancement_scan.csv
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from decision_engine.common import de_path, ensure_dir  # noqa: E402
from decision_engine.counterfactual import stress as ST  # noqa: E402
from decision_engine.evaluation.recommendation import recommender_backtest as BT  # noqa: E402
from decision_engine.monitoring import daily_signal as DS  # noqa: E402
from decision_engine.optimization import pareto as PA  # noqa: E402
from decision_engine.optimization import ranking as RK  # noqa: E402
from decision_engine.optimization import utility as U  # noqa: E402
from decision_engine.portfolio import optimizer as PO  # noqa: E402
from decision_engine.recommendation import candidates as CG  # noqa: E402
from decision_engine.recommendation import reference_inputs as RI  # noqa: E402
from decision_engine.recommendation.evaluate_candidates import CandidateEvaluator  # noqa: E402

LOSS_TOL = {"conservative": 0.10, "balanced": 0.25, "aggressive": 0.50}


def _plans_for(city, area, budget, plant, harvest, risk_pref="balanced", as_of=None, max_candidates=400):
    gen = CG.generate_candidate_plans(city=city, available_area_mu=area, budget=budget,
                                      earliest_plant_date=plant, latest_harvest_date=harvest,
                                      risk_preference=risk_pref, max_candidates=max_candidates)
    ev = CandidateEvaluator(as_of=as_of)
    df = ev.evaluate_many(gen["candidates"], verbose=False)
    ok = df[df["evaluable"]].copy()
    plans = RK.collapse_area_variants(ok, LOSS_TOL[risk_pref] * budget)
    plans = U.utility_report(plans)
    return gen, ev, ok, plans


def main(city="沈阳", area=100.0, budget=500000.0,
         plant="2027-03-01", harvest="2027-10-31"):
    opt_dir = ensure_dir(de_path("evaluation", "optimization"))
    port_dir = ensure_dir(de_path("evaluation", "portfolio"))
    rec_dir = ensure_dir(de_path("evaluation", "recommendation"))
    t0 = time.time()

    gen, ev, ok, plans = _plans_for(city, area, budget, plant, harvest)
    print(f"[opt] {city}: candidates={len(ok)} plans={len(plans)}", flush=True)

    # 1) Pareto 示例
    front = PA.compute_pareto_frontier(U.utility_report(ok))
    cols = ["crop", "harvest_date", "area_mu", "pareto_style", "profit_baseline",
            "profit_pessimistic", "HRI", "market_risk", "climate_risk", "confidence_score"]
    front[[c for c in cols if c in front.columns]].to_csv(opt_dir / "pareto_examples.csv",
                                                          index=False, encoding="utf-8-sig")
    print(f"[opt] pareto front={len(front)}")

    # 2) 压力测试（Top5 方案 × 全部 shocks）× 3 种偏好
    srows = []
    for pref in ["conservative", "balanced", "aggressive"]:
        rows = plans.sort_values(f"utility_{pref}", ascending=False).head(5).to_dict("records")
        for r in rows:
            st = ST.stress_plan(r, engine=ev.engine)
            for sc in st["scenarios"]:
                if sc.get("status") != "ok":
                    continue
                srows.append({"risk_preference": pref, "crop": r["crop"], "harvest_date": str(r["harvest_date"]),
                              "area_mu": r["area_mu"], "shock": sc["shock"],
                              "profit_delta": sc["profit_delta"], "profit_delta_pct": sc["profit_delta_pct"],
                              "score_delta": sc["score_delta"], "roi_delta": sc["roi_delta"],
                              "still_profitable": sc["still_profitable"]})
    st_df = pd.DataFrame(srows)
    st_df.to_csv(opt_dir / "stress_test_results.csv", index=False, encoding="utf-8-sig")
    print(f"[opt] stress rows={len(st_df)} ({time.time()-t0:.0f}s)")

    # 3) 权重表
    wrows = []
    for pref, w in U.PREFERENCE_WEIGHTS.items():
        wrows.append({"preference": pref, **w})
    pd.DataFrame(wrows).to_csv(opt_dir / "utility_weights.csv", index=False, encoding="utf-8-sig")

    # 4) 组合回测（每 60 天一个 cutoff，比较组合 vs 单作物最优，用实现价格结算）
    ds = pd.read_parquet(de_path("data", "processed", "decision_dataset_v1.parquet"), columns=["date"])
    ds["date"] = pd.to_datetime(ds["date"])
    cut, rows_pb = pd.Timestamp("2024-06-01"), []
    while cut <= ds["date"].max() - pd.Timedelta(days=180):
        T = str(cut.date())
        gen2, ev2, ok2, plans2 = _plans_for(city, area, budget,
                                            str((cut + pd.Timedelta(days=10)).date()),
                                            str((cut + pd.Timedelta(days=150)).date()),
                                            as_of=T, max_candidates=200)
        if not len(plans2):
            cut += pd.Timedelta(days=60)
            continue
        pf = PO.optimize_crop_portfolio(plans2, area, budget, "balanced",
                                        max_acceptable_loss=LOSS_TOL["balanced"] * budget, as_of=T)
        if pf.get("status") != "ok":
            cut += pd.Timedelta(days=60)
            continue
        def realized(alloc_rows):
            tot = 0.0
            for a in alloc_rows:
                c = a["crop"]
                nxt = plans2[plans2["crop"] == c]
                if not len(nxt):
                    continue
                r = nxt.iloc[0]
                o = BT.realized_outcome(city, c, r["harvest_start"], r["harvest_date"],
                                        float(r["cost_per_mu"]), float(r["expected_yield_per_mu"]), float(a["area_mu"]))
                if o:
                    tot += o["realized_profit"]
            return tot
        port_profit = realized(pf["allocation"])
        single = pf["single_crop_reference"]
        r_single = plans2[plans2["crop"] == single["crop"]]
        single_profit = realized([{"crop": single["crop"], "area_mu": single["area_mu"]}]) if len(r_single) else None
        rows_pb.append({"cutoff": T, "city": city,
                        "portfolio_profit_realized": round(port_profit, 2),
                        "single_crop_profit_realized": None if single_profit is None else round(single_profit, 2),
                        "portfolio_utility": pf["portfolio_metrics"]["portfolio_utility"],
                        "single_utility": single["utility"],
                        "hhi": pf["portfolio_metrics"]["hhi"],
                        "avg_pairwise_corr": pf["portfolio_metrics"]["avg_pairwise_corr"],
                        "n_crops": len(pf["allocation"]),
                        "allocation": ";".join(f"{a['crop']}:{a['area_mu']}" for a in pf["allocation"]),
                        "single_crop": single["crop"]})
        print(f"[portfolio-bt] {T}: portfolio={port_profit:,.0f} single={single_profit if single_profit is None else round(single_profit):,}", flush=True)
        cut += pd.Timedelta(days=60)
    pb = pd.DataFrame(rows_pb)
    pb.to_csv(port_dir / "portfolio_backtest.csv", index=False, encoding="utf-8-sig")
    print(f"[opt] portfolio backtest rows={len(pb)}")

    # 5) 每日信号快照 + 阈值表
    crops = gen["meta"]["crop_pool"]
    snap = DS.warning_table(city, crops, as_of_date=str(ds["date"].max().date()))
    snap.to_csv(rec_dir / "daily_signal_snapshot.csv", index=False, encoding="utf-8-sig")
    thr_rows = []
    for c in crops:
        t = DS.warning_thresholds(city, c)
        thr_rows.append({"city": city, "crop": c,
                         "HRI_p75": (t.get("HRI") or {}).get("p75"), "HRI_p90": (t.get("HRI") or {}).get("p90"),
                         "HRI_p95": (t.get("HRI") or {}).get("p95"),
                         "MR_p75": (t.get("market_risk") or {}).get("p75"),
                         "MR_p90": (t.get("market_risk") or {}).get("p90"),
                         "MR_p95": (t.get("market_risk") or {}).get("p95")})
    pd.DataFrame(thr_rows).to_csv(rec_dir / "warning_thresholds.csv", index=False, encoding="utf-8-sig")
    print("\n[signal snapshot]\n", snap.to_string(index=False))

    # 6) V3 增强扫描
    RI.scan_v3_enhancements().to_csv(rec_dir / "v3_enhancement_scan.csv", index=False, encoding="utf-8-sig")
    print(f"\n[opt] done {time.time()-t0:.0f}s")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default="沈阳")
    ap.add_argument("--area", type=float, default=100.0)
    ap.add_argument("--budget", type=float, default=500000.0)
    ap.add_argument("--plant", default="2027-03-01")
    ap.add_argument("--harvest", default="2027-10-31")
    a = ap.parse_args()
    main(a.city, a.area, a.budget, a.plant, a.harvest)