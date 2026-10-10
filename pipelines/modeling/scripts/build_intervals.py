# -*- coding: utf-8 -*-
"""
Phase 3 入口：P10/P50/P90 区间 + calibration 对比。

  python3 decision_engine/scripts/build_intervals.py

输出：
  decision_engine/evaluation/backtests/interval_predictions.parquet
  decision_engine/evaluation/metrics/interval_calibration.csv          (per crop×fold)
  decision_engine/evaluation/metrics/interval_calibration_summary.csv
  decision_engine/models/registry/interval_selection.json
"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from decision_engine.common import de_path, ensure_dir, write_json  # noqa: E402
from decision_engine.models import intervals as iv  # noqa: E402
from decision_engine.models import train_price as tp  # noqa: E402


def best_point_family() -> str:
    """选择残差校正所用点模型族：model_comparison.csv 中 mean_WAPE 最低的 ML 族。"""
    p = de_path("evaluation", "metrics", "model_comparison.csv")
    if p.exists():
        df = pd.read_csv(p)
        ml = df[~df["route"].isin(["baseline"])]
        if len(ml):
            return ml.groupby("model")["mean_WAPE"].mean().sort_values().index[0]
    return "extra_trees"


def main():
    t0 = time.time()
    ds = pd.read_parquet(de_path("data", "processed", "decision_dataset_v1.parquet"))
    ds["date"] = pd.to_datetime(ds["date"])

    fam = best_point_family()
    print(f"[interval] 残差校正点模型族 = {fam}")
    facs = tp.make_model_factories(42)
    make_model = facs.get(fam, facs["extra_trees"])

    parts = [iv.seasonal_quantile_intervals(ds)]
    print(f"[interval] seasonal done {time.time()-t0:.0f}s", flush=True)
    parts.append(iv.seasonal_window_quantile_intervals(ds))
    print(f"[interval] seasonal_window done {time.time()-t0:.0f}s", flush=True)
    parts.append(iv.residual_calibration_intervals(ds, make_model))
    print(f"[interval] residual done {time.time()-t0:.0f}s", flush=True)
    parts.append(iv.residual_calibration_expanding_intervals(ds, make_model))
    print(f"[interval] residual_expanding done {time.time()-t0:.0f}s", flush=True)
    parts.append(iv.residual_calibration_recent_intervals(ds, make_model))
    print(f"[interval] residual_recent done {time.time()-t0:.0f}s", flush=True)
    parts.append(iv.residual_adaptive_scaled_intervals(ds, make_model))
    print(f"[interval] residual_adaptive done {time.time()-t0:.0f}s", flush=True)
    parts.append(iv.quantile_regression_intervals(ds))
    print(f"[interval] quantile_regression done {time.time()-t0:.0f}s", flush=True)
    parts.append(iv.mapie_enbpi_intervals(ds))
    print(f"[interval] mapie enbpi done {time.time()-t0:.0f}s", flush=True)
    parts.append(iv.mapie_enbpi_calibrated_intervals(ds))
    print(f"[interval] mapie enbpi_calibrated done {time.time()-t0:.0f}s", flush=True)
    parts.append(iv.mapie_aci_intervals(ds))
    print(f"[interval] mapie aci done {time.time()-t0:.0f}s", flush=True)

    all_iv = pd.concat(parts, ignore_index=True)
    per, agg = iv.evaluate_intervals(all_iv)

    bt = ensure_dir(de_path("evaluation", "backtests"))
    mt = ensure_dir(de_path("evaluation", "metrics"))
    all_iv.to_parquet(bt / "interval_predictions.parquet", index=False)
    per.to_csv(mt / "interval_calibration.csv", index=False, encoding="utf-8-sig")
    agg.to_csv(mt / "interval_calibration_summary.csv", index=False, encoding="utf-8-sig")
    print("\n[interval summary]\n", agg.to_string(index=False))

    # 选择：coverage 接近 0.8（|gap|<=0.05）且宽度较小；若不达标则标注 scenario range
    ok = agg[agg["coverage_gap"] <= 0.05]
    if len(ok):
        best = ok.sort_values("mean_width").iloc[0]
        calibrated = True
    else:
        best = agg.iloc[0]
        calibrated = False
    sel = {"method": best["method"], "coverage": float(best["coverage"]),
           "mean_width": float(best["mean_width"]), "nominal": iv.NOMINAL,
           "is_calibrated_interval": bool(calibrated),
           "point_model_family_for_residual": fam,
           "note": "P10/P50/P90 nominal coverage=80%；仅当 empirical coverage 接近名义值时称为 prediction interval"}
    write_json(sel, de_path("models", "registry", "interval_selection.json"))
    print(f"\n[interval] selected: {sel}", flush=True)

    # 合并产物：predictions.parquet + 选定方法的 lower/upper（含 city），满足
    # 「date/city/crop/actual/prediction/lower/upper/model/fold」字段要求
    preds_path = bt / "predictions.parquet"
    if preds_path.exists():
        p = pd.read_parquet(preds_path)
        key = all_iv[all_iv["method"] == best["method"]][["crop", "fold", "date", "lo", "hi"]]
        key = key.groupby(["crop", "fold", "date"], as_index=False).agg(lo=("lo", "mean"), hi=("hi", "mean"))
        m = p.merge(key, on=["crop", "fold", "date"], how="left")
        m["city"] = m["city"] if "city" in m.columns else "沈阳"
        m["lower"] = m["lo"]
        m["upper"] = m["hi"]
        m["interval_method"] = best["method"]
        cols = ["date", "city", "crop", "target", "fold", "route", "model",
                "actual", "prediction", "lower", "upper", "anchor_price", "interval_method"]
        m = m[[c for c in cols if c in m.columns] + [c for c in m.columns if c not in cols]]
        m.to_parquet(bt / "predictions_with_intervals.parquet", index=False)
        print(f"[interval] merged predictions_with_intervals: {m.shape}", flush=True)
    print(f"[interval] done {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()