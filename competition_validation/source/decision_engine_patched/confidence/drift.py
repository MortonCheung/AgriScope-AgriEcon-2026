# -*- coding: utf-8 -*-
"""数据漂移检查（Evidently 的轻量自研补充；用于 Confidence Engine）。

对每个作物：训练期（<= ref_end） vs 近期（最近 12 个月）关键特征的 KS 检验。
漂移份额高 → confidence 降低（不改变风险与收益数值）。
"""
from __future__ import annotations
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from scipy import stats

KEY_FEATURES = ["price_per_kg", "price_ma30", "volatility_30", "price_return_30",
                "price_momentum_30", "expanding_price_percentile", "volume_ma30"]


def drift_report(ds: pd.DataFrame, ref_end: str = "2023-12-31",
                 cur_start: str = "2025-09-01") -> pd.DataFrame:
    rows = []
    for crop, sub in ds.groupby("crop"):
        ref = sub[sub["date"] <= pd.Timestamp(ref_end)]
        cur = sub[sub["date"] >= pd.Timestamp(cur_start)]
        for f in KEY_FEATURES:
            if f not in sub.columns:
                continue
            a, b = ref[f].dropna(), cur[f].dropna()
            if len(a) < 50 or len(b) < 30:
                continue
            ks, p = stats.ks_2samp(a, b)
            rows.append({"crop": crop, "feature": f, "ks_stat": float(ks),
                         "p_value": float(p), "drifted": bool(p < 0.01 and ks > 0.15),
                         "ref_mean": float(a.mean()), "cur_mean": float(b.mean())})
    return pd.DataFrame(rows)


def drift_score(ds: pd.DataFrame, crop: str, ref_end: str = "2023-12-31",
                cur_start: str = "2025-09-01") -> Dict:
    rep = drift_report(ds[ds["crop"] == crop], ref_end, cur_start)
    if rep.empty:
        return {"drift_share": None, "score": 50.0, "note": "样本不足，无法判断漂移"}
    share = float(rep["drifted"].mean())
    score = float(np.clip(100 - share * 120, 0, 100))
    return {"drift_share": round(share, 3), "score": score,
            "drifted_features": rep.loc[rep["drifted"], "feature"].tolist(),
            "note": ("当前特征分布与训练期存在明显漂移 → 降低 confidence；不影响预测的风险数值"
                     if share > 0.2 else "特征分布与训练期一致")}