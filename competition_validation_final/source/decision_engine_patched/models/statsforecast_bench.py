# -*- coding: utf-8 -*-
"""P0 开源评估 1/…: Nixtla StatsForecast 统计模型基线（公平时间回测）。

公平性设计：
  - 与自研模型使用完全相同的回测窗口（同一 fold、同一评估原点集合）；
  - 评估原点 = 观测日（series_end 取观测日，step_size=7 → 所有 cutoff 均为观测日）;
  - 预测窗口 30 天，取窗口内日预测均值 与 dataset 的 target_mean_price_next_30d 对比；
  - refit=False（walk-forward，不重训参数，只用最新数据前推）——速度快，且对统计模型是标准做法；
    在报告中明确记录该语义。
"""
from __future__ import annotations
import time
from typing import Dict, List

import numpy as np
import pandas as pd

from decision_engine.models.backtest import FOLDS, metrics_table

STEPS_PER_YEAR = 75   # 覆盖约一年（75 窗口 × 5 天步长 + 30 天视野 ≈ 400 天）
STEP = 5              # 步长 5 天：30 ≡ 0 (mod 5) → cutoff 与 series_end 同为工作日，保证原点对齐观测日
H = 30


def build_daily_series(ds: pd.DataFrame, crop: str, end_date: pd.Timestamp) -> pd.DataFrame:
    """日频 ffill 序列（仅用 <=t 的观测；ffill 不会引入未来）。"""
    sub = ds[ds["crop"] == crop].sort_values("date")
    sub = sub[sub["date"] <= end_date]
    s = pd.Series(sub["price_per_kg"].values,
                  index=pd.to_datetime(sub["date"]))
    cal = pd.date_range(s.index.min(), end_date, freq="D")
    s = s.reindex(cal).ffill()
    return pd.DataFrame({"unique_id": f"沈阳_{crop}", "ds": s.index, "y": s.values})


def make_sf_models() -> Dict[str, object]:
    from statsforecast.models import (Naive, SeasonalNaive, AutoARIMA, AutoETS,
                                      AutoTheta, AutoCES)
    return {
        "sf_naive": Naive(),
        "sf_seasonal_naive": SeasonalNaive(season_length=7),
        "sf_auto_arima": AutoARIMA(season_length=7),
        "sf_auto_ets": AutoETS(season_length=7),
        "sf_auto_theta": AutoTheta(season_length=7),
        "sf_auto_ces": AutoCES(season_length=7),
    }


def run_sf_fold(ds: pd.DataFrame, crop: str, fold: dict, models: Dict[str, object],
                n_windows: int = STEPS_PER_YEAR) -> List[dict]:
    """单 (crop, fold) 的 walk-forward 预测。返回每个原点一行的记录。"""
    from statsforecast import StatsForecast

    series_end = pd.to_datetime(fold["test_end"])
    sub = ds[ds["crop"] == crop]
    obs = sub[sub["date"] <= series_end]["date"]
    series_end = pd.to_datetime(obs.max())          # 对齐到观测日
    train_series = build_daily_series(ds, crop, series_end)

    target_map = sub.set_index("date")["target_mean_price_next_30d"]
    rows = []
    for name, model in models.items():
        sf = StatsForecast(models=[model], freq="D", n_jobs=-1)
        t0 = time.time()
        try:
            cv = sf.cross_validation(df=train_series, h=H, step_size=STEP,
                                     n_windows=n_windows, refit=False)
        except Exception as e:
            rows.append({"crop": crop, "fold": fold["name"], "model": name,
                         "status": f"FAILED:{type(e).__name__}:{str(e)[:120]}"})
            continue
        rt = time.time() - t0
        pred_col = [c for c in cv.columns if c not in ("unique_id", "ds", "cutoff", "y")][0]
        t_start = pd.Timestamp(fold["test_start"])
        for cutoff, grp in cv.groupby("cutoff"):
            cutoff = pd.Timestamp(cutoff)
            if cutoff < t_start:            # 评估原点必须落在 fold 测试期内（公平性）
                continue
            if cutoff not in target_map.index:
                continue
            actual = target_map.loc[cutoff]
            if pd.isna(actual):
                continue
            pred_mean = float(np.nanmean(grp[pred_col].values))
            rows.append({"crop": crop, "fold": fold["name"], "model": name,
                         "origin_date": cutoff, "pred_window_mean": pred_mean,
                         "actual_window_mean": float(actual),
                         "n_pred_days": int(grp[pred_col].notna().sum()),
                         "runtime_sec": rt, "status": "OK"})
    return rows


def run_sf_benchmark(ds: pd.DataFrame, crops: List[str] | None = None) -> pd.DataFrame:
    models = make_sf_models()
    crops = crops or sorted(ds["crop"].unique())
    all_rows = []
    for crop in crops:
        for fold in FOLDS:
            t0 = time.time()
            rows = run_sf_fold(ds, crop, fold, models)
            all_rows.extend(rows)
            n_ok = sum(1 for r in rows if r.get("status") == "OK")
            print(f"[sf] {crop} {fold['name']}: rows={n_ok} ({time.time()-t0:.1f}s)")
    df = pd.DataFrame(all_rows)
    df = df[df["status"] == "OK"].copy()
    # 指标（per model, crop, fold）
    mets = []
    for (m, c, f), g in df.groupby(["model", "crop", "fold"]):
        mm = metrics_table(g["actual_window_mean"].values, g["pred_window_mean"].values)
        mm.update({"model": m, "crop": c, "fold": f, "runtime_sec": g["runtime_sec"].mean()})
        mets.append(mm)
    return df, pd.DataFrame(mets)


def compare_with_inhouse(sf_preds: pd.DataFrame, preds_path) -> pd.DataFrame:
    """在相同 (crop, fold, origin_date) 原点集合上重算自研模型指标。"""
    preds = pd.read_parquet(preds_path)
    preds = preds[preds["target"] == "target_mean_price_next_30d"].copy()
    preds["date"] = pd.to_datetime(preds["date"])
    origins = sf_preds[["crop", "fold", "origin_date"]].drop_duplicates()
    m = preds.merge(origins, left_on=["crop", "fold", "date"],
                    right_on=["crop", "fold", "origin_date"], how="inner")
    mets = []
    for (model, route, crop, fold), g in m.groupby(["model", "route", "crop", "fold"]):
        mm = metrics_table(g["actual"].values, g["prediction"].values,
                           anchor=g["anchor_price"].values)
        mm.update({"model": model, "route": route, "crop": crop, "fold": fold})
        mets.append(mm)
    return pd.DataFrame(mets)