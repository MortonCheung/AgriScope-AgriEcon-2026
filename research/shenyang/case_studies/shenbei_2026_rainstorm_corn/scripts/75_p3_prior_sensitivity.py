#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P3-11 Prior Sensitivity（S0/S1/S2）+ 2026 情景的模型算式（诊断用，非反事实结论）。"""
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
    y = np.log(d["yield_kg_ha"].values.astype(float))
    T = d["time_index"].values.astype(float)
    R = d["primary_rain_exposure"].values.astype(float)
    ZT = (T - T.mean()) / T.std(ddof=1)
    ZR = (R - R.mean()) / R.std(ddof=1)
    Rmean, Rsd = R.mean(), R.std(ddof=1)

    feat = pd.read_csv(FEAT)
    hist = feat[(feat.year >= 1991) & (feat.year <= 2025)]["repro_precip_max_5d"].astype(float)
    normal_p50 = float(np.median(hist))
    R_2026 = 252.8
    ZR_2026 = (R_2026 - Rmean) / Rsd
    ZR_normal = (normal_p50 - Rmean) / Rsd
    ZT_2026 = (9 - T.mean()) / T.std(ddof=1)   # 2026 对应 time_index=9

    rows = []
    for k in ["S0", "S1", "S2"]:
        out = sample(y, ZT, ZR, PRIORS[k], use_R=True, seed=SEED)
        flat = out["chain"].reshape(-1, out["chain"].shape[2])
        a, bT, bR, ls = flat[:, 0], flat[:, 1], flat[:, 2], flat[:, 3]
        # A 世界（实际 2026 暴露）与 B 世界（正常暴露）的模型算式（同 draws 配对）
        muA = a + bT * ZT_2026 + bR * ZR_2026
        muB = a + bT * ZT_2026 + bR * ZR_normal
        # 只比较确定性部分（不含噪声），表示“暴露替换”的模型算式差异
        YA = np.exp(muA); YB = np.exp(muB)
        dY = YB - YA
        rel = (YB - YA) / YB
        rows.append(dict(
            prior=k,
            beta_R_median=round(float(np.median(bR)), 4),
            beta_R_CrI95=f"[{np.quantile(bR,0.025):.4f}, {np.quantile(bR,0.975):.4f}]",
            P_betaR_lt0=round(float((bR < 0).mean()), 3),
            Y_A_median=round(float(np.median(YA)), 0),
            Y_B_median=round(float(np.median(YB)), 0),
            dY_median=round(float(np.median(dY)), 0),
            dY_CrI95=f"[{np.quantile(dY,0.025):.0f}, {np.quantile(dY,0.975):.0f}]",
            rel_median_pct=round(float(np.median(rel) * 100), 2),
            rel_CrI95=f"[{np.quantile(rel,0.025)*100:.2f}, {np.quantile(rel,0.975)*100:.2f}]",
        ))
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(M1, "sensitivity", "prior_sensitivity_summary.csv"), index=False, encoding="utf-8-sig")

    with open(os.path.join(M1, "sensitivity", "PRIOR_SENSITIVITY.md"), "w", encoding="utf-8") as f:
        f.write("# PRIOR_SENSITIVITY.md（P3-11）\n\n")
        f.write(f"正常暴露基准 NORMAL_P50（1991–2025，抽雄吐丝期 `repro_precip_max_5d` 中位数）= **{normal_p50:.1f} mm**；"
                f"2026 实际 = **{R_2026} mm**；标准化后 ZR_normal={ZR_normal:.2f}，ZR_2026={ZR_2026:.2f}。\n\n")
        f.write(df.to_string(index=False) + "\n\n")
        f.write("## 判读\n")
        f.write("- 三个先验下 `beta_R` 的 posterior median / CrI / P(<0) **是否反转**；\n")
        f.write("- ✅ 不反转 → 方向较稳；❌ 反转或差异巨大 → 结果 **prior-sensitive**。\n\n")
        f.write("> ⚠️ **重要**：上表 `Y_A/Y_B/dY/rel` 是**模型算式（model arithmetic）**，"
                "用于展示“暴露替换”在前述系数下会怎样，**不是反事实结论**；\n"
                "> 由于 LOYO 未通过（Gate C FAIL）且 2026 属强外推，本轮**不产出 B 世界定量结论**"
                "（见 `07_counterfactual/B_no_disaster/NOT_ELIGIBLE.md`）。\n")
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
