# -*- coding: utf-8 -*-
"""Phase 10 / §40-§46: 历史推荐回测 + 决策政策基准 + 跟风抑制评估。

严格 point-in-time：每个历史 cutoff 只用 <= T 的数据（复用 v1 的 as_of 机制）。
对比政策：
  Policy A  只追求预测利润（utility = 收益最大化）
  Policy B  只追求低风险（最小化风险综合）
  Policy C  AgriScope Balanced（本项目效用）
  Policy D  Seasonal / naive（历史同月最优 / 当前价格最高）
另加：Random（固定种子）、Top1 / Top3 平均。

指标：realized return、downside、max drawdown、hit rate（区间命中）、regret。
"""
from __future__ import annotations
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from decision_engine.common import de_path
from decision_engine.recommendation import candidates as CG
from decision_engine.recommendation.evaluate_candidates import CandidateEvaluator
from decision_engine.recommendation.recommender import recommend_plans
from decision_engine.optimization import utility as U
from decision_engine.optimization import ranking as RK

REPLAY_AREA_MU = 60.0
REPLAY_BUDGET = 300000.0


# ---------------------------------------------------------------- 实现收益计算
def _price_series(city: str, crop: str) -> pd.Series:
    if city == "沈阳":
        ds = pd.read_parquet(de_path("data", "processed", "decision_dataset_v1.parquet"),
                             columns=["date", "crop", "price_per_kg"])
    else:
        p = de_path("data", "features", f"regional_{city}.parquet")
        if not p.exists():
            return pd.Series(dtype=float)
        ds = pd.read_parquet(p, columns=["date", "crop", "price_per_kg"])
    ds["date"] = pd.to_datetime(ds["date"])
    s = ds[ds["crop"] == crop].set_index("date")["price_per_kg"].sort_index()
    return s


def realized_outcome(city: str, crop: str, harvest_start, harvest_end,
                     cost_per_mu: float, yield_per_mu: float, area_mu: float) -> Optional[Dict]:
    """未来真实结果（仅用于评价，不进入任何输入）。"""
    hs, he = pd.Timestamp(harvest_start), pd.Timestamp(harvest_end)
    s = _price_series(city, crop)
    if s.empty:
        return None
    win = s[(s.index >= hs) & (s.index <= he)]
    if len(win) < 3:
        return None
    mean_p = float(win.mean())
    profit = area_mu * (yield_per_mu * mean_p - cost_per_mu)
    return {"realized_price_mean": mean_p, "realized_price_min": float(win.min()),
            "realized_price_max": float(win.max()), "realized_profit": profit,
            "realized_return_per_mu": yield_per_mu * mean_p - cost_per_mu}


def _policy_pick(plans: pd.DataFrame, policy: str, seed: int = 42) -> pd.DataFrame:
    if policy == "A_profit_only":
        return plans.sort_values("profit_baseline", ascending=False)
    if policy == "B_risk_only":
        return plans.assign(_r=plans["HRI"].fillna(50) + plans["market_risk"].fillna(50)
                            + plans["climate_risk"].fillna(50)).sort_values("_r")
    if policy == "C_agriscope_balanced":
        return plans.sort_values("utility_score", ascending=False)
    if policy == "D_naive_highest_price":
        # 当期市场价格最高的作物（last-value naive 推荐）
        col = "price_latest" if "price_latest" in plans.columns else "price_mid"
        return plans.sort_values(col, ascending=False)
    if policy == "D_seasonal_best_month":
        # 历史同月 P50 最高的作物（季节基线推荐）
        return plans.sort_values("price_mid", ascending=False)
    if policy == "Random":
        rng = np.random.RandomState(seed)
        return plans.iloc[rng.permutation(len(plans))]
    return plans.sort_values("utility_score", ascending=False)


def backtest_recommender(city: str = "沈阳", cutoffs: Optional[List[str]] = None,
                         horizon_days: int = 150, step_days: int = 30,
                         risk_preference: str = "balanced",
                         policies: Optional[List[str]] = None,
                         max_candidates: int = 240, verbose: bool = True) -> Dict:
    ds = pd.read_parquet(de_path("data", "processed", "decision_dataset_v1.parquet"),
                         columns=["date"]) if city == "沈阳" else pd.read_parquet(
        de_path("data", "features", f"regional_{city}.parquet"), columns=["date"])
    ds["date"] = pd.to_datetime(ds["date"])
    data_end = ds["date"].max()
    if cutoffs is None:
        first = pd.Timestamp("2024-06-01")
        last = data_end - pd.Timedelta(days=horizon_days)
        cur, cutoffs = first, []
        while cur <= last:
            cutoffs.append(str(cur.date()))
            cur += pd.Timedelta(days=step_days)

    policies = policies or ["C_agriscope_balanced", "A_profit_only", "B_risk_only",
                            "D_naive_highest_price", "Random"]
    rows = []
    for T in cutoffs:
        rec = recommend_plans(city=city, available_area_mu=REPLAY_AREA_MU, budget=REPLAY_BUDGET,
                              earliest_plant_date=str((pd.Timestamp(T) + pd.Timedelta(days=10)).date()),
                              latest_harvest_date=str((pd.Timestamp(T) + pd.Timedelta(days=horizon_days)).date()),
                              risk_preference=risk_preference, mode="single", as_of=T,
                              run_stress=False, max_candidates=max_candidates)
        if rec.get("status") != "ok":
            if verbose:
                print(f"[rec-bt] {T}: {rec.get('status')}")
            continue
        # 用同一候选池重算政策排序（保证公平：同一批候选、同一评估）
        gen = CG.generate_candidate_plans(
            city=city, available_area_mu=REPLAY_AREA_MU, budget=REPLAY_BUDGET,
            earliest_plant_date=str((pd.Timestamp(T) + pd.Timedelta(days=10)).date()),
            latest_harvest_date=str((pd.Timestamp(T) + pd.Timedelta(days=horizon_days)).date()),
            risk_preference=risk_preference, max_candidates=max_candidates)
        ev = CandidateEvaluator(as_of=T)
        df = ev.evaluate_many(gen["candidates"], verbose=False)
        ok = df[df["evaluable"]].copy()
        if not len(ok):
            continue
        plans = U.utility_report(RK.collapse_area_variants(ok, 0.25 * REPLAY_BUDGET))
        for pol in policies:
            ranked = _policy_pick(plans, pol, seed=abs(hash((city, pol, T))) % (10 ** 6))
            for rank_label, k in [("top1", 1), ("top3", min(3, len(ranked)))]:
                sel = ranked.head(k)
                outs = []
                for _, r in sel.iterrows():
                    o = realized_outcome(city, r["crop"], r["harvest_start"], r["harvest_date"],
                                         float(r["cost_per_mu"]), float(r["expected_yield_per_mu"]),
                                         float(r["area_mu"]))
                    if o:
                        outs.append({**o, "crop": r["crop"], "harvest_date": str(r["harvest_date"]),
                                     "area_mu": float(r["area_mu"]), "price_low": r["price_low"],
                                     "price_high": r["price_high"], "price_mid": r["price_mid"],
                                     "profit_baseline": r["profit_baseline"],
                                     "profit_pessimistic": r["profit_pessimistic"],
                                     "HRI": r["HRI"], "market_risk": r["market_risk"],
                                     "climate_risk": r["climate_risk"],
                                     "utility_score": r["utility_score"],
                                     "decision_score": r["decision_score"],
                                     "confidence": r["confidence_score"],
                                     "plant_date": str(r["plant_date"])})
                if not outs:
                    continue
                realized_profit = float(np.mean([o["realized_profit"] for o in outs]))
                rows.append({
                    "cutoff": T, "policy": pol, "rank": rank_label, "n_plans": len(outs),
                    "crops": ";".join(o["crop"] for o in outs),
                    "realized_profit_mean": realized_profit,
                    "realized_return_per_mu_mean": float(np.mean([o["realized_return_per_mu"] for o in outs])),
                    "predicted_profit_mean": float(np.mean([o["profit_baseline"] for o in outs])),
                    "prediction_error_mean": float(np.mean([o["realized_profit"] - o["profit_baseline"] for o in outs])),
                    "downside_gap_mean": float(np.mean([o["realized_profit"] - o["profit_pessimistic"] for o in outs])),
                    "worst_price_ratio": float(np.mean([o["realized_price_min"] / max(o["price_mid"], 1e-9) for o in outs])),
                    "hit_rate": float(np.mean([(o["price_low"] <= o["realized_price_mean"] <= o["price_high"]) for o in outs])),
                    "HRI_mean": float(np.mean([o["HRI"] for o in outs if o["HRI"] is not None])) if any(o["HRI"] is not None for o in outs) else None,
                    "market_risk_mean": float(np.mean([o["market_risk"] for o in outs if o["market_risk"] is not None])) if any(o["market_risk"] is not None for o in outs) else None,
                    "climate_risk_mean": float(np.mean([o["climate_risk"] for o in outs if o["climate_risk"] is not None])) if any(o["climate_risk"] is not None for o in outs) else None,
                    "confidence_mean": float(np.mean([o["confidence"] for o in outs])),
                })
        if verbose:
            print(f"[rec-bt] {T}: candidates={len(ok)} plans={len(plans)}", flush=True)
    bt = pd.DataFrame(rows)
    if not len(bt):
        return {"status": "no_results", "backtest": bt}
    # regret：同一 cutoff 内最佳政策实现利润 − 该政策实现利润
    best = bt[bt["rank"] == "top1"].groupby("cutoff")["realized_profit_mean"].max().rename("best")
    bt = bt.merge(best, on="cutoff", how="left")
    bt["regret"] = bt["best"] - bt["realized_profit_mean"]
    summary = (bt.groupby(["policy", "rank"])
               .agg(realized_profit_mean=("realized_profit_mean", "mean"),
                    downside_gap_mean=("downside_gap_mean", "mean"),
                    hit_rate=("hit_rate", "mean"),
                    mean_regret=("regret", "mean"),
                    HRI_mean=("HRI_mean", "mean"),
                    market_risk_mean=("market_risk_mean", "mean"),
                    confidence_mean=("confidence_mean", "mean"),
                    n_cutoffs=("cutoff", "count"))
               .reset_index())
    return {"status": "ok", "backtest": bt, "summary": summary}


def herding_suppression(bt: pd.DataFrame) -> pd.DataFrame:
    """§43/§44：High-HRI 推荐率（profit-only vs balanced）。"""
    if not len(bt):
        return pd.DataFrame()
    d = bt[bt["rank"] == "top1"].copy()
    # 用作物 HRI 的历史 P90 作为门限（此处用批次内分位近似，报告里注明）
    thr = d["HRI_mean"].quantile(0.90)
    d["high_hri_pick"] = d["HRI_mean"] >= thr
    out = (d.groupby("policy").agg(high_hri_rate=("high_hri_pick", "mean"),
                                   mean_HRI=("HRI_mean", "mean"),
                                   n=("cutoff", "count")).reset_index())
    out["threshold_used"] = round(float(thr), 2)
    out["note"] = "High-HRI 推荐率 = 推荐方案 HRI 处于批次 P90 以上的比例；用于检验是否抑制盲目追高"
    return out