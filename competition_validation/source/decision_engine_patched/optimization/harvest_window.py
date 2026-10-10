# -*- coding: utf-8 -*-
"""Phase 5 / §16 §17 §49 §50: 上市窗口优化 + 面积优化 + 盈亏平衡 v2 + 价格×亩产矩阵。

§17 关键约束：**不许利用预测噪音择时**。
  仅当两个窗口的综合效果差异 **显著超过模型误差 / 情景区间** 时，才区分窗口；
  否则合并为区间（如「7 月上中旬」/「7 月 5 日—7 月 19 日」）。
"""
from __future__ import annotations
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from decision_engine.common import de_path
from decision_engine.optimization import utility as U
from decision_engine.optimization import ranking as R


# ---------------------------------------------------------------- 模型误差 → 显著性阈值
def model_error_threshold(crop: str, revenue: float, area_mu: float,
                          yield_per_mu: float, wape_map: Dict[str, float] | None = None) -> Dict:
    """由回测 WAPE 与区间宽度推导"材料差异"阈值（元）。

    Final 生产路径：调用方传入 `wape_map`（来自 Final price_model_selection.csv），不读 v1；
    未传入时回退旧路径（仅供 LEGACY pipeline / 旧验收）。
    """
    thr = {"wape_pct": None, "profit_threshold": None, "price_band": None}
    wape = None
    if wape_map is not None:
        if crop in wape_map:
            wape = float(wape_map[crop])
            thr["wape_pct"] = wape
    else:
        p = de_path("evaluation", "metrics", "model_selection.csv")
        if p.exists():
            sel = pd.read_csv(p)
            row = sel[sel["crop"] == crop]
            if len(row):
                wape = float(row.iloc[0]["mean_WAPE"])
                thr["wape_pct"] = wape
    # 利润阈值 = WAPE × 收入（一个模型误差量级），至少 3% 收入
    w = (wape / 100.0) if wape else 0.06
    thr["profit_threshold"] = round(max(w, 0.03) * revenue, 2)
    return thr


def _material(profit_a: float, profit_b: float, thr: Dict, util_a: float, util_b: float) -> bool:
    """差异是否"材料级"：利润差超过模型误差量级，或效用差 > 0.02。"""
    pt = thr.get("profit_threshold") or 0.0
    return (abs(profit_a - profit_b) > pt) or (abs(util_a - util_b) > 0.02)


def optimize_harvest_window(city: str, crop: str, eval_df: pd.DataFrame,
                            risk_preference: str = "balanced",
                            max_acceptable_loss: Optional[float] = None,
                            wape_map: Dict[str, float] | None = None) -> Dict:
    """给定 city×crop 的已评估候选（含多上市窗口），输出推荐/备选/回避窗口。

    eval_df 需包含同一 crop 的多个 (plant_date, harvest_date, area_mu) 行（已评估）。
    """
    sub = eval_df[(eval_df["crop"] == crop) & (eval_df["evaluable"])].copy()
    if not len(sub):
        return {"crop": crop, "status": "no_evaluable_candidate"}
    sub = U.utility_report(R.collapse_area_variants(sub, max_acceptable_loss, ))
    sub = sub.sort_values("utility_score", ascending=False).reset_index(drop=True)
    best = sub.iloc[0]
    thr = model_error_threshold(crop, float(best["profit_baseline"]), float(best["area_mu"]),
                               float(best["expected_yield_per_mu"]), wape_map=wape_map)

    # 与最优"材料等价"的窗口 → 合并为同一推荐区间
    equiv = [r for _, r in sub.iterrows()
             if not _material(float(r["profit_baseline"]), float(best["profit_baseline"]),
                              thr, float(r["utility_score"]), float(best["utility_score"]))]
    starts = sorted(pd.Timestamp(r["harvest_start"] if "harvest_start" in r else r["harvest_date"]) for r in equiv)
    ends = sorted(pd.Timestamp(r["harvest_date"]) for r in equiv)
    recommended = {"harvest_window": f"{starts[0].date()} ~ {ends[-1].date()}",
                   "n_equivalent_windows": len(equiv),
                   "area_mu": float(best["area_mu"]),
                   "crop": crop,
                   "profit_baseline": float(best["profit_baseline"]),
                   "profit_pessimistic": float(best["profit_pessimistic"]),
                   "price_mid": float(best["price_mid"]),
                   "HRI": float(best["HRI"]), "market_risk": float(best["market_risk"]),
                   "climate_risk": float(best["climate_risk"]),
                   "utility_score": float(best["utility_score"]),
                   "decision_score": float(best["decision_score"]),
                   "confidence": float(best["confidence_score"]),
                   "is_merged_range": len(equiv) > 1}
    alternatives = [{"harvest_window": f"{pd.Timestamp(r['harvest_date']).date()}",
                     "utility_score": round(float(r["utility_score"]), 4),
                     "profit_baseline": float(r["profit_baseline"]),
                     "delta_profit_vs_best": round(float(r["profit_baseline"] - best["profit_baseline"]), 2),
                     "material_difference": _material(float(r["profit_baseline"]), float(best["profit_baseline"]),
                                                      thr, float(r["utility_score"]), float(best["utility_score"]))}
                    for _, r in sub.iloc[1:4].iterrows()]
    avoid = [{"harvest_window": f"{pd.Timestamp(r['harvest_date']).date()}",
              "utility_score": round(float(r["utility_score"]), 4),
              "reason": "效用最低窗口（含最差下行/风险组合）"}
             for _, r in sub.tail(2).iterrows()]
    return {"crop": crop, "city": city, "status": "ok",
            "recommended_window": recommended, "alternative_windows": alternatives,
            "avoid_windows": avoid, "material_difference_threshold": thr,
            "n_candidates": len(sub),
            "note": "窗口粒度受模型误差限制：差异不显著时合并为区间，不给出精确到日的择时建议"}


# ---------------------------------------------------------------- 面积优化 + 盈亏平衡 v2
def break_even_analysis(cost_per_mu: float, yield_per_mu: float, price_mid: float) -> Dict:
    """§49 盈亏平衡三式（公式明确）。"""
    be_price = cost_per_mu / yield_per_mu if yield_per_mu else None
    be_yield = cost_per_mu / price_mid if price_mid else None
    be_cost = price_mid * yield_per_mu
    return {
        "break_even_price": round(be_price, 4) if be_price else None,
        "break_even_yield_kg_per_mu": round(be_yield, 1) if be_yield else None,
        "break_even_cost_per_mu": round(be_cost, 2),
        "formula": {
            "break_even_price": "cost_per_mu / yield_per_mu（元/kg）",
            "break_even_yield": "cost_per_mu / price（kg/亩）",
            "break_even_cost": "price × yield（元/亩，成本超过此值即不值得种）",
        },
        "interpretation": {
            "至少卖多少钱不亏": round(be_price, 4) if be_price else None,
            "亩产至少多少不亏": round(be_yield, 1) if be_yield else None,
            "成本超过多少就不值得种": round(be_cost, 2),
        },
    }


def price_yield_matrix(cost_per_mu: float, yield_per_mu: float, price_mid: float,
                       area_mu: float, price_range: tuple = (-0.20, 0.20),
                       yield_range: tuple = (-0.20, 0.20), n: int = 9) -> Dict:
    """§50 价格 × 亩产 二维收益矩阵 + 亏损区域占比。"""
    prices = price_mid * np.linspace(1 + price_range[0], 1 + price_range[1], n)
    yields = yield_per_mu * np.linspace(1 + yield_range[0], 1 + yield_range[1], n)
    total_cost = area_mu * cost_per_mu
    mat = np.zeros((len(yields), len(prices)))
    for i, y in enumerate(yields):
        for j, p in enumerate(prices):
            mat[i, j] = area_mu * y * p - total_cost
    loss_ratio = float((mat < 0).mean())
    return {
        "price_axis": [round(float(p), 3) for p in prices],
        "yield_axis": [round(float(y), 1) for y in yields],
        "profit_matrix": np.round(mat, 2).tolist(),
        "loss_region_ratio": round(loss_ratio, 3),
        "price_range_pct": list(price_range), "yield_range_pct": list(yield_range),
        "note": "压力情景矩阵（非概率），用于展示盈亏结构",
    }


def optimize_area(crop_options: pd.DataFrame, available_area_mu: float, budget: float,
                  cost_per_mu: float, yield_per_mu: float,
                  max_acceptable_loss: Optional[float] = None,
                  risk_preference: str = "balanced") -> Dict:
    """§19 §51 面积优化：经营风险约束下的建议面积（非"生物学最优"）。

    crop_options: 同一作物同一上市窗口下的多面积候选评估行（含 profit_*）。
    """
    d = crop_options.sort_values("area_mu").copy()
    if not len(d):
        return {"status": "no_options"}
    d["worst_case_loss"] = np.maximum(0.0, -pd.to_numeric(d["profit_pessimistic"], errors="coerce").fillna(0.0))
    d["exposure_pct_budget"] = (d["total_cost"] / budget * 100).round(1) if budget else None
    tol = max_acceptable_loss
    if tol is None:
        # 风险偏好默认容忍度（占预算比例）
        tol = {"conservative": 0.10, "balanced": 0.25, "aggressive": 0.50}.get(risk_preference, 0.25) * budget
    ok = d[d["worst_case_loss"] <= tol]
    rec = ok.iloc[-1] if len(ok) else d.iloc[0]
    mid = float(d.iloc[len(d) // 2]["price_mid"]) if "price_mid" in d else None
    out = {
        "status": "ok", "crop": d.iloc[0]["crop"],
        "harvest_window": f"{d.iloc[0].get('harvest_start', d.iloc[0]['harvest_date'])} ~ {d.iloc[0]['harvest_date']}",
        "loss_tolerance": {"max_acceptable_loss": float(tol),
                           "source": "user" if max_acceptable_loss is not None else f"default_{risk_preference}"},
        "recommended_area_mu": float(rec["area_mu"]),
        "recommended_area_feasible": bool(len(ok)),
        "max_feasible_area_mu": float(d["area_mu"].max()),
        "worst_case_loss_at_recommended": float(rec["worst_case_loss"]),
        "exposure_pct_of_budget": float(rec["exposure_pct_budget"]) if rec["exposure_pct_budget"] is not None else None,
        "area_table": d[["area_mu", "total_cost", "profit_pessimistic", "profit_baseline",
                         "profit_optimistic", "worst_case_loss"]].round(2).to_dict("records"),
        "break_even": break_even_analysis(cost_per_mu, yield_per_mu,
                                          mid if mid else float(d.iloc[0]["price_mid"])),
        "sensitivity_matrix": price_yield_matrix(cost_per_mu, yield_per_mu,
                                                 mid if mid else float(d.iloc[0]["price_mid"]),
                                                 float(rec["area_mu"])),
        "note": "这是经营风险约束下的建议面积；不声称任何生物学最优，也不假设面积影响市场价格",
    }
    if not len(ok):
        out["warning"] = "所有面积档位的悲观情景亏损都超过容忍度 → 建议缩小面积或更换方案"
    return out