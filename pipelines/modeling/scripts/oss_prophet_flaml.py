# -*- coding: utf-8 -*-
"""
开源 P2 评估：Prophet（季节基线） + FLAML（轻量 AutoML）。

  python3 decision_engine/scripts/oss_prophet_flaml.py

公平性：
  - Prophet：与 StatsForecast 相同的 weekly 原点集合、窗口均值目标；
    每 fold×crop 仅拟合一次（no-refit walk-forward，与 SF refit=False 语义一致）。
  - FLAML：pooled 路由，time-based 内部验证；同一 fold 测试集评估。
输出：
  decision_engine/evaluation/open_source/prophet_origins.csv
  decision_engine/evaluation/open_source/flaml_metrics.csv
"""
from __future__ import annotations
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from decision_engine.common import de_path, ensure_dir  # noqa: E402
from decision_engine.models.backtest import FOLDS, fold_mask, metrics_table  # noqa: E402
from decision_engine.models.oss_common import upsert_benchmark, pkg_version  # noqa: E402
from decision_engine.models.statsforecast_bench import build_daily_series  # noqa: E402
from decision_engine.models.train_price import (FEATURE_COLS, MIN_TRAIN_ROWS,  # noqa: E402
                                                PRIMARY_TARGET)


def run_prophet(ds: pd.DataFrame) -> pd.DataFrame:
    try:
        from prophet import Prophet
    except Exception as e:
        print("[prophet] import failed:", e)
        return pd.DataFrame()
    rows = []
    for crop in sorted(ds["crop"].unique()):
        for fold in FOLDS:
            train_end = pd.Timestamp(fold["train_end"])
            series = build_daily_series(ds, crop, train_end)
            m = Prophet(yearly_seasonality=True, weekly_seasonality=True,
                        daily_seasonality=False, changepoint_prior_scale=0.05)
            m.fit(series.rename(columns={"ds": "ds", "y": "y"}))
            # 预测到 test_end + 30
            horizon = (pd.Timestamp(fold["test_end"]) - train_end).days + 31
            future = m.make_future_dataframe(periods=horizon, freq="D", include_history=False)
            fc = m.predict(future)[["ds", "yhat"]].set_index("ds")["yhat"]
            # weekly 原点
            sub = ds[ds["crop"] == crop]
            tgt = sub.set_index("date")[PRIMARY_TARGET]
            origins = sorted([d for d in sub["date"]
                              if pd.Timestamp(fold["test_start"]) <= d <= pd.Timestamp(fold["test_end"])])[::5]
            for t in origins:
                t = pd.Timestamp(t)
                win = fc[(fc.index > t) & (fc.index <= t + pd.Timedelta(days=30))]
                if len(win) < 20:
                    continue
                if t not in tgt.index or pd.isna(tgt.loc[t]):
                    continue
                rows.append({"crop": crop, "fold": fold["name"], "origin_date": t,
                             "model": "prophet", "pred_window_mean": float(win.mean()),
                             "actual_window_mean": float(tgt.loc[t])})
    return pd.DataFrame(rows)


def run_flaml(ds: pd.DataFrame, time_budget: int = 60) -> tuple[pd.DataFrame, pd.DataFrame]:
    try:
        from flaml import AutoML
    except Exception as e:
        print("[flaml] import failed:", e)
        return pd.DataFrame(), pd.DataFrame()
    preds, mets = [], []
    for fold in FOLDS:
        tr_all, te_all = fold_mask(ds, fold)
        tr = ds[tr_all & ds[PRIMARY_TARGET].notna()].copy()
        te = ds[te_all & ds[PRIMARY_TARGET].notna()].copy()
        if len(tr) < MIN_TRAIN_ROWS or not len(te):
            continue
        trf = tr[FEATURE_COLS].copy()
        tef = te[FEATURE_COLS].copy()
        trf["crop_cat"] = tr["crop"].astype("category").cat.codes
        tef["crop_cat"] = te["crop"].astype("category").cat.codes
        t0 = time.time()
        automl = AutoML()
        automl.fit(trf, tr[PRIMARY_TARGET], task="regression", time_budget=time_budget,
                   split_type="time", eval_method="holdout", seed=42, verbose=0)
        rt = time.time() - t0
        p = automl.predict(tef)
        for dt, crop, act, pr in zip(te["date"], te["crop"], te[PRIMARY_TARGET], p):
            preds.append({"date": dt, "crop": crop, "model": "flaml_pooled",
                          "fold": fold["name"], "route": "pooled",
                          "target": PRIMARY_TARGET, "actual": float(act),
                          "prediction": float(pr), "runtime_sec": rt,
                          "best_model": automl.best_estimator})
        mm = metrics_table(te[PRIMARY_TARGET].values, np.asarray(p))
        mm.update({"model": "flaml_pooled", "fold": fold["name"], "route": "pooled",
                   "runtime_sec": rt, "best_estimator": automl.best_estimator})
        mets.append(mm)
        print(f"[flaml] {fold['name']}: WAPE={mm['WAPE']:.2f} best={automl.best_estimator} ({rt:.0f}s)", flush=True)
    return pd.DataFrame(preds), pd.DataFrame(mets)


def main():
    ds = pd.read_parquet(de_path("data", "processed", "decision_dataset_v1.parquet"))
    ds["date"] = pd.to_datetime(ds["date"])
    out = ensure_dir(de_path("evaluation", "open_source"))

    t0 = time.time()
    pr = run_prophet(ds)
    if len(pr):
        pr.to_csv(out / "prophet_origins.csv", index=False, encoding="utf-8-sig")
        mets = []
        for (crop, fold), g in pr.groupby(["crop", "fold"]):
            mm = metrics_table(g["actual_window_mean"].values, g["pred_window_mean"].values)
            mm.update({"model": "prophet", "crop": crop, "fold": fold})
            mets.append(mm)
        pm = pd.DataFrame(mets)
        pm.to_csv(out / "prophet_metrics.csv", index=False, encoding="utf-8-sig")
        agg = pm.groupby("model").agg(MAE=("MAE", "mean"), RMSE=("RMSE", "mean"),
                                      sMAPE=("sMAPE", "mean"), WAPE=("WAPE", "mean")).reset_index()
        print("[prophet]\n", agg.to_string(index=False), flush=True)
        upsert_benchmark([{"library": "prophet", "model": "prophet", "version": pkg_version("prophet"),
                           "city": "沈阳", "crop": c, "target": PRIMARY_TARGET,
                           "route": "univariate_walkforward",
                           "MAE": round(float(g["MAE"].mean()), 4), "RMSE": round(float(g["RMSE"].mean()), 4),
                           "sMAPE": round(float(g["sMAPE"].mean()), 4), "WAPE": round(float(g["WAPE"].mean()), 4),
                           "status": "BENCHMARK_ONLY" if float(g["WAPE"].mean()) > 6 else "BENCHMARK_ONLY",
                           "reason": "季节基线候选（trend+weekly+yearly+changepoints）；与 SF/自研同原点比较"}
                          for c, g in pm.groupby("crop")])
    print(f"[prophet] {time.time()-t0:.0f}s", flush=True)

    fp, fm = run_flaml(ds)
    if len(fm):
        fm.to_csv(out / "flaml_metrics.csv", index=False, encoding="utf-8-sig")
        print("[flaml]\n", fm.to_string(index=False), flush=True)
        upsert_benchmark([{"library": "flaml", "model": "flaml_pooled", "version": pkg_version("flaml"),
                           "city": "沈阳", "crop": "ALL(pooled)", "target": PRIMARY_TARGET,
                           "route": "pooled", "MAE": round(float(fm["MAE"].mean()), 4),
                           "RMSE": round(float(fm["RMSE"].mean()), 4),
                           "sMAPE": round(float(fm["sMAPE"].mean()), 4),
                           "WAPE": round(float(fm["WAPE"].mean()), 4),
                           "runtime_sec": round(float(fm["runtime_sec"].sum()), 1),
                           "status": "BENCHMARK_ONLY",
                           "reason": f"轻量 AutoML（time-based holdout）；best={fm['best_estimator'].iloc[0]}"}])


if __name__ == "__main__":
    main()