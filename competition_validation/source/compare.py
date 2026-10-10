#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""experiments/analysis/compare.py — 修复前后对照 + 显著性 + 年份稳健性。

输出（写入 experiments/results/analysis/）：
  hri_before_after.csv          逐 crop×window 的 HRI 时序稳健性对照
  hri_summary_before_after.csv  计数对照（raw / robust 显著数）
  strategy_before_after.csv     策略指标对照（旧 vs 修复后）
  strategy_significance.csv     各策略 vs Random_expectation（HAC + 块 bootstrap）
  strategy_by_year.csv          按年份分块的策略表现（稳健性）
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
os.environ.setdefault("PROJECT_ROOT", str(EXP / "root"))
sys.path.insert(0, str(EXP / "code" / "src"))

import numpy as np
import pandas as pd
from scipy import stats

OUT = EXP / "results" / "analysis"
OUT.mkdir(parents=True, exist_ok=True)

A = EXP / "results" / "A00_repro_unpatched" / "exports"
B = EXP / "results" / "B01_fixed" / "exports"
BASE = EXP / "baseline"

SEED, NBOOT = 42, 4000


def circ_block(x: np.ndarray, n: int, block: int, rng) -> np.ndarray:
    m = len(x)
    nb = int(np.ceil(n / block))
    st = rng.randint(0, m, size=nb)
    idx = np.concatenate([(np.arange(s, s + block) % m) for s in st])[:n]
    return x[idx]


def block_boot_ci_p(d: np.ndarray, block: int, n_boot: int = NBOOT, seed: int = SEED):
    d = np.asarray(d, float)
    d = d[np.isfinite(d)]
    if len(d) < 8:
        return np.nan, np.nan, np.nan, np.nan, len(d)
    obs = float(d.mean())
    c = d - obs
    rng = np.random.RandomState(seed)
    bs = np.empty(n_boot)
    for b in range(n_boot):
        bs[b] = circ_block(c, len(d), block, rng).mean()
    lo, hi = np.percentile(bs, [2.5, 97.5])
    # 双侧 p：观测均值在零分布中的位置
    p = float(np.mean(np.abs(bs) >= abs(obs)))
    return obs, float(obs - hi), float(obs - lo), max(p, 1.0 / n_boot), len(d)


def hac_p(d: np.ndarray, lags: int):
    import statsmodels.api as sm
    d = np.asarray(d, float)
    d = d[np.isfinite(d)]
    if len(d) < 8:
        return np.nan, np.nan
    X = np.ones((len(d), 1))
    ols = sm.OLS(d, X).fit(cov_type="HAC", cov_kwds={"maxlags": max(1, lags)})
    return float(ols.tvalues[0]), float(ols.pvalues[0])


# ----------------------------------------------------------------- 1. HRI 对照
def hri_compare():
    def load(p):
        f = p / "tables" / "hri_timeseries_validation.csv"
        return pd.read_csv(f) if f.exists() else pd.DataFrame()
    a, b = load(A), load(B)
    # 旧结果可能只在冻结基线里（A 已复现），优先用 A
    if not len(a):
        a = pd.read_csv(BASE / "hri_timeseries_validation.csv")
    key = ["city", "crop", "window_w"]
    cols = key + ["n_high", "n_low", "mean_diff", "p_raw_overlapping", "p_nonoverlap",
                  "p_block_bootstrap", "hac_p", "nonoverlap_stride", "robust_significant", "raw_significant"]
    m = a[cols].merge(b[cols], on=key, suffixes=("_old", "_new"))
    m.to_csv(OUT / "hri_before_after.csv", index=False, encoding="utf-8-sig")

    rows = []
    for tag, df in [("旧(未修复)", a), ("新(修复后)", b)]:
        for w in [4, 8, 12]:
            s = df[(df.city == "沈阳") & (df.window_w == w)]
            if not len(s):
                continue
            rows.append({"版本": tag, "窗口_周": w, "作物数": len(s),
                         "raw显著数": int(s["raw_significant"].sum()),
                         "robust显著数": int(s["robust_significant"].sum()),
                         "平均p_raw": float(s["p_raw_overlapping"].mean()),
                         "平均p_boot": float(s["p_block_bootstrap"].mean()),
                         "平均p_hac": float(s["hac_p"].mean()),
                         "平均分组差": float(s["mean_diff"].mean())})
    sm = pd.DataFrame(rows)
    sm.to_csv(OUT / "hri_summary_before_after.csv", index=False, encoding="utf-8-sig")
    return sm, m


# ----------------------------------------------------------------- 2. 策略对照
def strategy_compare():
    def bench(p, name):
        f = p / "tables" / name
        return pd.read_csv(f) if f.exists() else pd.DataFrame()
    a = bench(A, "strategy_benchmark.csv")
    if not len(a):
        a = pd.read_csv(BASE / "strategy_benchmark.csv")
    a = a.assign(版本="旧(未修复)")
    b7 = bench(B, "strategy_benchmark_step7.csv").assign(版本="新(step7)")
    b30 = bench(B, "strategy_benchmark_step30.csv").assign(版本="新(step30)")
    allb = pd.concat([a, b7, b30], ignore_index=True)
    keep = ["版本", "cutoff_step_days", "strategy", "n", "mean_market_return", "median_market_return",
            "downside", "worst_market_return", "p_down", "win_rate", "high_hri_rate",
            "mean_regret", "stability"]
    keep = [c for c in keep if c in allb.columns]
    allb[keep].to_csv(OUT / "strategy_before_after.csv", index=False, encoding="utf-8-sig")
    return allb


# ----------------------------------------------------------------- 3. 显著性 + 年份稳健性
def strategy_significance_and_year():
    def load_bt(p, name):
        f = p / "eval" / name
        return pd.read_parquet(f) if f.exists() else None
    out_sig, out_year = [], []
    sets = [("旧(未修复)", load_bt(A, "strategy_backtest.parquet")),
            ("新(step7)", load_bt(B, "strategy_backtest_step7.parquet")),
            ("新(step30)", load_bt(B, "strategy_backtest_step30.parquet"))]
    for tag, bt in sets:
        if bt is None:
            continue
        bt = bt.copy()
        bt["date"] = pd.to_datetime(bt["date"])
        bt["year"] = bt["date"].dt.year
        piv = bt.pivot_table(index="date", columns="strategy",
                             values="realized_return", aggfunc="first").sort_index()
        if "Random_expectation" not in piv.columns:
            continue
        ref = piv["Random_expectation"]
        lags = max(1, int(round(len(piv) / 10)))   # 切点步长使相邻样本近似非重叠
        for s in piv.columns:
            if s == "Random_expectation":
                continue
            d = (piv[s] - ref).dropna().values
            mean, lo, hi, p_boot, n = block_boot_ci_p(d, block=3)
            t_hac, p_hac = hac_p(d, lags)
            out_sig.append({"版本": tag, "策略": s, "n切点": n,
                            "相对Random均值": mean, "CI下": lo, "CI上": hi,
                            "块bootstrap_p": p_boot, "HAC_t": t_hac, "HAC_p": p_hac,
                            "显著(两项同时<0.05)": bool(p_boot < 0.05 and p_hac < 0.05)})
        # 年份稳健性：策略均值（含 Random 参照）
        for y, g in bt.groupby("year"):
            for s, sub in g.groupby("strategy"):
                out_year.append({"版本": tag, "年份": int(y), "策略": s, "n": int(len(sub)),
                                 "平均市场收益": float(sub["realized_return"].mean()),
                                 "下跌概率": float((sub["realized_return"] < 0).mean()),
                                 "高HRI命中率": float(sub["high_hri"].mean())})
    pd.DataFrame(out_sig).to_csv(OUT / "strategy_significance.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(out_year).to_csv(OUT / "strategy_by_year.csv", index=False, encoding="utf-8-sig")
    return pd.DataFrame(out_sig), pd.DataFrame(out_year)


# ----------------------------------------------------------------- 4. 年度稳健性：HRI 分组差按年
def hri_by_year():
    rows = []
    for tag, p in [("旧(未修复)", A), ("新(修复后)", B)]:
        f = p / "eval" / "hri_weekly_沈阳.parquet"
        if not f.exists():
            continue
        h = pd.read_parquet(f)
        h = h[h["HRI"].notna()]
        for w in [4, 8, 12]:
            fc = f"fwd_{w}w"
            if fc not in h.columns:
                continue
            for y, g in h.groupby("iso_year"):
                hi = g[g.hri_pct >= 80][fc].dropna()
                lo = g[g.hri_pct <= 50][fc].dropna()
                if len(hi) < 10 or len(lo) < 10:
                    continue
                rows.append({"版本": tag, "年份": int(y), "窗口_周": w,
                             "n_high": len(hi), "n_low": len(lo),
                             "分组差": float(hi.mean() - lo.mean()),
                             "p_raw": float(stats.mannwhitneyu(hi, lo, alternative="two-sided")[1])})
    d = pd.DataFrame(rows)
    d.to_csv(OUT / "hri_by_year.csv", index=False, encoding="utf-8-sig")
    return d


if __name__ == "__main__":
    print("A exports:", A.exists(), "| B exports:", B.exists())
    sm, _ = hri_compare()
    print("\n== HRI 时序稳健性对照（沈阳）==")
    print(sm.to_string(index=False))
    allb = strategy_compare()
    print("\n== 策略对照（旧 step7/全部日期 vs 新 step7 vs 新 step30）==")
    sel = allb[allb["strategy"].isin(["Balanced_old", "Balanced_fix_v1", "Balanced_fix_v2",
                                      "Profit_only", "Highest_forecast_return",
                                      "Highest_price_level", "Chase_price", "Chase_price_momentum",
                                      "Risk_only", "Low_risk", "Random", "Random_seeded",
                                      "Random_expectation"])]
    print(sel[["版本", "cutoff_step_days", "strategy", "n", "mean_market_return",
               "p_down", "high_hri_rate"]].to_string(index=False))
    sig, yr = strategy_significance_and_year()
    print("\n== 策略显著性（vs Random_expectation）==")
    print(sig[sig["版本"] == "新(step30)"].sort_values("相对Random均值", ascending=False).to_string(index=False))
    hy = hri_by_year()
    print("\n== HRI 分组差（年份稳健性，窗口=12）==")
    print(hy[hy["窗口_周"] == 12].to_string(index=False))
    print("\nwritten ->", OUT)
