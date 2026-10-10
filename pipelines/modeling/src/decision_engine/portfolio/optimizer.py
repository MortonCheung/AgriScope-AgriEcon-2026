# -*- coding: utf-8 -*-
"""Phase 6 / §20 §25 §26 §52 §53: 多作物组合优化（离散搜索 + 局部改进）。

模型假设（透明记录）：
  - 土地可分割；每个面积单元在一个生产季只种一种作物（**不做复种**，§53）；
  - 面积不影响单价（无「面积→市场供给」因果模型）；
  - 组合仅在同一规划季内（同季组合）；
  - 目标：组合效用最大 = 收益/下行/风险/集中度/相关性 的透明聚合。

算法：多起点 + 步进爬山（确定性、可复现），规模小（≤10 作物 × 面积阶梯）无需外部求解器。
"""
from __future__ import annotations
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from decision_engine.portfolio.risk import portfolio_metrics, portfolio_utility, crop_return_correlation
from decision_engine.optimization import utility as U


def _crop_plan_table(cands: pd.DataFrame, max_options_per_crop: int = 1) -> Dict[str, Dict]:
    """每个作物选 1（或前 N）个代表方案（按 utility），作为组合的基本单元。"""
    out = {}
    for crop, g in cands.groupby("crop"):
        g = g.sort_values("utility_score", ascending=False).head(max_options_per_crop)
        out[crop] = g.iloc[0].to_dict()
    return out


def _bump(alloc: Dict[str, float], crop: str, step: float):
    a = dict(alloc)
    a[crop] = a.get(crop, 0.0) + step
    return a


def optimize_crop_portfolio(
    cands: pd.DataFrame,
    available_area_mu: float,
    budget: float,
    risk_preference: str = "balanced",
    step: Optional[float] = None,
    max_crops: int = 5,
    min_area_per_crop: float = 1.0,
    max_acceptable_loss: Optional[float] = None,
    include_idle_land: bool = True,
    as_of: Optional[str] = None,
    price_df: Optional[pd.DataFrame] = None,
) -> Dict:
    """price_df: Final 价格序列（final_v1），传入则组合相关性计算完全走 Final，不读 v1。"""
    if not len(cands):
        return {"status": "no_candidates"}
    d = cands[cands["evaluable"]].copy()
    if not len(d):
        return {"status": "no_evaluable_candidates"}

    if step is None:
        step = 1.0 if available_area_mu <= 50 else (5.0 if available_area_mu <= 200 else 10.0)

    # 1) 每个作物先取效用最高的方案（组合目标是作物结构，不是窗口微调）
    plans = _crop_plan_table(d, 1)
    # 2) 只保留效用最高的 max_crops 个作物进入组合搜索
    ranked = sorted(plans.items(), key=lambda kv: -float(kv[1]["utility_score"]))
    plans = dict(ranked[:max_crops])
    crops = list(plans.keys())

    city = d.iloc[0]["city"]
    corr = crop_return_correlation(city, crops, as_of=as_of, price_df=price_df)

    def caps(crop: str) -> tuple:
        cost = float(plans[crop]["cost_per_mu"])
        max_by_budget = budget / cost if cost > 0 else available_area_mu
        return min(available_area_mu, max_by_budget), cost

    def evaluate(alloc: Dict[str, float]) -> Dict:
        pm = portfolio_metrics(alloc, plans, corr)
        pm["idle_area_mu"] = round(available_area_mu - pm["total_area_mu"], 2)
        u = portfolio_utility(pm, budget, risk_preference)
        pm["portfolio_utility"] = round(float(u), 4)
        return pm

    # 3) 多起点
    starts: List[Dict[str, float]] = []
    caps_all = {c: caps(c)[0] for c in crops}
    # (a) 各作物单独满配
    for c in crops:
        a = {c: min(step * np.floor(caps_all[c] / step) or step, caps_all[c])}
        starts.append(a)
    # (b) 平均分配（受预算/面积约束）
    n = len(crops)
    equal_cap = min(available_area_mu / n, min(caps_all.values()))
    eq = min(step * np.floor(equal_cap / step), equal_cap)
    if eq >= min_area_per_crop:
        starts.append({c: eq for c in crops})
    # (c) 贪心填充：按效用边际收益依次加分
    greedy: Dict[str, float] = {}
    remaining_area, remaining_budget = available_area_mu, budget
    for c in sorted(crops, key=lambda x: -float(plans[x]["utility_score"])):
        cap, cost = caps(c)
        take = min(cap, remaining_area, remaining_budget / cost)
        take = step * np.floor(take / step)
        if take >= min_area_per_crop:
            greedy[c] = take
            remaining_area -= take
            remaining_budget -= take * cost
    if greedy:
        starts.append(greedy)

    # 4) 局部改进（步进移动土地，贪心上升）
    best_alloc, best_pm = None, None
    forbidden_violation = None
    for s0 in starts:
        alloc = dict(s0)
        pm = evaluate(alloc)
        improved = True
        guard = 0
        while improved and guard < 200:
            improved = False
            guard += 1
            for src in list(alloc.keys()) + [None]:
                for dst in crops:
                    if src == dst:
                        continue
                    trial = dict(alloc)
                    if src is not None:
                        if trial.get(src, 0) - step < min_area_per_crop * 0:
                            pass
                        trial[src] = trial.get(src, 0) - step
                        if trial.get(src, 0) <= 0:
                            trial.pop(src, None)
                    cap_dst, cost_dst = caps(dst)
                    if trial.get(dst, 0) + step > cap_dst:
                        continue
                    trial[dst] = trial.get(dst, 0) + step
                    if sum(trial.values()) > available_area_mu + 1e-9:
                        continue
                    cost = sum(v * caps(c)[1] for c, v in trial.items())
                    if cost > budget + 1e-6:
                        continue
                    # 损失容忍约束（§51）
                    if max_acceptable_loss is not None:
                        loss = sum(abs(min(0.0, plans[c]["profit_pessimistic"])) / max(plans[c]["area_mu"], 1e-9) * v
                                   for c, v in trial.items())
                        if loss > max_acceptable_loss:
                            forbidden_violation = "loss_tolerance"
                            continue
                    pm_t = evaluate(trial)
                    if pm_t["portfolio_utility"] > pm["portfolio_utility"] + 1e-6:
                        alloc, pm, improved = trial, pm_t, True
        if best_pm is None or pm["portfolio_utility"] > best_pm["portfolio_utility"]:
            best_alloc, best_pm = alloc, pm

    # 5) 单作物对照（最优单作物满配）用于 compare_both
    single_best = max((evaluate({c: caps_all[c]}) | {"crop": c} for c in crops),
                      key=lambda x: x["portfolio_utility"])

    return {
        "status": "ok",
        "risk_preference": risk_preference,
        "step_mu": step,
        "crops_considered": crops,
        "allocation": [{"crop": c, "area_mu": round(a, 1),
                        "share": round(a / max(sum(best_alloc.values()), 1e-9), 4),
                        "harvest_date": str(plans[c]["harvest_date"]),
                        "plant_date": str(plans[c]["plant_date"]),
                        "cost_per_mu": float(plans[c]["cost_per_mu"]),
                        "profit_baseline": round(plans[c]["profit_baseline"] / max(plans[c]["area_mu"], 1e-9) * a, 2),
                        "HRI": plans[c]["HRI"], "market_risk": plans[c]["market_risk"],
                        "climate_risk": plans[c]["climate_risk"]}
                       for c, a in sorted(best_alloc.items(), key=lambda kv: -kv[1])],
        "idle_area_mu": round(available_area_mu - sum(best_alloc.values()), 2),
        "portfolio_metrics": best_pm,
        "single_crop_reference": {
            "crop": single_best["crop"],
            "area_mu": round(single_best["total_area_mu"], 1),
            "utility": single_best["portfolio_utility"],
            "hhi": single_best["hhi"], "profit_baseline": single_best["portfolio_profit_baseline"],
            "profit_pessimistic": single_best["portfolio_profit_pessimistic"],
            "risk_adjusted_market": single_best["risk_adjusted_market"],
        },
        "notes": [
            "组合仅为同季方案（不做复种）；土地可分割，每单元一季一种作物",
            "面积不影响价格（无农户级市场冲击模型），面积只决定敞口规模",
            "组合是否优于单作物由效用与风险指标判定，不预设结论",
        ],
    }