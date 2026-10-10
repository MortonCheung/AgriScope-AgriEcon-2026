# Long-Horizon Decision Replay

> RC2，模型 `long_horizon_v2_rc2`，数据 `f04b01b9b8399c15`，预注册协议 `3259aaad287e25b757c62e9bb293aaf0471a0bca34ffb5fae5a82f1ef8d7affe`。
> 历史 2024/2025/2026 已参与 RC1 target/model 选择；本轮没有真正 untouched 历史段。
> 2026 指标是 **reused retrospective audit**；`untouched_metric=null`、`final_effective_n=0`。

相同cutoff、同10作物、同真实Harvest outcome下，按预测价格/current price−1排序，选择一个作物；realized outcome=Harvest实际价格/current price−1。regret=当日事后最佳作物relative price return−所选作物return。不混用不同作物绝对元/公斤，不能宣称利润或最佳农业决策。
对照statistical_long、target-aligned seasonal、开发选定simple baseline、short_only_30d_seasonal_proxy、随机期望、seed17随机。short-only是当时历史季节30日均价proxy，不使用全历史训练的冻结Final权重，避免未来泄漏；不是正式短期Decision v1策略胜负证明。LLM/hybrid缺真实数值证据，明确NOT_EVALUATED，不拿stub填补。成本/产量/设施/作物可种性未知，不能模拟真实利润。

| horizon | policy | n | mean_return | mean_regret | worst_regret | worst_return | downside_p10 | top1_accuracy | retrospective_exposure_blocks | selection_turnover | crop_concentration | actual_independent_samples | rank_accuracy | direction_accuracy | llm_status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 30 | random_expected | 144 | -0.070 | 0.388 | 1.318 | -0.356 | -0.246 | 0.000 | 5 | 0.000 | 1.000 | 0 | N/A | N/A | NOT_EVALUATED_NO_REAL_LLM_NUMERIC_EVIDENCE |
| 30 | random_seed17 | 144 | -0.082 | 0.399 | 1.649 | -0.508 | -0.344 | 0.076 | 5 | 0.930 | 0.125 | 0 | N/A | N/A | NOT_EVALUATED_NO_REAL_LLM_NUMERIC_EVIDENCE |
| 30 | seasonal_baseline | 144 | 0.147 | 0.170 | 1.378 | -0.124 | -0.086 | 0.299 | 5 | 0.056 | 0.590 | 0 | 0.441 | 0.716 | NOT_EVALUATED_NO_REAL_LLM_NUMERIC_EVIDENCE |
| 30 | selected_simple_baseline | 144 | 0.200 | 0.117 | 0.941 | -0.331 | -0.179 | 0.444 | 5 | 0.105 | 0.306 | 0 | 0.441 | 0.514 | NOT_EVALUATED_NO_REAL_LLM_NUMERIC_EVIDENCE |
| 30 | short_only_30d_seasonal_proxy | 144 | 0.197 | 0.121 | 1.121 | -0.331 | -0.179 | 0.431 | 5 | 0.119 | 0.312 | 0 | N/A | N/A | NOT_EVALUATED_NO_REAL_LLM_NUMERIC_EVIDENCE |
| 30 | statistical_long | 144 | 0.249 | 0.068 | 0.525 | -0.169 | -0.101 | 0.486 | 5 | 0.133 | 0.229 | 0 | 0.589 | 0.640 | NOT_EVALUATED_NO_REAL_LLM_NUMERIC_EVIDENCE |
| 60 | random_expected | 124 | -0.145 | 0.481 | 1.252 | -0.452 | -0.385 | 0.000 | 3 | 0.000 | 1.000 | 0 | N/A | N/A | NOT_EVALUATED_NO_REAL_LLM_NUMERIC_EVIDENCE |
| 60 | random_seed17 | 124 | -0.177 | 0.512 | 1.581 | -0.672 | -0.473 | 0.097 | 3 | 0.902 | 0.161 | 0 | N/A | N/A | NOT_EVALUATED_NO_REAL_LLM_NUMERIC_EVIDENCE |
| 60 | seasonal_baseline | 124 | 0.254 | 0.082 | 0.646 | -0.307 | -0.151 | 0.444 | 3 | 0.049 | 0.581 | 0 | 0.650 | 0.846 | NOT_EVALUATED_NO_REAL_LLM_NUMERIC_EVIDENCE |
| 60 | selected_simple_baseline | 124 | 0.255 | 0.081 | 0.731 | -0.267 | -0.148 | 0.540 | 3 | 0.106 | 0.387 | 0 | 0.719 | 0.742 | NOT_EVALUATED_NO_REAL_LLM_NUMERIC_EVIDENCE |
| 60 | short_only_30d_seasonal_proxy | 124 | 0.113 | 0.223 | 1.169 | -0.430 | -0.274 | 0.306 | 3 | 0.106 | 0.363 | 0 | N/A | N/A | NOT_EVALUATED_NO_REAL_LLM_NUMERIC_EVIDENCE |
| 60 | statistical_long | 124 | 0.269 | 0.066 | 0.761 | -0.295 | -0.200 | 0.565 | 3 | 0.130 | 0.306 | 0 | 0.687 | 0.770 | NOT_EVALUATED_NO_REAL_LLM_NUMERIC_EVIDENCE |
| 90 | random_expected | 103 | -0.218 | 0.471 | 0.879 | -0.543 | -0.486 | 0.000 | 2 | 0.000 | 1.000 | 0 | N/A | N/A | NOT_EVALUATED_NO_REAL_LLM_NUMERIC_EVIDENCE |
| 90 | random_seed17 | 103 | -0.236 | 0.489 | 1.208 | -0.678 | -0.553 | 0.107 | 2 | 0.882 | 0.223 | 0 | N/A | N/A | NOT_EVALUATED_NO_REAL_LLM_NUMERIC_EVIDENCE |
| 90 | seasonal_baseline | 103 | 0.201 | 0.053 | 0.403 | -0.122 | -0.099 | 0.660 | 2 | 0.049 | 0.534 | 0 | 0.732 | 0.860 | NOT_EVALUATED_NO_REAL_LLM_NUMERIC_EVIDENCE |
| 90 | selected_simple_baseline | 103 | 0.129 | 0.124 | 0.630 | -0.122 | -0.099 | 0.612 | 2 | 0.059 | 0.680 | 0 | 0.808 | 0.798 | NOT_EVALUATED_NO_REAL_LLM_NUMERIC_EVIDENCE |
| 90 | short_only_30d_seasonal_proxy | 103 | -0.032 | 0.285 | 0.919 | -0.507 | -0.323 | 0.058 | 2 | 0.088 | 0.437 | 0 | N/A | N/A | NOT_EVALUATED_NO_REAL_LLM_NUMERIC_EVIDENCE |
| 90 | statistical_long | 103 | 0.177 | 0.076 | 0.630 | -0.122 | -0.099 | 0.738 | 2 | 0.059 | 0.602 | 0 | 0.730 | 0.832 | NOT_EVALUATED_NO_REAL_LLM_NUMERIC_EVIDENCE |
| 120 | random_expected | 82 | -0.321 | 0.440 | 0.666 | -0.517 | -0.492 | 0.000 | 1 | 0.000 | 1.000 | 0 | N/A | N/A | NOT_EVALUATED_NO_REAL_LLM_NUMERIC_EVIDENCE |
| 120 | random_seed17 | 82 | -0.322 | 0.442 | 1.107 | -0.716 | -0.626 | 0.098 | 1 | 0.914 | 0.134 | 0 | N/A | N/A | NOT_EVALUATED_NO_REAL_LLM_NUMERIC_EVIDENCE |
| 120 | seasonal_baseline | 82 | 0.041 | 0.079 | 0.529 | -0.275 | -0.165 | 0.695 | 1 | 0.074 | 0.451 | 0 | 0.735 | 0.874 | NOT_EVALUATED_NO_REAL_LLM_NUMERIC_EVIDENCE |
| 120 | selected_simple_baseline | 82 | 0.040 | 0.080 | 0.480 | -0.087 | -0.068 | 0.634 | 1 | 0.062 | 0.573 | 0 | 0.830 | 0.899 | NOT_EVALUATED_NO_REAL_LLM_NUMERIC_EVIDENCE |
| 120 | short_only_30d_seasonal_proxy | 82 | -0.133 | 0.252 | 0.618 | -0.603 | -0.551 | 0.146 | 1 | 0.074 | 0.415 | 0 | N/A | N/A | NOT_EVALUATED_NO_REAL_LLM_NUMERIC_EVIDENCE |
| 120 | statistical_long | 82 | 0.033 | 0.087 | 0.480 | -0.125 | -0.072 | 0.622 | 1 | 0.025 | 0.451 | 0 | 0.783 | 0.888 | NOT_EVALUATED_NO_REAL_LLM_NUMERIC_EVIDENCE |
| 150 | random_expected | 62 | -0.384 | 0.379 | 0.515 | -0.518 | -0.488 | 0.000 | 1 | 0.000 | 1.000 | 0 | N/A | N/A | NOT_EVALUATED_NO_REAL_LLM_NUMERIC_EVIDENCE |
| 150 | random_seed17 | 62 | -0.381 | 0.376 | 0.682 | -0.732 | -0.661 | 0.065 | 1 | 0.885 | 0.161 | 0 | N/A | N/A | NOT_EVALUATED_NO_REAL_LLM_NUMERIC_EVIDENCE |
| 150 | seasonal_baseline | 62 | -0.102 | 0.096 | 0.320 | -0.405 | -0.345 | 0.500 | 1 | 0.066 | 0.323 | 0 | 0.694 | 0.952 | NOT_EVALUATED_NO_REAL_LLM_NUMERIC_EVIDENCE |
| 150 | selected_simple_baseline | 62 | -0.282 | 0.276 | 0.551 | -0.580 | -0.527 | 0.129 | 1 | 0.033 | 0.548 | 0 | 0.756 | 0.844 | NOT_EVALUATED_NO_REAL_LLM_NUMERIC_EVIDENCE |
| 150 | short_only_30d_seasonal_proxy | 62 | -0.251 | 0.245 | 0.681 | -0.644 | -0.609 | 0.145 | 1 | 0.082 | 0.532 | 0 | N/A | N/A | NOT_EVALUATED_NO_REAL_LLM_NUMERIC_EVIDENCE |
| 150 | statistical_long | 62 | -0.249 | 0.243 | 0.551 | -0.580 | -0.527 | 0.194 | 1 | 0.033 | 0.484 | 0 | 0.699 | 0.847 | NOT_EVALUATED_NO_REAL_LLM_NUMERIC_EVIDENCE |
| 180 | random_expected | 41 | -0.429 | 0.379 | 0.464 | -0.489 | -0.472 | 0.000 | 1 | 0.000 | 1.000 | 0 | N/A | N/A | NOT_EVALUATED_NO_REAL_LLM_NUMERIC_EVIDENCE |
| 180 | random_seed17 | 41 | -0.409 | 0.358 | 0.688 | -0.732 | -0.657 | 0.195 | 1 | 0.900 | 0.195 | 0 | N/A | N/A | NOT_EVALUATED_NO_REAL_LLM_NUMERIC_EVIDENCE |
| 180 | seasonal_baseline | 41 | -0.245 | 0.195 | 0.386 | -0.442 | -0.376 | 0.244 | 1 | 0.200 | 0.512 | 0 | 0.708 | 1.000 | NOT_EVALUATED_NO_REAL_LLM_NUMERIC_EVIDENCE |
| 180 | selected_simple_baseline | 41 | -0.435 | 0.384 | 0.515 | -0.524 | -0.514 | 0.000 | 1 | 0.000 | 1.000 | 0 | 0.683 | 0.800 | NOT_EVALUATED_NO_REAL_LLM_NUMERIC_EVIDENCE |
| 180 | short_only_30d_seasonal_proxy | 41 | -0.320 | 0.270 | 0.633 | -0.642 | -0.634 | 0.073 | 1 | 0.100 | 0.659 | 0 | N/A | N/A | NOT_EVALUATED_NO_REAL_LLM_NUMERIC_EVIDENCE |
| 180 | statistical_long | 41 | -0.333 | 0.283 | 0.472 | -0.524 | -0.482 | 0.244 | 1 | 0.025 | 0.756 | 0 | 0.676 | 0.776 | NOT_EVALUATED_NO_REAL_LLM_NUMERIC_EVIDENCE |

强推荐限制：全部长期registry仍scenario；历史regret改善只说明市场相对价格proxy，未来独立决策效果尚未证实。稠密cutoff的策略平均值/最坏值是描述统计，共享未来窗口，n行数不是独立决策样本数。

按真实回放判定（不据此重新选模型或调策略）：

- 30d：长期统计策略 regret 0.0681，季节基线 0.1702；回顾样本中统计策略较好，仅5个保守exposure blocks。
- 60d：长期统计策略 regret 0.0665，季节基线 0.0817；回顾样本中统计策略较好，仅3个保守exposure blocks。
- 90d：长期统计策略 regret 0.0765，季节基线 0.0525；统计策略未改善季节基线，仅2个保守exposure blocks。
- 120d：长期统计策略 regret 0.0867，季节基线 0.0785；统计策略未改善季节基线，仅1个保守exposure blocks。
- 150d：长期统计策略 regret 0.2431，季节基线 0.0962；统计策略未改善季节基线，仅1个保守exposure blocks。
- 180d：长期统计策略 regret 0.2828，季节基线 0.1946；统计策略未改善季节基线，仅1个保守exposure blocks。
