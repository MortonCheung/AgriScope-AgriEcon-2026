# -*- coding: utf-8 -*-
"""P0 开源评估 4/…: Optuna 超参数调优（时间序列验证目标，禁止随机 CV）。

objective（与模型选择原则一致）：
  对每个 crop：score_c = mean_fold(WAPE) + λ · std_fold(WAPE)
  总目标 = mean_c(score_c)          （λ 默认 0.5）
"""
from __future__ import annotations
from typing import Callable, Dict, List

import numpy as np
import optuna
import pandas as pd

from decision_engine.models.backtest import FOLDS, fold_mask
from decision_engine.models.train_price import MIN_TRAIN_ROWS

optuna.logging.set_verbosity(optuna.logging.WARNING)
LAMBDA = 0.5


def _fold_wapes(ds: pd.DataFrame, feature_cols: List[str], target: str,
                make_model: Callable, route: str) -> List[float]:
    """返回逐 fold 的 WAPE（per_crop 路由下先按 crop 平均）。"""
    d = ds.copy()
    fold_wapes = []
    for fold in FOLDS:
        tr_all, te_all = fold_mask(d, fold)
        if route == "pooled":
            tr = d[tr_all & d[target].notna()]
            te = d[te_all & d[target].notna()]
            if len(tr) < MIN_TRAIN_ROWS or not len(te):
                continue
            trf = tr[feature_cols].copy()
            tef = te[feature_cols].copy()
            trf["crop_cat"] = tr["crop"].astype("category").cat.codes
            tef["crop_cat"] = te["crop"].astype("category").cat.codes
            m = make_model()
            m.fit(trf, tr[target])
            p = m.predict(tef)
            y = te[target].values
            fold_wapes.append(float(np.abs(y - p).sum() / np.abs(y).sum() * 100))
        else:
            crop_wapes = []
            for crop, sub in d.groupby("crop"):
                tr = sub[tr_all.loc[sub.index] & sub[target].notna()]
                te = sub[te_all.loc[sub.index] & sub[target].notna()]
                if len(tr) < MIN_TRAIN_ROWS or not len(te):
                    continue
                m = make_model()
                m.fit(tr[feature_cols], tr[target])
                p = m.predict(te[feature_cols])
                y = te[target].values
                crop_wapes.append(float(np.abs(y - p).sum() / np.abs(y).sum() * 100))
            if crop_wapes:
                fold_wapes.append(float(np.mean(crop_wapes)))
    return fold_wapes


def objective_factory(ds, feature_cols, target, make_model, route):
    def objective(trial):
        model = make_model(trial)
        wapes = _fold_wapes(ds, feature_cols, target, lambda: model, route)
        if not wapes:
            return 1e6
        return float(np.mean(wapes) + LAMBDA * np.std(wapes))
    return objective


# ---------------------------------------------------------------- 各家族搜索空间
def space_histgb(trial):
    from sklearn.pipeline import Pipeline
    from sklearn.impute import SimpleImputer
    from sklearn.ensemble import HistGradientBoostingRegressor
    p = dict(
        learning_rate=trial.suggest_float("learning_rate", 0.02, 0.2, log=True),
        max_leaf_nodes=trial.suggest_int("max_leaf_nodes", 15, 63),
        max_iter=trial.suggest_int("max_iter", 150, 700, step=50),
        min_samples_leaf=trial.suggest_int("min_samples_leaf", 5, 40),
        l2_regularization=trial.suggest_float("l2_regularization", 1e-3, 1.0, log=True),
    )
    return Pipeline([("imp", SimpleImputer(strategy="median")),
                     ("m", HistGradientBoostingRegressor(random_state=42, **p))])


def space_extra_trees(trial):
    from sklearn.pipeline import Pipeline
    from sklearn.impute import SimpleImputer
    from sklearn.ensemble import ExtraTreesRegressor
    p = dict(
        n_estimators=trial.suggest_int("n_estimators", 200, 700, step=100),
        min_samples_leaf=trial.suggest_int("min_samples_leaf", 1, 10),
        max_features=trial.suggest_float("max_features", 0.2, 1.0),
    )
    return Pipeline([("imp", SimpleImputer(strategy="median")),
                     ("m", ExtraTreesRegressor(random_state=42, n_jobs=-1, **p))])


def space_random_forest(trial):
    from sklearn.pipeline import Pipeline
    from sklearn.impute import SimpleImputer
    from sklearn.ensemble import RandomForestRegressor
    p = dict(
        n_estimators=trial.suggest_int("n_estimators", 200, 700, step=100),
        min_samples_leaf=trial.suggest_int("min_samples_leaf", 1, 10),
        max_features=trial.suggest_float("max_features", 0.2, 1.0),
    )
    return Pipeline([("imp", SimpleImputer(strategy="median")),
                     ("m", RandomForestRegressor(random_state=42, n_jobs=-1, **p))])


def space_ridge(trial):
    from sklearn.pipeline import Pipeline
    from sklearn.impute import SimpleImputer
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import Ridge
    p = dict(alpha=trial.suggest_float("alpha", 1e-3, 300, log=True))
    return Pipeline([("imp", SimpleImputer(strategy="median")),
                     ("sc", StandardScaler()), ("m", Ridge(random_state=42, **p))])


def space_elasticnet(trial):
    from sklearn.pipeline import Pipeline
    from sklearn.impute import SimpleImputer
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import ElasticNet
    p = dict(alpha=trial.suggest_float("alpha", 1e-4, 10, log=True),
             l1_ratio=trial.suggest_float("l1_ratio", 0.05, 0.95))
    return Pipeline([("imp", SimpleImputer(strategy="median")),
                     ("sc", StandardScaler()),
                     ("m", ElasticNet(random_state=42, max_iter=20000, **p))])


def space_lightgbm(trial):
    from lightgbm import LGBMRegressor
    from sklearn.pipeline import Pipeline
    from sklearn.impute import SimpleImputer
    p = dict(
        n_estimators=trial.suggest_int("n_estimators", 200, 900, step=100),
        learning_rate=trial.suggest_float("learning_rate", 0.02, 0.2, log=True),
        num_leaves=trial.suggest_int("num_leaves", 15, 63),
        min_child_samples=trial.suggest_int("min_child_samples", 5, 40),
        subsample=trial.suggest_float("subsample", 0.6, 1.0),
        colsample_bytree=trial.suggest_float("colsample_bytree", 0.5, 1.0),
    )
    return Pipeline([("imp", SimpleImputer(strategy="median")),
                     ("m", LGBMRegressor(random_state=42, n_jobs=-1, verbose=-1, **p))])


def space_ebm(trial):
    from interpret.glassbox import ExplainableBoostingRegressor
    from sklearn.pipeline import Pipeline
    from sklearn.impute import SimpleImputer
    p = dict(
        max_rounds=trial.suggest_int("max_rounds", 500, 3000, step=250),
        interactions=trial.suggest_int("interactions", 0, 15),
        learning_rate=trial.suggest_float("learning_rate", 0.01, 0.08, log=True),
    )
    return Pipeline([("imp", SimpleImputer(strategy="median")),
                     ("m", ExplainableBoostingRegressor(random_state=42, **p))])


SPACES: Dict[str, Callable] = {
    "hist_gradient_boosting": space_histgb,
    "extra_trees": space_extra_trees,
    "random_forest": space_random_forest,
    "ridge": space_ridge,
    "elasticnet": space_elasticnet,
    "lightgbm": space_lightgbm,
    "ebm": space_ebm,
}


def tune(family: str, ds, feature_cols, target: str, route: str = "per_crop",
         n_trials: int = 30, seed: int = 42) -> dict:
    space = SPACES[family]
    study = optuna.create_study(direction="minimize",
                                sampler=optuna.samplers.TPESampler(seed=seed))
    study.optimize(objective_factory(ds, feature_cols, target, space, route),
                   n_trials=n_trials, show_progress_bar=False)
    return {"family": family, "route": route, "target": target,
            "best_value": study.best_value, "best_params": study.best_params,
            "n_trials": n_trials}