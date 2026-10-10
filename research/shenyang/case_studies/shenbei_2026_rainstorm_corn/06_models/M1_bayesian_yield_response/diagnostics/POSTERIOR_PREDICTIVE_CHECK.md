# POSTERIOR_PREDICTIVE_CHECK.md（P3-08）

model  obs_mean  rep_mean  obs_sd  rep_sd  obs_min  rep_min  obs_max  rep_max  sd_of_year_means_obs  sd_of_year_means_rep
   M0    8055.0    8061.0   990.0   807.0   6505.0   4674.0   9228.0  13738.0                 990.0                 807.0
M1_S0    8055.0    8072.0   990.0   824.0   6505.0   4608.0   9228.0  14199.0                 990.0                 824.0

## 判读
- M1_S0 的 95% 预测区间能否覆盖观测的 8 个年份；
- 模型能否重现**年际波动**（year-means 的 SD），而非只画一条均线；
- 若预测区间过宽或无法覆盖极值年份（如 2018 低产、2023 高产），须在结论中说明。

> 图：`diagnostics/posterior_predictive.png`
