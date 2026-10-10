# -*- coding: utf-8 -*-
"""
P0 开源评估 1/…: StatsForecast 基准入口。

  python3 decision_engine/scripts/oss_statsforecast.py

输出：
  decision_engine/evaluation/open_source/statsforecast_origins.csv
  decision_engine/evaluation/open_source/statsforecast_metrics.csv
  decision_engine/evaluation/open_source/sf_vs_inhouse_same_origins.csv
  （并 upsert OPEN_SOURCE_MODEL_BENCHMARK.csv）
"""
from __future__ import annotations
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from decision_engine.common import de_path, ensure_dir  # noqa: E402
from decision_engine.models import statsforecast_bench as sfb  # noqa: E402
from decision_engine.models.oss_common import upsert_benchmark, pkg_version  # noqa: E402


def main():
    t0 = time.time()
    ds = pd.read_parquet(de_path("data", "processed", "decision_dataset_v1.parquet"))
    ds["date"] = pd.to_datetime(ds["date"])
    out_dir = ensure_dir(de_path("evaluation", "open_source"))

    sf_preds, sf_mets = sfb.run_sf_benchmark(ds)
    sf_preds.to_csv(out_dir / "statsforecast_origins.csv", index=False, encoding="utf-8-sig")
    sf_mets.to_csv(out_dir / "statsforecast_metrics.csv", index=False, encoding="utf-8-sig")

    # 同原点集合对比自研模型
    preds_path = de_path("evaluation", "backtests", "predictions.parquet")
    if preds_path.exists():
        inhouse = sfb.compare_with_inhouse(sf_preds, preds_path)
        inhouse.to_csv(out_dir / "sf_vs_inhouse_same_origins.csv", index=False, encoding="utf-8-sig")
        both = pd.concat([sf_mets.assign(source="statsforecast"),
                          inhouse[inhouse["route"] != "baseline"].assign(source="inhouse"),
                          inhouse[inhouse["route"] == "baseline"].assign(source="inhouse_baseline")],
                         ignore_index=True)
        both.to_csv(out_dir / "sf_vs_inhouse_metrics.csv", index=False, encoding="utf-8-sig")
        # 汇总
        summ = (both.groupby(["source", "model"])
                .agg(mean_WAPE=("WAPE", "mean"), mean_MAE=("MAE", "mean"),
                     mean_sMAPE=("sMAPE", "mean"), folds=("WAPE", "count")).reset_index()
                .sort_values("mean_WAPE"))
        summ.to_csv(out_dir / "sf_vs_inhouse_summary.csv", index=False, encoding="utf-8-sig")
        print("\n[sf vs inhouse]\n", summ.to_string(index=False))

        # 逐作物 head-to-head：最终选定模型 vs 最优 SF 模型（相同原点）
        sel_path = de_path("evaluation", "metrics", "model_selection.csv")
        if sel_path.exists():
            sel = pd.read_csv(sel_path)
            rows_hh = []
            for _, r in sel.iterrows():
                crop, model, route = r["crop"], r["model"], r["route"]
                inhouse_m = inhouse[(inhouse["crop"] == crop) & (inhouse["model"] == model)]
                sf_m = sf_mets[sf_mets["crop"] == crop]
                if not len(inhouse_m) or not len(sf_m):
                    continue
                best_sf = sf_m.groupby("model")["WAPE"].mean().sort_values()
                rows_hh.append({
                    "crop": crop, "inhouse_selected": model,
                    "inhouse_WAPE": round(float(inhouse_m["WAPE"].mean()), 3),
                    "best_sf_model": best_sf.index[0],
                    "best_sf_WAPE": round(float(best_sf.iloc[0]), 3),
                    "delta": round(float(inhouse_m["WAPE"].mean() - best_sf.iloc[0]), 3),
                })
            hh = pd.DataFrame(rows_hh)
            hh.to_csv(out_dir / "sf_head_to_head_by_crop.csv", index=False, encoding="utf-8-sig")
            print("\n[head-to-head per crop]\n", hh.to_string(index=False))

    # upsert 到统一 benchmark（per crop 聚合）
    rows = []
    ver = pkg_version("statsforecast")
    agg = (sf_mets.groupby(["model", "crop"])
           .agg(MAE=("MAE", "mean"), RMSE=("RMSE", "mean"), sMAPE=("sMAPE", "mean"),
                WAPE=("WAPE", "mean"), runtime=("runtime_sec", "sum")).reset_index())
    for _, r in agg.iterrows():
        rows.append({"library": "statsforecast", "model": r["model"], "version": ver,
                     "city": "沈阳", "crop": r["crop"], "target": "target_mean_price_next_30d",
                     "route": "univariate_walkforward",
                     "MAE": round(r["MAE"], 4), "RMSE": round(r["RMSE"], 4),
                     "sMAPE": round(r["sMAPE"], 4), "WAPE": round(r["WAPE"], 4),
                     "coverage": None, "interval_width": None,
                     "runtime_sec": round(r["runtime"], 2), "artifact_size_mb": None,
                     "status": "BENCHMARK_ONLY",
                     "reason": "统计基线候选；与 ML/基线在同一 fold 与原点上比较"})
    upsert_benchmark(rows)
    print(f"[sf] done {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()