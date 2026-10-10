# -*- coding: utf-8 -*-
"""时间回测框架（expanding window，严格 point-in-time）。

禁止随机 split；每个 fold 的测试期都有明确的 train_end。
目标值不足（窗口不完整）的样本不参与训练与评估。
"""
from __future__ import annotations
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

FOLDS = [
    {"name": "fold1_test2024", "train_end": "2023-12-31",
     "test_start": "2024-01-01", "test_end": "2024-12-31"},
    {"name": "fold2_test2025", "train_end": "2024-12-31",
     "test_start": "2025-01-01", "test_end": "2025-12-31"},
    {"name": "fold3_test2026", "train_end": "2025-12-31",
     "test_start": "2026-01-01", "test_end": "2026-09-14"},
]

# [P0-C FIX] 前瞻标签的 purge / embargo 天数（按目标 horizon 设定）。
# 目标 target_mean_price_next_{h}d 使用 (t, t+h] 的价格；因此训练样本必须满足
#     t + h <= train_end
# 否则该训练标签在模型训练截止时点尚不可获得，且会用到测试期价格 → 标签泄漏。
# 测试样本同样要求标签窗口落在测试期内：t + h <= test_end。


def target_horizon_days(target: str) -> int:
    """从目标列名解析前瞻天数，如 target_mean_price_next_30d -> 30。"""
    try:
        return int(str(target).split("next_")[1].split("d")[0])
    except Exception:
        return 0


def fold_mask(df: pd.DataFrame, fold: Dict, purge_days: int = 0,
              embargo_test_tail: bool = True) -> Tuple[pd.Series, pd.Series]:
    """时间折掩码（含前瞻标签 purge）。

    purge_days = 0 时与历史行为一致（`train = date <= train_end`）。
    purge_days = h 时训练样本要求 label 窗口（t, t+h] 完全落在 train_end 之前，
    测试样本要求 label 窗口完全落在 test_end 之前。
    """
    d = pd.to_datetime(df["date"])
    tr_end = pd.Timestamp(fold["train_end"]) - pd.Timedelta(days=int(purge_days))
    train = d <= tr_end
    te_hi = pd.Timestamp(fold["test_end"])
    if embargo_test_tail and purge_days > 0:
        te_hi = te_hi - pd.Timedelta(days=int(purge_days))
    test = (d >= pd.Timestamp(fold["test_start"])) & (d <= te_hi)
    return train, test


def smape(y: np.ndarray, p: np.ndarray) -> float:
    denom = np.abs(y) + np.abs(p)
    m = denom > 0
    if m.sum() == 0:
        return np.nan
    return float(np.mean(2 * np.abs(y[m] - p[m]) / denom[m]) * 100)


def wape(y: np.ndarray, p: np.ndarray) -> float:
    s = np.abs(y).sum()
    if s == 0:
        return np.nan
    return float(np.abs(y - p).sum() / s * 100)


def metrics_table(y: np.ndarray, p: np.ndarray, anchor: np.ndarray | None = None) -> Dict[str, float]:
    m = np.isfinite(y) & np.isfinite(p)
    y, p = y[m], p[m]
    out = {
        "n": int(len(y)),
        "MAE": float(np.mean(np.abs(y - p))) if len(y) else np.nan,
        "RMSE": float(np.sqrt(np.mean((y - p) ** 2))) if len(y) else np.nan,
        "sMAPE": smape(y, p),
        "WAPE": wape(y, p),
        "bias": float(np.mean(p - y)) if len(y) else np.nan,
    }
    if anchor is not None:
        a = anchor[m]
        da = np.sign(p - a) == np.sign(y - a)
        out["direction_accuracy"] = float(np.mean(da)) if len(y) else np.nan
    return out


def prev_year_window_mean(ds: pd.DataFrame, days: int = 30) -> np.ndarray:
    """上一年同期窗口均值（基线：previous_year_same_period）。

    对 t：mean(price in (t-365-days, t-365])，严格早于 t。"""
    ds = ds.sort_values(["crop", "date"]).reset_index(drop=True)
    out = np.full(len(ds), np.nan)
    dts = pd.to_datetime(ds["date"])
    for crop, sub in ds.groupby("crop", sort=False):
        sub_d = pd.to_datetime(sub["date"]).values.astype("datetime64[D]")
        p = sub["price_per_kg"].values.astype(float)
        idx = sub.index.values
        for j, d in enumerate(sub_d):
            lo = np.searchsorted(sub_d, d - np.timedelta64(365 + days, "D"), side="right")
            hi = np.searchsorted(sub_d, d - np.timedelta64(365, "D"), side="right")
            if hi > lo:
                out[idx[j]] = p[lo:hi].mean()
    return out