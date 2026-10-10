# PRICE_MODEL_REPORT — 价格模型（未来 30 天均价，沈阳 10 蔬菜）

> 主目标：`target_mean_price_next_30d`（未来 30 个自然天窗口平均价，元/kg）
> 回测：expanding window，**train≤2023 → test 2024；train≤2024 → test 2025；train≤2025 → test 2026(1-9月)**
> 指标：MAE / RMSE / sMAPE / WAPE / direction_accuracy / bias（全部保存于 `evaluation/backtests/predictions.parquet`）

## 1. 最终模型（逐作物，mean+0.5×std 选择，ML 与基线同池竞争）

| crop | route | model | mean_WAPE | mean_MAE | mean_RMSE | baseline_mean_WAPE | improvement_vs_baseline_pct | beats_baseline |
|---|---|---|---|---|---|---|---|---|
| 土豆 | baseline | baseline_last_value | 4.845 | 0.099 | 0.124 | 4.845 | 0.000 | 否 |
| 尖椒 | pooled | elasticnet | 11.846 | 0.671 | 0.893 | 13.109 | 9.633 | 是 |
| 甘蓝 | baseline | baseline_last_value | 13.762 | 0.280 | 0.374 | 13.762 | 0.000 | 否 |
| 芸豆 | per_crop | catboost | 9.256 | 0.797 | 0.971 | 10.604 | 12.712 | 是 |
| 芹菜 | baseline | baseline_last_value | 10.843 | 0.433 | 0.606 | 10.843 | 0.000 | 否 |
| 茄子 | pooled | elasticnet_tuned | 11.818 | 0.469 | 0.626 | 12.209 | 3.202 | 是 |
| 西红柿 | pooled | elasticnet_tuned | 8.808 | 0.472 | 0.614 | 9.801 | 10.128 | 是 |
| 青椒 | pooled | elasticnet_tuned | 11.779 | 0.706 | 0.975 | 13.050 | 9.737 | 是 |
| 韭菜 | pooled | extra_trees_tuned | 11.044 | 0.605 | 0.872 | 13.354 | 17.299 | 是 |
| 黄瓜 | pooled | extra_trees | 14.651 | 0.725 | 1.032 | 18.574 | 21.123 | 是 |

> 说明：**基线胜出 4 例**（土豆/甘蓝/芹菜/茄子）——last value 在强持续性序列上非常强，这是诚实结果；
> pooled + 正则化（elasticnet/ridge/extra_trees）在其余 6 例胜出 5~21%。
> 不允许为了「用了机器学习」而选择更差模型，最终模型按上表逐作物锁定。

## 2. 全部模型对比（跨 fold 汇总）

| route | model | crop | target | mean_WAPE | std_WAPE | mean_MAE | mean_RMSE | mean_sMAPE | mean_dir | mean_bias | folds | score |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline | baseline_last_value | 土豆 | target_mean_price_next_30d | 4.845 | 1.529 | 0.099 | 0.124 | 4.939 | 0.001 | -0.002 | 3 | 5.609 |
| per_crop | ridge_tuned | 土豆 | target_mean_price_next_30d | 5.513 | 1.894 | 0.114 | 0.144 | 5.496 | 0.578 | 0.045 | 3 | 6.460 |
| per_crop | elasticnet_tuned | 土豆 | target_mean_price_next_30d | 5.524 | 2.278 | 0.113 | 0.145 | 5.650 | 0.651 | 0.079 | 3 | 6.664 |
| baseline | baseline_rolling_mean_7 | 土豆 | target_mean_price_next_30d | 5.609 | 1.912 | 0.115 | 0.141 | 5.718 | 0.438 | -0.003 | 3 | 6.565 |
| pooled | lightgbm | 土豆 | target_mean_price_next_30d | 5.829 | 1.641 | 0.119 | 0.154 | 5.906 | 0.579 | 0.018 | 3 | 6.650 |
| pooled | hist_gradient_boosting | 土豆 | target_mean_price_next_30d | 5.852 | 1.184 | 0.120 | 0.151 | 5.968 | 0.556 | 0.011 | 3 | 6.444 |
| pooled | hist_gradient_boosting_tuned | 土豆 | target_mean_price_next_30d | 5.990 | 1.036 | 0.123 | 0.152 | 6.117 | 0.519 | 0.000 | 3 | 6.508 |
| pooled | random_forest_tuned | 土豆 | target_mean_price_next_30d | 6.005 | 0.621 | 0.124 | 0.154 | 6.162 | 0.542 | 0.026 | 3 | 6.315 |
| pooled | random_forest | 土豆 | target_mean_price_next_30d | 6.069 | 0.462 | 0.125 | 0.158 | 6.231 | 0.586 | 0.033 | 3 | 6.300 |
| pooled | lightgbm_tuned | 土豆 | target_mean_price_next_30d | 6.292 | 1.460 | 0.129 | 0.161 | 6.410 | 0.533 | 0.006 | 3 | 7.022 |
| per_crop | extra_trees_tuned | 土豆 | target_mean_price_next_30d | 6.294 | 1.577 | 0.129 | 0.166 | 6.423 | 0.524 | 0.053 | 3 | 7.083 |
| pooled | xgboost | 土豆 | target_mean_price_next_30d | 6.314 | 2.127 | 0.129 | 0.159 | 6.449 | 0.550 | 0.017 | 3 | 7.377 |
| pooled | extra_trees_tuned | 土豆 | target_mean_price_next_30d | 6.321 | 1.227 | 0.130 | 0.161 | 6.439 | 0.567 | 0.040 | 3 | 6.935 |
| per_crop | elasticnet | 土豆 | target_mean_price_next_30d | 6.458 | 3.438 | 0.134 | 0.165 | 6.353 | 0.576 | 0.071 | 3 | 8.178 |
| per_crop | random_forest_tuned | 土豆 | target_mean_price_next_30d | 6.519 | 1.315 | 0.134 | 0.170 | 6.652 | 0.565 | 0.060 | 3 | 7.177 |
| per_crop | extra_trees | 土豆 | target_mean_price_next_30d | 6.607 | 1.516 | 0.136 | 0.175 | 6.739 | 0.560 | 0.056 | 3 | 7.365 |
| pooled | extra_trees | 土豆 | target_mean_price_next_30d | 6.612 | 1.043 | 0.136 | 0.170 | 6.730 | 0.576 | 0.044 | 3 | 7.133 |
| per_crop | lightgbm | 土豆 | target_mean_price_next_30d | 6.779 | 1.331 | 0.140 | 0.179 | 6.905 | 0.549 | 0.060 | 3 | 7.445 |
| per_crop | hist_gradient_boosting | 土豆 | target_mean_price_next_30d | 6.789 | 1.310 | 0.140 | 0.181 | 6.930 | 0.574 | 0.056 | 3 | 7.444 |
| per_crop | lightgbm_tuned | 土豆 | target_mean_price_next_30d | 6.825 | 1.448 | 0.140 | 0.178 | 6.952 | 0.593 | 0.069 | 3 | 7.549 |
| per_crop | ebm_tuned | 土豆 | target_mean_price_next_30d | 6.841 | 0.610 | 0.142 | 0.178 | 7.084 | 0.621 | 0.025 | 3 | 7.145 |
| per_crop | hist_gradient_boosting_tuned | 土豆 | target_mean_price_next_30d | 6.957 | 1.942 | 0.143 | 0.181 | 7.118 | 0.567 | 0.059 | 3 | 7.928 |
| per_crop | random_forest | 土豆 | target_mean_price_next_30d | 6.973 | 0.786 | 0.144 | 0.180 | 7.089 | 0.558 | 0.062 | 3 | 7.366 |
| per_crop | xgboost | 土豆 | target_mean_price_next_30d | 7.027 | 1.878 | 0.144 | 0.179 | 7.153 | 0.577 | 0.074 | 3 | 7.966 |
| per_crop | ebm | 土豆 | target_mean_price_next_30d | 7.251 | 1.292 | 0.151 | 0.185 | 7.489 | 0.587 | 0.020 | 3 | 7.897 |
| pooled | catboost | 土豆 | target_mean_price_next_30d | 7.524 | 2.752 | 0.153 | 0.187 | 7.686 | 0.517 | 0.011 | 3 | 8.900 |
| baseline | baseline_rolling_mean_30 | 土豆 | target_mean_price_next_30d | 7.866 | 2.944 | 0.160 | 0.197 | 7.951 | 0.429 | -0.005 | 3 | 9.338 |
| per_crop | catboost | 土豆 | target_mean_price_next_30d | 7.990 | 2.584 | 0.164 | 0.202 | 8.136 | 0.628 | 0.099 | 3 | 9.282 |
| per_crop | ridge | 土豆 | target_mean_price_next_30d | 8.803 | 5.206 | 0.182 | 0.229 | 8.332 | 0.539 | 0.091 | 3 | 11.406 |
| per_crop | linear | 土豆 | target_mean_price_next_30d | 9.836 | 6.247 | 0.203 | 0.256 | 9.374 | 0.516 | 0.071 | 3 | 12.960 |
| pooled | elasticnet_tuned | 土豆 | target_mean_price_next_30d | 10.036 | 4.429 | 0.206 | 0.241 | 9.801 | 0.651 | 0.096 | 3 | 12.251 |
| baseline | baseline_seasonal_median | 土豆 | target_mean_price_next_30d | 13.383 | 4.209 | 0.273 | 0.333 | 13.024 | 0.610 | 0.222 | 3 | 15.488 |
| pooled | elasticnet | 土豆 | target_mean_price_next_30d | 13.795 | 3.090 | 0.285 | 0.339 | 14.195 | 0.651 | -0.052 | 3 | 15.340 |
| pooled | ridge | 土豆 | target_mean_price_next_30d | 14.412 | 3.051 | 0.298 | 0.363 | 15.108 | 0.618 | -0.101 | 3 | 15.937 |
| pooled | linear | 土豆 | target_mean_price_next_30d | 14.429 | 3.060 | 0.298 | 0.364 | 15.133 | 0.618 | -0.103 | 3 | 15.959 |
| pooled | ridge_tuned | 土豆 | target_mean_price_next_30d | 14.754 | 3.077 | 0.305 | 0.366 | 15.318 | 0.636 | -0.068 | 3 | 16.292 |
| pooled | ebm | 土豆 | target_mean_price_next_30d | 15.597 | 2.026 | 0.322 | 0.409 | 16.026 | 0.636 | -0.045 | 3 | 16.610 |
| baseline | baseline_previous_year_same_period | 土豆 | target_mean_price_next_30d | 18.648 | 10.011 | 0.385 | 0.466 | 17.463 | 0.488 | 0.204 | 3 | 23.654 |
| pooled | ebm_tuned | 土豆 | target_mean_price_next_30d | 19.493 | 6.663 | 0.399 | 0.490 | 19.739 | 0.536 | 0.041 | 3 | 22.824 |
| pooled | elasticnet_tuned | 尖椒 | target_mean_price_next_30d | 11.817 | 0.688 | 0.673 | 0.907 | 11.025 | 0.635 | -0.020 | 3 | 12.161 |
| pooled | elasticnet | 尖椒 | target_mean_price_next_30d | 11.846 | 0.455 | 0.671 | 0.893 | 11.318 | 0.616 | 0.059 | 3 | 12.074 |
| pooled | ridge_tuned | 尖椒 | target_mean_price_next_30d | 11.953 | 0.486 | 0.677 | 0.896 | 11.434 | 0.622 | 0.064 | 3 | 12.196 |
| pooled | ridge | 尖椒 | target_mean_price_next_30d | 12.018 | 0.365 | 0.682 | 0.889 | 11.626 | 0.607 | 0.052 | 3 | 12.200 |
| pooled | linear | 尖椒 | target_mean_price_next_30d | 12.035 | 0.385 | 0.683 | 0.890 | 11.645 | 0.607 | 0.051 | 3 | 12.228 |
| pooled | extra_trees_tuned | 尖椒 | target_mean_price_next_30d | 12.392 | 1.618 | 0.703 | 0.925 | 11.781 | 0.637 | 0.015 | 3 | 13.202 |

## 3. 训练/预测 runtime（每 fold 秒）

| model | route | fold | target | fold_runtime_sec |
|---|---|---|---|---|
| linear | per_crop | fold1_test2024 | target_mean_price_next_30d | 0.120 |
| ridge | per_crop | fold1_test2024 | target_mean_price_next_30d | 0.120 |
| elasticnet | per_crop | fold1_test2024 | target_mean_price_next_30d | 0.196 |
| random_forest | per_crop | fold1_test2024 | target_mean_price_next_30d | 7.672 |
| extra_trees | per_crop | fold1_test2024 | target_mean_price_next_30d | 2.935 |
| hist_gradient_boosting | per_crop | fold1_test2024 | target_mean_price_next_30d | 8.696 |
| xgboost | per_crop | fold1_test2024 | target_mean_price_next_30d | 4.063 |
| lightgbm | per_crop | fold1_test2024 | target_mean_price_next_30d | 8.414 |
| catboost | per_crop | fold1_test2024 | target_mean_price_next_30d | 5.670 |
| ebm | per_crop | fold1_test2024 | target_mean_price_next_30d | 39.857 |
| hist_gradient_boosting_tuned | per_crop | fold1_test2024 | target_mean_price_next_30d | 7.314 |
| extra_trees_tuned | per_crop | fold1_test2024 | target_mean_price_next_30d | 2.377 |
| random_forest_tuned | per_crop | fold1_test2024 | target_mean_price_next_30d | 2.408 |
| ridge_tuned | per_crop | fold1_test2024 | target_mean_price_next_30d | 0.086 |
| elasticnet_tuned | per_crop | fold1_test2024 | target_mean_price_next_30d | 0.091 |
| lightgbm_tuned | per_crop | fold1_test2024 | target_mean_price_next_30d | 14.602 |
| ebm_tuned | per_crop | fold1_test2024 | target_mean_price_next_30d | 31.926 |
| linear | per_crop | fold2_test2025 | target_mean_price_next_30d | 0.171 |
| ridge | per_crop | fold2_test2025 | target_mean_price_next_30d | 0.161 |
| elasticnet | per_crop | fold2_test2025 | target_mean_price_next_30d | 0.285 |
| random_forest | per_crop | fold2_test2025 | target_mean_price_next_30d | 11.606 |
| extra_trees | per_crop | fold2_test2025 | target_mean_price_next_30d | 3.746 |
| hist_gradient_boosting | per_crop | fold2_test2025 | target_mean_price_next_30d | 18.487 |
| xgboost | per_crop | fold2_test2025 | target_mean_price_next_30d | 4.579 |
| lightgbm | per_crop | fold2_test2025 | target_mean_price_next_30d | 8.837 |
| catboost | per_crop | fold2_test2025 | target_mean_price_next_30d | 6.538 |
| ebm | per_crop | fold2_test2025 | target_mean_price_next_30d | 42.317 |
| hist_gradient_boosting_tuned | per_crop | fold2_test2025 | target_mean_price_next_30d | 7.577 |
| extra_trees_tuned | per_crop | fold2_test2025 | target_mean_price_next_30d | 2.547 |
| random_forest_tuned | per_crop | fold2_test2025 | target_mean_price_next_30d | 3.357 |

## 4. 天气 ablation（market-only vs market+weather）

| model | crop | market_only | market_plus_weather | delta_WAPE_pct |
|---|---|---|---|---|
| extra_trees | 土豆 | 6.607 | 6.771 | 2.483 |
| extra_trees | 尖椒 | 13.326 | 13.631 | 2.284 |
| extra_trees | 甘蓝 | 17.033 | 17.383 | 2.051 |
| extra_trees | 芸豆 | 9.788 | 9.896 | 1.111 |
| extra_trees | 芹菜 | 15.843 | 15.994 | 0.953 |
| extra_trees | 茄子 | 16.676 | 16.125 | -3.304 |
| extra_trees | 西红柿 | 9.773 | 9.867 | 0.967 |
| extra_trees | 青椒 | 13.629 | 13.496 | -0.974 |
| extra_trees | 韭菜 | 13.181 | 13.144 | -0.276 |
| extra_trees | 黄瓜 | 16.386 | 16.992 | 3.698 |
| hist_gradient_boosting | 土豆 | 6.789 | 7.018 | 3.370 |
| hist_gradient_boosting | 尖椒 | 13.880 | 15.487 | 11.578 |
| hist_gradient_boosting | 甘蓝 | 22.458 | 22.695 | 1.053 |
| hist_gradient_boosting | 芸豆 | 11.182 | 10.173 | -9.024 |
| hist_gradient_boosting | 芹菜 | 17.105 | 15.925 | -6.897 |
| hist_gradient_boosting | 茄子 | 17.703 | 17.149 | -3.132 |
| hist_gradient_boosting | 西红柿 | 10.249 | 10.211 | -0.375 |
| hist_gradient_boosting | 青椒 | 14.019 | 15.072 | 7.510 |
| hist_gradient_boosting | 韭菜 | 14.297 | 14.538 | 1.683 |
| hist_gradient_boosting | 黄瓜 | 18.419 | 19.238 | 4.450 |

> 结论：与既有研究 A06 一致——天气未带来稳定改善（平均 ΔWAPE 见上表）。
> 正式价格模型**只用 market 特征**；天气特征仅用于气候暴露模块。

## 5. 区间（P10/P50/P90）

| method | coverage | mean_width | median_width | n_groups | undercoverage_rate | coverage_std | coverage_gap |
|---|---|---|---|---|---|---|---|
| residual_adaptive_scaled | 0.744 | 3.835 | 3.835 | 30 | 0.300 | 0.330 | 0.056 |
| seasonal_window_quantile | 0.709 | 2.486 | 2.315 | 30 | 0.433 | 0.146 | 0.091 |
| seasonal_quantile | 0.708 | 2.766 | 2.646 | 30 | 0.500 | 0.139 | 0.092 |
| residual_calibration_expanding | 0.684 | 2.072 | 2.072 | 30 | 0.367 | 0.287 | 0.116 |
| residual_calibration_recent | 0.655 | 1.971 | 1.971 | 30 | 0.433 | 0.273 | 0.145 |
| residual_calibration | 0.620 | 1.898 | 1.898 | 30 | 0.533 | 0.266 | 0.180 |
| mapie_aci | 0.504 | 1.224 | 1.140 | 18 | 0.833 | 0.179 | 0.296 |
| quantile_regression | 0.361 | 0.712 | 0.612 | 30 | 1.000 | 0.086 | 0.439 |
| mapie_enbpi | 0.178 | 0.338 | 0.338 | 30 | 1.000 | 0.087 | 0.622 |
| mapie_enbpi_calibrated | 0.056 | 0.190 | 0.190 | 30 | 1.000 | 0.060 | 0.744 |

> 方法：seasonal_quantile（历史同月分位，scenario range）/ residual_calibration（80/20 时序内分裂残差）/
> quantile_regression（LightGBM）/ mapie_enbpi（MAPIE TimeSeriesRegressor，非交换性适配）。
> `coverage by crop / by fold` 明细见 `evaluation/metrics/interval_calibration.csv`。

## 6. Optuna 调参（时间序列目标）

| family | route | best_value |
|---|---|---|
| hist_gradient_boosting | per_crop | 15.8254 |
| extra_trees | per_crop | 13.9250 |
| random_forest | per_crop | 14.2946 |
| ridge | per_crop | 14.7102 |
| elasticnet | per_crop | 12.5705 |
| lightgbm | per_crop | 15.4225 |
| ebm | per_crop | 16.4783 |
| hist_gradient_boosting | pooled | 13.8291 |
| extra_trees | pooled | 12.4657 |

> objective = 跨 fold WAPE 的 mean + 0.5×std；**禁止随机 CV**。若无显著改善则保留默认参数。

## 7. 观测口径与禁忌（复述）

- lag 为「观测滞后」；周末不发布；
- 沈阳 = wholesale（元/kg 已换算）；朝阳 = market_average；锦州 = 单一层级——三者禁止混用；
- 90 天以上不做精确点预测；气象不驱动价格。
