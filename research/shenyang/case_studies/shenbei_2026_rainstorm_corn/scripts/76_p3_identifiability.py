#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P3-12/P3-13：2026 支持域审计（EXTRAPOLATION_AUDIT.md）+ 小样本可识别性模拟。
模拟：用真实 2018–2025 的 X（时间/暴露），在若干真实 beta_R 情景下生成 n=8 数据集，
    拟合同一 M1_S0 模型，统计方向识别率 / CrI 覆盖率 / P(beta_R<0)。
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from m1_lib import sample  # noqa
from m1_priors import PRIORS  # noqa

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
M1 = os.path.join(BASE, "06_models", "M1_bayesian_yield_response")
FZ = os.path.join(M1, "data", "M1_dataset_frozen.csv")
FEAT = os.path.join(BASE, "04_marts", "corn_year_weather_features.csv")
SEED = 20260922


def main():
    d = pd.read_csv(FZ)
    T = d["time_index"].values.astype(float)
    R = d["primary_rain_exposure"].values.astype(float)
    ZT = (T - T.mean()) / T.std(ddof=1)
    ZR = (R - R.mean()) / R.std(ddof=1)
    Rmean, Rsd = R.mean(), R.std(ddof=1)

    # ---------------- 外推审计 ----------------
    feat = pd.read_csv(FEAT)
    hist = feat[(feat.year >= 1991) & (feat.year <= 2025)]["repro_precip_max_5d"].astype(float)
    v26 = 252.8
    rows = [
        ("train_2018_2025_min", float(R.min())),
        ("train_2018_2025_max", float(R.max())),
        ("train_2018_2025_median", float(np.median(R))),
        ("2026_value", v26),
        ("1991_2025_p50", float(np.percentile(hist, 50))),
        ("1991_2025_p95", float(np.percentile(hist, 95))),
        ("1991_2025_p99", float(np.percentile(hist, 99))),
        ("1991_2025_max", float(hist.max())),
    ]
    ex = pd.DataFrame(rows, columns=["item", "value_mm"])
    zr26 = (v26 - Rmean) / Rsd
    above_train = v26 > R.max()
    n_hist_above = int((hist >= v26).sum())
    with open(os.path.join(M1, "validation", "EXTRAPOLATION_AUDIT.md"), "w", encoding="utf-8") as f:
        f.write("# EXTRAPOLATION_AUDIT.md（P3-12）\n\n")
        f.write(ex.to_string(index=False) + "\n\n")
        f.write(f"- 2026 主暴露 = **{v26} mm**；2018–2025 训练上限 = **{R.max()} mm** → "
                f"{'**超出训练范围**' if above_train else '在训练范围内'}。\n")
        f.write(f"- 标准化后 ZR_2026 = **{zr26:.2f}** 个训练标准差。\n")
        f.write(f"- 1991–2025 中 ≥ {v26} mm 的年份数：**{n_hist_above}**（即 2026 为 1991–2025 的 **{float((hist < v26).mean()*100):.1f} 分位**）。\n\n")
        f.write("## 判定\n")
        if zr26 > 3:
            f.write("### `STRONG_EXTRAPOLATION`\n- 2026 暴露远超 2018–2025 训练经验（>3 SD），"
                    "M1 对 2026 的预测属**强外推**；即使贝叶斯在数学上可算，也不得伪装为有历史样本支持的插值预测。\n")
        elif zr26 > 1.5:
            f.write("### `MILD_EXTRAPOLATION`\n- 2026 暴露略超训练范围。\n")
        else:
            f.write("### `INTERPOLATION`\n- 2026 暴露处于训练范围内。\n")
    print("EXTRAPOLATION:", dict(v26=v26, train_max=float(R.max()), zr26=round(zr26, 2), above=above_train))

    # ---------------- 可识别性模拟 ----------------
    a_true = float(np.log(d["yield_kg_ha"].values.mean()))
    bT_true = 0.105
    sig_true = 0.08
    scenarios = {"beta=0 (null)": 0.0, "beta=-0.03 (mild)": -0.03,
                 "beta=-0.06 (moderate)": -0.06, "beta=-0.10 (strong)": -0.10}
    NSIM = 200
    rng = np.random.default_rng(SEED)
    sim_rows = []
    for name, bR_true in scenarios.items():
        detected = 0; correct_dir = 0; cover = 0; pneg = []
        for s in range(NSIM):
            ysim = a_true + bT_true * ZT + bR_true * ZR + sig_true * rng.normal(size=len(ZT))
            out = sample(ysim, ZT, ZR, PRIORS["S0"], use_R=True, n_chains=4,
                         warmup=1200, draws=1200, seed=SEED + 1000 + s)
            flat = out["chain"].reshape(-1, out["chain"].shape[2])
            bR = flat[:, 2]
            lo, hi = np.quantile(bR, [0.025, 0.975])
            excl0 = (lo > 0) or (hi < 0)
            if excl0:
                detected += 1
                if (bR_true < 0 and hi < 0) or (bR_true == 0):
                    correct_dir += 1
            if lo <= bR_true <= hi:
                cover += 1
            pneg.append(float((bR < 0).mean()))
        sim_rows.append(dict(scenario=name, true_beta_R=bR_true,
                             detection_rate_95CrI_excl0=round(detected / NSIM, 3),
                             correct_direction_rate=round(correct_dir / NSIM, 3),
                             CrI95_coverage_of_true=round(cover / NSIM, 3),
                             mean_P_betaR_lt0=round(float(np.mean(pneg)), 3)))
    sim = pd.DataFrame(sim_rows)
    sim.to_csv(os.path.join(M1, "validation", "identifiability_simulation.csv"), index=False, encoding="utf-8-sig")
    with open(os.path.join(M1, "validation", "IDENTIFIABILITY_SIMULATION.md"), "w", encoding="utf-8") as f:
        f.write("# IDENTIFIABILITY_SIMULATION.md（P3-13）\n\n")
        f.write(f"用真实 X（2018–2025 time & exposure）生成 n=8 合成数据；每情景 {NSIM} 次；"
                f"拟合 M1_S0（warmup=1200,draws=1200,4链）。\n\n")
        f.write(sim.to_string(index=False) + "\n\n")
        f.write("## 判读\n")
        f.write("- `detection_rate_95CrI_excl0`：真实存在效应时，n=8 能否以 95% CrI 排除 0；\n")
        f.write("- `CrI95_coverage_of_true`：95% CrI 覆盖真值的频率（应≈0.95）；\n")
        f.write("- 若即使**中等效应**识别率仍低 → 本地数据几乎没有识别力，只能提供有限更新。\n")
    print(sim.to_string(index=False))


if __name__ == "__main__":
    main()
