# -*- coding: utf-8 -*-
"""Phase 8：长期 baseline 集合（正式对照集）。

两类：
  A. 行内 PIT baseline（无需训练，逐 anchor 只用其自身过去）：
       b_last_value            当前价（随机游走，长期点值的天然对手）
       b_seasonal_naive_365    去年同日附近最近一次观测
       b_same_season_mean      历史同月（严格更早日期）均值
       b_same_season_median    历史同月（严格更早日期）中位数
       b_drift_trend90         近 90 观测对数价格 OLS 斜率外推（含漂移随机游走）
  B. 训练型 baseline（逐 fold 在 train 上拟合，route=per_crop）：
       m_linear / m_extra_trees / m_elasticnet   复用已验证的模型工厂

所有 baseline 均为 point-in-time；h 依赖项（drift）按 horizon 单独生成。
"""
from __future__ import annotations
from typing import Callable, Dict, List

import numpy as np
import pandas as pd

ROWWISE_BASELINES = ["b_last_value", "b_seasonal_naive_365", "b_same_season_mean",
                     "b_same_season_median", "b_drift_trend90"]
TRAINED_BASELINES = ["m_linear", "m_extra_trees", "m_elasticnet", "m_catboost"]

DRIFT_WINDOW = 90
MIN_SEASON_SAMPLES = 5


def rowwise_baselines(df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """返回带预测列的副本（列名 = baseline 名）。严格 point-in-time。"""
    d = df.sort_values(["crop", "date"]).reset_index(drop=True).copy()
    out = {m: np.full(len(d), np.nan) for m in ROWWISE_BASELINES}
    for _crop, sub in d.groupby("crop", sort=False):
        sub = sub.sort_values("date")
        dates = sub["date"].values.astype("datetime64[D]")
        px = sub["price_per_kg"].values.astype(float)
        idx = sub.index.values
        n = len(sub)
        month_pool: Dict[int, List[float]] = {}
        logp = np.log(np.where(px > 0, px, np.nan))
        for j in range(n):
            t = dates[j]
            # A1 当前价
            out["b_last_value"][idx[j]] = px[j]
            # A2 去年同日（<= t-365 的最近观测）
            p365 = np.searchsorted(dates, t - np.timedelta64(365, "D"), side="right") - 1
            if p365 >= 0:
                out["b_seasonal_naive_365"][idx[j]] = px[p365]
            # A3/A4 历史同月（严格更早日期）
            m = pd.Timestamp(t).month
            pool = month_pool.setdefault(m, [])
            if len(pool) >= MIN_SEASON_SAMPLES:
                arr = np.asarray(pool, dtype=float)
                out["b_same_season_mean"][idx[j]] = float(arr.mean())
                out["b_same_season_median"][idx[j]] = float(np.median(arr))
            pool.append(px[j])
            # A5 近 90 观测对数价漂移外推
            lo = max(0, j - DRIFT_WINDOW + 1)
            if j - lo + 1 >= DRIFT_WINDOW:
                y = logp[lo:j + 1]
                x = (dates[lo:j + 1] - t).astype("timedelta64[D]").astype(float)
                if np.isfinite(y).all():
                    slope = float(np.polyfit(x, y, 1)[0])       # 每天对数收益
                    out["b_drift_trend90"][idx[j]] = float(px[j] * np.exp(slope * horizon))
    for k, v in out.items():
        d[k] = v
    return d


_RENAME = {"linear": "m_linear", "extra_trees": "m_extra_trees",
           "elasticnet": "m_elasticnet", "catboost": "m_catboost"}


def trained_factories() -> Dict[str, Callable]:
    """复用 decision_engine 的模型工厂（linear / extra_trees / elasticnet / catboost）。"""
    from decision_engine.models.train_price import make_model_factories
    allf = make_model_factories(include_optional=True)
    return {m: allf[m] for m in _RENAME if m in allf}


def rename_trained(name: str) -> str:
    return _RENAME.get(name, name)


if __name__ == "__main__":
    from .common import load_frozen_dataset
    base = load_frozen_dataset()
    r = rowwise_baselines(base, 90)
    print(r[ROWWISE_BASELINES].notna().mean().round(3).to_string())