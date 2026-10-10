#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成论文图1（技术路线）与图4-1（预测值 vs 实际值）。输出到 results/figures_final/"""
import os
from pathlib import Path
EXP = Path(__file__).resolve().parent.parent
OUT = EXP / "results" / "figures_final"
OUT.mkdir(parents=True, exist_ok=True)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np
import pandas as pd

for f in ["Arial Unicode MS", "PingFang SC", "Heiti TC", "STHeiti"]:
    try:
        matplotlib.font_manager.findfont(f, fallback_to_default=False)
        plt.rcParams["font.family"] = f
        break
    except Exception:
        continue
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 160

# ---------------- 图1 技术路线
steps = [
    ("数据治理\n来源登记·批量清洗·口径统一", "#d6eaf8"),
    ("季节规律识别\n季节指数·稳健分解·趋势检验", "#d6eaf8"),
    ("严格样本外预测\ntruncation 检验·purge/embargo·滚动回测", "#d5f5e3"),
    ("追高风险指数 HRI\npast-only 合成·三类时间序列检验·BH 校正", "#fdebd0"),
    ("策略构建\n相对收益·风险平衡·尾部风险·随机基准", "#fdebd0"),
    ("滚动回测与配对比较\n块 Bootstrap·HAC·多重比较校正", "#f8d7da"),
    ("实证结果与稳健性\n两种切点口径·分年·多种子随机", "#f8d7da"),
    ("经济解释与政策建议\n风险提示而非价格预测", "#e8daef"),
]
fig, ax = plt.subplots(figsize=(6.6, 7.6))
ax.set_xlim(0, 10); ax.set_ylim(0, len(steps) * 1.25); ax.axis("off")
for i, (txt, c) in enumerate(steps):
    y = (len(steps) - 1 - i) * 1.25
    box = FancyBboxPatch((0.7, y + 0.12), 8.6, 0.92,
                         boxstyle="round,pad=0.06,rounding_size=0.12",
                         linewidth=1.0, edgecolor="#566573", facecolor=c)
    ax.add_patch(box)
    ax.text(5.0, y + 0.58, txt, ha="center", va="center", fontsize=9.5)
    if i < len(steps) - 1:
        ar = FancyArrowPatch((5.0, y + 0.10), (5.0, y - 0.10),
                             arrowstyle="-|>", mutation_scale=12, color="#566573")
        ax.add_patch(ar)
ax.set_title("图1  研究技术路线", fontsize=12, pad=8)
fig.tight_layout(); fig.savefig(OUT / "F0_roadmap.png"); plt.close(fig)

# ---------------- 图4-1 预测值 vs 实际值（沈阳 h=30，OOT）
preds = pd.read_parquet(EXP / "results" / "B02_pit_fixed" / "exports" / "eval" / "price_predictions.parquet")
sel = pd.read_csv(EXP / "results" / "B02_pit_fixed" / "exports" / "tables" / "price_model_selection.csv")
s30 = sel[(sel.city == "沈阳") & (sel.horizon == 30)]
keys = set(zip(s30["crop"], s30["model"], s30["route"]))
p = preds[(preds.city == "沈阳") & (preds.target == "target_mean_price_next_30d")].copy()
p = p[[(c, m, r) in keys for c, m, r in zip(p["crop"], p["model"], p["route"])]]
p = p.dropna(subset=["prediction", "actual"])

fig, axes = plt.subplots(1, 2, figsize=(11.6, 4.3))
ax = axes[0]
ax.scatter(p["actual"], p["prediction"], s=5, alpha=0.25, color="#2471a3", edgecolors="none")
lim = [0, min(20, float(np.nanpercentile(p["actual"], 99.5)))]
ax.plot(lim, lim, "r--", lw=1, label="45° 参考线")
ax.set_xlim(lim); ax.set_ylim(lim)
ax.set_xlabel("实际 30 天窗口均价（元/公斤）"); ax.set_ylabel("预测 30 天窗口均价（元/公斤）")
ax.set_title("（a）预测值 vs 实际值（全部品种合并）", fontsize=10)
ax.legend(frameon=False, fontsize=8); ax.grid(alpha=0.2)

ax = axes[1]
sel2 = s30.sort_values("mean_WAPE")
y = np.arange(len(sel2))
imp = (sel2["baseline_WAPE"] - sel2["mean_WAPE"]) / sel2["baseline_WAPE"] * 100
col = ["#1e8449" if v > 0 else "#c0392b" for v in imp]
ax.barh(y, imp, color=col, alpha=0.9)
ax.set_yticks(y); ax.set_yticklabels(sel2["crop"], fontsize=8)
ax.axvline(0, color="k", lw=0.8)
ax.set_xlabel("WAPE 相对最优基线的改善（%）")
ax.set_title("（b）十种蔬菜的预测精度改善", fontsize=10)
ax.grid(axis="x", alpha=0.25)
for i, v in enumerate(imp):
    ax.text(v + (0.4 if v >= 0 else -0.4), i, f"{v:.1f}%", va="center",
            ha="left" if v >= 0 else "right", fontsize=7)
fig.suptitle("图4-1  30 天窗口价格预测的样本外表现（沈阳十种蔬菜，三折滚动回测）", fontsize=11)
fig.tight_layout(); fig.savefig(OUT / "F5_pred_vs_actual.png"); plt.close(fig)
print("done ->", OUT)
print("saved:", sorted(x for x in os.listdir(OUT)))
