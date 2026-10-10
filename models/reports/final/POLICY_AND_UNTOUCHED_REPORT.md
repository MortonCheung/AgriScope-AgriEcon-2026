# Policy Decision & Untouched Evaluation（§12/§13/§14/§15/§53）

## 时间切分（明确声明）
- **development** 2021–2023（训练）
- **policy_tuning** 2024–2025（Balanced 修复所用）
- **untouched_2026** 2026-01~09（**完全未参与任何权重/阈值调整**）

## 各期策略表现（指标 = market_return，非农户利润）
| period | strategy | n | mean_market_return | median_market_return | downside | worst | p_down | high_hri_rate | selection_diversity_n_crops | crop_concentration_hhi |
|---|---|---|---|---|---|---|---|---|---|---|
| policy_tuning | AgriScope_Balanced_fix | 498 | 0.0242 | 0.0027 | -0.1084 | -0.3026 | 0.4859 | 0.0020 | 7 | 0.3378 |
| policy_tuning | AgriScope_Balanced_old | 498 | 0.0082 | 0.0006 | -0.1168 | -0.3026 | 0.4960 | 0.1466 | 7 | 0.3478 |
| policy_tuning | Chase_price | 498 | -0.0042 | -0.0173 | -0.1189 | -0.3993 | 0.5462 | 0.2149 | 4 | 0.7092 |
| policy_tuning | Most_Robust | 498 | 0.0221 | 0.0048 | -0.1007 | -0.3230 | 0.4839 | 0.0301 | 7 | 0.2296 |
| policy_tuning | Profit_only | 498 | 0.0156 | 0.0001 | -0.1128 | -0.3591 | 0.4980 | 0.1486 | 3 | 0.8343 |
| policy_tuning | Random | 498 | 0.0346 | 0.0061 | -0.1040 | -0.3715 | 0.4679 | 0.0783 | 10 | 0.1023 |
| policy_tuning | Risk_only | 498 | 0.0589 | 0.0345 | -0.0912 | -0.2843 | 0.3554 | 0.0000 | 10 | 0.1585 |
| untouched_2026 | AgriScope_Balanced_fix | 154 | -0.0089 | -0.0134 | -0.0710 | -0.1842 | 0.5844 | 0.0130 | 3 | 0.6334 |
| untouched_2026 | AgriScope_Balanced_old | 154 | -0.0148 | -0.0314 | -0.0733 | -0.1842 | 0.6364 | 0.0649 | 3 | 0.9368 |
| untouched_2026 | Chase_price | 154 | -0.0293 | -0.0459 | -0.0915 | -0.3377 | 0.6753 | 0.1169 | 4 | 0.7557 |
| untouched_2026 | Most_Robust | 154 | -0.0107 | -0.0167 | -0.0694 | -0.2058 | 0.6039 | 0.0000 | 4 | 0.6431 |
| untouched_2026 | Profit_only | 154 | -0.0274 | -0.0452 | -0.0891 | -0.3377 | 0.6688 | 0.1039 | 3 | 0.7888 |
| untouched_2026 | Random | 154 | -0.0200 | -0.0326 | -0.1044 | -0.3594 | 0.6299 | 0.1104 | 10 | 0.1030 |
| untouched_2026 | Risk_only | 154 | -0.0203 | -0.0095 | -0.1022 | -0.3650 | 0.5390 | 0.0000 | 7 | 0.1615 |


## 默认策略决策：**A**
- 依据：Balanced_fix 在 untouched 期不劣于 Random，downside 不劣于 Profit_only，且高-HRI 抑制在 tuning/untouched 一致（无 evaluation overfitting）→ 保留 Balanced 为默认
- untouched 2026：Balanced_fix -0.01 / Profit_only -0.03 / Risk_only -0.02 / Random -0.02
- 高-HRI 选中率：Balanced_fix 0.0130 vs Profit_only 0.1039（untouched 期一致被抑制）
- downside：Balanced_fix -0.07 vs Profit_only -0.09
- 选择多样性 3.0 作物 / HHI 0.63（未退化为「只选最低风险」）
- evaluation overfitting 检查：**True**
