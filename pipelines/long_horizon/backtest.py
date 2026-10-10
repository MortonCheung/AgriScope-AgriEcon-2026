# -*- coding: utf-8 -*-
"""Phase 15（引擎部分）：长期 walk-forward 回测。

- 复用 Final 已验证的折定义（FOLDS / fold_mask）与指标函数，保证「同折同口径」；
- 行内 baseline 逐 row PIT；训练型 baseline 逐 fold 在 train 上拟合、test 上预测；
- 每个 (method, crop, fold, horizon) 输出 MAE/RMSE/sMAPE/WAPE/MASE/bias/direction_accuracy。
"""
from __future__ import annotations
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from decision_engine.models.backtest import FOLDS, fold_mask, metrics_table
from decision_engine.final.models import FINAL_FEATURE_COLS, _factories
from decision_engine.final.fcommon import ensure_dir

from .baselines import rowwise_baselines, ROWWISE_BASELINES, TRAINED_BASELINES, rename_trained
from .common import LH_ARTIFACTS

MIN_TRAIN_ROWS = 200


def _mase_denominator(sub_train: pd.DataFrame) -> float:
    """MASE 分母：train 段 anchor 价格的一阶观测差分平均绝对值（非季节 naive）。"""
    p = sub_train.sort_values("date")["price_per_kg"].values.astype(float)
    if len(p) < 2:
        return np.nan
    return float(np.mean(np.abs(np.diff(p))))


def _metrics(sub: pd.DataFrame, denom: float) -> Dict[str, float]:
    m = metrics_table(sub["actual"].values, sub["prediction"].values,
                      anchor=sub["anchor_price"].values)
    mae = m["MAE"]
    m["MASE"] = float(mae / denom) if (denom and np.isfinite(denom) and denom > 0) else np.nan
    return m


def evaluate_horizon(df: pd.DataFrame, target_col: str, horizon: int,
                     folds: List[dict] = FOLDS,
                     feature_cols: Optional[List[str]] = None,
                     factories: Optional[Dict] = None,
                     with_trained: bool = True,
                     rb_full: Optional[pd.DataFrame] = None) -> Dict[str, pd.DataFrame]:
    """对单一 target 列做长期回测；返回 {'preds': 长表, 'mets': 长表}。

    rb_full：可选，预先在**完整 df**上算好的行内 baseline（同一 horizon 可跨 target 复用；
    在完整 df 上计算才能让历史同月/去年同日的池子完整，避免尾部截断）。
    """
    feature_cols = feature_cols or FINAL_FEATURE_COLS
    d = df[df[target_col].notna()].copy()          # 只保留标签可用的 anchor
    d["_dt"] = pd.to_datetime(d["date"])

    # ---------- A. 行内 PIT baseline ----------
    rb = rb_full if rb_full is not None else rowwise_baselines(df, horizon)
    pred_rows = []
    for fold in folds:
        _, te_all = fold_mask(rb, fold)
        te = rb[te_all & rb[target_col].notna()]
        for method in ROWWISE_BASELINES:
            sub = te[te[method].notna()]
            for dt, crop, act, pr, anc in zip(sub["date"], sub["crop"], sub[target_col],
                                              sub[method], sub["price_per_kg"]):
                pred_rows.append({"date": dt, "crop": crop, "method": method,
                                  "family": "rowwise", "fold": fold["name"],
                                  "horizon": horizon, "target": target_col,
                                  "actual": float(act), "prediction": float(pr),
                                  "anchor_price": float(anc)})

    # ---------- B. 训练型 baseline ----------
    if with_trained:
        facs = factories if factories is not None else _factories()
        use = {rename_trained(k): v for k, v in facs.items() if rename_trained(k) in TRAINED_BASELINES}
        for fold in folds:
            tr_all, te_all = fold_mask(d, fold)
            for crop, sub in d.groupby("crop", sort=False):
                tr = sub[tr_all.loc[sub.index]]
                te = sub[te_all.loc[sub.index]]
                if len(tr) < MIN_TRAIN_ROWS or len(te) == 0:
                    continue
                tr = tr[tr[target_col].notna()]
                if len(tr) < MIN_TRAIN_ROWS:
                    continue
                for method, fac in use.items():
                    try:
                        model = fac()
                        model.fit(tr[feature_cols], tr[target_col])
                        p = model.predict(te[feature_cols])
                    except Exception:  # noqa: BLE001
                        continue
                    for dt, act, pr, anc in zip(te["date"], te[target_col], p, te["price_per_kg"]):
                        pred_rows.append({"date": dt, "crop": crop, "method": method,
                                          "family": "trained", "fold": fold["name"],
                                          "horizon": horizon, "target": target_col,
                                          "actual": float(act), "prediction": float(pr),
                                          "anchor_price": float(anc)})

    preds = pd.DataFrame(pred_rows)
    if not len(preds):
        return {"preds": preds, "mets": pd.DataFrame()}

    # ---------- C. 指标 ----------
    denoms = {}
    for fold in folds:
        tr_all, _ = fold_mask(d, fold)
        for crop, sub in d.groupby("crop", sort=False):
            tr = sub[tr_all.loc[sub.index] & sub[target_col].notna()]
            denoms[(crop, fold["name"])] = _mase_denominator(tr)
    met_rows = []
    for (method, family, crop, fold_), sub in preds.groupby(["method", "family", "crop", "fold"]):
        mm = _metrics(sub, denoms.get((crop, fold_), np.nan))
        mm.update({"method": method, "family": family, "crop": crop, "fold": fold_,
                   "horizon": horizon, "target": target_col})
        met_rows.append(mm)
    mets = pd.DataFrame(met_rows)
    return {"preds": preds, "mets": mets}


def summarize(mets: pd.DataFrame, metric: str = "WAPE") -> pd.DataFrame:
    """按 (method, crop, horizon) 聚合跨 fold 均值 / 波动 / 最差折。"""
    g = mets.groupby(["method", "family", "crop", "horizon"])
    out = g.agg(mean=("WAPE", "mean"), std=("WAPE", "std"), worst=("WAPE", "max"),
                mean_MAE=("MAE", "mean"), mean_sMAPE=("sMAPE", "mean"),
                mean_MASE=("MASE", "mean"), mean_bias=("bias", "mean"),
                mean_dir=("direction_accuracy", "mean"), folds=("WAPE", "count"),
                n_obs=("n", "sum")).reset_index()
    out["mean_WAPE"] = out["mean"]; out["std_WAPE"] = out["std"]
    out["worst_WAPE"] = out["worst"]
    out["score"] = out["mean_WAPE"] + 0.5 * out["std_WAPE"].fillna(0)
    return out


__all__ = ["evaluate_horizon", "summarize", "FOLDS", "ensure_dir", "LH_ARTIFACTS"]