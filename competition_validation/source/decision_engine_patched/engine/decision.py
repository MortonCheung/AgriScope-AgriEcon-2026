# -*- coding: utf-8 -*-
"""Phase 10: 综合 Decision Score（0-100）+ 风险偏好 + 敏感性。

- 风险偏好只影响权重（Utility），不改变客观风险数值；
- 三种偏好同时计算，输出 score_stability（排名/分数对偏好与权重的敏感性）；
- decision_score ≠ confidence_score（差方案也可能高置信）。
"""
from __future__ import annotations
from typing import Dict, List

import numpy as np

WEIGHTS = {
    "conservative": {"expected_return": 0.20, "downside": 0.30, "market_risk": 0.20,
                     "herding": 0.15, "climate": 0.15},
    "balanced":     {"expected_return": 0.35, "downside": 0.20, "market_risk": 0.20,
                     "herding": 0.15, "climate": 0.10},
    "aggressive":   {"expected_return": 0.50, "downside": 0.15, "market_risk": 0.15,
                     "herding": 0.10, "climate": 0.10},
}


def _scale_roi(roi: float) -> float:
    """ROI → 0-100：-30% 及以下=0；+50% 及以上=100（线性）。"""
    return float(np.clip((roi + 0.30) / 0.80 * 100, 0, 100))


def decision_score(roi_baseline: float, roi_pessimistic: float,
                   market_risk: float, herding_risk: float, climate_risk: float,
                   risk_preference: str = "balanced") -> Dict:
    comps = {
        "expected_return": _scale_roi(roi_baseline),
        "downside": _scale_roi(roi_pessimistic),
        "market_risk": 100 - float(np.clip(market_risk, 0, 100)),
        "herding": 100 - float(np.clip(herding_risk, 0, 100)),
        "climate": 100 - float(np.clip(climate_risk, 0, 100)),
    }
    scores = {pref: float(sum(w[k] * comps[k] for k in w)) for pref, w in WEIGHTS.items()}
    pref = risk_preference if risk_preference in WEIGHTS else "balanced"
    s = scores[pref]
    grade = "A" if s >= 80 else "B" if s >= 65 else "C" if s >= 50 else "D"
    all_vals = list(scores.values())
    stability = 1 - (max(all_vals) - min(all_vals)) / 100.0
    return {
        "score": round(s, 1),
        "grade": grade,
        "risk_preference": pref,
        "components": {k: round(v, 1) for k, v in comps.items()},
        "weights_used": WEIGHTS[pref],
        "scores_by_preference": {k: round(v, 1) for k, v in scores.items()},
        "score_stability": round(float(stability), 3),
        "stability_note": ("偏好切换会显著改变评分，结论对风险偏好敏感"
                           if stability < 0.85 else "评分对风险偏好不敏感（稳定）"),
    }


def compare_scenarios(rows: List[Dict]) -> Dict:
    """多方案比较：按 score 排序 + 排名稳定性检查。"""
    import pandas as pd
    df = pd.DataFrame(rows)
    if df.empty:
        return {"ranking": [], "note": "无方案"}
    df = df.sort_values("score", ascending=False).reset_index(drop=True)
    # 各偏好下的排名
    rank_cols = [c for c in df.columns if c.startswith("score_")]
    ranks = {c: df[c].rank(ascending=False) for c in rank_cols}
    rank_stability = {}
    for c, r in ranks.items():
        rank_stability[c] = float(r.std())
    return {
        "ranking": df.to_dict(orient="records"),
        "rank_std_by_preference": rank_stability,
        "note": "rank_std 越小排名越稳定；>1 说明结论对风险偏好敏感",
    }