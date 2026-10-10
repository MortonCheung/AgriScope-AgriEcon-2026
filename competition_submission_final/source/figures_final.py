#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""experiments/analysis/figures_final.py — 权威结果的论文图表（修复后）。

输出 -> experiments/results/figures_final/*.png
"""
from __future__ import annotations
import os
from pathlib import Path

EXP = Path(__file__).resolve().parent.parent
V = EXP / "results" / "validation" / "fixed"
A = EXP / "results" / "audit_fixed"
OUT = EXP / "results" / "figures_final"
OUT.mkdir(parents=True, exist_ok=True)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

for f in ["Arial Unicode MS", "PingFang SC", "Heiti TC", "STHeiti", "Songti SC"]:
    try:
        matplotlib.font_manager.findfont(f, fallback_to_default=False)
        plt.rcParams["font.family"] = f
        break
    except Exception:
        continue
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 150

NAME_CN = {
    "Seasonal": "季节策略", "Highest_forecast_return": "相对收益策略",
    "Balanced_fix_v2": "风险平衡策略", "Most_Robust": "最小尾部风险策略",
    "Low_risk": "低风险策略", "Chase_price_momentum": "追涨策略",
    "Highest_price_level": "最高价策略", "Balanced_old": "旧风险平衡",
    "Balanced_fix_v1": "风险平衡v1",
}

# ---------------- 图1：HRI 分年分组差（12 周，修复后）
h = pd.read_parquet(EXP / "results" / "B02_pit_fixed" / "exports" / "eval" / "hri_weekly_沈阳.parquet")
h = h[h["HRI"].notna()]
from scipy import stats
rows = []
for y, g in h.groupby("iso_year"):
    hi = g[g.hri_pct >= 80]["fwd_12w"].dropna()
    lo = g[g.hri_pct <= 50]["fwd_12w"].dropna()
    if len(hi) < 10 or len(lo) < 10:
        continue
    rows.append({"year": int(y), "diff": float(hi.mean() - lo.mean()),
                 "p": float(stats.mannwhitneyu(hi, lo, alternative="two-sided")[1]),
                 "n_hi": len(hi), "n_lo": len(lo)})
d1 = pd.DataFrame(rows)
fig, ax = plt.subplots(figsize=(7.0, 3.6))
xv = np.arange(len(d1))
ax.bar(xv, d1["diff"], 0.55, color="#2471a3", alpha=0.9)
for i, r in d1.iterrows():
    ax.text(i, r["diff"] - 0.03, f"p={r['p']:.1e}".replace("e-0", "e-"), ha="center", fontsize=7)
ax.axhline(0, color="k", lw=0.8)
ax.set_xticks(xv); ax.set_xticklabels([str(y) for y in d1["year"]])
ax.set_ylabel("高HRI组 − 低HRI组\n未来12周收益差")
ax.set_title("追高风险指数与未来12周收益：分年分组差（沈阳十种蔬菜）")
ax.grid(axis="y", alpha=0.25)
fig.tight_layout(); fig.savefig(OUT / "F1_hri_by_year.png"); plt.close(fig)

# ---------------- 图2：策略相对均匀随机基准的超额（主图）
c = pd.read_csv(V / "compare_vs_random.csv")
fig, axes = plt.subplots(1, 2, figsize=(12.4, 4.4))
for ax, step in zip(axes, [7, 30]):
    s = c[c.cutoff_step_days == step].sort_values("mean_diff")
    y = np.arange(len(s))
    sig = s["显著_BH-FDR"].values.astype(bool)
    col = ["#1e8449" if v else "#7f8c8d" for v in sig]
    ax.barh(y, s["mean_diff"], color=col, alpha=0.9)
    ax.errorbar(s["mean_diff"], y, xerr=[s["mean_diff"] - s["ci_lo"], s["ci_hi"] - s["mean_diff"]],
                fmt="none", ecolor="k", elinewidth=1, capsize=2)
    ax.axvline(0, color="#c0392b", ls="--", lw=1)
    ax.set_yticks(y)
    ax.set_yticklabels([NAME_CN.get(x, x) for x in s["strategy_A"]], fontsize=8)
    ax.set_xlabel("相对均匀随机基准的超额\n（未来30天窗口均价/建仓价 − 1）")
    ax.set_title(f"step{step}（{int(s['n'].iloc[0])} 个切点）")
    ax.grid(axis="x", alpha=0.25)
axes[0].set_title("（a）7 天步长，窗口重叠", fontsize=10)
axes[1].set_title("（b）30 天步长，窗口不重叠", fontsize=10)
fig.suptitle("各策略相对均匀随机基准的超额（95% Bootstrap 置信区间；绿色＝BH-FDR 校正后显著）", fontsize=11)
fig.tight_layout(); fig.savefig(OUT / "F2_strategy_vs_random.png"); plt.close(fig)

# ---------------- 图3：策略选中高 HRI 环境比例
lv = pd.read_csv(V / "strategy_levels.csv")
fig, axes = plt.subplots(1, 2, figsize=(12.4, 4.0))
for ax, step in zip(axes, [7, 30]):
    s = lv[lv.cutoff_step_days == step].copy()
    s = s[s.strategy != "Random_expectation"].sort_values("high_hri_rate")
    y = np.arange(len(s))
    ax.barh(y, s["high_hri_rate"] * 100, color="#b9770e", alpha=0.85)
    ax.set_yticks(y); ax.set_yticklabels([NAME_CN.get(x, x) for x in s.strategy], fontsize=8)
    ax.set_xlabel("选中高 HRI 作物比例（%）")
    ax.grid(axis="x", alpha=0.25)
    ax.set_title(f"step{step}")
fig.suptitle("各策略“踩入追高环境”的程度（均匀随机选择的期望约为 10%）", fontsize=11)
fig.tight_layout(); fig.savefig(OUT / "F3_high_hri_rate.png"); plt.close(fig)

# ---------------- 图4：HRI 检验的严格度梯度
sm = pd.read_csv(A / "H_hri_summary_multiple_testing.csv")
fig, ax = plt.subplots(figsize=(7.4, 3.6))
x = np.arange(len(sm)); w = 0.26
ax.bar(x - w, sm["raw显著"], w, label="普通双侧检验", color="#bdc3c7")
ax.bar(x, sm["robust原判"], w, label="块Bootstrap+HAC 同时显著", color="#5dade2")
ax.bar(x + w, sm["两项均过BH"], w, label="BH-FDR 校正后仍显著", color="#2471a3")
for i in range(len(sm)):
    for off, col in [(-w, "raw显著"), (0, "robust原判"), (w, "两项均过BH")]:
        ax.text(i + off, sm[col].iloc[i] + 0.12, str(int(sm[col].iloc[i])), ha="center", fontsize=7)
ax.set_xticks(x); ax.set_xticklabels([f"{int(w0)} 周" for w0 in sm["window_w"]])
ax.set_ylabel("显著作物数 / 10"); ax.set_ylim(0, 11)
ax.set_title("追高风险指数验证：检验严格度提高后显著数量的衰减")
ax.legend(frameon=False, fontsize=8)
ax.grid(axis="y", alpha=0.25)
fig.tight_layout(); fig.savefig(OUT / "F4_hri_significance.png"); plt.close(fig)

print("figures ->", OUT)
for f in sorted(os.listdir(OUT)):
    print(" ", f)
