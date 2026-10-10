# -*- coding: utf-8 -*-
"""Phase 9 / §37-§39 §47-§48 §52 §65-§66: 种植方案推荐器（Decision Engine v2 核心 API）。

  recommend_plans(...)        → 完整推荐（Top5 + Pareto + 组合 + 压力测试 + 解释）
  make_planting_decision(...) → 最高层入口（推荐 + 组合 + 窗口/面积 + 解释）

严格复用 v1 评估内核（DecisionEngine.evaluate_plan），不重算价格/风险。
"""
from __future__ import annotations
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from decision_engine.common import de_path
from decision_engine.counterfactual import stress as ST
from decision_engine.engine.engine import DecisionEngine
from decision_engine.optimization import harvest_window as HW
from decision_engine.optimization import pareto as PA
from decision_engine.optimization import ranking as RK
from decision_engine.optimization import utility as U
from decision_engine.portfolio import optimizer as PO
from decision_engine.recommendation import candidates as CG
from decision_engine.recommendation import explainer as EX
from decision_engine.recommendation.evaluate_candidates import CandidateEvaluator, summarize_evaluation

LOSS_TOLERANCE_BY_PREF = {"conservative": 0.10, "balanced": 0.25, "aggressive": 0.50}


# ---------------------------------------------------------------- 辅助
def _proxy_penalty(df: pd.DataFrame) -> Dict[str, float]:
    """§6 参考值/proxy → 降低推荐置信度（最多 15 分）。"""
    if not len(df):
        return {}
    def _share(col: str) -> float:
        if col not in df.columns:
            return 1.0                       # 缺失即视为未知来源 → 按 proxy 处理
        s = df[col]
        if s.dtype != bool:
            s = s.astype(str).str.lower().isin(["true", "1", "yes"])
        return float(s.fillna(True).mean())
    pen = 15.0 * (0.5 * _share("cost_is_proxy") + 0.5 * _share("yield_is_proxy"))
    return {"reference_proxy": round(pen, 2)} if pen > 0 else {}


def _profit_plausibility(row: Dict, sector_cost_per_mu: float = 4617.69) -> Dict:
    """利润合理性检查（防止 proxy 成本口径不完整导致利润虚高，§60 数学边界）。"""
    area = float(row.get("area_mu") or 0) or 1.0
    prof = row.get("profit_baseline")
    ppm = (float(prof) / area) if prof is not None else None
    cost = row.get("cost_per_mu")
    flags = []
    if ppm is not None and ppm > 15000:
        flags.append(f"亩均净收益 {ppm:,.0f} 元/亩 异常偏高（>15000）")
    if cost is not None and float(cost) < 0.6 * sector_cost_per_mu:
        flags.append(f"参考成本 {float(cost):,.0f} 元/亩 低于蔬菜混合口径成本（{sector_cost_per_mu:,.0f}）60% 以上 → "
                     "成本科目可能不完整（不含人工/地租/折旧），利润存在高估风险")
    return {"profit_per_mu": None if ppm is None else round(ppm, 2),
            "cost_per_mu": cost, "sector_cost_reference": sector_cost_per_mu,
            "plausible": len(flags) == 0, "flags": flags,
            "note": "基于口径比较的合理性提示，不是精度评估"}


def _herding_check(city: str, rec_row: Dict, crops: List[str]) -> Dict:
    """§43/§44：检查推荐是否只是"追当前最高价"，以及 HRI 是否抑制了追高。"""
    out = {"recommended_crop": rec_row.get("crop"), "HRI": rec_row.get("HRI")}
    # 当前最高价作物（截至最新观测）
    latest_price = {}
    if city == "沈阳":
        ds = pd.read_parquet(de_path("data", "processed", "decision_dataset_v1.parquet"),
                             columns=["date", "crop", "price_per_kg"])
    else:
        p = de_path("data", "features", f"regional_{city}.parquet")
        if not p.exists():
            return out
        ds = pd.read_parquet(p, columns=["date", "crop", "price_per_kg"])
    ds["date"] = pd.to_datetime(ds["date"])
    for c in crops:
        s = ds[ds["crop"] == c]["price_per_kg"].dropna()
        if len(s):
            latest_price[c] = float(s.iloc[-1])
    if latest_price:
        highest = max(latest_price, key=latest_price.get)
        ranked = sorted(latest_price.items(), key=lambda kv: -kv[1])
        out["current_highest_price_crop"] = highest
        out["recommended_is_highest_price"] = bool(rec_row.get("crop") == highest)
        out["recommended_price_rank"] = 1 + [c for c, _ in ranked].index(rec_row.get("crop")) \
            if rec_row.get("crop") in latest_price else None
        out["n_crops"] = len(ranked)
    # 是否落在 HRI 高分位（用 HRI 历史 P90）
    try:
        from decision_engine.monitoring.daily_signal import warning_thresholds
        thr = warning_thresholds(city, rec_row.get("crop")).get("HRI")
        if thr and rec_row.get("HRI") is not None:
            out["HRI_p90_threshold"] = round(thr["p90"], 2)
            out["recommended_in_HRI_top10pct"] = bool(rec_row["HRI"] >= thr["p90"])
    except Exception:
        pass
    out["note"] = "用于检验系统是否在盲目追高（HRI/市场风险是否真正抑制了高价诱惑）"
    return out


def _plan_block(row: Dict) -> Dict:
    """§39 recommended_plan 字段。"""
    return {
        "crop": row.get("crop"),
        "city": row.get("city"),
        "planting_window": f"{row.get('plant_date')}（来源：{row.get('planting_date_source', 'n/a')}）",
        "harvest_window": f"{row.get('harvest_start', row.get('harvest_date'))} ~ {row.get('harvest_date')}",
        "area_mu": row.get("area_mu"),
        "price_low": row.get("price_low"), "price_mid": row.get("price_mid"), "price_high": row.get("price_high"),
        "price_method": row.get("price_method"), "is_calibrated_interval": row.get("is_calibrated_interval"),
        "profit_pessimistic": row.get("profit_pessimistic"),
        "profit_baseline": row.get("profit_baseline"),
        "profit_optimistic": row.get("profit_optimistic"),
        "HRI": row.get("HRI"), "market_risk": row.get("market_risk"),
        "climate_exposure": row.get("climate_risk"),
        "decision_score": row.get("decision_score"), "decision_grade": row.get("decision_grade"),
        "utility_score": row.get("utility_score"),
        "confidence": row.get("confidence_score"), "confidence_grade": row.get("confidence_grade"),
        "cost_per_mu": row.get("cost_per_mu"), "expected_yield_per_mu": row.get("expected_yield_per_mu"),
        "cost_level": row.get("cost_level"), "yield_level": row.get("yield_level"),
    }


# ---------------------------------------------------------------- 主入口
def recommend_plans(
    city: str = "沈阳",
    available_area_mu: float = 100,
    budget: float = 500000,
    earliest_plant_date: str = "2027-03-01",
    latest_harvest_date: str = "2027-10-31",
    risk_preference: str = "balanced",
    mode: str = "compare_both",
    top_n: int = 5,
    allowed_crops: Optional[List[str]] = None,
    excluded_crops: Optional[List[str]] = None,
    cost_per_mu_by_crop: Optional[Dict[str, float]] = None,
    expected_yield_by_crop: Optional[Dict[str, float]] = None,
    max_area_per_crop: Optional[float] = None,
    max_acceptable_loss: Optional[float] = None,
    min_area_per_crop: float = 1.0,
    harvest_window_days: int = 10,
    max_candidates: int = 800,
    allow_proxy: bool = True,
    as_of: Optional[str] = None,
    run_stress: bool = True,
    verbose: bool = False,
) -> Dict:
    request = {"city": city, "available_area_mu": available_area_mu, "budget": budget,
               "earliest_plant_date": earliest_plant_date, "latest_harvest_date": latest_harvest_date,
               "risk_preference": risk_preference, "mode": mode, "as_of": as_of,
               "allowed_crops": allowed_crops, "excluded_crops": excluded_crops,
               "max_acceptable_loss": max_acceptable_loss}
    gen = CG.generate_candidate_plans(
        city=city, available_area_mu=available_area_mu, budget=budget,
        earliest_plant_date=earliest_plant_date, latest_harvest_date=latest_harvest_date,
        risk_preference=risk_preference, allowed_crops=allowed_crops, excluded_crops=excluded_crops,
        cost_per_mu_by_crop=cost_per_mu_by_crop, expected_yield_by_crop=expected_yield_by_crop,
        max_area_per_crop=max_area_per_crop, min_area_per_crop=min_area_per_crop,
        harvest_window_days=harvest_window_days, max_candidates=max_candidates, allow_proxy=allow_proxy)
    if gen.get("status") != "ok":
        return {"status": gen.get("status"), "request": request,
                "reason": gen.get("reason") or "无可行候选方案",
                "recommended_plan": None, "alternatives": [], "pareto_frontier": [],
                "portfolio_plan": None, "risk_summary": {}, "stress_test": {},
                "confidence": {}, "reasons": [], "limitations": [
                    "大连/铁岭/丹东无连续官方价格序列 → 不提供价格与推荐（v1 审计结论）"]}

    ev = CandidateEvaluator(as_of=as_of)
    df = ev.evaluate_many(gen["candidates"], verbose=verbose)
    ok = df[df["evaluable"]].copy()
    if not len(ok):
        return {"status": "no_evaluable_candidate", "request": request,
                "recommended_plan": None, "alternatives": [], "pareto_frontier": [],
                "portfolio_plan": None, "risk_summary": {}, "stress_test": {},
                "confidence": {}, "reasons": [], "limitations": []}

    # 面积容忍度：用户值 > 风险偏好默认
    if max_acceptable_loss is None:
        max_acceptable_loss_eff = LOSS_TOLERANCE_BY_PREF.get(risk_preference, 0.25) * budget
        loss_source = f"default_{risk_preference}"
    else:
        max_acceptable_loss_eff = float(max_acceptable_loss)
        loss_source = "user"

    plans = RK.collapse_area_variants(ok, max_acceptable_loss_eff)
    plans = U.utility_report(plans)
    plans = plans.sort_values("utility_score", ascending=False).reset_index(drop=True)
    front = PA.compute_pareto_frontier(U.utility_report(ok))

    # Top-N 方案（§37）：按**不同作物**聚类，每个作物取效用最高的上市窗口
    per_crop = (plans.sort_values("utility_score", ascending=False)
                .drop_duplicates(subset=["crop"], keep="first")
                .reset_index(drop=True))
    top = per_crop.head(max(top_n, 5)).copy()
    # 推荐作物的窗口变体（供用户在同一作物内比较上市时间）
    within_crop = plans[plans["crop"] == per_crop.iloc[0]["crop"]].head(4)

    # 窗口优化（对推荐作物）
    best = plans.iloc[0]
    win = HW.optimize_harvest_window(city, best["crop"], ok, risk_preference, max_acceptable_loss_eff)
    # 面积优化（推荐方案的面积档位）
    area_tbl = ok[(ok["crop"] == best["crop"]) & (ok["harvest_date"] == best["harvest_date"])]
    area_res = HW.optimize_area(area_tbl, available_area_mu, budget, float(best["cost_per_mu"]),
                                float(best["expected_yield_per_mu"]), max_acceptable_loss_eff,
                                risk_preference) if len(area_tbl) else {"status": "no_area_options"}

    # 组合优化
    portfolio = PO.optimize_crop_portfolio(plans, available_area_mu, budget, risk_preference,
                                           step=None, max_crops=5,
                                           max_acceptable_loss=max_acceptable_loss_eff, as_of=as_of)

    # 压力测试 + 鲁棒
    stress = {}
    if run_stress:
        rows = plans.head(min(6, len(plans))).to_dict("records")
        robust = ST.robust_plan_selection(rows, engine=ev.engine)
        stress = {"top_plans": robust,
                  "recommended_plan_stress": ST.stress_plan(best.to_dict(), engine=ev.engine)}
    robust_plan = (stress.get("top_plans", {}) or {}).get("minimax_regret_plan")

    # Top-N 标签（允许重复方案）
    labeled = {
        "Best Return": plans.sort_values("profit_baseline", ascending=False).iloc[0].to_dict(),
        "Best Balanced": plans.sort_values("utility_balanced", ascending=False).iloc[0].to_dict(),
        "Lowest Risk": plans.assign(
            _risk=np.maximum(plans["HRI"], np.maximum(plans["market_risk"], plans["climate_risk"]))
        ).sort_values("_risk").iloc[0].to_dict(),
        "Most Robust": robust_plan,
        "Alternative": (plans.drop(index=[plans.index[0]]).iloc[0].to_dict() if len(plans) > 1 else None),
    }

    # 稳定性与推荐置信度
    ws = U.weight_sensitivity(plans, risk_preference)
    ip = RK.ranking_under_input_perturbation(plans, risk_preference)
    base_conf = float(plans.head(min(3, len(plans)))["confidence_score"].mean())
    data_cov = float((~plans["cost_is_proxy"]).mean()) if "cost_is_proxy" in plans else 0.0
    scenario_rob = None
    if stress.get("top_plans", {}).get("table"):
        t = pd.DataFrame(stress["top_plans"]["table"])
        if len(t) and t["worst_case_profit"].notna().any():
            scenario_rob = float(np.clip((t["worst_case_profit"].clip(lower=0)).mean() /
                                         max(t["base_profit"].mean(), 1e-9), 0, 1))
    penalties = _proxy_penalty(plans)
    conf = RK.recommendation_confidence(
        plans, ip, base_conf, scenario_rob, data_cov, penalties=penalties,
        level_penalties={"calendar": {"confidence_penalty": float(np.mean(
            [p.get("calendar_confidence_penalty", 0.0) for p in plans.to_dict("records")]))}})

    # 备选与解释（对比对象：不同作物中效用最高的方案）
    alt_rows = per_crop.drop(index=[per_crop.index[0]]).to_dict("records")
    expl = EX.explain_plan(best.to_dict(), {"risk_preference": risk_preference})
    diff_crop_alt = alt_rows[0] if alt_rows else None
    cmp_target = diff_crop_alt
    cmp_reason = EX.comparison_reason(best.to_dict(), cmp_target, risk_preference) if cmp_target else ""

    # 机会成本（用全量方案的次优与最佳收益参照）
    opp = RK.opportunity_cost(best.to_dict(), plans.drop(index=[plans.index[0]]).to_dict("records"))

    # 利润合理性检查（proxy 成本口径不完整 → 利润可能虚高）
    plaus = _profit_plausibility(best.to_dict())

    # 追高检查
    herding = _herding_check(city, best.to_dict(), gen["meta"]["crop_pool"])

    # 组合 vs 单作物结论（compare_both）
    mode_cmp = None
    if mode == "compare_both" and portfolio.get("status") == "ok":
        pu = portfolio["portfolio_metrics"]["portfolio_utility"]
        su = portfolio["single_crop_reference"]["utility"]
        mode_cmp = {"portfolio_utility": pu, "single_crop_utility": su,
                    "preferred": "portfolio" if pu > su else ("single_crop" if su > pu else "tie"),
                    "note": "组合是否更优由效用与风险指标判定，不预设'组合一定更好'"}

    # 限制项
    limits = [
        "价格区间为历史同月分位（scenario range），未校准为概率区间",
        "参考成本/亩产为 proxy 时利润口径偏粗（部分来源仅含种子+肥料+农药，不含人工/地租/折旧）",
        "面积不影响价格（无农户级市场冲击模型）",
        "不做复种；组合仅同季；土地可分割",
        "不做跨城市联合优化（无同口径跨城价格）",
        "风险偏好只改变排序权重，不改变价格预测与风险指标数值",
        "推荐置信度已按 proxy/日历强度/排序稳定性折扣",
    ]
    if not portfolio.get("status") == "ok":
        limits.append("组合优化不可用（候选不足）")

    from decision_engine.recommendation import reference_inputs as RI
    result = {
        "status": "ok",
        "request": request,
        "recommended_plan": _plan_block(best.to_dict()),
        "alternatives": [_plan_block(r) for r in per_crop.iloc[1:max(top_n, 5)].to_dict("records")],
        "top_plans": [{"crop": r["crop"], "harvest_date": str(r["harvest_date"]), "area_mu": r["area_mu"],
                       "utility_score": round(float(r["utility_score"]), 4),
                       "profit_baseline": round(float(r["profit_baseline"]), 2),
                       "HRI": r["HRI"], "market_risk": r["market_risk"], "climate_risk": r["climate_risk"],
                       "confidence": r["confidence_score"], "data_reliability": r.get("data_reliability")}
                      for r in top.to_dict("records")],
        "top_plans_note": "Top-N 按不同作物聚类（每个作物取效用最高的上市窗口）；同一作物的窗口选项见 harvest_window_optimization",
        "within_crop_windows": [{"crop": r["crop"], "harvest_window": f"{r.get('harvest_start', r['harvest_date'])} ~ {r['harvest_date']}",
                                 "utility_score": round(float(r["utility_score"]), 4),
                                 "profit_baseline": round(float(r["profit_baseline"]), 2)}
                                for r in within_crop.to_dict("records")],
        "labels": EX.plan_label_summary(labeled),
        "pareto_frontier": [{"crop": r["crop"], "harvest_date": str(r["harvest_date"]),
                             "area_mu": r["area_mu"], "style": r.get("pareto_style"),
                             "profit_baseline": round(float(r["profit_baseline"]), 2),
                             "profit_pessimistic": round(float(r["profit_pessimistic"]), 2),
                             "HRI": r["HRI"], "market_risk": r["market_risk"],
                             "climate_risk": r["climate_risk"], "confidence": r["confidence_score"]}
                            for r in front.head(25).to_dict("records")],
        "harvest_window_optimization": win,
        "area_optimization": area_res,
        "portfolio_plan": portfolio,
        "mode_comparison": mode_cmp,
        "risk_summary": {
            "recommended": {"HRI": best["HRI"], "market_risk": best["market_risk"],
                            "climate_risk": best["climate_risk"]},
            "loss_tolerance": {"max_acceptable_loss": round(max_acceptable_loss_eff, 2), "source": loss_source},
            "herding_check": herding,
            "profit_plausibility": plaus,
        },
        "stress_test": stress,
        "confidence": conf,
        "ranking_stability": {"weight_sensitivity": ws, "input_perturbation": ip},
        "opportunity_cost": opp,
        "comparison_reason": cmp_reason,
        "reasons": expl["reasons"], "tradeoffs": expl["tradeoffs"], "plan_risks": expl["risks"],
        "limitations": limits,
        "evidence": {
            "evaluation_summary": summarize_evaluation(df).to_dict("records"),
            "candidate_meta": {k: v for k, v in gen["meta"].items() if k != "rejected"},
            "rejected_crops": gen["meta"].get("rejected", [])[:10],
            "v3_enhancements": RI.scan_v3_enhancements().to_dict("records"),
        },
        "performance": {"engine_calls": ev.n_calls, "cache_hits": ev.n_cache_hits,
                        "n_candidates": len(df), "n_plans": len(plans)},
    }
    return result


def make_planting_decision(request: Dict) -> Dict:
    """§65/§66 最高层 API：直接返回完整种植建议。"""
    if not isinstance(request, dict):
        return {"status": "invalid_input", "reason": "request 必须是 dict"}
    kw = dict(request)
    kw.setdefault("mode", "compare_both")
    return recommend_plans(**kw)