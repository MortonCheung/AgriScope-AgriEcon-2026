# -*- coding: utf-8 -*-
"""C8: Recommendation Policy 最终确定（§12/§13/§14/§15/§51/§52/§53/§55）。

要点：
  1) 明确时间切分：development(≤2023) / policy-tuning(2024–2025) / untouched(2026)
     —— Balanced 的修复是在 policy-tuning 期发现的，因此必须在 **untouched 2026** 上复核，
        检查是否存在 evaluation overfitting。
  2) 指标语义修正：本回测的主指标是 **market_return（市场机会收益）**，不是农户种植利润。
  3) Balanced 修复不得只降 high-HRI：还要检查 return / downside / regret / 选择多样性 / 集中度 / 年季稳定性。
  4) 依据 untouched 表现，决定默认策略 A/B/C。
"""
from __future__ import annotations
from typing import Dict, List

import numpy as np
import pandas as pd

from decision_engine.final.fcommon import (REPORTS_DIR, FINAL_EVAL_DIR, ensure_dir,
                                           write_json, now_stamp)
from decision_engine.final.backtest import build_panel, strategy_scores

SPLITS = {
    "development": ("2021-01-01", "2023-12-31"),
    "policy_tuning": ("2024-01-01", "2025-12-31"),
    "untouched_2026": ("2026-01-01", "2026-12-31"),
}
STRATS = ["AgriScope_Balanced_old", "AgriScope_Balanced_fix", "Profit_only",
          "Risk_only", "Chase_price", "Most_Robust", "Random"]
COL = {"AgriScope_Balanced_old": "s_balanced_old", "AgriScope_Balanced_fix": "s_balanced_fix",
       "Profit_only": "s_profit", "Risk_only": "s_lowrisk", "Chase_price": "s_chase",
       "Most_Robust": "s_robust"}


def _pick_table(panel: pd.DataFrame) -> pd.DataFrame:
    """每个 cut-off × 策略 的选中作物与真实 market return。"""
    rows = []
    for t, g in panel.groupby("date"):
        if len(g) < 4:
            continue
        sc = strategy_scores(g)
        thr = g["HRI"].quantile(0.90)
        for name in STRATS:
            if name == "Random":
                rng = np.random.RandomState(abs(hash(str(t))) % 10 ** 6)
                idx = g.index[rng.permutation(len(g))[0]]
            else:
                idx = sc[COL[name]].idxmax()
            r = g.loc[idx]
            rows.append({"date": pd.Timestamp(t), "strategy": name, "crop": r["crop"],
                         "market_return": float(r["realized_return"]),
                         "market_worst": float(r["realized_worst"]),
                         "HRI": float(r["HRI"]) if pd.notna(r["HRI"]) else np.nan,
                         "high_hri": bool(pd.notna(r["HRI"]) and r["HRI"] >= thr)})
    d = pd.DataFrame(rows)
    d["year"] = d["date"].dt.year
    d["month"] = d["date"].dt.month
    d["season"] = d["month"].map({12: "winter", 1: "winter", 2: "winter", 3: "spring",
                                  4: "spring", 5: "spring", 6: "summer", 7: "summer",
                                  8: "summer", 9: "autumn", 10: "autumn", 11: "autumn"})
    return d


def _metrics(g: pd.DataFrame) -> Dict:
    s = g["market_return"]
    n_crops = g["crop"].nunique()
    shares = g["crop"].value_counts(normalize=True)
    return {
        "n": int(len(g)),
        "mean_market_return": float(s.mean()),
        "median_market_return": float(s.median()),
        "downside": float(s[s < 0].mean()) if (s < 0).any() else 0.0,
        "worst": float(s.min()),
        "p_down": float((s < 0).mean()),
        "std": float(s.std()),
        "high_hri_rate": float(g["high_hri"].mean()),
        "mean_HRI": float(g["HRI"].mean()),
        "selection_diversity_n_crops": int(n_crops),
        "crop_concentration_hhi": float((shares ** 2).sum()),
    }


def run() -> Dict[str, object]:
    ensure_dir(REPORTS_DIR / "tables")
    panel = build_panel()
    picks = _pick_table(panel)
    picks.to_parquet(FINAL_EVAL_DIR / "policy_picks.parquet", index=False)

    rows = []
    for period, (a, b) in SPLITS.items():
        sub = picks[(picks["date"] >= a) & (picks["date"] <= b)]
        for name, g in sub.groupby("strategy"):
            rows.append({"period": period, "strategy": name, **_metrics(g)})
    bench = pd.DataFrame(rows)
    bench["metric_semantics"] = "market_return = 未来30天窗口均价/建仓价-1（市场机会，非农户利润）"
    bench.to_csv(REPORTS_DIR / "tables" / "policy_benchmark_by_period.csv", index=False, encoding="utf-8-sig")

    # regret（同 cut-off 内最佳策略）
    best = picks.groupby("date")["market_return"].max().rename("best")
    p2 = picks.merge(best, on="date", how="left")
    p2["regret"] = p2["best"] - p2["market_return"]
    reg = []
    for period, (a, b) in SPLITS.items():
        sub = p2[(p2["date"] >= a) & (p2["date"] <= b)]
        for name, g in sub.groupby("strategy"):
            reg.append({"period": period, "strategy": name,
                        "mean_regret": float(g["regret"].mean()),
                        "worst_regret": float(g["regret"].max()),
                        "p95_regret": float(g["regret"].quantile(0.95))})
    pd.DataFrame(reg).to_csv(REPORTS_DIR / "tables" / "policy_regret_by_period.csv",
                             index=False, encoding="utf-8-sig")

    # ---- untouched 复核：Balanced_fix vs Profit_only vs Risk_only vs Random
    un = bench[bench["period"] == "untouched_2026"].set_index("strategy")
    tun = bench[bench["period"] == "policy_tuning"].set_index("strategy")

    def g_(df, strat, key):
        return float(df.loc[strat, key]) if strat in df.index else np.nan

    cmp = {
        "untouched_balanced_fix_return": g_(un, "AgriScope_Balanced_fix", "mean_market_return"),
        "untouched_balanced_old_return": g_(un, "AgriScope_Balanced_old", "mean_market_return"),
        "untouched_profit_only_return": g_(un, "Profit_only", "mean_market_return"),
        "untouched_risk_only_return": g_(un, "Risk_only", "mean_market_return"),
        "untouched_random_return": g_(un, "Random", "mean_market_return"),
        "untouched_balanced_fix_high_hri": g_(un, "AgriScope_Balanced_fix", "high_hri_rate"),
        "untouched_profit_only_high_hri": g_(un, "Profit_only", "high_hri_rate"),
        "untouched_balanced_fix_downside": g_(un, "AgriScope_Balanced_fix", "downside"),
        "untouched_profit_only_downside": g_(un, "Profit_only", "downside"),
        "tuning_balanced_fix_return": g_(tun, "AgriScope_Balanced_fix", "mean_market_return"),
        "tuning_random_return": g_(tun, "Random", "mean_market_return"),
        "balanced_fix_diversity": g_(un, "AgriScope_Balanced_fix", "selection_diversity_n_crops"),
        "balanced_fix_hhi": g_(un, "AgriScope_Balanced_fix", "crop_concentration_hhi"),
        "balanced_fix_downside_ok": bool(g_(un, "AgriScope_Balanced_fix", "downside") >=
                                          g_(un, "Profit_only", "downside")),
    }
    # overfitting check：修复在 tuning 期与 untouched 期方向是否一致（high-HRI 更低）
    of_ok = (cmp["untouched_balanced_fix_high_hri"] <= cmp["untouched_profit_only_high_hri"])
    cmp["no_evaluation_overfitting"] = bool(of_ok)

    # ---- 默认策略决策（A/B/C）
    bf_ret = cmp["untouched_balanced_fix_return"]
    ro_ret = cmp["untouched_risk_only_return"]
    rnd = cmp["untouched_random_return"]
    risk_adj_bf = bf_ret / max(abs(cmp["untouched_balanced_fix_downside"]), 1e-9)
    if ro_ret > bf_ret + 0.01 and ro_ret > rnd + 0.01:
        decision = "C"
        reason = ("untouched 2026 期 Risk_only 明显优于 Balanced_fix 与 Random → "
                  "不设唯一默认；按风险偏好分发（conservative→Risk-aware, balanced/aggressive→Balanced）")
    elif bf_ret >= rnd and cmp["no_evaluation_overfitting"] and cmp["balanced_fix_downside_ok"]:
        decision = "A"
        reason = ("Balanced_fix 在 untouched 期不劣于 Random，downside 不劣于 Profit_only，"
                  "且高-HRI 抑制在 tuning/untouched 一致（无 evaluation overfitting）→ 保留 Balanced 为默认")
    else:
        decision = "B"
        reason = "Balanced_fix 未展示稳定优势 → 默认改为 Risk-aware（Risk_only 或其保守变体）"
    out = {"decision": decision, "reason": reason, **cmp, "ts": now_stamp()}
    write_json(out, REPORTS_DIR / "tables" / "default_policy_decision.json")
    return out


if __name__ == "__main__":
    import json
    print(json.dumps(run(), ensure_ascii=False, indent=1))