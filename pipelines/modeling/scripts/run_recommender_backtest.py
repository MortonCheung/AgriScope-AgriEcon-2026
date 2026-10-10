# -*- coding: utf-8 -*-
"""
Phase 10 入口：推荐器历史回测 + 政策基准 + 跟风抑制 + 推荐案例。

  python3 decision_engine/scripts/run_recommender_backtest.py [--cities 沈阳,朝阳] [--step-days 30]

输出：
  decision_engine/evaluation/recommendation/recommender_backtest.parquet
  decision_engine/evaluation/recommendation/policy_benchmark.csv
  decision_engine/evaluation/recommendation/ranking_stability.csv
  decision_engine/evaluation/recommendation/herding_suppression.csv
  decision_engine/evaluation/recommendation/recommendation_cases.csv
  decision_engine/evaluation/cases/recommendation_cases.json
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
from decision_engine.evaluation.recommendation import recommender_backtest as BT  # noqa: E402
from decision_engine.optimization import utility as U  # noqa: E402
from decision_engine.recommendation.recommender import recommend_plans  # noqa: E402


def main(cities, step_days: int = 30):
    out_dir = ensure_dir(de_path("evaluation", "recommendation"))
    cases_dir = ensure_dir(de_path("evaluation", "cases"))
    t0 = time.time()
    all_bt, all_sum, all_herd = [], [], []
    for city in cities:
        res = BT.backtest_recommender(city=city, step_days=step_days, risk_preference="balanced")
        if res.get("status") != "ok":
            print(f"[rec-bt] {city}: {res.get('status')}（跳过）")
            continue
        bt, summ = res["backtest"], res["summary"]
        bt["city"] = city
        summ["city"] = city
        all_bt.append(bt)
        all_sum.append(summ)
        h = BT.herding_suppression(bt)
        if len(h):
            h["city"] = city
            all_herd.append(h)
        print(f"[rec-bt] {city}: cutoffs={bt['cutoff'].nunique()} rows={len(bt)} ({time.time()-t0:.0f}s)", flush=True)

    if not all_bt:
        print("[rec-bt] 无回测结果")
        return
    bt = pd.concat(all_bt, ignore_index=True)
    summ = pd.concat(all_sum, ignore_index=True)
    bt.to_parquet(out_dir / "recommender_backtest.parquet", index=False)
    summ.to_csv(out_dir / "policy_benchmark.csv", index=False, encoding="utf-8-sig")
    print("\n[policy benchmark]\n", summ.sort_values(["rank", "realized_profit_mean"], ascending=[True, False]).to_string(index=False))

    herd = pd.concat(all_herd, ignore_index=True) if all_herd else pd.DataFrame()
    if len(herd):
        herd.to_csv(out_dir / "herding_suppression.csv", index=False, encoding="utf-8-sig")
        print("\n[herding suppression]\n", herd.to_string(index=False))

    # 排序稳定性（对多个 cutoff 的推荐作物集合）
    stab_rows = []
    for (city, cutoff), g in bt[(bt["rank"] == "top1")].groupby(["city", "cutoff"]):
        for pol in g["policy"].unique():
            stab_rows.append({"city": city, "cutoff": cutoff, "policy": pol,
                              "crop": g[g["policy"] == pol]["crops"].iloc[0],
                              "realized_profit": g[g["policy"] == pol]["realized_profit_mean"].iloc[0]})
    stab = pd.DataFrame(stab_rows)
    if len(stab):
        # 各政策在相邻 cutoff 之间推荐作物保持不变的比例
        rows = []
        for (city, pol), g in stab.groupby(["city", "policy"]):
            g = g.sort_values("cutoff")
            same = (g["crop"].shift() == g["crop"]).iloc[1:]
            rows.append({"city": city, "policy": pol, "n_cutoffs": len(g),
                         "crop_retention_rate": float(same.mean()) if len(same) else None,
                         "n_distinct_crops": int(g["crop"].nunique()),
                         "top1_crop_mode": g["crop"].mode().iat[0] if len(g["crop"].mode()) else None})
        rs = pd.DataFrame(rows)
        rs.to_csv(out_dir / "ranking_stability.csv", index=False, encoding="utf-8-sig")
        print("\n[ranking stability]\n", rs.to_string(index=False))

    # 案例：10 个真实推荐 + 1 个失败案例（自动规则，不 cherry-pick）
    cases = []
    top1 = bt[bt["rank"] == "top1"].copy()
    if len(top1):
        pick = top1.sample(n=min(10, len(top1)), random_state=42) if len(top1) > 10 else top1
        for _, r in pick.iterrows():
            cases.append({"case_type": "recommendation", "city": r["city"], "cutoff": r["cutoff"],
                          "policy": r["policy"], "crops": r["crops"],
                          "realized_profit": round(float(r["realized_profit_mean"]), 2),
                          "predicted_profit": None if pd.isna(r["predicted_profit_mean"]) else round(float(r["predicted_profit_mean"]), 2),
                          "hit_rate": round(float(r["hit_rate"]), 3),
                          "HRI_mean": None if pd.isna(r["HRI_mean"]) else round(float(r["HRI_mean"]), 1),
                          "confidence": None if pd.isna(r["confidence_mean"]) else round(float(r["confidence_mean"]), 1)})
        worst = top1.sort_values("realized_profit_mean").head(1).iloc[0]
        cases.append({"case_type": "failure", "city": worst["city"], "cutoff": worst["cutoff"],
                      "policy": worst["policy"], "crops": worst["crops"],
                      "realized_profit": round(float(worst["realized_profit_mean"]), 2),
                      "predicted_profit": None if pd.isna(worst["predicted_profit_mean"]) else round(float(worst["predicted_profit_mean"]), 2),
                      "hit_rate": round(float(worst["hit_rate"]), 3),
                      "note": "实现利润最低的推荐（失败案例，必须展示）"})
    pd.DataFrame(cases).to_csv(out_dir / "recommendation_cases.csv", index=False, encoding="utf-8-sig")
    with open(cases_dir / "recommendation_cases.json", "w", encoding="utf-8") as f:
        json.dump({"cases": cases, "selection_rule": "回测 top1 前 10 例 + 实现利润最低 1 例（自动规则）",
                   "replay_assumption": {"area_mu": BT.REPLAY_AREA_MU, "budget": BT.REPLAY_BUDGET,
                                         "note": "回测情景假设（非真实经营规模）；成本/亩产为参考或 proxy 口径"}},
                  f, ensure_ascii=False, indent=2)
    print(f"\n[rec-bt] cases={len(cases)} | total {time.time()-t0:.0f}s")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cities", default="沈阳,朝阳")
    ap.add_argument("--step-days", type=int, default=30)
    a = ap.parse_args()
    main([c for c in a.cities.split(",") if c], a.step_days)