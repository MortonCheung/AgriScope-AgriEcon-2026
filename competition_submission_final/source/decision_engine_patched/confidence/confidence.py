# -*- coding: utf-8 -*-
"""Phase 9: Confidence Engine（结果可信度，≠ 决策评分）。

Confidence 不改变风险数值，只回答「这个结果有多可信」。
组成部分：data / model / interval / feature / domain，全部来自真实回测与数据覆盖统计。
"""
from __future__ import annotations
from typing import Dict, Optional

import numpy as np

WEIGHTS = {"data": 0.22, "model": 0.23, "interval": 0.18, "feature": 0.13,
           "domain": 0.14, "drift": 0.10}


def _clip(x, lo=0.0, hi=100.0):
    return float(max(lo, min(hi, x)))


def data_score(n_obs: int, coverage_ratio: float, missing_rate: float,
               source_quality: str = "A") -> Dict:
    history = _clip(min(1.0, n_obs / 1000.0) * 100)
    cover = _clip(coverage_ratio * 100)
    missing = _clip((1 - missing_rate) * 100)
    src = {"A": 100, "B": 75, "C": 50, "D": 25}.get(source_quality, 50)
    return {"history_length_score": history, "coverage_score": cover,
            "missing_score": missing, "source_quality_score": float(src),
            "score": float(np.mean([history, cover, missing, src]))}


def model_score(model_wape: Optional[float], baseline_wape: Optional[float],
                fold_wape_std: Optional[float]) -> Dict:
    if model_wape is None or baseline_wape is None or not np.isfinite(model_wape):
        return {"score": 40.0, "note": "无模型回测指标（可能为无价格模型的降级城市）"}
    improvement = (baseline_wape - model_wape) / baseline_wape * 100 if baseline_wape else 0.0
    perf = _clip(50 + improvement * 5)   # 与基线持平=50；好 10% = 100；差 10% = 0
    stab = _clip(100 - (fold_wape_std or 0) * 5)
    return {"improvement_vs_baseline_pct": round(improvement, 2),
            "performance_score": perf, "stability_score": stab,
            "score": float(np.mean([perf, stab]))}


def interval_score(coverage: Optional[float], nominal: float = 0.80,
                   width_ratio: Optional[float] = None) -> Dict:
    if coverage is None or not np.isfinite(coverage):
        return {"score": 50.0, "note": "无区间校准结果"}
    gap = abs(coverage - nominal)
    sc = _clip(100 - gap * 200)   # gap 0 → 100；gap 0.1 → 80；gap 0.25 → 50
    return {"empirical_coverage": round(float(coverage), 4), "coverage_gap": round(gap, 4),
            "score": sc}


def feature_score(hri_coverage: Optional[float], climate_coverage: Optional[float]) -> Dict:
    vals = [v for v in [hri_coverage, climate_coverage] if v is not None and np.isfinite(v)]
    return {"hri_feature_coverage": hri_coverage, "climate_feature_coverage": climate_coverage,
            "score": float(np.mean(vals) * 100) if vals else 50.0}


def domain_score(harvest_within_data_support: bool, plan_days_beyond_data: int,
                 inputs_within_historical_range: bool, market_data_available: bool) -> Dict:
    sc = 100.0
    if not market_data_available:
        sc -= 35
    if not harvest_within_data_support:
        sc -= 20
    if plan_days_beyond_data > 365:
        sc -= 15
    elif plan_days_beyond_data > 180:
        sc -= 8
    if not inputs_within_historical_range:
        sc -= 15
    return {"score": _clip(sc),
            "harvest_within_data_support": harvest_within_data_support,
            "plan_days_beyond_data": plan_days_beyond_data,
            "inputs_within_historical_range": inputs_within_historical_range,
            "market_data_available": market_data_available}


def confidence_engine(parts: Dict[str, Dict], extra_note: str = "") -> Dict:
    total = sum(WEIGHTS[k] * parts[k]["score"] for k in WEIGHTS if k in parts)
    wsum = sum(WEIGHTS[k] for k in WEIGHTS if k in parts)
    total = total / wsum if wsum else np.nan
    grade = "A" if total >= 80 else "B" if total >= 65 else "C" if total >= 50 else "D"
    return {
        "score": round(float(total), 1),
        "grade": grade,
        "components": {k: round(parts[k]["score"], 1) for k in WEIGHTS},
        "details": parts,
        "weights": WEIGHTS,
        "note": extra_note or "confidence 仅表示结果可信度，不改变风险与收益数值",
    }