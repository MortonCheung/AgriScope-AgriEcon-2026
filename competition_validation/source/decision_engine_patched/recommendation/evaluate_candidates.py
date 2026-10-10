# -*- coding: utf-8 -*-
"""Phase 3 / §10 §58: 候选方案批量评估（复用 v1 evaluate_plan + 缓存）。

性能设计（§58）：
  - DecisionEngine 只加载一次（load once）；
  - 缓存 key = (city, crop, plant_date, harvest_date, cost_per_mu, yield_per_kg)
    → 因为面积只线性影响利润（无「面积→市场供给」因果模型），ROI / 风险 / 评分与面积无关；
  - 面积在缓存结果上按比例缩放，避免 4 倍重复推理。

输出长表：candidate_id, crop, plant/harvest, area, cost, yield,
          price_low/mid/high, profit_pessimistic/baseline/optimistic,
          market_risk, HRI, climate_risk, decision_score, confidence
"""
from __future__ import annotations
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from decision_engine.common import de_path
from decision_engine.engine.engine import DecisionEngine


class CandidateEvaluator:
    def __init__(self, as_of: Optional[str] = None, engine: Optional[DecisionEngine] = None):
        self.engine = engine or DecisionEngine(as_of=as_of)
        self.cache: Dict[tuple, Dict] = {}
        self.n_calls = 0
        self.n_cache_hits = 0

    # ---------------------------------------------------------------- 单方案
    def _unit_key(self, c: Dict) -> tuple:
        return (c["city"], c["crop"], c["plant_date"], c["harvest_date"],
                float(c["cost_per_mu"]), float(c["expected_yield_per_mu"]))

    def evaluate_unit(self, c: Dict) -> Dict:
        key = self._unit_key(c)
        if key in self.cache:
            self.n_cache_hits += 1
            return self.cache[key]
        plan = {"city": c["city"], "crop": c["crop"],
                "plant_date": c["plant_date"], "harvest_date": c["harvest_date"],
                "area_mu": 1.0, "cost_per_mu": float(c["cost_per_mu"]),
                "expected_yield_per_mu": float(c["expected_yield_per_mu"]),
                "risk_preference": c.get("risk_preference", "balanced")}
        r = self.engine.evaluate_plan(plan)
        self.n_calls += 1
        self.cache[key] = r
        return r

    def evaluate(self, c: Dict) -> Dict:
        """返回该候选（含面积缩放后利润）的评估结果。"""
        unit = self.evaluate_unit(c)
        area = float(c["area_mu"])
        out = {
            "candidate_id": c["candidate_id"], "city": c["city"], "crop": c["crop"],
            "plant_date": c["plant_date"], "harvest_date": c["harvest_date"],
            "area_mu": area, "cost_per_mu": float(c["cost_per_mu"]),
            "expected_yield_per_mu": float(c["expected_yield_per_mu"]),
            "status": unit.get("status"),
        }
        if unit.get("status") != "ok":
            out.update({"evaluable": False, "reason": unit.get("error") or unit.get("price", {}).get("reason")})
            return out
        p, pr, rk, dec, cf = (unit["price"], unit["profit"], unit["risk"], unit["decision"], unit["confidence"])
        out.update({
            "evaluable": True,
            "price_low": p["low"], "price_mid": p["mid"], "price_high": p["high"],
            "price_method": p.get("method"), "price_statistic": p.get("statistic"),
            "is_calibrated_interval": bool(p.get("is_calibrated_interval")),
            "break_even_price": pr["break_even_price"],
            "profit_pessimistic": pr["pessimistic"]["profit"] * area,
            "profit_baseline": pr["baseline"]["profit"] * area,
            "profit_optimistic": pr["optimistic"]["profit"] * area,
            "roi_pessimistic": pr["pessimistic"]["roi"], "roi_baseline": pr["baseline"]["roi"],
            "roi_optimistic": pr["optimistic"]["roi"],
            "total_cost": pr["total_cost"] * area,
            "market_risk": (rk.get("market") or {}).get("value"),
            "market_risk_level": (rk.get("market") or {}).get("level"),
            "HRI": (rk.get("herding") or {}).get("value"),
            "HRI_level": (rk.get("herding") or {}).get("level"),
            "herding_components": (rk.get("herding") or {}).get("components"),
            "climate_risk": (rk.get("climate") or {}).get("climate_exposure_score"),
            "climate_years": (rk.get("climate") or {}).get("n_years"),
            "production_available": bool((rk.get("production") or {}).get("available")),
            "decision_score": dec.get("score"), "decision_grade": dec.get("grade"),
            "score_stability": dec.get("score_stability"),
            "confidence_score": cf.get("score"), "confidence_grade": cf.get("grade"),
            "confidence_components": cf.get("components"),
            "price_trend": (p.get("trend") or {}).get("direction"),
            "price_latest": (p.get("trend") or {}).get("price_latest"),
            # 候选元信息（供组合/置信度/解释层使用）
            "planting_date_source": c.get("planting_date_source"),
            "constraint_strength": c.get("constraint_strength"),
            "calendar_confidence_penalty": c.get("calendar_confidence_penalty"),
            "agro_warnings": c.get("agro_warnings"),
            "cost_is_proxy": c.get("cost_is_proxy"), "yield_is_proxy": c.get("yield_is_proxy"),
            "cost_level": c.get("cost_level"), "yield_level": c.get("yield_level"),
            "reference_warning": c.get("reference_warning"),
            "risk_preference": c.get("risk_preference"),
            "harvest_start": c.get("harvest_start"),
            "reasons": unit.get("reasons"), "limitations": unit.get("limitations"),
        })
        return out

    # ---------------------------------------------------------------- 批量
    def evaluate_many(self, candidates: List[Dict], verbose: bool = True) -> pd.DataFrame:
        rows = []
        for i, c in enumerate(candidates):
            rows.append(self.evaluate(c))
            if verbose and (i + 1) % 50 == 0:
                print(f"[eval] {i+1}/{len(candidates)} (engine calls={self.n_calls}, cache hits={self.n_cache_hits})",
                      flush=True)
        df = pd.DataFrame(rows)
        if verbose:
            print(f"[eval] done: {len(df)} candidates | engine calls={self.n_calls} | cache hits={self.n_cache_hits} "
                  f"| evaluable={int(df['evaluable'].sum()) if 'evaluable' in df else 0}", flush=True)
        return df


def summarize_evaluation(df: pd.DataFrame) -> pd.DataFrame:
    """按候选维度统计可评估率与关键指标范围（用于报告）。"""
    if not len(df):
        return pd.DataFrame()
    ok = df[df["evaluable"]]
    return pd.DataFrame([{
        "n_candidates": len(df), "n_evaluable": len(ok),
        "n_status_insufficient": (df["status"] != "ok").sum() if "status" in df else 0,
        "profit_baseline_min": ok["profit_baseline"].min() if len(ok) else None,
        "profit_baseline_max": ok["profit_baseline"].max() if len(ok) else None,
        "HRI_min": ok["HRI"].min() if len(ok) else None, "HRI_max": ok["HRI"].max() if len(ok) else None,
        "confidence_min": ok["confidence_score"].min() if len(ok) else None,
        "confidence_max": ok["confidence_score"].max() if len(ok) else None,
    }])