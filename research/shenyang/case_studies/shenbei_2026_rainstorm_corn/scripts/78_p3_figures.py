#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P3 正式图件 F1–F7（不夸大不确定性；含单位/年份/来源/图注）。"""
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
FIG = os.path.join(M1, "figures")
os.makedirs(FIG, exist_ok=True)
plt.rcParams["font.sans-serif"] = ["Arial Unicode MS", "Heiti TC", "PingFang SC", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False
SRC = "数据来源：沈北玉米单产=沈阳统计年鉴(A)/沈北区级年鉴(B,2025)；暴露=ERA5再分析(D)"


def main():
    d = pd.read_csv(os.path.join(M1, "data", "M1_dataset_frozen.csv"))
    y = d["yield_kg_ha"].values; yr = d["year"].values
    R = d["primary_rain_exposure"].values; T = d["time_index"].values
    ch = np.load(os.path.join(M1, "fits", "M1_S0_posterior.npz"))["chain"]
    flat = ch.reshape(-1, ch.shape[2])

    # F1 单产 + 趋势
    fig, ax = plt.subplots(figsize=(8, 4))
    k, b = np.polyfit(yr, y, 1)
    ax.plot(yr, y, "o-", color="#c53030", label="观测单产")
    ax.plot(yr, k * yr + b, "--", color="#2b6cb0", label=f"线性趋势 +{k:.0f} kg/ha/年")
    ax.set_title("图1 沈北新区玉米单产 2018–2025 与时间趋势"); ax.set_xlabel("年"); ax.set_ylabel("kg/ha")
    ax.legend(); ax.set_xticks(yr)
    fig.text(0.01, -0.02, SRC, fontsize=7)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "F1_yield_trend.png"), dpi=130, bbox_inches="tight"); plt.close(fig)

    # F2 主暴露年际
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(yr, R, color="#3182ce")
    ax.axhline(np.median(pd.read_csv(os.path.join(BASE, "04_marts", "corn_year_weather_features.csv"))
                         .query("1991<=year<=2025")["repro_precip_max_5d"]), color="#805ad5", ls="--", label="1991–2025 中位数")
    ax.axhline(252.8, color="#c53030", ls=":", label="2026 实际 252.8mm")
    ax.set_title("图2 主极端降雨变量（抽雄吐丝期最大5日累计降水）2018–2025"); ax.set_xlabel("年"); ax.set_ylabel("mm")
    ax.legend(); ax.set_xticks(yr)
    fig.text(0.01, -0.02, SRC, fontsize=7)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "F2_exposure.png"), dpi=130, bbox_inches="tight"); plt.close(fig)

    # F3 暴露 vs 单产
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.scatter(R, y, color="#2b6cb0")
    for xi, yi, a in zip(R, y, yr):
        ax.annotate(str(a), (xi, yi), fontsize=8, xytext=(3, 3), textcoords="offset points")
    ax.set_title("图3 抽雄吐丝期最大5日降水 vs 玉米单产（标注年份）")
    ax.set_xlabel("repro_precip_max_5d (mm)"); ax.set_ylabel("单产 (kg/ha)")
    fig.text(0.01, -0.02, SRC, fontsize=7)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "F3_exposure_vs_yield.png"), dpi=130, bbox_inches="tight"); plt.close(fig)

    # F4 Prior vs Posterior (beta_R)
    fig, axes = plt.subplots(1, 3, figsize=(14, 4), sharey=True)
    for ax, kk in zip(axes, ["S0", "S1", "S2"]):
        mu, sd = PRIORS[kk]["beta_R"]
        xs = np.linspace(-0.3, 0.2, 400)
        ax.plot(xs, np.exp(-0.5 * ((xs - mu) / sd) ** 2), color="#805ad5", label="prior")
        br = flat[:, 2] if kk == "S0" else np.load(os.path.join(M1, "fits", f"M1_{kk}_posterior.npz"))["chain"].reshape(-1, 4)[:, 2]
        ax.hist(br, bins=60, density=True, color="#3182ce", alpha=0.6, label="posterior")
        ax.axvline(0, color="k", lw=0.8)
        ax.set_title(f"图4-{kk}: beta_R prior vs posterior"); ax.set_xlabel("beta_R (每 1 SD 降水对 log 单产)")
        ax.legend(fontsize=8)
    fig.text(0.01, -0.02, "prior=先验密度(未归一化曲线)；posterior=后验抽样直方图", fontsize=7)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "F4_prior_vs_posterior.png"), dpi=130, bbox_inches="tight"); plt.close(fig)

    # F5 后验预测（复用已生成图）
    # F6/F7 LOYO
    loyo = pd.read_csv(os.path.join(M1, "validation", "LOYO_predictions.csv"))
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(loyo.year, loyo.observed_yield, "s-", color="#c53030", label="观测")
    ax.plot(loyo.year, loyo.M0_pred_mean, "o--", color="#a0aec0", label="M0 预测")
    ax.plot(loyo.year, loyo.M1_S0_pred_mean, "o-", color="#2b6cb0", label="M1_S0 预测")
    ax.fill_between(loyo.year, loyo["M1_S0_95_interval"].str.strip("[]").str.split(",").str[0].astype(float),
                    loyo["M1_S0_95_interval"].str.strip("[]").str.split(",").str[1].astype(float),
                    color="#90cdf4", alpha=0.4, label="M1 95% 预测区间")
    ax.set_title("图6 Exact LOYO：观测 vs M0/M1 预测（每折重拟合）")
    ax.set_xlabel("年"); ax.set_ylabel("kg/ha"); ax.legend(fontsize=8); ax.set_xticks(loyo.year)
    fig.text(0.01, -0.02, SRC, fontsize=7)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "F6_loyo_predictions.png"), dpi=130, bbox_inches="tight"); plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4))
    w = 0.4
    ax.bar(loyo.year - w / 2, np.abs(loyo.M0_error), w, color="#a0aec0", label="|M0 误差|")
    ax.bar(loyo.year + w / 2, np.abs(loyo.M1_S0_error), w, color="#2b6cb0", label="|M1_S0 误差|")
    ax.set_title("图7 LOYO 绝对误差：M0 vs M1_S0"); ax.set_xlabel("年"); ax.set_ylabel("|预测−观测| (kg/ha)")
    ax.legend(); ax.set_xticks(loyo.year)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "F7_loyo_error.png"), dpi=130, bbox_inches="tight"); plt.close(fig)

    with open(os.path.join(FIG, "FIGURES_README.md"), "w", encoding="utf-8") as f:
        f.write("""# FIGURES_README.md

| 图 | 文件 | 内容 |
|---|---|---|
| 图1 | F1_yield_trend.png | 2018–2025 玉米单产 + 时间趋势 |
| 图2 | F2_exposure.png | 主极端降雨变量年际变化（含 2026 与历史中位数） |
| 图3 | F3_exposure_vs_yield.png | 极端降水 vs 单产（标注年份） |
| 图4 | F4_prior_vs_posterior.png | beta_R 的 Prior vs Posterior（S0/S1/S2） |
| 图5 | ../diagnostics/posterior_predictive.png | Posterior Predictive Check |
| 图6 | F6_loyo_predictions.png | LOYO 真实值 vs 预测值（M0/M1） |
| 图7 | F7_loyo_error.png | M0 vs M1 LOYO 绝对误差 |
| 图8 | —（未生成） | B 世界 A vs B 后验分布：**因 Gate C FAIL，未生成**（见 07_counterfactual/B_no_disaster/NOT_ELIGIBLE.md） |
""")
    print("figures:", sorted(os.listdir(FIG)))


if __name__ == "__main__":
    main()
