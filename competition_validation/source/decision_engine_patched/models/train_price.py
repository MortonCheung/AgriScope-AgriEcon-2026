# -*- coding: utf-8 -*-
"""Phase 2: 价格模型训练与时间回测（沈阳 10 蔬菜）。

- Baseline：last value / MA7 / MA30 / seasonal median / previous year same period
- ML：Linear / Ridge / ElasticNet / RF / ExtraTrees / HistGB（+可选 XGB/LGBM/CatBoost/EBM）
- Route A（每作物独立） vs Route B（合并 + crop 类别）
- 全部使用同一 expanding-window 时间回测；禁止随机 split
- 评估：MAE / RMSE / sMAPE / WAPE / direction_accuracy / bias
"""
from __future__ import annotations
import time
from typing import Callable, Dict, List

import numpy as np
import pandas as pd

from decision_engine.common import de_path
from decision_engine.models.backtest import FOLDS, fold_mask, metrics_table, prev_year_window_mean

SEED = 42
MIN_TRAIN_ROWS = 200

OBS_LAGS = [1, 2, 3, 5, 7, 10, 14, 21, 30, 45, 60, 90]
CAL_LAGS = [7, 14, 30, 60, 90]

FEATURE_COLS: List[str] = (
    ["price_per_kg",
     "year", "month", "week", "day_of_year", "quarter",
     "sin_doy", "cos_doy", "sin_month", "cos_month"]
    + [f"price_lag_obs_{k}" for k in OBS_LAGS]
    + [f"price_lag_cal_{k}" for k in CAL_LAGS]
    + [f"price_ma{w}" for w in [7, 14, 30, 60, 90]]
    + ["price_median7", "price_median30"]
    + [f"price_std{w}" for w in [7, 30, 60, 90]]
    + [f"price_return_{w}" for w in [7, 14, 30, 60, 90]]
    + [f"price_momentum_{w}" for w in [30, 60, 90]]
    + ["continuous_rise_days", "continuous_fall_days"]
    + [f"rolling_slope_{w}" for w in [7, 30, 60]]
    + [f"volatility_{w}" for w in [7, 30, 60]]
    + ["rolling_max_30", "drawdown_30", "max_drawdown_90"]
    + ["expanding_price_percentile", "same_month_price_percentile", "same_season_price_percentile"]
    + ["seasonal_p10", "seasonal_p50", "seasonal_p90", "price_vs_seasonal_p50",
       "seasonal_sample_count", "seasonal_year_count", "seasonal_feature_available"]
    + ["volume_ma7", "volume_ma30", "volume_zscore", "volume_percentile",
       "volume_change_1d", "volume_change_7d"]
)

WEATHER_COLS: List[str] = [
    "tmax", "tmin", "tmean", "precip", "precip_7d", "precip_14d", "precip_30d",
    "heavy_rain_flag", "heavy_rain_days_30", "temp_anomaly", "precip_anomaly",
    "soil_moisture_0_7", "soil_moisture_7_28", "soil_moisture_28_100",
    "soil_moisture_percentile", "dry_spell_days",
    "temp_p90_flag", "temp_p95_flag", "rolling_heat_days_7",
]

TARGET_COLS: List[str] = [
    "target_price_t7", "target_price_t14", "target_price_t30",
    "target_mean_price_next_7d", "target_mean_price_next_14d", "target_mean_price_next_30d",
    "target_median_price_next_30d", "target_min_price_next_30d", "target_max_price_next_30d",
]

PRIMARY_TARGET = "target_mean_price_next_30d"


# ---------------------------------------------------------------- 模型族
def make_model_factories(seed: int = SEED, include_optional: bool = True) -> Dict[str, Callable]:
    from sklearn.pipeline import Pipeline
    from sklearn.impute import SimpleImputer
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LinearRegression, Ridge, ElasticNet
    from sklearn.ensemble import (RandomForestRegressor, ExtraTreesRegressor,
                                  HistGradientBoostingRegressor)

    def pipe(est, scale=False):
        steps = [("imp", SimpleImputer(strategy="median"))]
        if scale:
            steps.append(("sc", StandardScaler()))
        steps.append(("m", est))
        return Pipeline(steps)

    facs: Dict[str, Callable] = {
        "linear": lambda: pipe(LinearRegression()),
        "ridge": lambda: pipe(Ridge(alpha=1.0, random_state=seed), scale=True),
        "elasticnet": lambda: pipe(ElasticNet(alpha=0.01, l1_ratio=0.5, max_iter=10000, random_state=seed), scale=True),
        "random_forest": lambda: pipe(RandomForestRegressor(
            n_estimators=400, min_samples_leaf=3, n_jobs=-1, random_state=seed)),
        "extra_trees": lambda: pipe(ExtraTreesRegressor(
            n_estimators=400, min_samples_leaf=3, n_jobs=-1, random_state=seed)),
        "hist_gradient_boosting": lambda: pipe(HistGradientBoostingRegressor(
            max_iter=300, learning_rate=0.06, max_leaf_nodes=31, random_state=seed)),
    }
    if include_optional:
        try:
            from xgboost import XGBRegressor
            facs["xgboost"] = lambda: pipe(XGBRegressor(
                n_estimators=400, learning_rate=0.05, max_depth=5, subsample=0.8,
                colsample_bytree=0.8, random_state=seed, n_jobs=-1, verbosity=0))
        except Exception:
            pass
        try:
            from lightgbm import LGBMRegressor
            facs["lightgbm"] = lambda: pipe(LGBMRegressor(
                n_estimators=400, learning_rate=0.05, num_leaves=31,
                random_state=seed, n_jobs=-1, verbose=-1))
        except Exception:
            pass
        try:
            from catboost import CatBoostRegressor
            facs["catboost"] = lambda: pipe(CatBoostRegressor(
                iterations=400, learning_rate=0.05, depth=6, random_seed=seed, verbose=0))
        except Exception:
            pass
        try:
            from interpret.glassbox import ExplainableBoostingRegressor
            facs["ebm"] = lambda: pipe(ExplainableBoostingRegressor(
                random_state=seed, max_rounds=1000, interactions=6, outer_bags=4))
        except Exception:
            pass
    return facs


def make_tuned_factories(seed: int = SEED) -> Dict[str, Callable]:
    """从 models/registry/tuned_params.json（Optuna 结果，per_crop 路由）构建 tuned 模型族。"""
    import json
    p = de_path("models", "registry", "tuned_params.json")
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
    except Exception:
        return {}
    from sklearn.pipeline import Pipeline
    from sklearn.impute import SimpleImputer
    from sklearn.preprocessing import StandardScaler

    def pipe(est, scale=False):
        steps = [("imp", SimpleImputer(strategy="median"))]
        if scale:
            steps.append(("sc", StandardScaler()))
        steps.append(("m", est))
        return Pipeline(steps)

    out: Dict[str, Callable] = {}
    for r in data.get("results", []):
        fam, params = r.get("family"), r.get("best_params")
        if not params or r.get("route") != "per_crop":
            continue
        try:
            if fam == "hist_gradient_boosting":
                from sklearn.ensemble import HistGradientBoostingRegressor
                out["hist_gradient_boosting_tuned"] = (
                    lambda p=params: pipe(HistGradientBoostingRegressor(random_state=seed, **p)))
            elif fam == "extra_trees":
                from sklearn.ensemble import ExtraTreesRegressor
                out["extra_trees_tuned"] = (
                    lambda p=params: pipe(ExtraTreesRegressor(random_state=seed, n_jobs=-1, **p)))
            elif fam == "random_forest":
                from sklearn.ensemble import RandomForestRegressor
                out["random_forest_tuned"] = (
                    lambda p=params: pipe(RandomForestRegressor(random_state=seed, n_jobs=-1, **p)))
            elif fam == "ridge":
                from sklearn.linear_model import Ridge
                out["ridge_tuned"] = lambda p=params: pipe(Ridge(random_state=seed, **p), scale=True)
            elif fam == "elasticnet":
                from sklearn.linear_model import ElasticNet
                out["elasticnet_tuned"] = lambda p=params: pipe(
                    ElasticNet(random_state=seed, max_iter=20000, **p), scale=True)
            elif fam == "lightgbm":
                from lightgbm import LGBMRegressor
                out["lightgbm_tuned"] = lambda p=params: pipe(
                    LGBMRegressor(random_state=seed, n_jobs=-1, verbose=-1, **p))
            elif fam == "ebm":
                from interpret.glassbox import ExplainableBoostingRegressor
                out["ebm_tuned"] = lambda p=params: pipe(
                    ExplainableBoostingRegressor(random_state=seed, outer_bags=4, **p))
        except Exception:
            continue
    return out


# ---------------------------------------------------------------- 回测执行
def run_ml_backtest(
    ds: pd.DataFrame,
    feature_cols: List[str],
    target: str,
    factories: Dict[str, Callable],
    route: str = "per_crop",
    folds: List[dict] = FOLDS,
    seed: int = SEED,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """返回 (predictions, metrics)。predictions 长表；metrics 每 (model,crop,fold)。"""
    d = ds.copy()
    d["_fold_dt"] = pd.to_datetime(d["date"])
    crops = sorted(d["crop"].unique()) if route == "per_crop" else ["__ALL__"]
    pred_rows: List[dict] = []
    met_rows: List[dict] = []

    for fold in folds:
        tr_all, te_all = fold_mask(d, fold)
        for model_name, fac in factories.items():
            t0 = time.time()
            if route == "per_crop":
                for crop in crops:
                    sub = d[d["crop"] == crop]
                    tr = sub[tr_all.loc[sub.index] & sub[target].notna()]
                    te = sub[te_all.loc[sub.index] & sub[target].notna()]
                    if len(tr) < MIN_TRAIN_ROWS or len(te) == 0:
                        continue
                    m = fac()
                    m.fit(tr[feature_cols], tr[target])
                    p = m.predict(te[feature_cols])
                    for dt, act, pr, anc in zip(te["date"], te[target], p, te["price_per_kg"]):
                        pred_rows.append({"date": dt, "crop": crop, "model": model_name,
                                          "fold": fold["name"], "route": route, "target": target,
                                          "actual": float(act), "prediction": float(pr),
                                          "anchor_price": float(anc)})
            else:
                tr = d[tr_all & d[target].notna()].copy()
                te = d[te_all & d[target].notna()].copy()
                if len(tr) >= MIN_TRAIN_ROWS and len(te) > 0:
                    trf = tr[feature_cols].copy()
                    tef = te[feature_cols].copy()
                    trf["crop_cat"] = tr["crop"].astype("category").cat.codes
                    tef["crop_cat"] = te["crop"].astype("category").cat.codes
                    m = fac()
                    m.fit(trf, tr[target])
                    p = m.predict(tef)
                    for dt, crop, act, pr, anc in zip(te["date"], te["crop"], te[target], p, te["price_per_kg"]):
                        pred_rows.append({"date": dt, "crop": crop, "model": model_name,
                                          "fold": fold["name"], "route": route, "target": target,
                                          "actual": float(act), "prediction": float(pr),
                                          "anchor_price": float(anc)})
            rt = time.time() - t0
            met_rows.append({"model": model_name, "route": route, "fold": fold["name"],
                             "target": target, "fold_runtime_sec": rt})

    preds = pd.DataFrame(pred_rows).dropna(how="all").reset_index(drop=True)
    # 逐 model×crop×fold 指标
    mets = []
    if len(preds):
        for (model, route_, crop, fold_), sub in preds.groupby(["model", "route", "crop", "fold"]):
            mm = metrics_table(sub["actual"].values, sub["prediction"].values,
                               anchor=sub["anchor_price"].values)
            mm.update({"model": model, "route": route_, "crop": crop, "fold": fold_,
                       "target": target})
            mets.append(mm)
    mets = pd.DataFrame(mets)
    rt = pd.DataFrame(met_rows)
    return preds, mets, rt


def baseline_predictions(ds: pd.DataFrame, target: str, folds: List[dict] = FOLDS) -> pd.DataFrame:
    """5 个基线（不需要训练，均为 point-in-time 派生列/窗口）。"""
    d = ds.copy()
    d["_fold_dt"] = pd.to_datetime(d["date"])
    d["baseline_last_value"] = d["price_per_kg"]
    d["baseline_rolling_mean_7"] = d["price_ma7"]
    d["baseline_rolling_mean_30"] = d["price_ma30"]
    d["baseline_seasonal_median"] = d["seasonal_p50"]
    days = int(target.split("next_")[1].split("d")[0]) if "next_" in target else 30
    d["baseline_previous_year_same_period"] = prev_year_window_mean(ds, days=days)
    rows = []
    for fold in folds:
        _, te_all = fold_mask(d, fold)
        te = d[te_all & d[target].notna()]
        for model in [c for c in d.columns if c.startswith("baseline_")]:
            for dt, crop, act, pr, anc in zip(te["date"], te["crop"], te[target], te[model], te["price_per_kg"]):
                rows.append({"date": dt, "crop": crop, "model": model,
                             "fold": fold["name"], "route": "baseline", "target": target,
                             "actual": float(act), "prediction": float(pr) if pd.notna(pr) else np.nan,
                             "anchor_price": float(anc)})
    return pd.DataFrame(rows)


def baseline_metrics(preds: pd.DataFrame) -> pd.DataFrame:
    mets = []
    for (model, crop, fold_), sub in preds.groupby(["model", "crop", "fold"]):
        mm = metrics_table(sub["actual"].values, sub["prediction"].values,
                           anchor=sub["anchor_price"].values)
        mm.update({"model": model, "route": "baseline", "crop": crop, "fold": fold_,
                   "target": sub["target"].iloc[0]})
        mets.append(mm)
    return pd.DataFrame(mets)


def summarize_metrics(mets: pd.DataFrame, metric: str = "WAPE") -> pd.DataFrame:
    """按 (route, model, crop, target) 汇总跨 fold 均值与波动。"""
    g = mets.groupby(["route", "model", "crop", "target"])
    out = g.agg(mean_WAPE=("WAPE", "mean"), std_WAPE=("WAPE", "std"),
                mean_MAE=("MAE", "mean"), mean_RMSE=("RMSE", "mean"),
                mean_sMAPE=("sMAPE", "mean"), mean_dir=("direction_accuracy", "mean"),
                mean_bias=("bias", "mean"), folds=("WAPE", "count")).reset_index()
    out["score"] = out["mean_WAPE"] + 0.5 * out["std_WAPE"].fillna(0)
    return out.sort_values(["crop", "score"])


def select_final_models(summary: pd.DataFrame, target: str = PRIMARY_TARGET) -> pd.DataFrame:
    """每作物选择 mean+λ·std 最小的方案（ML 与基线同池竞争）。"""
    s = summary[summary["target"] == target]
    best = s.sort_values("score").groupby("crop", as_index=False).first()
    base = (s[s["route"] == "baseline"].sort_values("score")
            .groupby("crop", as_index=False).first()
            .rename(columns={"model": "best_baseline", "mean_WAPE": "baseline_mean_WAPE",
                             "mean_MAE": "baseline_mean_MAE", "score": "baseline_score"})
            [["crop", "best_baseline", "baseline_mean_WAPE", "baseline_mean_MAE", "baseline_score"]])
    best = best.merge(base, on="crop", how="left")
    best["improvement_vs_baseline_pct"] = (best["baseline_mean_WAPE"] - best["mean_WAPE"]) / best["baseline_mean_WAPE"] * 100
    best["beats_baseline"] = best["mean_WAPE"] < best["baseline_mean_WAPE"]
    return best.sort_values("crop")