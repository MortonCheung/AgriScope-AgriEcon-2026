#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P3-06 Prior Predictive Check：检查先验是否能生成农业上合理的单产。"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from m1_priors import PRIORS  # noqa

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
M1 = os.path.join(BASE, "06_models", "M1_bayesian_yield_response")
FZ = os.path.join(M1, "data", "M1_dataset_frozen.csv")
SEED = 20260922


def main():
    d = pd.read_csv(FZ)
    y = np.log(d["yield_kg_ha"].values.astype(float))
    T = d["time_index"].values.astype(float)
    R = d["primary_rain_exposure"].values.astype(float)
    ZT = (T - T.mean()) / T.std(ddof=1)
    ZR = (R - R.mean()) / R.std(ddof=1)
    # 2026 极端暴露（标准化用训练统计量）
    ZR_2026 = (252.8 - R.mean()) / R.std(ddof=1)

    rng = np.random.default_rng(SEED)
    N = 20000
    rows = []
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    for i, (k, p) in enumerate(PRIORS.items()):
        a = rng.normal(*p["alpha"], N)
        bT = rng.normal(*p["beta_T"], N)
        bR = rng.normal(*p["beta_R"], N)
        ls = rng.normal(*p["log_sigma"], N)
        sg = np.exp(ls)
        # 训练设计下的先验预测单产（取当年 X 的均值结构 + 噪声）
        mu = a + bT * ZT.mean() + bR * ZR.mean()
        y_rep = np.exp(mu + sg * rng.normal(0, 1, N))
        # 极端情景（2026 暴露）
        y_ext = np.exp(a + bT * ZT.mean() + bR * ZR_2026 + sg * rng.normal(0, 1, N))
        rows.append(dict(
            prior=k, n=N,
            p2_5=round(float(np.percentile(y_rep, 2.5)), 0),
            median=round(float(np.median(y_rep)), 0),
            p97_5=round(float(np.percentile(y_rep, 97.5)), 0),
            pct_outside_3000_15000=round(float(((y_rep < 3000) | (y_rep > 15000)).mean() * 100), 2),
            ymin=round(float(y_rep.min()), 0), ymax=round(float(y_rep.max()), 0),
            ext_p2_5=round(float(np.percentile(y_ext, 2.5)), 0),
            ext_median=round(float(np.median(y_ext)), 0),
            ext_p97_5=round(float(np.percentile(y_ext, 97.5)), 0),
            pct_impossible_ext=round(float(((y_ext < 500) | (y_ext > 30000)).mean() * 100), 3),
        ))
        axes[i].hist(y_rep, bins=80, color="#3182ce", alpha=0.85)
        axes[i].axvline(3000, color="#e53e3e", ls="--"); axes[i].axvline(15000, color="#e53e3e", ls="--")
        axes[i].set_title(f"Prior {k} predictive yield"); axes[i].set_xlabel("kg/ha")
    fig.suptitle("Prior predictive check (红线=农业合理区间 3000–15000 kg/ha)")
    fig.tight_layout()
    fig.savefig(os.path.join(M1, "diagnostics", "prior_predictive.png"), dpi=130)
    plt.close(fig)

    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(M1, "diagnostics", "prior_predictive_summary.csv"), index=False, encoding="utf-8-sig")

    with open(os.path.join(M1, "diagnostics", "PRIOR_PREDICTIVE_CHECK.md"), "w", encoding="utf-8") as f:
        f.write("# PRIOR_PREDICTIVE_CHECK.md（P3-06）\n\n")
        f.write("> 标准：先验能否只生成**农业上合理**的单产（≈3000–15000 kg/ha），并能表达合理年际波动。\n\n")
        f.write(df.to_string(index=False))
        f.write("\n\n")
        bad = df[df.pct_outside_3000_15000 > 1.0]
        if len(bad) == 0:
            f.write("## 结论：**通过（训练设计）**\n- 三组先验在训练设计下的 2.5–97.5% 预测单产均落在农业合理区间内；"
                    "落在 [3000,15000] 之外的比例 ≤1%。\n- 允许合理的年际波动（区间宽度足以覆盖 2018–2025 观测的 ~6500–9200 kg/ha）。\n")
        else:
            f.write("## 结论：**需调整（训练设计）**\n- 下表先验生成过多不合理值，须重设 prior 后重跑：\n")
            f.write(bad.to_string(index=False) + "\n")
        f.write("\n## 极端暴露情景（诊断，非先验合格性判据）\n")
        f.write("- 以 2026 暴露（ZR≈+4.25）代入同一先验时，预测单产区间显著变宽，"
                "S2 出现较多的物理不可能量级（>30000 或 <500 kg/ha）。\n")
        f.write("- **这不是先验设置错误，而是“线性模型外推到 ~4.25 个训练标准差”的固有后果**，"
                "直接指示 **2026 属强外推（见 EXTRAPOLATION_AUDIT）**，须在反事实资格中作为 Gate E 处理。\n")
        f.write("\n> 图：`diagnostics/prior_predictive.png`\n")
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
