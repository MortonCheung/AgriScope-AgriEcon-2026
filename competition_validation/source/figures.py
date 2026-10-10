#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""experiments/analysis/figures.py — 生成论文核心图表（PNG）。"""
from __future__ import annotations
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
OUT = EXP / "results" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# 中文字体（macOS）
for f in ["Arial Unicode MS", "PingFang SC", "Heiti TC", "STHeiti", "Songti SC"]:
    try:
        matplotlib.font_manager.findfont(f, fallback_to_default=False)
        plt.rcParams["font.family"] = f
        break
    except Exception:
        continue
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 150

AN = EXP / "results" / "analysis"

# ---- F1: HRI 12 周分组差按年份（修复前 vs 修复后）
hy = pd.read_csv(AN / "hri_by_year.csv")
hy12 = hy[hy["窗口_周"] == 12]
fig, ax = plt.subplots(figsize=(7.2, 3.6))
years = sorted(hy12["年份"].unique())
w = 0.38
for i, (tag, c) in enumerate([("旧(未修复)", "#c0392b"), ("新(修复后)", "#2471a3")]):
    s = hy12[hy12["版本"] == tag].set_index("年份")["分组差"].reindex(years)
    ax.bar(np.arange(len(years)) + (i - 0.5) * w, s.values, w, label=tag, color=c, alpha=0.85)
ax.axhline(0, color="k", lw=0.8)
ax.set_xticks(range(len(years)))
ax.set_xticklabels([str(y) for y in years])
ax.set_ylabel("高HRI组 − 低HRI组\n未来12周收益差")
ax.set_title("图1  HRI 的未来收益区分力（按年份，沈阳10蔬菜，12周窗口）")
ax.legend(frameon=False, fontsize=8)
ax.grid(axis="y", alpha=0.25)
fig.tight_layout()
fig.savefig(OUT / "F1_hri_by_year.png")
plt.close(fig)

# ---- F2: 策略平均市场收益 vs 随机期望（step30，含 95% CI）
sig = pd.read_csv(AN / "strategy_significance.csv")
s30 = sig[sig["版本"] == "新(step30)"].sort_values("相对Random均值")
rd = pd.read_csv(AN / "strategy_before_after.csv")
ref = rd[(rd["版本"] == "新(step30)") & (rd["strategy"] == "Random_expectation")]["mean_market_return"]
ref = float(ref.iloc[0]) if len(ref) else 0.0
fig, ax = plt.subplots(figsize=(7.6, 4.2))
y = np.arange(len(s30))
mean = ref + s30["相对Random均值"].values
lo = ref + s30["CI下"].values
hi = ref + s30["CI上"].values
sigflag = s30["显著(两项同时<0.05)"].values
colors = ["#1e8449" if v else "#7f8c8d" for v in sigflag]
ax.barh(y, mean, color=colors, alpha=0.85)
ax.errorbar(mean, y, xerr=[mean - lo, hi - mean], fmt="none", ecolor="k", elinewidth=1, capsize=2)
ax.axvline(ref, color="#c0392b", ls="--", lw=1, label=f"随机期望基准 {ref:.3f}")
ax.set_yticks(y)
ax.set_yticklabels(s30["策略"], fontsize=8)
ax.set_xlabel("未来30天窗口均价/建仓价 − 1（市场机会收益）")
ax.set_title("图2  策略相对随机基准的超额（非重叠30天切点，含95% Bootstrap CI）")
ax.legend(frameon=False, fontsize=8)
ax.grid(axis="x", alpha=0.25)
fig.tight_layout()
fig.savefig(OUT / "F2_strategy_vs_random.png")
plt.close(fig)

# ---- F3: 高-HRI 命中率 修复前 vs 修复后（策略口径修正效果）
old = rd[(rd["版本"] == "旧(未修复)")]
new = rd[(rd["版本"] == "新(step7)")]
pairs = [("Balanced_old", "Balanced_old"),
         ("Profit_only", "Highest_forecast_return"),
         ("Chase_price", "Chase_price_momentum"),
         ("Balanced_fix_v1", "Balanced_fix_v2")]
labels, ov, nv = [], [], []
for a, b in pairs:
    oa = old[old["strategy"] == a]["high_hri_rate"]
    nb = new[new["strategy"] == b]["high_hri_rate"]
    if len(oa) and len(nb):
        labels.append(f"{a}\n→{b}")
        ov.append(float(oa.iloc[0]) * 100)
        nv.append(float(nb.iloc[0]) * 100)
fig, ax = plt.subplots(figsize=(7.0, 3.6))
x = np.arange(len(labels)); w = 0.38
ax.bar(x - w / 2, ov, w, label="修复前", color="#c0392b", alpha=0.85)
ax.bar(x + w / 2, nv, w, label="修复后", color="#2471a3", alpha=0.85)
ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=8)
ax.set_ylabel("选中高-HRI 作物比例 (%)")
ax.set_title("图3  策略“踩追逐高风险”程度：修复前后对照")
ax.legend(frameon=False, fontsize=8)
ax.grid(axis="y", alpha=0.25)
fig.tight_layout()
fig.savefig(OUT / "F3_high_hri_rate.png")
plt.close(fig)

# ---- F4: HRI 稳健显著性 修复前后（12周）
sm = pd.read_csv(AN / "hri_summary_before_after.csv")
s12 = sm[sm["窗口_周"] == 12]
fig, ax = plt.subplots(figsize=(6.4, 3.4))
x = np.arange(2); w = 0.38
ax.bar(x - w / 2, s12["raw显著数"].values, w, label="普通双侧检验显著", color="#bdc3c7")
ax.bar(x + w / 2, s12["robust显著数"].values, w, label="时间序列稳健显著(块bootstrap+HAC)", color="#2874a6")
ax.set_xticks(x); ax.set_xticklabels(s12["版本"])
ax.set_ylabel("显著作物数 / 10")
ax.set_ylim(0, 11)
for i in range(len(s12)):
    ax.text(i - w / 2, s12["raw显著数"].values[i] + .1, str(int(s12["raw显著数"].values[i])), ha="center", fontsize=8)
    ax.text(i + w / 2, s12["robust显著数"].values[i] + .1, str(int(s12["robust显著数"].values[i])), ha="center", fontsize=8)
ax.set_title("图4  HRI 12周验证：修复前 vs 修复后")
ax.legend(frameon=False, fontsize=8)
ax.grid(axis="y", alpha=0.25)
fig.tight_layout()
fig.savefig(OUT / "F4_hri_significance.png")
plt.close(fig)

print("figures ->", OUT)
for f in sorted(os.listdir(OUT)):
    print(" ", f)
