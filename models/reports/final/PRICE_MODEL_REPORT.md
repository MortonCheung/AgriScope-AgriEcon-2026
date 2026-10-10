# Price Model Report (Final)

严格 OOT：walk-forward expanding，folds = 2024 / 2025 / 2026(截尾)。禁止随机 split。
特征：FINAL_FEATURE_COLS（仅价格派生，无 volume、无 weather）。选择标准：mean_WAPE + 0.5·std_WAPE。

## h=30 逐作物选择（沈阳）
| crop | route | model | mean_WAPE | std_WAPE | worst_WAPE | mean_bias | baseline_WAPE | improvement_vs_baseline_pct | beats_baseline |
|---|---|---|---|---|---|---|---|---|---|
| 土豆 | baseline | baseline_last_value | 4.8449 | 1.5289 | 5.8907 | -0.0025 | 4.8449 | 0.0000 | False |
| 尖椒 | pooled | elasticnet | 11.6365 | 0.5192 | 12.1378 | -0.0002 | 13.1091 | 11.2335 | True |
| 甘蓝 | baseline | baseline_last_value | 13.7617 | 1.8774 | 15.8474 | 0.0092 | 13.7617 | 0.0000 | False |
| 芸豆 | pooled | elasticnet | 9.0618 | 2.0578 | 11.2516 | 0.0248 | 10.6035 | 14.5399 | True |
| 芹菜 | baseline | baseline_last_value | 10.8425 | 3.2101 | 14.3258 | 0.0100 | 10.8425 | 0.0000 | False |
| 茄子 | pooled | elasticnet_tuned | 11.6613 | 1.6256 | 13.5203 | 0.1027 | 12.2094 | 4.4894 | True |
| 西红柿 | pooled | elasticnet_tuned | 8.7836 | 0.9024 | 9.8256 | -0.0029 | 9.8006 | 10.3772 | True |
| 青椒 | pooled | elasticnet_tuned | 11.8133 | 1.4477 | 13.1161 | 0.0028 | 13.0501 | 9.4775 | True |
| 韭菜 | per_crop | elasticnet_tuned | 10.6866 | 1.3661 | 12.0870 | -0.1708 | 13.3535 | 19.9716 | True |
| 黄瓜 | pooled | extra_trees | 15.1016 | 0.7627 | 15.8051 | -0.0126 | 18.5741 | 18.6956 | True |


## 多 horizon WAPE（沈阳）
| crop | 7 | 14 | 30 | 60 | 90 |
|---|---|---|---|---|---|
| 土豆 | 2.3137 | 3.2101 | 4.8449 | 7.0804 | 8.3769 |
| 尖椒 | 5.0449 | 7.5729 | 11.6365 | 15.8550 | 18.3630 |
| 甘蓝 | 5.7499 | 8.3051 | 13.7617 | 19.0076 | 20.9963 |
| 芸豆 | 5.1196 | 6.9911 | 9.0618 | 8.9636 | 8.3003 |
| 芹菜 | 5.0436 | 7.3407 | 10.8425 | 14.8962 | 17.2931 |
| 茄子 | 6.2305 | 9.0337 | 11.6613 | 14.8786 | 14.8891 |
| 西红柿 | 4.3572 | 6.2744 | 8.7836 | 12.1330 | 14.6241 |
| 青椒 | 5.0927 | 7.5793 | 11.8133 | 13.5737 | 13.5672 |
| 韭菜 | 5.3922 | 8.0713 | 10.6866 | 12.8891 | 12.5810 |
| 黄瓜 | 7.7714 | 11.4839 | 15.1016 | 17.4470 | 17.8874 |


## Scenario Range 逐 crop × horizon（§21/§22/§23）
- 汇总：{'city': '沈阳', 'n_crop_horizon': 50, 'status_counts': {'scenario_range_widened': 35, 'scenario_range': 15}, 'worst_coverage': 0.5113122171945701, 'mean_coverage': 0.7095827270232232, 'horizons': [7, 14, 30, 60, 90], 'ts': '2026-10-07 19:32:18'}
- 状态含义：`scenario_range` 覆盖率稳定 / `scenario_range_widened` 加宽后达标（标注倍数）/ `scenario_range_unreliable` 加宽仍不足 / `no_range_available` 样本不足。**不再用总体覆盖率掩盖最差作物。**
| horizon | crop | method | n | coverage | mean_width | widen_factor | status |
|---|---|---|---|---|---|---|---|
| 7 | 土豆 | seasonal_window_quantile | 673 | 0.5329 | 0.8864 | 1.5010 | scenario_range_widened |
| 7 | 尖椒 | seasonal_window_quantile | 673 | 0.7769 | 3.9329 | 1.0300 | scenario_range |
| 7 | 甘蓝 | seasonal_window_quantile | 673 | 0.6482 | 1.8453 | 1.2340 | scenario_range_widened |
| 7 | 芸豆 | residual_recent | 668 | 0.8578 | 2.3253 | 1.0000 | scenario_range |
| 7 | 芹菜 | seasonal_window_quantile | 673 | 0.7395 | 2.4496 | 1.0820 | scenario_range_widened |
| 7 | 茄子 | seasonal_window_quantile | 673 | 0.7201 | 2.8188 | 1.1110 | scenario_range_widened |
| 7 | 西红柿 | residual_recent | 668 | 0.7620 | 0.7141 | 1.0500 | scenario_range |
| 7 | 青椒 | seasonal_window_quantile | 673 | 0.7440 | 3.7251 | 1.0750 | scenario_range_widened |
| 7 | 韭菜 | seasonal_window_quantile | 673 | 0.7216 | 2.6609 | 1.1090 | scenario_range_widened |
| 7 | 黄瓜 | residual_expanding | 668 | 0.6766 | 1.3788 | 1.1820 | scenario_range_widened |
| 14 | 土豆 | seasonal_window_quantile | 673 | 0.5113 | 0.8683 | 1.5650 | scenario_range_widened |
| 14 | 尖椒 | seasonal_window_quantile | 673 | 0.7557 | 3.8247 | 1.0590 | scenario_range |
| 14 | 甘蓝 | seasonal_window_quantile | 673 | 0.6184 | 1.7985 | 1.2940 | scenario_range_widened |
| 14 | 芸豆 | residual_expanding | 663 | 0.8431 | 3.8193 | 1.0000 | scenario_range |
| 14 | 芹菜 | seasonal_window_quantile | 673 | 0.7376 | 2.3880 | 1.0850 | scenario_range_widened |
| 14 | 茄子 | seasonal_window_quantile | 673 | 0.7300 | 2.6622 | 1.0960 | scenario_range_widened |
| 14 | 西红柿 | seasonal_window_quantile | 673 | 0.7602 | 2.7999 | 1.0520 | scenario_range |
| 14 | 青椒 | seasonal_window_quantile | 673 | 0.7391 | 3.5874 | 1.0820 | scenario_range_widened |
| 14 | 韭菜 | residual_expanding | 663 | 0.7617 | 1.1949 | 1.0500 | scenario_range |
| 14 | 黄瓜 | residual_expanding | 663 | 0.7029 | 2.2998 | 1.1380 | scenario_range_widened |


## 折元数据（§15：train→past / validate→future，含样本数）
| fold | train_start | train_end | validation_start | validation_end | n_train | n_validation | crop | train_end_declared |
|---|---|---|---|---|---|---|---|---|
| fold1_test2024 | 2021-01-01 | 2023-12-29 | 2024-01-01 | 2024-12-31 | 737 | 248 | 土豆 | 2023-12-31 |
| fold1_test2024 | 2021-01-01 | 2023-12-29 | 2024-01-01 | 2024-12-31 | 737 | 248 | 尖椒 | 2023-12-31 |
| fold1_test2024 | 2021-01-01 | 2023-12-29 | 2024-01-01 | 2024-12-31 | 737 | 248 | 甘蓝 | 2023-12-31 |
| fold1_test2024 | 2021-01-01 | 2023-12-29 | 2024-01-01 | 2024-12-31 | 737 | 248 | 芸豆 | 2023-12-31 |
| fold1_test2024 | 2021-01-01 | 2023-12-29 | 2024-01-01 | 2024-12-31 | 737 | 248 | 芹菜 | 2023-12-31 |
| fold1_test2024 | 2021-01-01 | 2023-12-29 | 2024-01-01 | 2024-12-31 | 737 | 248 | 茄子 | 2023-12-31 |
| fold1_test2024 | 2021-01-01 | 2023-12-29 | 2024-01-01 | 2024-12-31 | 737 | 248 | 西红柿 | 2023-12-31 |
| fold1_test2024 | 2021-01-01 | 2023-12-29 | 2024-01-01 | 2024-12-31 | 737 | 248 | 青椒 | 2023-12-31 |
| fold1_test2024 | 2021-01-01 | 2023-12-29 | 2024-01-01 | 2024-12-31 | 737 | 248 | 韭菜 | 2023-12-31 |
| fold1_test2024 | 2021-01-01 | 2023-12-29 | 2024-01-01 | 2024-12-31 | 737 | 248 | 黄瓜 | 2023-12-31 |
| fold2_test2025 | 2021-01-01 | 2024-12-31 | 2025-01-02 | 2025-12-31 | 985 | 250 | 土豆 | 2024-12-31 |
| fold2_test2025 | 2021-01-01 | 2024-12-31 | 2025-01-02 | 2025-12-31 | 985 | 250 | 尖椒 | 2024-12-31 |
| fold2_test2025 | 2021-01-01 | 2024-12-31 | 2025-01-02 | 2025-12-31 | 985 | 250 | 甘蓝 | 2024-12-31 |
| fold2_test2025 | 2021-01-01 | 2024-12-31 | 2025-01-02 | 2025-12-31 | 985 | 250 | 芸豆 | 2024-12-31 |
| fold2_test2025 | 2021-01-01 | 2024-12-31 | 2025-01-02 | 2025-12-31 | 985 | 250 | 芹菜 | 2024-12-31 |
| fold2_test2025 | 2021-01-01 | 2024-12-31 | 2025-01-02 | 2025-12-31 | 985 | 250 | 茄子 | 2024-12-31 |
| fold2_test2025 | 2021-01-01 | 2024-12-31 | 2025-01-02 | 2025-12-31 | 985 | 250 | 西红柿 | 2024-12-31 |
| fold2_test2025 | 2021-01-01 | 2024-12-31 | 2025-01-02 | 2025-12-31 | 985 | 250 | 青椒 | 2024-12-31 |
| fold2_test2025 | 2021-01-01 | 2024-12-31 | 2025-01-02 | 2025-12-31 | 985 | 250 | 韭菜 | 2024-12-31 |
| fold2_test2025 | 2021-01-01 | 2024-12-31 | 2025-01-02 | 2025-12-31 | 985 | 250 | 黄瓜 | 2024-12-31 |
| fold3_test2026 | 2021-01-01 | 2025-12-31 | 2026-01-05 | 2026-08-14 | 1235 | 154 | 土豆 | 2025-12-31 |
| fold3_test2026 | 2021-01-01 | 2025-12-31 | 2026-01-05 | 2026-08-14 | 1235 | 154 | 尖椒 | 2025-12-31 |
| fold3_test2026 | 2021-01-01 | 2025-12-31 | 2026-01-05 | 2026-08-14 | 1235 | 154 | 甘蓝 | 2025-12-31 |
| fold3_test2026 | 2021-01-01 | 2025-12-31 | 2026-01-05 | 2026-08-14 | 1235 | 154 | 芸豆 | 2025-12-31 |


## 天气消融（with vs without weather, h=30）
| model | mean_with | mean_without | mean_delta | n_improved | n |
|---|---|---|---|---|---|
| elasticnet | 15.7259 | 15.6337 | 0.0922 | 13 | 30 |
| extra_trees | 13.1324 | 13.1354 | -0.0030 | 15 | 30 |


**结论**：天气默认**不进入**价格模型；消融见上表。复杂模型打不过 baseline 的作物一律回退 baseline。
