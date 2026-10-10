# PRIOR_DOMINANCE_AUDIT.md（P3-10）

判据（针对 `beta_R`）：posterior_sd/prior_sd <0.5 → DATA_INFORMATIVE；0.5–0.9 → MIXED；>0.9 → PRIOR_DOMINATED

- **M1_S0**: beta_R posterior sd/prior sd = **0.435** → `DATA_INFORMATIVE`；P(beta_R<0) = 0.767
- **M1_S1**: beta_R posterior sd/prior sd = **0.258** → `DATA_INFORMATIVE`；P(beta_R<0) = 0.799
- **M1_S2**: beta_R posterior sd/prior sd = **0.219** → `DATA_INFORMATIVE`；P(beta_R<0) = 0.784

> 若为 PRIOR_DOMINATED / MIXED，反事实必须标记为“文献约束下的情景推演”，不得写成“沈北数据证明”。
