# -*- coding: utf-8 -*-
"""Phase 7 / §27-§31: 反事实压力测试 + 鲁棒决策 + Minimax Regret。

定位：**参数压力测试 / what-if 情景**，不是因果推断。
禁止写法："暴雨导致减产 20%"；正确写法："在『亩产下降 20%』压力情景下……"

支持的 shocks（§28）：price ±10%/20%、cost +10%/20%、yield −10%/20%、
harvest delay +7/14d、climate risk↑、market risk↑。
"""
from __future__ import annotations
from copy import deepcopy
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from decision_engine.engine.engine import DecisionEngine
from decision_engine.profit.profit import evaluate_profit

DEFAULT_SHOCKS = [
    {"name": "price_-10%", "type": "price", "factor": 0.90},
    {"name": "price_-20%", "type": "price", "factor": 0.80},
    {"name": "price_+10%", "type": "price", "factor": 1.10},
    {"name": "cost_+10%", "type": "cost", "factor": 1.10},
    {"name": "cost_+20%", "type": "cost", "factor": 1.20},
    {"name": "yield_-10%", "type": "yield", "factor": 0.90},
    {"name": "yield_-20%", "type": "yield", "factor": 0.80},
    {"name": "harvest_delay_+7d", "type": "harvest_delay", "days": 7},
    {"name": "harvest_delay_+14d", "type": "harvest_delay", "days": 14},
    {"name": "climate_risk_+15", "type": "climate_add", "delta": 15.0},
    {"name": "market_risk_+15", "type": "market_add", "delta": 15.0},
]


def _score_from(roi_base: float, roi_pess: float, mr: float, hri: float, cl: float,
                pref: str) -> Dict:
    from decision_engine.engine.decision import decision_score
    return decision_score(roi_base, roi_pess, mr, hri, cl, pref)


def stress_plan(row: Dict, shocks: Optional[List[Dict]] = None,
                engine: Optional[DecisionEngine] = None) -> Dict:
    """对单个已评估方案做压力测试。

    row 需含：city, crop, plant_date, harvest_date, area_mu, cost_per_mu,
             expected_yield_per_mu, price_low/mid/high, market_risk, HRI, climate_risk,
             risk_preference（可选）
    """
    shocks = shocks or DEFAULT_SHOCKS
    eng = engine or DecisionEngine(as_of=row.get("as_of"))
    area = float(row["area_mu"]); cost = float(row["cost_per_mu"])
    yld = float(row["expected_yield_per_mu"]); pref = row.get("risk_preference", "balanced")
    base_mr = float(row.get("market_risk") or 50); base_hri = float(row.get("HRI") or 50)
    base_cl = float(row.get("climate_risk") or 50)
    base = evaluate_profit(row["price_low"], row["price_mid"], row["price_high"], area, cost, yld)
    base_score = _score_from(base["scenarios"]["baseline"]["roi"], base["scenarios"]["pessimistic"]["roi"],
                             base_mr, base_hri, base_cl, pref)
    out = []
    for s in shocks:
        p = dict(row); mr, hri, cl = base_mr, base_hri, base_cl
        if s["type"] == "price":
            pl, pm, ph = row["price_low"] * s["factor"], row["price_mid"] * s["factor"], row["price_high"] * s["factor"]
        else:
            pl, pm, ph = row["price_low"], row["price_mid"], row["price_high"]
        if s["type"] == "cost":
            cost_s = cost * s["factor"]; yld_s = yld
        elif s["type"] == "yield":
            cost_s = cost; yld_s = yld * s["factor"]
        else:
            cost_s, yld_s = cost, yld
        if s["type"] == "harvest_delay":
            new_harvest = (pd.Timestamp(row["harvest_date"]) + pd.Timedelta(days=s["days"])).date()
            plan = {"city": row["city"], "crop": row["crop"], "plant_date": row["plant_date"],
                    "harvest_date": str(new_harvest), "area_mu": area, "cost_per_mu": cost,
                    "expected_yield_per_mu": yld, "risk_preference": pref}
            r = eng.evaluate_plan(plan)
            if r.get("status") != "ok":
                out.append({"shock": s["name"], "status": "not_evaluable", "reason": r.get("price", {}).get("reason")})
                continue
            pl, pm, ph = r["price"]["low"], r["price"]["mid"], r["price"]["high"]
            mr = (r["risk"]["market"] or {}).get("value") or mr
            hri = (r["risk"]["herding"] or {}).get("value") or hri
            cl = r["risk"]["climate"].get("climate_exposure_score") or cl
        if s["type"] == "climate_add":
            cl = min(100.0, cl + s["delta"])
            pl = pl * 0.98  # 气候暴露上升时对价格/产量不做因果假设，仅压力测试价格微幅波动
        if s["type"] == "market_add":
            mr = min(100.0, mr + s["delta"])
        pr = evaluate_profit(pl, pm, ph, area, cost_s, yld_s)
        sc = _score_from(pr["scenarios"]["baseline"]["roi"], pr["scenarios"]["pessimistic"]["roi"],
                         mr, hri, cl, pref)
        base_profit = base["scenarios"]["baseline"]["profit"]
        sh_profit = pr["scenarios"]["baseline"]["profit"]
        out.append({
            "shock": s["name"], "status": "ok",
            "profit_baseline": sh_profit,
            "profit_delta": round(sh_profit - base_profit, 2),
            "profit_delta_pct": round((sh_profit - base_profit) / abs(base_profit) * 100, 2) if base_profit else None,
            "roi_baseline": pr["scenarios"]["baseline"]["roi"],
            "roi_delta": round(pr["scenarios"]["baseline"]["roi"] - base["scenarios"]["baseline"]["roi"], 4),
            "profit_pessimistic": pr["scenarios"]["pessimistic"]["profit"],
            "decision_score": sc["score"],
            "score_delta": round(sc["score"] - base_score["score"], 2),
            "still_profitable": sh_profit > 0,
        })
    ok = [r for r in out if r["status"] == "ok"]
    worst = min(ok, key=lambda r: r["profit_baseline"]) if ok else None
    return {
        "plan": {"crop": row["crop"], "harvest_date": str(row["harvest_date"]), "area_mu": area},
        "base": {"profit_baseline": base["scenarios"]["baseline"]["profit"],
                 "profit_pessimistic": base["scenarios"]["pessimistic"]["profit"],
                 "decision_score": base_score["score"]},
        "scenarios": out,
        "worst_case_profit": worst["profit_baseline"] if worst else None,
        "worst_case_shock": worst["shock"] if worst else None,
        "worst_case_score": min((r["decision_score"] for r in ok), default=None),
        "n_loss_scenarios": sum(1 for r in ok if r["profit_baseline"] < 0),
        "note": "参数压力测试（what-if），不代表任何事件发生的概率或因果",
    }


def robust_plan_selection(rows: List[Dict], shocks: Optional[List[Dict]] = None,
                          engine: Optional[DecisionEngine] = None) -> Dict:
    """§30/§31 鲁棒决策 + Minimax Regret。"""
    results = []
    for r in rows:
        st = stress_plan(r, shocks, engine)
        results.append(st)
    if not results:
        return {"status": "no_plans"}
    # 每个情景下的最优利润 → regret 矩阵
    scenario_names = [s["shock"] for s in results[0]["scenarios"] if s["status"] == "ok"]
    best_per_scenario = {sn: max((res["scenarios"][i]["profit_baseline"]
                                  for res in results if len(res["scenarios"]) > i and res["scenarios"][i]["status"] == "ok"),
                                 default=None) for i, sn in enumerate(scenario_names)}
    table = []
    for res in results:
        regs = []
        for i, sn in enumerate(scenario_names):
            sc = res["scenarios"][i] if len(res["scenarios"]) > i else None
            if not sc or sc["status"] != "ok" or best_per_scenario[sn] is None:
                continue
            regs.append(best_per_scenario[sn] - sc["profit_baseline"])
        table.append({
            "crop": res["plan"]["crop"], "harvest_date": res["plan"]["harvest_date"],
            "area_mu": res["plan"]["area_mu"],
            "base_profit": res["base"]["profit_baseline"],
            "worst_case_profit": res["worst_case_profit"],
            "worst_case_score": res["worst_case_score"],
            "max_regret": max(regs) if regs else None,
            "mean_regret": float(np.mean(regs)) if regs else None,
            "n_loss_scenarios": res["n_loss_scenarios"],
        })
    t = pd.DataFrame(table)
    if not len(t):
        return {"status": "no_scenarios"}
    minimax = t.sort_values(["max_regret", "worst_case_profit"], ascending=[True, False]).iloc[0]
    most_profitable = t.sort_values("base_profit", ascending=False).iloc[0]
    return {
        "status": "ok",
        "table": t.to_dict("records"),
        "minimax_regret_plan": minimax.to_dict(),
        "most_profitable_plan": most_profitable.to_dict(),
        "best_worst_case_plan": t.sort_values("worst_case_profit", ascending=False).iloc[0].to_dict(),
        "interpretation": "Minimax Regret = 在最优情景与各压力情景下的最大机会损失最小；"
                          "可作为保守型种植建议；不等于概率意义上的最优",
    }