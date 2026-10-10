#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""experiments/analysis/final_strategy_comparison.py — 定稿前最后一项策略比较。

比较 7 个策略（冻结定义，不改权重、不调参、不重选切点）：
  Seasonal / Highest_forecast_return / Balanced_fix_v2 / Most_Robust /
  Random(=均匀随机期望) / Risk_only / Chase_price_momentum

两类检验：
  (1) 各策略 vs Random（族大小 k=6）
  (2) 重点配对：Highest_forecast_return / Balanced_fix_v2 分别 − Seasonal / Most_Robust（族大小 k=4）
推断：step30（不重叠）block=1 / HAC lag=1；
      step7 （30 天窗口按 7 天步长重叠）block=ceil(30/7)=5 / HAC lag=5；
      并对 block∈{1,3,5,10}、lag∈{1,3,5,8} 做敏感性；多重比较用 Bonferroni 与 BH-FDR。

输出 -> experiments/results/strategy_final/*.csv
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
DE_SRC = Path(os.environ.get("EXPERIMENTS_DE_SRC", EXP / "code" / "src"))
os.environ.setdefault("PROJECT_ROOT", str(EXP / "root"))
sys.path.insert(0, str(DE_SRC))
sys.path.insert(0, str(HERE))

import numpy as np
import pandas as pd

import audit_final as AF  # 复用同一推断与打分实现

# 确保 decision_engine 从指定代码树解析（audit_final 可能已插入默认路径）
sys.path[:] = [p for p in sys.path if str(EXP / "code" / "src") not in str(p)
               and str(EXP / "code_prev" / "src") not in str(p)]
sys.path.insert(0, str(DE_SRC))
OUT = Path(os.environ.get("OUTDIR", str(EXP / "results" / "strategy_final")))
OUT.mkdir(parents=True, exist_ok=True)

STRATS7 = ["Seasonal", "Highest_forecast_return", "Balanced_fix_v2", "Most_Robust",
           "Low_risk", "Chase_price_momentum"]
# 多重比较家族取**论文将报告的全部策略**（避免“家族挑选”）：k=9
STRATS_FAMILY = STRATS7 + ["Balanced_old", "Balanced_fix_v1", "Highest_price_level"]
PRIMARY_BLOCK = {7: 5, 30: 1}      # 重叠感知：step7 用 5，step30 用 1
PRIMARY_LAG = {7: 5, 30: 1}
BLOCKS = [1, 3, 5, 10]
LAGS = [1, 3, 5, 8]
PAIRS = [("Highest_forecast_return", "Seasonal"),
         ("Highest_forecast_return", "Most_Robust"),
         ("Balanced_fix_v2", "Seasonal"),
         ("Balanced_fix_v2", "Most_Robust")]


def paired_stats(d, block, lag, n_boot=4000, seed=AF.SEED):
    d = np.asarray(d, float)
    d = d[np.isfinite(d)]
    n = len(d)
    if n < 8:
        return dict(n=n)
    mean = float(d.mean())
    sd = float(d.std(ddof=1))
    cohen_d = mean / sd if sd > 0 else np.nan
    t_hac, p_hac = AF.hac(d, lag)
    _, lo, hi, p_boot = AF.boot_ci_p(d, block, n_boot=n_boot, seed=seed)
    # 配对 Wilcoxon（符号秩）作为分布无关参照
    from scipy import stats as st
    try:
        _, p_wil = st.wilcoxon(d, alternative="two-sided")
    except Exception:
        p_wil = np.nan
    return dict(n=n, mean_diff=mean, sd_diff=sd, cohen_d=cohen_d,
                ci_lo=lo, ci_hi=hi, hac_t=t_hac, p_hac=p_hac,
                p_boot=p_boot, p_wilcoxon=float(p_wil))


def build_records():
    from decision_engine.final.backtest import build_panel, _select_cutoffs
    panel = build_panel()
    out = {}
    for step in (7, 30):
        dates = _select_cutoffs(sorted(panel["date"].unique()), step)
        rec = pd.concat([AF.run_family(panel, dates, AF.new_scores, AF.NEW_STRATS, "new"),
                         AF.expectation_records(panel, dates, "new")], ignore_index=True)
        rec["cutoff_step_days"] = step
        out[step] = rec
        rec.to_csv(OUT / f"records_step{step}.csv", index=False, encoding="utf-8-sig")
    return panel, out


def levels_table(rec, step):
    rows = []
    for s, sub in rec.groupby("strategy"):
        r = np.asarray(sub["realized_return"], float)
        rows.append({"cutoff_step_days": step, "strategy": s, "n": len(r),
                     "mean_market_return": float(r.mean()),
                     "median_market_return": float(np.median(r)),
                     "downside": float(r[r < 0].mean()) if (r < 0).any() else 0.0,
                     "worst": float(r.min()),
                     "p05": float(np.quantile(r, 0.05)),
                     "p_down": float((r < 0).mean()),
                     "std": float(r.std(ddof=1)),
                     "high_hri_rate": float(sub["high_hri"].mean())})
    return pd.DataFrame(rows).sort_values("mean_market_return", ascending=False)


def compare_family(rec, step, family):
    """family: list of (name, seriesA, seriesB) 形式的配对定义。"""
    piv = rec.pivot_table(index="date", columns="strategy", values="realized_return", aggfunc="first").sort_index()
    rows = []
    for a, b in family:
        if a not in piv.columns or b not in piv.columns:
            continue
        d = (piv[a] - piv[b]).dropna().values
        st = paired_stats(d, PRIMARY_BLOCK[step], PRIMARY_LAG[step])
        for blk in BLOCKS:
            st[f"p_boot_block{blk}"] = AF.boot_ci_p(d, blk, n_boot=2000)[3]
        for lag in LAGS:
            st[f"p_hac_lag{lag}"] = AF.hac(d, lag)[1]
        st.update({"cutoff_step_days": step, "strategy_A": a, "strategy_B": b})
        rows.append(st)
    df = pd.DataFrame(rows)
    k = len(df)
    df["p_boot_max"] = df[[f"p_boot_block{b}" for b in BLOCKS]].max(axis=1)
    df["p_hac_max"] = df[[f"p_hac_lag{l}" for l in LAGS]].max(axis=1)
    df["bonferroni_p_boot_max"] = np.minimum(1, df["p_boot_max"] * k)
    df["bonferroni_p_hac_max"] = np.minimum(1, df["p_hac_max"] * k)
    df["bonferroni_p_primary"] = np.minimum(1, np.maximum(df["p_boot"], df["p_hac"]) * k)
    df["bh_fdr_boot"] = AF.bh_fdr(df["p_boot"].values)
    df["bh_fdr_hac"] = AF.bh_fdr(df["p_hac"].values)
    df["显著_未校正(主设定)"] = (df["p_boot"] < 0.05) & (df["p_hac"] < 0.05)
    df["显著_保守Bonferroni"] = (df["bonferroni_p_boot_max"] < 0.05) & (df["bonferroni_p_hac_max"] < 0.05)
    df["显著_BH-FDR"] = (df["bh_fdr_boot"] < 0.05) & (df["bh_fdr_hac"] < 0.05)
    return df


if __name__ == "__main__":
    panel, recs = build_records()
    print(f"panel rows={len(panel)} dates={panel['date'].nunique()}")

    lv = pd.concat([levels_table(recs[s], s) for s in (7, 30)], ignore_index=True)
    lv.to_csv(OUT / "strategy_levels.csv", index=False, encoding="utf-8-sig")
    print("\n=== 策略水平（含风险指标）===")
    for s in (7, 30):
        print(f"\n[step{s}]")
        print(lv[lv.cutoff_step_days == s].round(4).to_string(index=False))

    # 族1：各策略 vs Random（家族 k=9，含论文将报告的全部策略）
    fam1 = [(s, "Random_expectation") for s in STRATS_FAMILY]
    c1 = pd.concat([compare_family(recs[s], s, fam1) for s in (7, 30)], ignore_index=True)
    c1.to_csv(OUT / "compare_vs_random.csv", index=False, encoding="utf-8-sig")
    print("\n=== 族1：策略 vs 均匀随机（家族 k=9）===")
    cols = ["cutoff_step_days", "strategy_A", "n", "mean_diff", "cohen_d", "ci_lo", "ci_hi",
            "p_boot", "p_hac", "bonferroni_p_boot_max", "bonferroni_p_hac_max",
            "显著_保守Bonferroni", "显著_BH-FDR"]
    print(c1[cols].round(4).to_string(index=False))
    # k=6 敏感性（仅 6 个被点名策略）
    k6 = c1[c1["strategy_A"].isin(STRATS7)].copy()
    k6["bonferroni_k6_boot"] = np.minimum(1, k6["p_boot_max"] * 6)
    k6["bonferroni_k6_hac"] = np.minimum(1, k6["p_hac_max"] * 6)
    k6["显著_k6"] = (k6["bonferroni_k6_boot"] < 0.05) & (k6["bonferroni_k6_hac"] < 0.05)
    k6[["cutoff_step_days", "strategy_A", "mean_diff", "p_boot_max", "p_hac_max",
        "bonferroni_k6_boot", "bonferroni_k6_hac", "显著_k6"]].to_csv(
        OUT / "compare_vs_random_k6_sensitivity.csv", index=False, encoding="utf-8-sig")

    # 族2：重点配对
    c2 = pd.concat([compare_family(recs[s], s, PAIRS) for s in (7, 30)], ignore_index=True)
    c2.to_csv(OUT / "compare_pairs.csv", index=False, encoding="utf-8-sig")
    print("\n=== 族2：重点配对（k=4）===")
    cols2 = ["cutoff_step_days", "strategy_A", "strategy_B", "n", "mean_diff", "cohen_d",
             "ci_lo", "ci_hi", "p_boot", "p_hac", "p_wilcoxon",
             "bonferroni_p_primary", "bh_fdr_boot", "显著_保守Bonferroni", "显著_BH-FDR"]
    print(c2[cols2].round(4).to_string(index=False))
    print("\nwritten ->", OUT)
