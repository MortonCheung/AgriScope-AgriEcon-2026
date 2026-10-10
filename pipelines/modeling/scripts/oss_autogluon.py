# -*- coding: utf-8 -*-
"""
开源 P0 评估 2/…: AutoGluon-TimeSeries（独立 benchmark，candidate generator）。

  python3 decision_engine/scripts/oss_autogluon.py [--preset fast_training|medium_quality] [--time-limit 300]

公平性：
  - 与 StatsForecast/自研完全相同的 fold 与 weekly 原点集合（origin 对齐观测日）；
  - 每 fold 只 fit 一次；origin 处使用 predict(data<=origin)（walk-forward，无未来数据）；
  - 30 天窗口：window-mean 与 target_mean_price_next_30d 直接比较；
  - quantile（0.1/0.5/0.9）在观测日层面评估 coverage 与宽度。
输出：
  decision_engine/evaluation/open_source/autogluon_origins.csv
  decision_engine/evaluation/open_source/autogluon_quantile_daily.csv
  decision_engine/evaluation/open_source/autogluon_metrics.csv
  decision_engine/evaluation/open_source/autogluon_vs_inhouse.csv
"""
from __future__ import annotations
import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from decision_engine.common import de_path, ensure_dir  # noqa: E402
from decision_engine.models.backtest import FOLDS, metrics_table  # noqa: E402
from decision_engine.models.oss_common import upsert_benchmark, pkg_version  # noqa: E402
from decision_engine.models.statsforecast_bench import build_daily_series  # noqa: E402
from decision_engine.models.train_price import PRIMARY_TARGET  # noqa: E402

H = 30


def build_tsdf(ds: pd.DataFrame, series_end: pd.Timestamp):
    from autogluon.timeseries import TimeSeriesDataFrame
    frames = []
    for crop in sorted(ds["crop"].unique()):
        s = build_daily_series(ds, crop, series_end)
        frames.append(pd.DataFrame({"item_id": f"沈阳_{crop}",
                                    "timestamp": s["ds"].values, "target": s["y"].values}))
    return TimeSeriesDataFrame.from_data_frame(pd.concat(frames, ignore_index=True))


def main(preset: str = "fast_training", time_limit: int = 300):
    from autogluon.timeseries import TimeSeriesDataFrame, TimeSeriesPredictor

    ds = pd.read_parquet(de_path("data", "processed", "decision_dataset_v1.parquet"))
    ds["date"] = pd.to_datetime(ds["date"])
    out = ensure_dir(de_path("evaluation", "open_source"))

    origins_rows, daily_rows, met_rows = [], [], []
    t0 = time.time()
    for fold in FOLDS:
        train_end = pd.Timestamp(fold["train_end"])
        sub_all = ds[ds["date"] <= train_end]
        series_end = pd.to_datetime(sub_all["date"].max())
        train_tsdf = build_tsdf(ds, train_end)
        print(f"[ag] fold {fold['name']}: train items={train_tsdf.num_items} len={len(train_tsdf)}", flush=True)

        predictor = TimeSeriesPredictor(target="target", prediction_length=H,
                                        quantile_levels=[0.1, 0.5, 0.9],
                                        eval_metric="WAPE", verbosity=1)
        fit_t0 = time.time()
        predictor.fit(train_tsdf, presets=preset, time_limit=time_limit,
                      num_val_windows=2, refit_full=False)
        fit_rt = time.time() - fit_t0
        print(f"[ag]   fit {fit_rt:.0f}s models={predictor.model_names()}", flush=True)

        # origins：测试期内每 5 个观测一个原点（与 darts/prophet 一致），对齐观测日
        sub = ds[ds["crop"] == "土豆"]
        test_obs = sorted([d for d in sub["date"]
                           if pd.Timestamp(fold["test_start"]) <= d <= pd.Timestamp(fold["test_end"])])
        origins = test_obs[::5]

        for t in origins:
            t = pd.Timestamp(t)
            data_up_to = build_tsdf(ds, t)
            try:
                fc = predictor.predict(data_up_to)
            except Exception as e:
                print(f"[ag]   predict {t.date()} failed: {type(e).__name__} {str(e)[:100]}")
                continue
            for crop in sorted(ds["crop"].unique()):
                item = f"沈阳_{crop}"
                try:
                    fi = fc.loc[item]
                except Exception:
                    continue
                target_map = ds[ds["crop"] == crop].set_index("date")[PRIMARY_TARGET]
                if t not in target_map.index or pd.isna(target_map.loc[t]):
                    continue
                actual = float(target_map.loc[t])
                origins_rows.append({
                    "crop": crop, "fold": fold["name"], "model": "autogluon_" + preset,
                    "origin_date": t, "pred_window_mean": float(fi["mean"].mean()),
                    "q10_window_mean": float(fi["0.1"].mean()),
                    "q90_window_mean": float(fi["0.9"].mean()),
                    "actual_window_mean": actual,
                })
                # 观测日层面的 quantile 覆盖
                obs = ds[(ds["crop"] == crop) & (ds["date"] > t) & (ds["date"] <= t + pd.Timedelta(days=H))]
                obs = obs[obs["date"].isin(set(pd.to_datetime(fi.index.get_level_values("timestamp")).date))]
                for _, r in obs.iterrows():
                    ts = pd.Timestamp(r["date"])
                    if ts in fi.index:
                        daily_rows.append({
                            "crop": crop, "fold": fold["name"], "origin_date": t, "date": ts,
                            "actual": float(r["price_per_kg"]),
                            "q10": float(fi.loc[ts, "0.1"]), "q50": float(fi.loc[ts, "0.5"]),
                            "q90": float(fi.loc[ts, "0.9"])})
        print(f"[ag]   origins done {len(origins)} ({time.time()-t0:.0f}s)", flush=True)

        # fit 一次的 runtime/artifact
        model_dir = Path(predictor.path)
        size_mb = sum(f.stat().st_size for f in model_dir.rglob("*") if f.is_file()) / 1e6 if model_dir.exists() else None
        for m in predictor.model_names():
            met_rows.append({"model": f"autogluon_{preset}", "submodel": m, "fold": fold["name"],
                             "fit_runtime_sec": fit_rt, "artifact_size_mb": size_mb})

    origins = pd.DataFrame(origins_rows)
    daily = pd.DataFrame(daily_rows)
    origins.to_csv(out / "autogluon_origins.csv", index=False, encoding="utf-8-sig")
    daily.to_csv(out / "autogluon_quantile_daily.csv", index=False, encoding="utf-8-sig")

    mets = []
    for (crop, fold), g in origins.groupby(["crop", "fold"]):
        mm = metrics_table(g["actual_window_mean"].values, g["pred_window_mean"].values)
        mm.update({"model": f"autogluon_{preset}", "crop": crop, "fold": fold})
        mets.append(mm)
    mets = pd.DataFrame(mets)
    mets.to_csv(out / "autogluon_metrics.csv", index=False, encoding="utf-8-sig")

    # quantile 覆盖（观测日层面）
    cov_stats = None
    if len(daily):
        cov = ((daily["actual"] >= daily["q10"]) & (daily["actual"] <= daily["q90"]))
        cov_stats = {"coverage": float(cov.mean()), "mean_width": float((daily["q90"] - daily["q10"]).mean()),
                     "n": int(len(daily))}
        by_crop = daily.assign(hit=cov).groupby("crop").agg(
            coverage=("hit", "mean"), width=("q90", "mean")).reset_index()
        by_crop["mean_width"] = daily.assign(w=daily["q90"] - daily["q10"]).groupby("crop")["w"].mean().values
        by_crop.to_csv(out / "autogluon_coverage_by_crop.csv", index=False, encoding="utf-8-sig")
        print("[ag] quantile coverage:", cov_stats, flush=True)

    # vs 自研（同原点）
    preds_path = de_path("evaluation", "backtests", "predictions.parquet")
    if len(origins) and preds_path.exists():
        from decision_engine.models.statsforecast_bench import compare_with_inhouse
        inhouse = compare_with_inhouse(origins, preds_path)
        summ = pd.concat([
            mets.rename(columns={})[["model", "crop", "fold", "WAPE", "MAE"]],
            inhouse[["model", "crop", "fold", "WAPE", "MAE"]]], ignore_index=True)
        agg = summ.groupby("model").agg(mean_WAPE=("WAPE", "mean"), mean_MAE=("MAE", "mean"),
                                        n=("WAPE", "count")).reset_index().sort_values("mean_WAPE")
        agg.to_csv(out / "autogluon_vs_inhouse.csv", index=False, encoding="utf-8-sig")
        print("[ag vs inhouse]\n", agg.to_string(index=False), flush=True)

    # 报告所需：性能增益 / runtime / artifact / 依赖成本
    if len(mets):
        reason = (f"preset={preset}; mean WAPE={mets['WAPE'].mean():.2f}; fit_runtime={met_rows[0]['fit_runtime_sec']:.0f}s/fold; "
                  f"artifact_size={met_rows[0]['artifact_size_mb']}MB; 依赖：torch/lightning/gluonts 等（重）")
        rows = []
        for crop, g in mets.groupby("crop"):
            rows.append({"library": "autogluon.timeseries", "model": f"autogluon_{preset}",
                         "version": pkg_version("autogluon.timeseries"), "city": "沈阳", "crop": crop,
                         "target": PRIMARY_TARGET, "route": "multivariate_items",
                         "MAE": round(float(g["MAE"].mean()), 4), "RMSE": round(float(g["RMSE"].mean()), 4),
                         "sMAPE": round(float(g["sMAPE"].mean()), 4), "WAPE": round(float(g["WAPE"].mean()), 4),
                         "coverage": round(cov_stats["coverage"], 4) if cov_stats else None,
                         "interval_width": round(cov_stats["mean_width"], 4) if cov_stats else None,
                         "runtime_sec": round(float(met_rows[0]["fit_runtime_sec"]), 1),
                         "artifact_size_mb": met_rows[0]["artifact_size_mb"],
                         "status": "BENCHMARK_ONLY", "reason": reason})
        upsert_benchmark(rows)
    print(f"[ag] done {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preset", default="fast_training")
    ap.add_argument("--time-limit", type=int, default=300)
    args = ap.parse_args()
    main(args.preset, args.time_limit)