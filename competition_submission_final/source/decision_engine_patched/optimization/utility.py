# -*- coding: utf-8 -*-
"""Phase 4 / §13-§15: 多目标效用函数（透明、可解释、可敏感性分析）。

设计：
  - 各分量先标准化到 [0,1]（收益类用池内百分位排名，风险类用 /100）；
  - utility = w_ret·U(ROI_base) + w_down·U(ROI_pess) + w_conf·U(confidence)
              − ( w_mr·MR + w_hr·HRI + w_cl·CL )；
  - 三套透明权重（conservative / balanced / aggressive），**只改排序，不改客观量**；
  - 不混合「元 / 0-100 风险 / 概率」的原始尺度。

风险偏好不改变 price / HRI / market risk / climate exposure 的数值（客观量），
仅改变效用聚合权重。
"""
from __future__ import annotations
from typing import Dict, List

import numpy as np
import pandas as pd

# Final Model 修正（2026-10-07，Balanced 根因 = 情况 C）：
#   旧实现中收益/下行用「池内百分位」，而 market/HRI/climate 用「绝对值 /100」线性缩放
#   → HRI 分布聚集（多在 40–60）时惩罚几乎不区分候选，且高价（高 HRI）作物往往同时
#     有高收益预期，导致 Balanced 反而比 Profit-only 更追高（旧实测 13.0% > 8.7%）。
#   修正：风险分量统一改为**池内百分位**（可区分、量纲与收益项一致），并提高负项权重。
#   权重仍满足 Σ=1（保持 test_utility 约束）。
PREFERENCE_WEIGHTS = {
    # 正项：收益 / 下行 / 置信；负项：市场风险 / 跟风 / 气候
    "conservative": {"ret": 0.15, "down": 0.32, "conf": 0.08,
                     "market": 0.20, "herding": 0.18, "climate": 0.07},
    "balanced":     {"ret": 0.30, "down": 0.18, "conf": 0.07,
                     "market": 0.20, "herding": 0.20, "climate": 0.05},
    "aggressive":   {"ret": 0.42, "down": 0.10, "conf": 0.05,
                     "market": 0.18, "herding": 0.18, "climate": 0.07},
}


def _pct_rank(s: pd.Series) -> pd.Series:
    """稳健标准化：池内百分位（对异常值不敏感）。"""
    v = pd.to_numeric(s, errors="coerce")
    return v.rank(pct=True, na_option="bottom").fillna(0.5)


def _pct_rank_neutral(s: pd.Series) -> pd.Series:
    """池内百分位；缺失 → 0.5（中性），不把缺失当作「低风险」。"""
    v = pd.to_numeric(s, errors="coerce")
    return v.rank(pct=True, na_option="keep").fillna(0.5)


def normalize_components(df: pd.DataFrame) -> pd.DataFrame:
    d = pd.DataFrame(index=df.index)
    d["ret_norm"] = _pct_rank(df["roi_baseline"])
    d["down_norm"] = _pct_rank(df["roi_pessimistic"])
    d["conf_norm"] = (pd.to_numeric(df["confidence_score"], errors="coerce") / 100).clip(0, 1).fillna(0.5)
    # 风险分量：统一池内百分位（Final 修正，见上）
    for src, dst in [("market_risk", "market_norm"), ("HRI", "herding_norm"), ("climate_risk", "climate_norm")]:
        d[dst] = _pct_rank_neutral(df[src]) if src in df.columns else 0.5
    return d


COST_RELIABILITY = {"user_input": 1.0, "observed_city": 0.80, "neighboring_city": 0.60,
                    "observed_city_aggregate": 0.60, "regional_proxy": 0.40,
                    "sector_proxy": 0.35, "cross_city_proxy": 0.35}
YIELD_RELIABILITY = {"user_input": 1.0, "observed_city_county_crop": 0.90,
                     "observed_city_aggregate": 0.60, "cross_city_proxy": 0.40,
                     "neighboring_city": 0.50}


def reliability_factor(df: pd.DataFrame) -> pd.Series:
    """数据可靠性系数（0-1）：proxy 口径不应与用户实测同权（§6/§60）。"""
    def _r(level_col, table, default):
        if level_col not in df.columns:
            return pd.Series(default, index=df.index)
        return df[level_col].map(table).fillna(default)
    c = _r("cost_level", COST_RELIABILITY, 0.5)
    y = _r("yield_level", YIELD_RELIABILITY, 0.5)
    return (0.5 * c + 0.5 * y).clip(0.2, 1.0)


def utility_scores(df: pd.DataFrame, preference: str = "balanced",
                   weights_override: Dict[str, float] | None = None) -> pd.Series:
    if preference not in PREFERENCE_WEIGHTS:
        preference = "balanced"
    w = dict(PREFERENCE_WEIGHTS[preference])
    if weights_override:
        w.update(weights_override)
    c = normalize_components(df)
    rel = reliability_factor(df)
    # 置信度奖励按数据可靠性缩水：proxy 成本/亩产不能享受满额置信收益
    pos = w["ret"] * c["ret_norm"] + w["down"] * c["down_norm"] + w["conf"] * c["conf_norm"] * rel
    neg = w["market"] * c["market_norm"] + w["herding"] * c["herding_norm"] + w["climate"] * c["climate_norm"]
    return (pos - neg).rename("utility_score")


def utility_report(df: pd.DataFrame) -> pd.DataFrame:
    """加入三套偏好的 utility 与分量拆解（用于解释与敏感性）。"""
    d = df.copy()
    comp = normalize_components(d)
    for pref in PREFERENCE_WEIGHTS:
        d[f"utility_{pref}"] = utility_scores(d, pref)
    # 主 utility 由候选自身风险偏好决定（缺省 balanced）
    if "risk_preference" in d.columns:
        d["utility_score"] = [
            d.at[i, f"utility_{p if p in PREFERENCE_WEIGHTS else 'balanced'}"]
            for i, p in d["risk_preference"].items()]
    else:
        d["utility_score"] = d["utility_balanced"]
    for k, v in comp.items():
        d[f"norm_{k}"] = v
    d["data_reliability"] = reliability_factor(d)
    # 主导项（绝对贡献最大的三个），供解释层使用
    doms = []
    for i in d.index:
        pref = d.at[i, "risk_preference"] if "risk_preference" in d.columns else "balanced"
        w = PREFERENCE_WEIGHTS.get(pref, PREFERENCE_WEIGHTS["balanced"])
        contrib = {
            "+收益": w["ret"] * comp.at[i, "ret_norm"],
            "+下行保护": w["down"] * comp.at[i, "down_norm"],
            "+置信度(按数据可靠性)": w["conf"] * comp.at[i, "conf_norm"] * d.at[i, "data_reliability"],
            "−市场风险": -w["market"] * comp.at[i, "market_norm"],
            "−跟风风险": -w["herding"] * comp.at[i, "herding_norm"],
            "−气候暴露": -w["climate"] * comp.at[i, "climate_norm"],
        }
        top = sorted(contrib.items(), key=lambda kv: -abs(kv[1]))[:3]
        doms.append([{"component": k, "contribution": round(float(v), 4)} for k, v in top])
    d["utility_drivers"] = doms
    return d


def weight_sensitivity(df: pd.DataFrame, preference: str = "balanced",
                       n_draws: int = 200, jitter: float = 0.10, seed: int = 42,
                       top_k: int = 3) -> Dict:
    """§15 权重敏感性：±jitter 抖动下排名稳定性（Spearman + TopK 重合率）。"""
    from scipy import stats
    base = utility_scores(df, preference)
    order_base = base.rank(ascending=False)
    top_base = set(order_base.nsmallest(top_k).index)
    rng = np.random.RandomState(seed)
    rhos, overlaps = [], []
    for _ in range(n_draws):
        jw = {k: v * (1 + rng.uniform(-jitter, jitter)) for k, v in PREFERENCE_WEIGHTS[preference].items()}
        s = utility_scores(df, preference, weights_override=jw)
        rho = stats.spearmanr(base.values, s.values)[0]
        if np.isfinite(rho):
            rhos.append(float(rho))
        top = set(s.rank(ascending=False).nsmallest(top_k).index)
        overlaps.append(len(top & top_base) / top_k)
    sep = float(base.max() - base.sort_values(ascending=False).iloc[1]) if len(base) > 1 else np.nan
    within_eps = int((base >= base.max() - 0.02).sum())
    return {
        "preference": preference, "n_draws": n_draws, "jitter": jitter,
        "spearman_mean": float(np.mean(rhos)), "spearman_p05": float(np.percentile(rhos, 5)),
        "topk_overlap_mean": float(np.mean(overlaps)),
        "top1_minus_top2_utility": round(sep, 4),
        "n_within_0.02_of_best": within_eps,
        "stable": bool(np.mean(rhos) >= 0.95 and np.mean(overlaps) >= 0.66),
    }