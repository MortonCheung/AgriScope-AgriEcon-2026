# -*- coding: utf-8 -*-
"""Phase 8: 收益模型（用户输入为正式成本口径）。

公式（价格单位统一 元/kg，亩产 kg/亩，成本 元/亩）：
  Revenue = area_mu × yield_per_mu × price
  Total Cost = area_mu × cost_per_mu
  Profit = Revenue - Total Cost
  Break-even Price = cost_per_mu / yield_per_mu
"""
from __future__ import annotations
from typing import Dict


def _validate(area_mu: float, cost_per_mu: float, yield_per_mu: float):
    errs = []
    if not (area_mu and area_mu > 0):
        errs.append("area_mu 必须 > 0")
    if not (cost_per_mu and cost_per_mu > 0):
        errs.append("cost_per_mu 必须 > 0（项目内无历史亩均成本，须用户输入）")
    if not (yield_per_mu and yield_per_mu > 0):
        errs.append("expected_yield_per_mu 必须 > 0")
    return errs


def evaluate_profit(price_low: float, price_mid: float, price_high: float,
                    area_mu: float, cost_per_mu: float, expected_yield_per_mu: float,
                    is_calibrated_interval: bool = False) -> Dict:
    errs = _validate(area_mu, cost_per_mu, expected_yield_per_mu)
    if errs:
        return {"error": "; ".join(errs)}
    total_cost = area_mu * cost_per_mu
    be = cost_per_mu / expected_yield_per_mu

    def scen(p):
        revenue = area_mu * expected_yield_per_mu * p
        profit = revenue - total_cost
        roi = profit / total_cost
        margin = profit / revenue if revenue > 0 else None
        return {"price": round(p, 4), "revenue": round(revenue, 2),
                "profit": round(profit, 2), "roi": round(roi, 4),
                "profit_margin": round(margin, 4) if margin is not None else None}

    return {
        "unit": {"price": "CNY/kg", "revenue": "CNY", "profit": "CNY", "cost": "CNY"},
        "break_even_price": round(be, 4),
        "total_cost": round(total_cost, 2),
        "scenarios": {
            "pessimistic": scen(price_low),
            "baseline": scen(price_mid),
            "optimistic": scen(price_high),
        },
        "scenario_semantics": ("80% probability interval" if is_calibrated_interval
                               else "scenario profit（区间未校准为概率区间）"),
        "all_scenarios_loss": all(scen(p)["profit"] < 0 for p in [price_low, price_mid, price_high]),
        "all_scenarios_profit": all(scen(p)["profit"] > 0 for p in [price_low, price_mid, price_high]),
    }