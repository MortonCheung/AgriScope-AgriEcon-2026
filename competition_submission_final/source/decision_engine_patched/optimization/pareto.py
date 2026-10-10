# -*- coding: utf-8 -*-
"""Phase 4 / §12: Pareto 前沿（多目标，不输出"唯一最优"）。

目标（6 个）：
  最大化 expected_profit(profit_baseline)、downside_profit(profit_pessimistic)、confidence
  最小化 HRI、market_risk、climate_risk
"""
from __future__ import annotations
from typing import Dict, List

import numpy as np
import pandas as pd

OBJECTIVES = [
    ("profit_baseline", "max"), ("profit_pessimistic", "max"), ("confidence_score", "max"),
    ("HRI", "min"), ("market_risk", "min"), ("climate_risk", "min"),
]


def _matrix(df: pd.DataFrame) -> np.ndarray:
    cols = []
    for c, direction in OBJECTIVES:
        v = pd.to_numeric(df[c], errors="coerce").fillna(df[c].median() if df[c].notna().any() else 0.0)
        if direction == "min":
            v = -v
        cols.append(v.values.astype(float))
    return np.column_stack(cols)


def pareto_mask(df: pd.DataFrame, tol: float = 1e-9) -> np.ndarray:
    """返回布尔掩码：非支配解（在所有目标上都不劣，且至少一个目标更优）。"""
    if not len(df):
        return np.zeros(0, dtype=bool)
    M = _matrix(df)
    n = len(M)
    mask = np.ones(n, dtype=bool)
    for i in range(n):
        if not mask[i]:
            continue
        dominated = np.all(M >= M[i] - tol, axis=1) & np.any(M > M[i] + tol, axis=1)
        if dominated.any():
            mask[i] = False
    return mask


def compute_pareto_frontier(df: pd.DataFrame, max_points: int = 60) -> pd.DataFrame:
    """Pareto 前沿（去重 + 限幅，保持多样性），并标注每个解的风格。"""
    m = pareto_mask(df)
    front = df[m].copy()
    if not len(front):
        return front
    front["_dom_key"] = (front["crop"].astype(str) + "|" +
                         pd.to_datetime(front["harvest_date"]).dt.to_period("M").astype(str))
    front = front.sort_values("profit_baseline", ascending=False).drop_duplicates("_dom_key")
    if len(front) > max_points:
        idx = np.linspace(0, len(front) - 1, max_points).round().astype(int)
        front = front.iloc[idx]

    def _style(r) -> str:
        if r["profit_baseline"] >= front["profit_baseline"].quantile(0.85):
            return "best_return"
        if r["HRI"] <= front["HRI"].quantile(0.25) and r["market_risk"] <= front["market_risk"].quantile(0.35):
            return "lowest_risk"
        if r["profit_pessimistic"] >= front["profit_pessimistic"].quantile(0.85):
            return "best_downside"
        return "balanced"

    front["pareto_style"] = front.apply(_style, axis=1)
    return front.drop(columns=["_dom_key"]).reset_index(drop=True)


def pareto_summary(front: pd.DataFrame) -> pd.DataFrame:
    if not len(front):
        return pd.DataFrame()
    return (front.groupby("pareto_style")
            .agg(n=("candidate_id", "count"),
                 profit_baseline_med=("profit_baseline", "median"),
                 downside_med=("profit_pessimistic", "median"),
                 HRI_med=("HRI", "median"), market_risk_med=("market_risk", "median"),
                 climate_med=("climate_risk", "median"), conf_med=("confidence_score", "median"))
            .reset_index())