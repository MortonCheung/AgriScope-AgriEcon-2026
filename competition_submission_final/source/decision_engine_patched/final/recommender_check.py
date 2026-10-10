# -*- coding: utf-8 -*-
"""F12c: 用**生产推荐路径**（DecisionEngine + recommend_plans + utility）验证 Balanced 修复。

与旧 v2 结果对比（不覆盖旧产物，写入 models/evaluation/final/）。
"""
from __future__ import annotations
from typing import Dict

import pandas as pd

from decision_engine.final.fcommon import (FINAL_EVAL_DIR, REPORTS_DIR, DE, ensure_dir,
                                           write_json, now_stamp)
from decision_engine.evaluation.recommendation import recommender_backtest as BT

CITIES = ["沈阳", "朝阳"]
OLD_HERD = DE / "evaluation" / "recommendation" / "herding_suppression.csv"


def run() -> Dict[str, object]:
    ensure_dir(FINAL_EVAL_DIR)
    rows, herds = [], []
    for city in CITIES:
        r = BT.backtest_recommender(city=city, step_days=30, risk_preference="balanced",
                                    verbose=False)
        if r.get("status") != "ok":
            print(f"[rec-check] {city}: {r.get('status')}")
            continue
        bt, summ = r["backtest"], r["summary"]
        bt["city"] = city
        bt.to_parquet(FINAL_EVAL_DIR / f"recommender_backtest_{city}.parquet", index=False)
        summ["city"] = city
        rows.append(summ)
        h = BT.herding_suppression(bt)
        h["city"] = city
        herds.append(h)
    if not rows:
        return {"status": "no_results"}
    summ = pd.concat(rows, ignore_index=True)
    summ.to_csv(REPORTS_DIR / "tables" / "recommender_policy_benchmark.csv", index=False, encoding="utf-8-sig")
    herd = pd.concat(herds, ignore_index=True)
    herd.to_csv(REPORTS_DIR / "tables" / "herding_suppression_after.csv", index=False, encoding="utf-8-sig")

    out = {"policies": len(summ), "ts": now_stamp()}
    # before/after 对比（沈阳）
    try:
        old = pd.read_csv(OLD_HERD)
        old = old[old["city"] == "沈阳"][["policy", "high_hri_rate"]].rename(
            columns={"high_hri_rate": "before"})
        new = herd[herd["city"] == "沈阳"][["policy", "high_hri_rate", "mean_HRI"]].rename(
            columns={"high_hri_rate": "after"})
        cmp = old.merge(new, on="policy", how="outer")
        cmp.to_csv(REPORTS_DIR / "tables" / "balanced_fix_before_after.csv", index=False, encoding="utf-8-sig")
        b = cmp[cmp["policy"] == "C_agriscope_balanced"]
        a = cmp[cmp["policy"] == "A_profit_only"]
        out["balanced_before"] = float(b["before"].iloc[0]) if len(b) else None
        out["balanced_after"] = float(b["after"].iloc[0]) if len(b) else None
        out["profit_only_after"] = float(a["after"].iloc[0]) if len(a) else None
        out["fix_effective"] = bool(len(b) and len(a) and
                                    float(b["after"].iloc[0]) <= float(a["after"].iloc[0]) + 1e-9)
    except Exception as e:
        out["compare_error"] = str(e)
    # 固定阈值对照（消除「批次 P90 阈值随推荐集变化」导致的不可比）
    FIXED_THR = 73.2  # 旧 v2 记录的历史阈值
    try:
        fixed_rows = []
        oldparq = DE / "evaluation" / "recommendation" / "recommender_backtest.parquet"
        for tag, path in [("before", oldparq),
                          ("after", FINAL_EVAL_DIR / "recommender_backtest_沈阳.parquet")]:
            if not path.exists():
                continue
            bt = pd.read_parquet(path)
            bt = bt[(bt["rank"] == "top1") & (bt["city"] == "沈阳")]
            g = bt.groupby("policy").apply(
                lambda s: float((s["HRI_mean"] >= FIXED_THR).mean())).rename(tag)
            fixed_rows.append(g)
        if fixed_rows:
            fx = pd.concat(fixed_rows, axis=1).reset_index()
            fx.to_csv(REPORTS_DIR / "tables" / "balanced_fix_before_after_fixed_thr.csv",
                      index=False, encoding="utf-8-sig")
            out["fixed_threshold"] = FIXED_THR
    except Exception as e:
        out["fixed_thr_error"] = str(e)

    write_json(out, FINAL_EVAL_DIR / "recommender_fix_summary.json")
    return out


if __name__ == "__main__":
    print(run())