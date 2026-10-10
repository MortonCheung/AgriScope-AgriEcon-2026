# -*- coding: utf-8 -*-
"""
Phase 4-7 入口：HRI / Market Risk / Climate Exposure / Production Context。

  python3 decision_engine/scripts/build_risk_models.py

输出：
  decision_engine/data/features/hri_v1.parquet
  decision_engine/data/features/market_risk_v1.parquet
  decision_engine/data/features/climate_daily_{city}.parquet
  decision_engine/data/features/production_context.csv
  decision_engine/evaluation/metrics/hri_validation.csv
  decision_engine/evaluation/metrics/hri_sensitivity.csv
  decision_engine/evaluation/metrics/market_risk_validation.csv
"""
from __future__ import annotations
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from decision_engine.common import de_path, ensure_dir  # noqa: E402
from decision_engine.risk import climate, hri, market_risk, production  # noqa: E402


def main():
    t0 = time.time()
    ds = pd.read_parquet(de_path("data", "processed", "decision_dataset_v1.parquet"))
    ds["date"] = pd.to_datetime(ds["date"])
    fdir = ensure_dir(de_path("data", "features"))
    mdir = ensure_dir(de_path("evaluation", "metrics"))

    # ---- Production context ----
    pc = production.build_production_context()
    pc.to_csv(fdir / "production_context.csv", index=False, encoding="utf-8-sig")
    print(f"[production] rows={len(pc)} cities={pc['city'].nunique()} crops={pc['crop'].nunique()}")

    # ---- HRI ----
    h = hri.build_hri(ds)
    keep = (["date", "city", "crop", "price_per_kg"] +
            [f"c_{c}" for c in hri.COMPONENTS] +
            [c for c in h.columns if c.startswith("hri_")])
    h[keep].to_parquet(fdir / "hri_v1.parquet", index=False)
    print(f"[hri] rows={len(h)} cols={len(keep)}")

    sens = hri.sensitivity(h)
    sens.to_csv(mdir / "hri_sensitivity.csv", index=False, encoding="utf-8-sig")
    print("\n[hri sensitivity]\n", sens.to_string(index=False))

    val = hri.validate(hri.forward_returns(h))
    val.to_csv(mdir / "hri_validation.csv", index=False, encoding="utf-8-sig")
    print("\n[hri validation]\n", val.to_string(index=False))

    # ---- Market Risk ----
    iv_path = de_path("evaluation", "backtests", "interval_predictions.parquet")
    iv = pd.read_parquet(iv_path) if iv_path.exists() else None
    if iv is not None:
        iv["date"] = pd.to_datetime(iv["date"])
    mr = market_risk.build_market_risk(ds, interval_preds=iv)
    mkeep = (["date", "city", "crop", "price_per_kg"] +
             [c for c in mr.columns if c.startswith("mr_") or c.startswith("market_risk")])
    mr[mkeep].to_parquet(fdir / "market_risk_v1.parquet", index=False)
    mval = market_risk.validate(mr)
    mval.to_csv(mdir / "market_risk_validation.csv", index=False, encoding="utf-8-sig")
    print(f"\n[market_risk] rows={len(mr)}\n", mval.to_string(index=False))

    # ---- Climate daily (六城) ----
    clim_rows = []
    for city in ["沈阳", "朝阳", "锦州", "大连", "铁岭", "丹东"]:
        ce = climate.daily_exposure(city)
        ce.to_parquet(fdir / f"climate_daily_{climate.CITY_FILE[city]}.parquet", index=False)
        clim_rows.append({"city": city, "rows": len(ce),
                          "mean_exposure": float(ce["climate_exposure"].mean()),
                          "component_count_mean": float(ce["climate_component_count"].mean())})
    pd.DataFrame(clim_rows).to_csv(mdir / "climate_daily_summary.csv", index=False, encoding="utf-8-sig")
    print("\n[climate]\n", pd.DataFrame(clim_rows).to_string(index=False))

    # ---- 计划期暴露示例（供人工检查）----
    ex = []
    for city, plant, harv in [("沈阳", "2026-04-10", "2026-07-10"),
                              ("沈阳", "2026-06-01", "2026-09-14"),
                              ("锦州", "2026-04-01", "2026-06-30")]:
        ex.append(climate.plan_exposure(city, plant, harv))
    pd.DataFrame(ex).to_csv(de_path("evaluation", "metrics", "climate_plan_examples.csv"),
                            index=False, encoding="utf-8-sig")
    print(f"[climate] plan examples: {len(ex)}")
    print(f"[risk] done {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()