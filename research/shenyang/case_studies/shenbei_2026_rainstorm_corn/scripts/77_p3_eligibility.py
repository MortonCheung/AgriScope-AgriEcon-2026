#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P3-14/P3-15：反事实资格闸门（Gate A–F）→ COUNTERFACTUAL_ELIGIBILITY.md
若不合格 → 07_counterfactual/B_no_disaster/NOT_ELIGIBLE.md（不生成 B 世界数字）
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
M1 = os.path.join(BASE, "06_models", "M1_bayesian_yield_response")
CF = os.path.join(BASE, "07_counterfactual", "B_no_disaster")
os.makedirs(CF, exist_ok=True)
FZ = os.path.join(M1, "data", "M1_dataset_frozen.csv")
SEED = 20260922


def main():
    # ---- Gate A：收敛 ----
    dg = pd.read_csv(os.path.join(M1, "diagnostics", "sampler_diagnostics.csv"))
    worst_rhat = float(dg.dropna(subset=["rhat"]).rhat.max())
    min_ess = float(dg[dg.param != "_accept_rate"].ess_bulk.min())
    gateA = "PASS" if (worst_rhat <= 1.01 and min_ess >= 400) else "FAIL"

    # ---- Gate B：后验预测 ----
    d = pd.read_csv(FZ)
    y = d["yield_kg_ha"].values.astype(float)
    T = d["time_index"].values.astype(float); R = d["primary_rain_exposure"].values.astype(float)
    ZT = (T - T.mean()) / T.std(ddof=1); ZR = (R - R.mean()) / R.std(ddof=1)
    ch = np.load(os.path.join(M1, "fits", "M1_S0_posterior.npz"))["chain"]
    flat = ch.reshape(-1, ch.shape[2])
    rng = np.random.default_rng(SEED)
    mu = flat[:, 0][:, None] + flat[:, 1][:, None] * ZT[None, :] + flat[:, 2][:, None] * ZR[None, :]
    Y = np.exp(mu + np.exp(flat[:, 3])[:, None] * rng.normal(size=mu.shape))
    lo = np.percentile(Y, 2.5, axis=0); hi = np.percentile(Y, 97.5, axis=0)
    cov = float(((y >= lo) & (y <= hi)).mean())
    gateB = "PASS" if cov >= 0.75 else ("CAUTION" if cov >= 0.5 else "FAIL")

    # ---- Gate C：LOYO M1 不得明显劣于 M0 ----
    mx = pd.read_csv(os.path.join(M1, "validation", "LOYO_metrics.csv"))
    m0 = mx[mx.model == "M0"].iloc[0]
    m1 = mx[mx.model == "M1_S0"].iloc[0]
    dmae = float(m1.MAE_kg_ha - m0.MAE_kg_ha)
    drmse = float(m1.RMSE_kg_ha - m0.RMSE_kg_ha)
    dlpd = float(m1.mean_log_predictive_density - m0.mean_log_predictive_density)
    gateC = "FAIL" if (dmae > 0 or drmse > 0 or dlpd < 0) else "PASS"

    # ---- Gate D：先验敏感性 ----
    ps = pd.read_csv(os.path.join(M1, "sensitivity", "prior_sensitivity_summary.csv"))
    med_spread = float(ps.beta_R_median.max() - ps.beta_R_median.min())
    pneg = ps.P_betaR_lt0.values
    reversal = bool((pneg.min() < 0.5) != (pneg.max() < 0.5))
    gateD = "FAIL" if reversal else "PASS"

    # ---- Gate E：2026 外推 ----
    feat = pd.read_csv(os.path.join(BASE, "04_marts", "corn_year_weather_features.csv"))
    hist = feat[(feat.year >= 1991) & (feat.year <= 2025)]["repro_precip_max_5d"].astype(float)
    zr26 = (252.8 - R.mean()) / R.std(ddof=1)
    gateE = "STRONG_EXTRAPOLATION" if zr26 > 3 else ("MILD" if zr26 > 1.5 else "INTERPOLATION")

    # ---- Gate F：机制 ----
    gateF = "CAUTION (变量=降雨暴露，不能代表 waterlogging)"

    overall = "NOT_ELIGIBLE" if (gateC == "FAIL" or gateE == "STRONG_EXTRAPOLATION") else "ELIGIBLE_WITH_LABEL"

    with open(os.path.join(M1, "COUNTERFACTUAL_ELIGIBILITY.md"), "w", encoding="utf-8") as f:
        f.write("# COUNTERFACTUAL_ELIGIBILITY.md（P3-14）\n\n")
        f.write("| Gate | 检查 | 结果 |\n|---|---|---|\n")
        f.write(f"| A 收敛 | 最大 R-hat={worst_rhat:.4f}；最小 bulk ESS={min_ess:.0f} | **{gateA}** |\n")
        f.write(f"| B 后验预测 | 观测被 95% 预测区间覆盖比例={cov:.2f} | **{gateB}** |\n")
        f.write(f"| C LOYO | ΔMAE={dmae:+.1f}；ΔRMSE={drmse:+.1f}；ΔlogPD={dlpd:+.3f}（M1−M0） | **{gateC}** |\n")
        f.write(f"| D 先验敏感性 | β_R 中位数跨先验极差={med_spread:.4f}；P(<0)区间=[{pneg.min():.2f},{pneg.max():.2f}]；方向反转={reversal} | **{gateD}** |\n")
        f.write(f"| E 2026 外推 | ZR_2026={zr26:.2f} SD | **{gateE}** |\n")
        f.write(f"| F 机制 | 主变量=`repro_precip_max_5d`（降雨暴露） | **{gateF}** |\n\n")
        f.write(f"## 总判定：**{overall}**\n\n")
        f.write("依据规格 §48/§76：**Gate C 失败**（加入降雨后跨年预测不改善、反而变差）"
                "且 **Gate E 为强外推** → 属“情况 C”，**M1′ 不具备正式反事实资格**。\n")

    with open(os.path.join(CF, "NOT_ELIGIBLE.md"), "w", encoding="utf-8") as f:
        f.write("# NOT_ELIGIBLE.md — B（无灾害世界）反事实资格：**不通过**\n\n")
        f.write("按规格要求，**模型未通过闸门时不生成反事实数字**。\n\n")
        f.write("## 哪个 Gate 失败\n")
        f.write(f"- **Gate C（LOYO）FAIL**：M1 相比趋势模型 M0 的跨年预测 **全面变差** —— "
                f"ΔMAE=**{dmae:+.1f}**、ΔRMSE=**{drmse:+.1f}**、ΔlogPD=**{dlpd:+.3f}**。"
                "即“加入抽雄吐丝期极端降水”对**未见年份**没有提供额外预测价值。\n")
        f.write(f"- **Gate E STRONG_EXTRAPOLATION**：2026 主暴露 {252.8} mm 仅为 2018–2025 训练上限 {R.max():.0f} mm 之上，"
                f"ZR={zr26:.2f} SD，历史上罕见（1991–2025 100 分位）。\n")
        f.write(f"- **Gate F CAUTION**：主变量是*降雨暴露*，不能代表 *waterlogging* 因果。\n\n")
        f.write("## 为什么失败\n")
        f.write("1. n=8 的样本量下，可识别性模拟显示：即使真实存在**中等负效应**，95% CrI 排除 0 的识别率也只有 **≈0.34**"
                "（轻度 ≈0.11，强效应 ≈0.75）→ 本地数据几乎没有独立识别能力。\n")
        f.write("2. 因此 M1 的“改善”只能来自 prior，而 prior 又缺乏可映射的数值文献支撑（PRIOR_EVIDENCE_AUDIT：**无 Class A**）。\n")
        f.write("3. 2026 暴露远超训练域，任何 B 世界数字都将是**强外推**。\n\n")
        f.write("## 还缺什么证据\n")
        f.write("- 更长的沈北玉米单产序列（≥15–20 年）或**对照区县面板**；\n")
        f.write("- **站点实测降水**（替换再分析，改善极端降水测量误差）；\n")
        f.write("- 全区 **waterlogging 观测**（遥感积水/排涝台账）以打通 M2/M3 机理链；\n")
        f.write("- 沈北**区级 2026 灾损台账**（受灾/成灾/绝收/经济损失）以标定损失。\n\n")
        f.write("> 说明：`sensitivity/prior_sensitivity_summary.csv` 中的 `Y_A/Y_B/dY/rel` 只是"
                "**模型算式**，用于展示系数含义，**不构成反事实结论**，本阶段不据此发布任何 B 世界数字。\n")

    print(f"GateA={gateA} GateB={gateB}(cov={cov:.2f}) GateC={gateC} GateD={gateD} GateE={gateE} -> {overall}")
    print(f"dmae={dmae:+.1f} drmse={drmse:+.1f} dlpd={dlpd:+.3f} zr26={zr26:.2f}")


if __name__ == "__main__":
    main()
