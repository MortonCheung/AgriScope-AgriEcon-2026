# -*- coding: utf-8 -*-
"""Phase 6 / §21-§24: 组合风险聚合（透明，不强行套 Markowitz）。

组合风险 = 面积加权平均 + 集中度惩罚(HHI) + 相关性惩罚（历史收益相关）。
明确边界：**不声称"组合一定降低风险"**，只根据历史相关性与现有风险指标判断。
"""
from __future__ import annotations
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from decision_engine.common import de_path


def crop_return_correlation(city: str, crops: List[str], window: int = 60,
                            as_of: Optional[str] = None,
                            price_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """作物间历史价格收益相关性（past-only）。

    Final 生产路径：调用方传入 `price_df`（来自 final_v1 快照），**不读取 v1**；
    未传入时才回退到旧路径（仅供 LEGACY pipeline / 旧验收使用）。
    """
    if price_df is not None:
        ds = price_df[["date", "crop", "price_per_kg"]].copy()
        ds["date"] = pd.to_datetime(ds["date"])
    elif city == "沈阳":
        ds = pd.read_parquet(de_path("data", "processed", "decision_dataset_v1.parquet"),
                             columns=["date", "crop", "price_per_kg"])
        ds["date"] = pd.to_datetime(ds["date"])
    else:
        p = de_path("data", "features", f"regional_{city}.parquet")
        if not p.exists():
            return pd.DataFrame()
        ds = pd.read_parquet(p, columns=["date", "crop", "price_per_kg"])
        ds["date"] = pd.to_datetime(ds["date"])
    if as_of is not None:
        ds = ds[ds["date"] <= pd.Timestamp(as_of)]
    ds = ds[ds["crop"].isin(crops)]
    piv = ds.pivot_table(index="date", columns="crop", values="price_per_kg").sort_index()
    ret = piv.pct_change().tail(250)                    # 最近约一年交易日
    return ret.corr(min_periods=window)


def portfolio_metrics(alloc: Dict[str, float], crop_rows: Dict[str, Dict],
                      corr: Optional[pd.DataFrame] = None) -> Dict:
    """alloc: crop → area_mu；crop_rows: crop → 该作物被选方案的评估行（含风险与利润）。"""
    total_area = sum(alloc.values())
    if total_area <= 0:
        return {"total_area_mu": 0.0}
    shares = {c: a / total_area for c, a in alloc.items() if a > 0}
    hhi = float(sum(s ** 2 for s in shares.values()))
    n = len(shares)
    hhi_norm = float(np.clip((hhi - 1 / n) / (1 - 1 / n), 0, 1)) if n > 1 else 1.0

    def _wavg(key):
        vals = [(shares[c], crop_rows[c].get(key)) for c in shares
                if crop_rows[c].get(key) is not None and np.isfinite(crop_rows[c].get(key))]
        if not vals:
            return None
        wsum = sum(w for w, _ in vals)
        return float(sum(w * v for w, v in vals) / wsum) if wsum else None

    # 相关性惩罚：面积份额加权平均成对相关
    avg_corr = None
    if corr is not None and len(corr) and len(shares) > 1:
        cs = [c for c in shares if c in corr.index and c in corr.columns]
        if len(cs) > 1:
            pairs = [(shares[a] * shares[b], corr.loc[a, b]) for i, a in enumerate(cs) for b in cs[i + 1:]
                     if np.isfinite(corr.loc[a, b])]
            if pairs:
                wsum = sum(w for w, _ in pairs)
                avg_corr = float(sum(w * r for w, r in pairs) / wsum) if wsum else None
    corr_penalty = 0.25 * (avg_corr or 0) * hhi_norm
    conc_penalty = 0.25 * hhi_norm

    profit_base = sum(a * crop_rows[c]["profit_baseline"] / max(crop_rows[c]["area_mu"], 1e-9)
                      for c, a in alloc.items() if a > 0)
    profit_pess = sum(a * crop_rows[c]["profit_pessimistic"] / max(crop_rows[c]["area_mu"], 1e-9)
                      for c, a in alloc.items() if a > 0)
    profit_opt = sum(a * crop_rows[c]["profit_optimistic"] / max(crop_rows[c]["area_mu"], 1e-9)
                     for c, a in alloc.items() if a > 0)
    cost = sum(a * crop_rows[c]["cost_per_mu"] for c, a in alloc.items() if a > 0)

    hri = _wavg("HRI"); mr = _wavg("market_risk"); cl = _wavg("climate_risk")
    conf = _wavg("confidence_score")
    return {
        "total_area_mu": round(total_area, 2),
        "idle_area_mu": None,          # 由调用方补
        "shares": {c: round(s, 4) for c, s in shares.items()},
        "hhi": round(hhi, 4), "hhi_normalized": round(hhi_norm, 4),
        "avg_pairwise_corr": None if avg_corr is None else round(avg_corr, 4),
        "concentration_penalty": round(conc_penalty, 4),
        "correlation_penalty": round(corr_penalty, 4),
        "portfolio_profit_baseline": round(profit_base, 2),
        "portfolio_profit_pessimistic": round(profit_pess, 2),
        "portfolio_profit_optimistic": round(profit_opt, 2),
        "portfolio_cost": round(cost, 2),
        "portfolio_HRI": None if hri is None else round(hri, 2),
        "portfolio_market_risk": None if mr is None else round(mr, 2),
        "portfolio_climate_risk": None if cl is None else round(cl, 2),
        "portfolio_confidence": None if conf is None else round(conf, 2),
        "risk_adjusted_market": None if mr is None else round(mr * (1 + conc_penalty + corr_penalty), 2),
        "note": "组合风险 = 面积加权 + 集中度惩罚 + 相关性惩罚；不假设组合必然降低风险，"
                "也不假设单户面积会影响市场价格",
    }


def portfolio_utility(pm: Dict, budget: float, risk_preference: str = "balanced") -> float:
    """组合效用（同一效用结构，透明可解释）。"""
    if not pm or pm.get("total_area_mu", 0) <= 0:
        return -np.inf
    from decision_engine.optimization.utility import PREFERENCE_WEIGHTS
    w = PREFERENCE_WEIGHTS.get(risk_preference, PREFERENCE_WEIGHTS["balanced"])
    cost = max(pm["portfolio_cost"], 1e-9)
    roi = pm["portfolio_profit_baseline"] / cost
    roi_p = pm["portfolio_profit_pessimistic"] / cost
    mr = (pm["risk_adjusted_market"] or 50) / 100
    hri = (pm["portfolio_HRI"] or 50) / 100
    cl = (pm["portfolio_climate_risk"] or 50) / 100
    conf = (pm["portfolio_confidence"] or 60) / 100
    # 用 tanh 压缩 ROI，避免尺度失衡
    ret_u = float(np.tanh(roi))       # (-1,1)
    down_u = float(np.tanh(roi_p))
    return float(w["ret"] * ret_u + w["down"] * down_u + w["conf"] * conf
                 - w["market"] * mr - w["herding"] * hri - w["climate"] * cl)