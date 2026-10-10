# PRIOR_SENSITIVITY.md（P3-11）

正常暴露基准 NORMAL_P50（1991–2025，抽雄吐丝期 `repro_precip_max_5d` 中位数）= **80.7 mm**；2026 实际 = **252.8 mm**；标准化后 ZR_normal=0.05，ZR_2026=4.25。

prior  beta_R_median      beta_R_CrI95  P_betaR_lt0  Y_A_median  Y_B_median  dY_median      dY_CrI95  rel_median_pct       rel_CrI95
   S0        -0.0216 [-0.0739, 0.0379]        0.775      8832.0      9692.0      836.0 [-1658, 2635]            8.66 [-17.24, 26.70]
   S1        -0.0274 [-0.0921, 0.0385]        0.816      8653.0      9683.0     1037.0 [-1644, 3089]           10.88 [-17.57, 32.10]
   S2        -0.0235 [-0.0872, 0.0400]        0.791      8743.0      9661.0      907.0 [-1728, 3042]            9.41 [-18.32, 30.66]

## 判读
- 三个先验下 `beta_R` 的 posterior median / CrI / P(<0) **是否反转**；
- ✅ 不反转 → 方向较稳；❌ 反转或差异巨大 → 结果 **prior-sensitive**。

> ⚠️ **重要**：上表 `Y_A/Y_B/dY/rel` 是**模型算式（model arithmetic）**，用于展示“暴露替换”在前述系数下会怎样，**不是反事实结论**；
> 由于 LOYO 未通过（Gate C FAIL）且 2026 属强外推，本轮**不产出 B 世界定量结论**（见 `07_counterfactual/B_no_disaster/NOT_ELIGIBLE.md`）。
