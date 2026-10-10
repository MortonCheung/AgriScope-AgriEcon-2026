# -*- coding: utf-8 -*-
"""Decision Engine 演示：3 个完整输入输出 + 方案对比，落盘为 JSON（供报告引用）。"""
from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from decision_engine.common import de_path, ensure_dir  # noqa: E402
from decision_engine.engine.engine import DecisionEngine  # noqa: E402

PLANS = [
    {"city": "沈阳", "crop": "西红柿", "plant_date": "2026-10-10", "harvest_date": "2027-01-10",
     "area_mu": 80, "cost_per_mu": 5200, "expected_yield_per_mu": 4500, "risk_preference": "balanced"},
    {"city": "沈阳", "crop": "黄瓜", "plant_date": "2027-03-01", "harvest_date": "2027-06-10",
     "area_mu": 120, "cost_per_mu": 4800, "expected_yield_per_mu": 6000, "risk_preference": "conservative"},
    {"city": "朝阳", "crop": "西红柿", "plant_date": "2027-04-01", "harvest_date": "2027-07-01",
     "area_mu": 60, "cost_per_mu": 4200, "expected_yield_per_mu": 5000, "risk_preference": "aggressive"},
]


def main():
    eng = DecisionEngine()
    out = ensure_dir(de_path("outputs"))
    results = []
    for p in PLANS:
        r = eng.evaluate_plan(p)
        results.append({"input": p, "output": r})
        print(f"[demo] {p['city']}×{p['crop']}: status={r.get('status')} "
              f"score={(r.get('decision') or {}).get('score')} "
              f"conf={(r.get('confidence') or {}).get('grade')}", flush=True)
    cmp_res = eng.compare_plans(PLANS)
    detail = {"examples": results,
              "ranking": [{k: v for k, v in r.items() if k != "full_results"}
                          for r in cmp_res["ranking"]],
              "rank_std_by_preference": cmp_res["rank_std_by_preference"]}
    with open(out / "engine_examples.json", "w", encoding="utf-8") as f:
        json.dump(detail, f, ensure_ascii=False, indent=2, default=str)
    print(f"[demo] -> {out / 'engine_examples.json'}")


if __name__ == "__main__":
    main()