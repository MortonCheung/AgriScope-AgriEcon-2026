# -*- coding: utf-8 -*-
"""Phase 4 / §15 §46 §47: 排序稳定性、推荐置信度、机会成本。

- ranking_stability：权重 ±10% 抖动 + 输入（成本/亩产 ±10%）扰动下的 Top-K 稳定性；
- recommendation_confidence：模型置信度 + 候选分数间隔 + 排序稳定性 + 数据覆盖 + 情景稳健性；
- opportunity_cost：选择推荐方案相对"最高收益方案"少赚多少、下行改善多少。
"""
from __future__ import annotations
from typing import Dict, List

import numpy as np
import pandas as pd

from decision_engine.optimization.utility import PREFERENCE_WEIGHTS, utility_scores


def ranking_under_input_perturbation(df: pd.DataFrame, preference: str = "balanced",
                                     n_draws: int = 100, jitter: float = 0.10,
                                     seed: int = 42, top_k: int = 3) -> Dict:
    """§46 输入扰动（成本 ±10%、亩产 ±10%）下的推荐稳定性。"""
    from scipy import stats
    if not len(df):
        return {}
    base = utility_scores(df, preference)
    top_base = set(base.rank(ascending=False).nsmallest(top_k).index)
    rng = np.random.RandomState(seed)
    rhos, top1_keep, overlaps = [], [], []
    for _ in range(n_draws):
        d = df.copy()
        cf = 1 + rng.uniform(-jitter, jitter, len(d))
        yf = 1 + rng.uniform(-jitter, jitter, len(d))
        # 成本/亩产扰动 → ROI 与利润按相同方向变化；这里直接扰动 ROI（线性近似）
        d["roi_baseline"] = d["roi_baseline"] * (1 + rng.uniform(-0.15, 0.15, len(d)))
        d["roi_pessimistic"] = d["roi_pessimistic"] * (1 + rng.uniform(-0.20, 0.20, len(d)))
        s = utility_scores(d, preference)
        rho = stats.spearmanr(base.values, s.values)[0]
        if np.isfinite(rho):
            rhos.append(float(rho))
        order = s.rank(ascending=False)
        top1_keep.append(int(order.idxmin() == base.idxmin()))
        top = set(order.nsmallest(top_k).index)
        overlaps.append(len(top & top_base) / top_k)
    return {
        "n_draws": n_draws, "input_jitter": jitter,
        "spearman_mean": float(np.mean(rhos)) if rhos else np.nan,
        "top1_retention_rate": float(np.mean(top1_keep)),
        "topk_overlap_mean": float(np.mean(overlaps)),
    }


def recommendation_confidence(top_df: pd.DataFrame, ranking_stability: Dict,
                              base_conf: float, scenario_robustness: float = None,
                              data_coverage: float = None,
                              penalties: Dict[str, float] | None = None,
                              level_penalties: Dict[str, Dict] | None = None) -> Dict:
    """§47 推荐置信度：Top1 与 Top2 若几乎同分，不允许"强烈推荐"。"""
    components = {}
    components["underlying_model_confidence"] = float(base_conf) if base_conf is not None else 60.0
    sep = None
    if len(top_df) >= 2:
        s = top_df["utility_score"].sort_values(ascending=False).values
        sep = float(s[0] - s[1])
        # 间隔很小 → 分离度低（用 0.02 utility ≈ 显著性下限）
        components["score_separation"] = float(np.clip(sep / 0.05 * 100, 0, 100)) if sep is not None else 50.0
    else:
        components["score_separation"] = 40.0
    components["ranking_stability"] = float(np.clip(ranking_stability.get("spearman_mean", 0.9) * 100, 0, 100))
    components["data_coverage"] = float(data_coverage * 100) if data_coverage is not None else 50.0
    components["scenario_robustness"] = float(scenario_robustness * 100) if scenario_robustness is not None else 50.0

    weights = {"underlying_model_confidence": 0.30, "score_separation": 0.20,
               "ranking_stability": 0.20, "data_coverage": 0.15, "scenario_robustness": 0.15}
    score = sum(weights[k] * components[k] for k in weights)
    penalty_detail = dict(penalties or {})
    total_penalty = float(sum(penalty_detail.values()))
    if level_penalties:
        for k, v in level_penalties.items():
            penalty_detail[f"{k}(level)"] = round(float(v.get("confidence_penalty", 0.0)) * 100, 2)
        total_penalty += float(sum(penalty_detail[f"{k}(level)"] for k in (level_penalties or {})))
    score = float(np.clip(score - total_penalty, 0, 100))
    grade = "A" if score >= 80 else "B" if score >= 65 else "C" if score >= 50 else "D"
    note = None
    if sep is not None and sep < 0.02:
        note = f"Top1 与 Top2 效用几乎相同（Δ={sep:.4f}）→ 不给出「强烈推荐」，请视为并列方案"
    return {"score": round(float(score), 1), "grade": grade,
            "components": {k: round(v, 1) for k, v in components.items()},
            "weights": weights, "penalties": {k: round(v, 2) for k, v in penalty_detail.items()},
            "total_penalty": round(total_penalty, 2),
            "top1_minus_top2_utility": sep, "note": note}


def collapse_area_variants(df: pd.DataFrame, max_acceptable_loss: float | None = None,
                           utility_col: str = "utility_score") -> pd.DataFrame:
    """把「同一作物 × 同一上市窗口」的多个面积变体折叠为一个方案（面积单独决策）。

    面积选择规则（§19/§51）：
      - 若给定 max_acceptable_loss：取满足 worst_case_loss ≤ 容忍度的最大面积；
      - 否则取预算内的最大可行面积（面积不改变单价与风险，只改变敞口规模）；
      - 记录 n_area_options 与 worst_case_loss。
    说明：这不是"生物学最优面积"，而是经营风险约束下的建议面积。
    """
    if not len(df):
        return df
    d = df.copy()
    d["_window"] = (d["crop"].astype(str) + "|" + d["plant_date"].astype(str) + "|" + d["harvest_date"].astype(str))
    d["worst_case_loss"] = np.maximum(0.0, -pd.to_numeric(d["profit_pessimistic"], errors="coerce").fillna(0.0))
    picked = []
    for _, g in d.groupby("_window", sort=False):
        g = g.sort_values("area_mu", ascending=False)
        g_ok = g
        if max_acceptable_loss is not None:
            feas = g[g["worst_case_loss"] <= max_acceptable_loss]
            g_ok = feas if len(feas) else g.tail(1)     # 全部超限 → 取最小敞口并标注
        best = g_ok.iloc[0].copy()
        best["n_area_options"] = len(g)
        best["area_max_feasible"] = float(g["area_mu"].max())
        best["loss_tolerance_ok"] = (None if max_acceptable_loss is None
                                    else bool(best["worst_case_loss"] <= max_acceptable_loss))
        picked.append(best)
    out = pd.DataFrame(picked)
    return out.drop(columns=["_window"]).reset_index(drop=True)


def opportunity_cost(recommended: Dict, alternatives: List[Dict]) -> Dict:
    """§48 机会成本：相对最高收益方案，少赚多少 / 下行改善多少。"""
    if not alternatives:
        return {}
    best_return = max(alternatives, key=lambda r: r.get("profit_baseline") or -np.inf)
    best_down = max(alternatives, key=lambda r: r.get("profit_pessimistic") or -np.inf)
    rec_ret = recommended.get("profit_baseline")
    rec_down = recommended.get("profit_pessimistic")
    out = {
        "best_return_alternative": {"crop": best_return.get("crop"),
                                    "harvest_date": str(best_return.get("harvest_date")),
                                    "area_mu": best_return.get("area_mu"),
                                    "profit_baseline": best_return.get("profit_baseline")},
        "foregone_profit_vs_best_return": (None if (rec_ret is None or best_return.get("profit_baseline") is None)
                                           else round(best_return["profit_baseline"] - rec_ret, 2)),
        "downside_improvement_vs_best_return": (None if (rec_down is None or best_return.get("profit_pessimistic") is None)
                                                else round(rec_down - best_return["profit_pessimistic"], 2)),
        "best_downside_alternative": {"crop": best_down.get("crop"),
                                      "harvest_date": str(best_down.get("harvest_date")),
                                      "profit_pessimistic": best_down.get("profit_pessimistic")},
        "note": "机会成本为情景口径（P50/P10 情景利润），非概率保证",
    }
    return out