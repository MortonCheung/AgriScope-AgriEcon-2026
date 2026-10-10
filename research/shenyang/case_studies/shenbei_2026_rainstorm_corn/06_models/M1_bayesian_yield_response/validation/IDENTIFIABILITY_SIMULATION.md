# IDENTIFIABILITY_SIMULATION.md（P3-13）

用真实 X（2018–2025 time & exposure）生成 n=8 合成数据；每情景 200 次；拟合 M1_S0（warmup=1200,draws=1200,4链）。

             scenario  true_beta_R  detection_rate_95CrI_excl0  correct_direction_rate  CrI95_coverage_of_true  mean_P_betaR_lt0
        beta=0 (null)         0.00                        0.05                    0.05                   0.950             0.468
    beta=-0.03 (mild)        -0.03                        0.11                    0.11                   0.965             0.742
beta=-0.06 (moderate)        -0.06                        0.34                    0.34                   0.955             0.899
  beta=-0.10 (strong)        -0.10                        0.75                    0.75                   0.920             0.973

## 判读
- `detection_rate_95CrI_excl0`：真实存在效应时，n=8 能否以 95% CrI 排除 0；
- `CrI95_coverage_of_true`：95% CrI 覆盖真值的频率（应≈0.95）；
- 若即使**中等效应**识别率仍低 → 本地数据几乎没有识别力，只能提供有限更新。
