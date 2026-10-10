# -*- coding: utf-8 -*-
"""
开源 P1 评估：Amazon Chronos（zero-shot forecasting benchmark）。

  python3 decision_engine/scripts/oss_chronos.py [--model amazon/chronos-t5-tiny]

要求：
  - 优先 chronos-bolt-tiny/mini（若当前 chronos-forecasting 版本不支持 bolt，则使用 t5-tiny，
    并在报告中如实记录版本与模型大小）；
  - 只做 zero-shot：禁止训练大型 Transformer；
  - 先测 3 种代表性作物（西红柿/黄瓜/土豆），若有明显优势再扩展到 10 种。
输出：
  decision_engine/evaluation/open_source/chronos_origins.csv / chronos_metrics.csv
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
PILOT_CROPS = ["西红柿", "黄瓜", "土豆"]


def load_pipeline(model_name: str):
    import chronos
    # bolt 优先（若版本支持）
    for cls_name in ["ChronosBoltPipeline", "ChronosPipeline"]:
        cls = getattr(chronos, cls_name, None)
        if cls is not None and ("bolt" not in model_name or cls_name == "ChronosBoltPipeline"):
            try:
                return cls.from_pretrained(model_name), cls_name
            except Exception as e:
                print(f"[chronos] {cls_name} load failed: {type(e).__name__} {str(e)[:120]}", flush=True)
    raise RuntimeError("no usable chronos pipeline")


def main(model_name: str = "amazon/chronos-t5-tiny", crops: list | None = None):
    import torch
    ds = pd.read_parquet(de_path("data", "processed", "decision_dataset_v1.parquet"))
    ds["date"] = pd.to_datetime(ds["date"])
    out = ensure_dir(de_path("evaluation", "open_source"))
    crops = crops or PILOT_CROPS

    t0 = time.time()
    try:
        pipeline, cls_name = load_pipeline(model_name)
    except Exception as e:
        upsert_benchmark([{"library": "chronos-forecasting", "model": model_name,
                           "version": pkg_version("chronos"), "city": "沈阳", "crop": "pilot",
                           "target": PRIMARY_TARGET, "route": "zero_shot",
                           "status": "FAILED", "reason": f"模型加载失败: {type(e).__name__}: {str(e)[:100]}"}])
        print("[chronos] failed to load model", flush=True)
        return
    n_params = sum(p.numel() for p in getattr(pipeline, "model", torch.nn.Module()).parameters()) \
        if hasattr(pipeline, "model") else None
    print(f"[chronos] pipeline={cls_name} model={model_name} params={n_params}", flush=True)

    rows = []
    for crop in crops:
        for fold in FOLDS:
            series_end = pd.to_datetime(fold["test_end"])
            sub = ds[ds["crop"] == crop]
            obs = sub[sub["date"] <= series_end]["date"]
            series_end = pd.to_datetime(obs.max())
            daily = build_daily_series(ds, crop, series_end)
            y = daily["y"].values.astype(np.float32)
            target_map = sub.set_index("date")[PRIMARY_TARGET]
            test_obs = [d for d in sub["date"]
                        if pd.Timestamp(fold["test_start"]) <= d <= pd.Timestamp(fold["test_end"])][::5]
            for t in test_obs:
                t = pd.Timestamp(t)
                pos = int(np.searchsorted(daily["ds"].values,
                                          np.datetime64(t), side="right"))
                if pos < 100 or t not in target_map.index or pd.isna(target_map.loc[t]):
                    continue
                context = torch.tensor(y[max(0, pos - 512):pos])
                try:
                    fc = pipeline.predict(context, prediction_length=H)
                    arr = fc[0].numpy() if hasattr(fc[0], "numpy") else np.asarray(fc[0])
                except Exception as e:
                    rows.append({"crop": crop, "fold": fold["name"], "model": f"chronos[{cls_name}:{model_name.split('/')[-1]}]",
                                 "origin_date": t, "status": f"PREDICT_FAILED:{type(e).__name__}"})
                    continue
                # quantile: [num_samples, H] → 0.1/0.5/0.9
                q10 = np.quantile(arr, 0.10, axis=0) if arr.ndim > 1 else arr
                q50 = np.quantile(arr, 0.50, axis=0) if arr.ndim > 1 else arr
                q90 = np.quantile(arr, 0.90, axis=0) if arr.ndim > 1 else arr
                rows.append({"crop": crop, "fold": fold["name"],
                             "model": f"chronos[{cls_name}:{model_name.split('/')[-1]}]",
                             "origin_date": t, "status": "OK",
                             "pred_window_mean": float(np.mean(q50)),
                             "q10_window_mean": float(np.mean(q10)),
                             "q90_window_mean": float(np.mean(q90)),
                             "actual_window_mean": float(target_map.loc[t])})
        print(f"[chronos] {crop} done ({time.time()-t0:.0f}s)", flush=True)

    df = pd.DataFrame(rows)
    df.to_csv(out / "chronos_origins.csv", index=False, encoding="utf-8-sig")
    ok = df[df["status"] == "OK"] if len(df) else df
    if not len(ok):
        upsert_benchmark([{"library": "chronos-forecasting", "model": model_name,
                           "version": pkg_version("chronos"), "city": "沈阳", "crop": ",".join(crops),
                           "target": PRIMARY_TARGET, "route": "zero_shot",
                           "status": "FAILED", "reason": "所有预测失败"}])
        return
    mets = []
    for (crop, fold), g in ok.groupby(["crop", "fold"]):
        mm = metrics_table(g["actual_window_mean"].values, g["pred_window_mean"].values)
        mm.update({"model": g["model"].iloc[0], "crop": crop, "fold": fold})
        mets.append(mm)
    mets = pd.DataFrame(mets)
    mets.to_csv(out / "chronos_metrics.csv", index=False, encoding="utf-8-sig")
    cov = float(((ok["actual_window_mean"] >= ok["q10_window_mean"]) &
                 (ok["actual_window_mean"] <= ok["q90_window_mean"])).mean())
    width = float((ok["q90_window_mean"] - ok["q10_window_mean"]).mean())
    agg = mets.groupby("model").agg(MAE=("MAE", "mean"), RMSE=("RMSE", "mean"),
                                    sMAPE=("sMAPE", "mean"), WAPE=("WAPE", "mean")).reset_index()
    print("[chronos]\n", agg.to_string(index=False), f"\ncoverage={cov:.3f} width={width:.3f}", flush=True)

    # 与同原点自研模型比较
    preds_path = de_path("evaluation", "backtests", "predictions.parquet")
    if preds_path.exists():
        from decision_engine.models.statsforecast_bench import compare_with_inhouse
        inhouse = compare_with_inhouse(ok.rename(columns={"model": "model"}).assign(
            model=ok["model"]), preds_path) if False else compare_with_inhouse(ok, preds_path)
        agg2 = inhouse.groupby("model").agg(mean_WAPE=("WAPE", "mean")).reset_index().sort_values("mean_WAPE")
        print("[chronos vs inhouse]\n", agg2.head(12).to_string(index=False), flush=True)

    rows_b = []
    for _, r in agg.iterrows():
        rows_b.append({"library": "chronos-forecasting", "model": r["model"],
                       "version": pkg_version("chronos"), "city": "沈阳", "crop": ",".join(crops),
                       "target": PRIMARY_TARGET, "route": "zero_shot",
                       "MAE": round(float(r["MAE"]), 4), "RMSE": round(float(r["RMSE"]), 4),
                       "sMAPE": round(float(r["sMAPE"]), 4), "WAPE": round(float(r["WAPE"]), 4),
                       "coverage": round(cov, 4), "interval_width": round(width, 4),
                       "runtime_sec": round(time.time() - t0, 1),
                       "status": "BENCHMARK_ONLY",
                       "reason": f"zero-shot 预训练模型（{model_name}）；先 3 作物试点；与同原点自研比较后决定是否扩展"})
    upsert_benchmark(rows_b)
    print(f"[chronos] done {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="amazon/chronos-t5-tiny")
    ap.add_argument("--crops", default="")
    args = ap.parse_args()
    main(args.model, [c for c in args.crops.split(",") if c] or None)