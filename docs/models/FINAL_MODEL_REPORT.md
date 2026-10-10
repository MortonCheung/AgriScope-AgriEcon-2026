# FINAL_MODEL_REPORT — AgriScope Decision Engine v1

## 0. 交付概览

- 输入快照（SHA256）→ Decision Dataset v1（14,100×107）→ 特征（严格 past-only，cutoff 可复现）
  → 逐作物价格模型 + 区间 → HRI / Market Risk / Climate Exposure / Production Context
  → Profit / Confidence / Decision Score → Python API → 历史回放 + 案例 → 报告与图表。
- 一条命令全流程：`python3 decision_engine/scripts/run_all.py`

## 1. Dataset（数字）

- 行数：14,100；列数：107；范围：2021-01-01 00:00:00 ~ 2026-09-14 00:00:00；
- 10 作物 × 1,410 观测日（日期集合一致，周末/节假日不发布）；
- 价格 0 缺失；join 无膨胀（见 DATASET_REPORT）。

## 2. Price Model（逐作物最终选择）

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

## 3. Interval（P10/P50/P90）

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

选定方法：`residual_adaptive_scaled`，coverage=0.743665074710236，
is_calibrated_interval=False。

## 4. HRI（组成/权重/敏感性/验证）

- 组件与权重：见 `docs/HRI_REPORT.md`；
- 敏感性：方案间 Spearman 与 ±20% 权重扰动见 `evaluation/metrics/hri_sensitivity.csv`；
- 高 HRI（Top5%）之后的实际价格变化（30/60/90 天）见 HRI_REPORT 第 3 节。

## 5. Climate（组成/基线/边界）

- 组件：暴雨/降水 P90/连旱/土壤干/高温/温度异常；基线 2010-2019（无 1991-2020 数据，如实标注）；
- 计划期用「历史同期气候概率」，不是天气预报；详见 `docs/CLIMATE_RISK_REPORT.md`。

## 6. Decision Engine（3 个完整输入输出例子）

见 `docs/DECISION_ENGINE_SPEC.md` 第 2 节（含价格/收益/风险/评分/置信度/原因/证据/限制）。

## 7. Historical Replay（全样本，非精选）

- 整体覆盖率：0.6661016949152543（n=590.0）；P50 平均绝对误差 0.9395587112268484 元/kg；
- 按年/按作物明细：`evaluation/metrics/replay_coverage_by_year.csv` / `by_crop.csv`；
- 案例（自动规则选择，含失败案例）：3 个高 HRI + 2 个普通 + 1 个失败（`evaluation/cases/replay_cases.json`）。

| case_type | case_id | replay_date | crop | hri | hri_level | predicted_range | realized | interval_hit | decision_score | confidence | p50_error |
|---|---|---|---|---|---|---|---|---|---|---|---|
| high_hri | HIGH-1 | 2024-08-13 | 韭菜 | 92.900 | very_high | [5.711771428571429, 7.241904761904762, 8.465142857142856] | 6.115 | 是 | 74.600 | 90.700 | NA |
| high_hri | HIGH-2 | 2025-10-22 | 黄瓜 | 92.200 | very_high | [5.507255411255411, 6.6380952380952385, 8.049555555555555] | 7.445 | 是 | 74.400 | 86.000 | NA |
| high_hri | HIGH-3 | 2024-09-27 | 西红柿 | 91.900 | very_high | [4.58742857142857, 6.15, 7.209790476190476] | 4.749 | 是 | 74.600 | 85.700 | NA |
| normal | NORMAL-1 | 2024-02-15 | 芸豆 | 48.500 | low | [5.592842105263157, 7.441166666666667, 8.4523] | 7.934 | 是 | 81.400 | 84.800 | NA |
| normal | NORMAL-2 | 2026-02-04 | 黄瓜 | 48.400 | low | [2.4268571428571426, 2.581954545454546, 2.7733] | 2.935 | 否 | 83.800 | 86.000 | NA |
| failure | FAIL-1 | 2025-11-06 | 尖椒 | 62.700 | high | [5.07787012987013, 7.12090909090909, 9.122356725146197] | 11.601 | 否 | 84.100 | 84.800 | 4.480 |

## 8. 朝阳 / 锦州 简化扩展

| crop | model | mean_WAPE | baseline_mean_WAPE | beats_baseline |
|---|---|---|---|---|
| 仔猪 | baseline_last_value | 3.297 | 3.297 | 否 |
| 圆葱 | baseline_last_value | 3.914 | 3.914 | 否 |
| 土豆 | baseline_last_value | 5.254 | 5.254 | 否 |
| 大白菜 | baseline_last_value | 10.838 | 10.838 | 否 |
| 大米 | baseline_last_value | 0.037 | 0.037 | 否 |
| 大豆 | baseline_last_value | 0.264 | 0.264 | 否 |
| 油菜 | regional_extra_trees | 14.615 | 17.446 | 是 |
| 牛肉 | baseline_last_value | 0.796 | 0.796 | 否 |
| 玉米 | baseline_last_value | 0.995 | 0.995 | 否 |
| 生猪 | baseline_last_value | 4.148 | 4.148 | 否 |
| 白萝卜 | baseline_last_value | 7.158 | 7.158 | 否 |
| 羊肉 | baseline_last_value | 0.676 | 0.676 | 否 |
| 胡萝卜 | baseline_last_value | 3.293 | 3.293 | 否 |
| 芸豆 | regional_extra_trees | 12.808 | 12.948 | 是 |
| 芹菜 | baseline_last_value | 10.880 | 10.880 | 否 |
| 茄子 | baseline_last_value | 11.766 | 11.766 | 否 |
| 菜花 | baseline_last_value | 12.044 | 12.044 | 否 |
| 菠菜 | regional_extra_trees | 15.491 | 20.495 | 是 |
| 蒜苔 | baseline_last_value | 3.109 | 3.109 | 否 |
| 西红柿 | baseline_last_value | 10.845 | 10.845 | 否 |
| 青椒 | regional_histgb | 13.890 | 14.179 | 是 |
| 面粉 | baseline_last_value | 0.235 | 0.235 | 否 |
| 韭菜 | regional_extra_trees | 11.131 | 13.651 | 是 |
| 鲜猪肉 | baseline_last_value | 2.768 | 2.768 | 否 |
| 鸡肉 | baseline_last_value | 0.336 | 0.336 | 否 |
| 鸡蛋 | baseline_last_value | 5.750 | 5.750 | 否 |
| 黄瓜 | regional_histgb | 15.523 | 17.553 | 是 |
| 五花猪肉 | baseline_rolling_mean_7 | 4.156 | 4.156 | 否 |
| 土豆 | baseline_last_value | 12.300 | 12.300 | 否 |
| 大白菜 | baseline_last_value | 16.369 | 16.369 | 否 |
| 大葱 | regional_extra_trees | 14.058 | 13.700 | 否 |
| 尖椒 | baseline_last_value | 16.604 | 16.604 | 否 |
| 带鱼 | regional_histgb | 2.766 | 4.008 | 是 |
| 架豆王 | regional_extra_trees | 12.830 | 16.529 | 是 |
| 柑橘 | baseline_last_value | 8.681 | 8.681 | 否 |
| 梨 | baseline_last_value | 4.935 | 4.935 | 否 |
| 牛奶 | baseline_seasonal_median | 0.000 | 0.000 | 否 |
| 牛肉 | baseline_last_value | 1.708 | 1.708 | 否 |
| 紫茄子 | regional_extra_trees | 14.021 | 16.219 | 是 |
| 羊肉 | baseline_last_value | 1.721 | 1.721 | 否 |
| 胡萝卜 | baseline_last_value | 8.888 | 8.888 | 否 |
| 芹菜 | baseline_last_value | 13.985 | 13.985 | 否 |
| 苹果 | baseline_last_value | 2.319 | 2.319 | 否 |
| 菜花 | baseline_last_value | 19.423 | 19.423 | 否 |
| 西红柿 | regional_extra_trees | 10.585 | 12.758 | 是 |
_（仅显示前 45 行）_

大连/铁岭/丹东：返回 `insufficient_market_data`（生产背景 + 气候暴露 + 低置信度），不造模型。

## 9. 开源组件采用结论

| library | model | WAPE | MAE | status | reason |
|---|---|---|---|---|---|
| prophet | prophet | 28.608 | 0.595 | BENCHMARK_ONLY | 季节基线候选（trend+weekly+yearly+changepoints）；与 SF/自研同原点比较 |
| prophet | prophet | 40.222 | 2.211 | BENCHMARK_ONLY | 季节基线候选（trend+weekly+yearly+changepoints）；与 SF/自研同原点比较 |
| prophet | prophet | 71.575 | 1.478 | BENCHMARK_ONLY | 季节基线候选（trend+weekly+yearly+changepoints）；与 SF/自研同原点比较 |
| prophet | prophet | 21.052 | 1.810 | BENCHMARK_ONLY | 季节基线候选（trend+weekly+yearly+changepoints）；与 SF/自研同原点比较 |
| prophet | prophet | 63.013 | 2.476 | BENCHMARK_ONLY | 季节基线候选（trend+weekly+yearly+changepoints）；与 SF/自研同原点比较 |
| prophet | prophet | 48.815 | 1.952 | BENCHMARK_ONLY | 季节基线候选（trend+weekly+yearly+changepoints）；与 SF/自研同原点比较 |
| prophet | prophet | 36.370 | 1.944 | BENCHMARK_ONLY | 季节基线候选（trend+weekly+yearly+changepoints）；与 SF/自研同原点比较 |
| prophet | prophet | 36.343 | 2.192 | BENCHMARK_ONLY | 季节基线候选（trend+weekly+yearly+changepoints）；与 SF/自研同原点比较 |
| prophet | prophet | 19.296 | 1.060 | BENCHMARK_ONLY | 季节基线候选（trend+weekly+yearly+changepoints）；与 SF/自研同原点比较 |
| prophet | prophet | 37.156 | 1.827 | BENCHMARK_ONLY | 季节基线候选（trend+weekly+yearly+changepoints）；与 SF/自研同原点比较 |
| flaml | flaml_pooled | 13.159 | 0.630 | BENCHMARK_ONLY | 轻量 AutoML（time-based holdout）；best=catboost |
| statsforecast | sf_auto_arima | 5.212 | 0.107 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_auto_arima | 12.443 | 0.692 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_auto_arima | 12.597 | 0.255 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_auto_arima | 10.810 | 0.928 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_auto_arima | 11.221 | 0.449 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_auto_arima | 12.754 | 0.492 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_auto_arima | 9.381 | 0.496 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_auto_arima | 11.881 | 0.701 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_auto_arima | 13.492 | 0.727 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_auto_arima | 20.046 | 0.979 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_auto_ces | 5.372 | 0.110 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_auto_ces | 12.696 | 0.702 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_auto_ces | 13.412 | 0.273 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_auto_ces | 10.988 | 0.943 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_auto_ces | 11.196 | 0.447 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_auto_ces | 12.301 | 0.472 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_auto_ces | 9.536 | 0.503 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_auto_ces | 12.680 | 0.744 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_auto_ces | 13.935 | 0.750 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_auto_ces | 18.055 | 0.882 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_auto_ets | 5.212 | 0.107 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_auto_ets | 12.236 | 0.679 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_auto_ets | 12.988 | 0.263 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_auto_ets | 11.370 | 0.974 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_auto_ets | 11.198 | 0.448 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_auto_ets | 12.412 | 0.479 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_auto_ets | 9.654 | 0.510 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_auto_ets | 11.915 | 0.699 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_auto_ets | 14.320 | 0.771 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_auto_ets | 18.993 | 0.928 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_auto_theta | 5.245 | 0.107 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_auto_theta | 12.900 | 0.718 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_auto_theta | 13.427 | 0.273 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_auto_theta | 10.993 | 0.943 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_auto_theta | 11.207 | 0.448 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_auto_theta | 12.458 | 0.480 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_auto_theta | 9.775 | 0.516 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_auto_theta | 12.743 | 0.750 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_auto_theta | 14.290 | 0.768 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_auto_theta | 18.717 | 0.914 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_naive | 5.212 | 0.107 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_naive | 12.886 | 0.718 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_naive | 13.426 | 0.273 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_naive | 10.980 | 0.942 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_naive | 11.219 | 0.449 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_naive | 12.451 | 0.480 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_naive | 9.744 | 0.514 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_naive | 12.726 | 0.749 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |
| statsforecast | sf_naive | 14.295 | 0.769 | BENCHMARK_ONLY | 统计基线候选；与 ML/基线在同一 fold 与原点上比较 |

详细对比（含未采用与失败原因）见 `evaluation/open_source/OPEN_SOURCE_INTEGRATION_REPORT.md`。

## 10. 最终 runtime 依赖（保持轻量）

- 正式 pipeline：pandas / numpy / scikit-learn（+ 选定模型的实现库）+ 自研 calibration；
- 统计基线（StatsForecast 等）与 AutoGluon 等仅作 benchmark（详见开源报告），不进入正式 runtime；
- 具体因回测结果而定，若统计模型胜出则以其为正式实现。
