# -*- coding: utf-8 -*-
"""
Phase 11 / §63 §64 §65: v2 真实推荐示例（含完整示例 + 10 个不同约束案例 + 朝阳/锦州简化）。

  python3 decision_engine/scripts/run_v2_examples.py

输出：
  decision_engine/outputs/v2_recommendation.json          （§64 完整示例）
  decision_engine/evaluation/recommendation/recommendation_examples_10.csv
  decision_engine/evaluation/cases/recommendation_examples.json
  decision_engine/evaluation/recommendation/regional_recommendations.csv  （朝阳/锦州）
"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from decision_engine.common import de_path, ensure_dir  # noqa: E402
from decision_engine.recommendation.recommender import make_planting_decision  # noqa: E402

FULL_EXAMPLE = {"city": "沈阳", "available_area_mu": 100, "budget": 500000,
                "earliest_plant_date": "2027-03-01", "latest_harvest_date": "2027-10-31",
                "risk_preference": "balanced"}

CASES = [
    {"city": "沈阳", "available_area_mu": 30, "budget": 150000, "earliest_plant_date": "2027-03-01",
     "latest_harvest_date": "2027-08-31", "risk_preference": "conservative"},
    {"city": "沈阳", "available_area_mu": 50, "budget": 250000, "earliest_plant_date": "2027-04-01",
     "latest_harvest_date": "2027-09-30", "risk_preference": "balanced"},
    {"city": "沈阳", "available_area_mu": 80, "budget": 400000, "earliest_plant_date": "2027-05-01",
     "latest_harvest_date": "2027-10-31", "risk_preference": "aggressive"},
    {"city": "沈阳", "available_area_mu": 120, "budget": 600000, "earliest_plant_date": "2027-03-15",
     "latest_harvest_date": "2027-09-15", "risk_preference": "balanced"},
    {"city": "沈阳", "available_area_mu": 100, "budget": 800000, "earliest_plant_date": "2027-06-01",
     "latest_harvest_date": "2027-11-30", "risk_preference": "conservative"},
    {"city": "沈阳", "available_area_mu": 200, "budget": 1000000, "earliest_plant_date": "2027-03-01",
     "latest_harvest_date": "2027-10-31", "risk_preference": "aggressive"},
    {"city": "沈阳", "available_area_mu": 40, "budget": 200000, "earliest_plant_date": "2027-07-01",
     "latest_harvest_date": "2027-12-31", "risk_preference": "balanced"},
    {"city": "沈阳", "available_area_mu": 60, "budget": 300000, "earliest_plant_date": "2027-03-01",
     "latest_harvest_date": "2027-07-15", "risk_preference": "conservative"},
    {"city": "沈阳", "available_area_mu": 90, "budget": 450000, "earliest_plant_date": "2027-04-15",
     "latest_harvest_date": "2027-10-15", "risk_preference": "balanced"},
    {"city": "沈阳", "available_area_mu": 150, "budget": 750000, "earliest_plant_date": "2027-05-15",
     "latest_harvest_date": "2027-11-15", "risk_preference": "aggressive"},
]


def _row(i, req, r):
    p = r.get("recommended_plan") or {}
    return {"case_id": f"CASE-{i+1:02d}", "city": req["city"], "area_mu": req["available_area_mu"],
            "budget": req["budget"], "plant_from": req["earliest_plant_date"],
            "harvest_by": req["latest_harvest_date"], "risk_preference": req["risk_preference"],
            "status": r.get("status"),
            "recommended_crop": p.get("crop"), "harvest_window": p.get("harvest_window"),
            "area_recommended": p.get("area_mu"),
            "price_low": p.get("price_low"), "price_mid": p.get("price_mid"), "price_high": p.get("price_high"),
            "profit_baseline": p.get("profit_baseline"), "profit_pessimistic": p.get("profit_pessimistic"),
            "HRI": p.get("HRI"), "market_risk": p.get("market_risk"), "climate_exposure": p.get("climate_exposure"),
            "decision_score": p.get("decision_score"), "utility_score": p.get("utility_score"),
            "confidence": p.get("confidence"),
            "recommendation_confidence": (r.get("confidence") or {}).get("score"),
            "recommendation_grade": (r.get("confidence") or {}).get("grade"),
            "portfolio": ";".join(f"{a['crop']}:{a['area_mu']}" for a in
                                  ((r.get("portfolio_plan") or {}).get("allocation") or [])),
            "mode_preferred": (r.get("mode_comparison") or {}).get("preferred"),
            "herding_pick": (r.get("risk_summary", {}).get("herding_check") or {}).get("recommended_is_highest_price"),
            "note": ";".join((r.get("limitations") or [])[:1])}


def main():
    out_dir = ensure_dir(de_path("evaluation", "recommendation"))
    cases_dir = ensure_dir(de_path("evaluation", "cases"))
    ensure_dir(de_path("outputs"))
    t0 = time.time()

    # §64 完整示例
    full = make_planting_decision(FULL_EXAMPLE)
    with open(de_path("outputs", "v2_recommendation.json"), "w", encoding="utf-8") as f:
        json.dump(full, f, ensure_ascii=False, indent=2, default=str)
    p = full.get("recommended_plan") or {}
    print(f"[v2] 完整示例: {p.get('crop')} {p.get('harvest_window')} {p.get('area_mu')}亩 "
          f"| 利润 {p.get('profit_baseline')} | 置信 {(full.get('confidence') or {}).get('grade')} "
          f"({time.time()-t0:.0f}s)", flush=True)

    # §63 10 个案例
    rows, detail = [], []
    for i, req in enumerate(CASES):
        r = make_planting_decision(req)
        rows.append(_row(i, req, r))
        detail.append({"request": req, "output": r})
        print(f"[v2] CASE-{i+1:02d}: {rows[-1]['recommended_crop']} | {rows[-1]['recommendation_grade']}",
              flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(out_dir / "recommendation_examples_10.csv", index=False, encoding="utf-8-sig")
    with open(cases_dir / "recommendation_examples.json", "w", encoding="utf-8") as f:
        json.dump({"cases": detail, "note": "覆盖不同风险偏好/预算/面积/种植期；成本与亩产为参考或 proxy 口径"},
                  f, ensure_ascii=False, indent=2, default=str)

    # §65 朝阳 / 锦州 简化推荐
    reg_rows = []
    for city in ["朝阳", "锦州"]:
        req = {"city": city, "available_area_mu": 60, "budget": 250000,
               "earliest_plant_date": "2027-03-01", "latest_harvest_date": "2027-10-31",
               "risk_preference": "balanced"}
        r = make_planting_decision(req)
        pl = r.get("recommended_plan") or {}
        reg_rows.append({"city": city, "status": r.get("status"), "crop": pl.get("crop"),
                         "harvest_window": pl.get("harvest_window"), "area_mu": pl.get("area_mu"),
                         "price_mid": pl.get("price_mid"), "profit_baseline": pl.get("profit_baseline"),
                         "HRI": pl.get("HRI"), "market_risk": pl.get("market_risk"),
                         "confidence": (r.get("confidence") or {}).get("grade"),
                         "note": "简化模块（无成交量、价格层级不同）；成本/亩产为 proxy"})
        print(f"[v2] {city}: {r.get('status')} {pl.get('crop')}", flush=True)
    pd.DataFrame(reg_rows).to_csv(out_dir / "regional_recommendations.csv", index=False, encoding="utf-8-sig")
    print(f"[v2] done {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()