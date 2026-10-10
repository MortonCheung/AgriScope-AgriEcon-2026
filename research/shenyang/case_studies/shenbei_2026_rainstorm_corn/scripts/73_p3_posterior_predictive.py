#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P3-08 Posterior Predictive Check（M0 与 M1_S0）。"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
M1 = os.path.join(BASE, "06_models", "M1_bayesian_yield_response")
FZ = os.path.join(M1, "data", "M1_dataset_frozen.csv")
SEED = 20260922


def pred_draws(flat, ZT, ZR, use_R, rng):
    a, bT, bR, ls = flat[:, 0], flat[:, 1], flat[:, 2], flat[:, 3]
    mu = a[:, None] + bT[:, None] * ZT[None, :] + (bR[:, None] * ZR[None, :] if use_R else 0)
    return np.exp(mu + np.exp(ls)[:, None] * rng.normal(size=mu.shape))


def main():
    d = pd.read_csv(FZ)
    y = d["yield_kg_ha"].values.astype(float)
    T = d["time_index"].values.astype(float); R = d["primary_rain_exposure"].values.astype(float)
    ZT = (T - T.mean()) / T.std(ddof=1); ZR = (R - R.mean()) / R.std(ddof=1)
    years = d["year"].values
    rng = np.random.default_rng(SEED)

    res = {}
    stats = []
    for name, fn, use_R in [("M0", "M0_posterior.npz", False),
                            ("M1_S0", "M1_S0_posterior.npz", True)]:
        ch = np.load(os.path.join(M1, "fits", fn))["chain"]
        flat = ch.reshape(-1, ch.shape[2])
        Y = pred_draws(flat, ZT, ZR, use_R, rng)
        res[name] = Y
        stats.append(dict(model=name,
                          obs_mean=round(float(y.mean()), 0), rep_mean=round(float(Y.mean()), 0),
                          obs_sd=round(float(y.std(ddof=1)), 0), rep_sd=round(float(Y.mean(0).std(ddof=1)), 0),
                          obs_min=round(float(y.min()), 0), rep_min=round(float(Y.min(0).mean()), 0),
                          obs_max=round(float(y.max()), 0), rep_max=round(float(Y.max(0).mean()), 0),
                          sd_of_year_means_obs=round(float(y.std(ddof=1)), 0),
                          sd_of_year_means_rep=round(float(Y.mean(0).std(ddof=1)), 0)))
    sdf = pd.DataFrame(stats)
    sdf.to_csv(os.path.join(M1, "diagnostics", "posterior_predictive_stats.csv"), index=False, encoding="utf-8-sig")

    # 图：观测 vs 后验预测区间
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5), sharey=True)
    for ax, name in zip(axes, ["M0", "M1_S0"]):
        Y = res[name]
        lo = np.percentile(Y, 2.5, axis=0); hi = np.percentile(Y, 97.5, axis=0)
        med = np.percentile(Y, 50, axis=0)
        ax.fill_between(years, lo, hi, color="#90cdf4", alpha=0.6, label="95% 预测区间")
        ax.plot(years, med, color="#2b6cb0", marker="o", label="预测中位数")
        ax.plot(years, y, color="#c53030", marker="s", label="观测单产")
        ax.set_title(name); ax.set_xlabel("年"); ax.set_ylabel("kg/ha")
        ax.legend(fontsize=8); ax.set_xticks(years)
    fig.suptitle("Posterior Predictive Check（沈北玉米单产）")
    fig.tight_layout(); fig.savefig(os.path.join(M1, "diagnostics", "posterior_predictive.png"), dpi=130)
    plt.close(fig)

    with open(os.path.join(M1, "diagnostics", "POSTERIOR_PREDICTIVE_CHECK.md"), "w", encoding="utf-8") as f:
        f.write("# POSTERIOR_PREDICTIVE_CHECK.md（P3-08）\n\n")
        f.write(sdf.to_string(index=False) + "\n\n")
        f.write("## 判读\n")
        f.write("- M1_S0 的 95% 预测区间能否覆盖观测的 8 个年份；\n")
        f.write("- 模型能否重现**年际波动**（year-means 的 SD），而非只画一条均线；\n")
        f.write("- 若预测区间过宽或无法覆盖极值年份（如 2018 低产、2023 高产），须在结论中说明。\n\n")
        f.write("> 图：`diagnostics/posterior_predictive.png`\n")
    print(sdf.to_string(index=False))


if __name__ == "__main__":
    main()
