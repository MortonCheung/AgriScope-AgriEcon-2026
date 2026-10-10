# Long-Horizon Registry / Method Map（Phase 17）

> 数据指纹 `f04b01b9b8399c15`；生成时间 `2026-10-08 01:07:58`。
> Gate 阈值由 **development 段（fold1=2024）** 推出：bias_frac_p95=0.5297，
> worst_ratio_p95=1.740（n_dev=178560）。

## 1. 状态分布

| production_status | n |
|---|---|
| EXPLORATORY_SCENARIO_ONLY | 20 |
| PRODUCTION_POINT | 28 |
| SCENARIO_ONLY | 12 |


## 2. 完整 Registry（60 行 → `artifacts/LONG_HORIZON_REGISTRY.csv`）

| crop | horizon | method | confidence | range_type | production_status | baseline_last_value_WAPE | range_coverage_oot |
|---|---|---|---|---|---|---|---|
| 土豆 | 30 | b_last_value | high | prediction_interval | SCENARIO_ONLY | 4.845 | 0.842 |
| 尖椒 | 30 | b_last_value | high | prediction_interval | SCENARIO_ONLY | 13.109 | 0.832 |
| 甘蓝 | 30 | b_last_value | high | prediction_interval | SCENARIO_ONLY | 13.762 | 0.879 |
| 芸豆 | 30 | m_catboost | high | prediction_interval | PRODUCTION_POINT | 10.604 | 0.894 |
| 芹菜 | 30 | b_last_value | high | scenario_range | SCENARIO_ONLY | 10.843 | 0.946 |
| 茄子 | 30 | b_last_value | high | prediction_interval | SCENARIO_ONLY | 12.209 | 0.743 |
| 西红柿 | 30 | b_last_value | high | prediction_interval | SCENARIO_ONLY | 9.801 | 0.844 |
| 青椒 | 30 | b_last_value | high | prediction_interval | SCENARIO_ONLY | 13.050 | 0.847 |
| 韭菜 | 30 | b_last_value | high | scenario_range | SCENARIO_ONLY | 13.354 | 0.624 |
| 黄瓜 | 30 | m_extra_trees | high | scenario_range | PRODUCTION_POINT | 18.574 | 0.911 |
| 土豆 | 60 | b_last_value | high | prediction_interval | SCENARIO_ONLY | 7.080 | 0.817 |
| 尖椒 | 60 | m_catboost | high | scenario_range | PRODUCTION_POINT | 19.823 | 0.486 |
| 甘蓝 | 60 | b_last_value | high | prediction_interval | SCENARIO_ONLY | 22.103 | 0.898 |
| 芸豆 | 60 | m_catboost | high | scenario_range | PRODUCTION_POINT | 12.952 | 0.906 |
| 芹菜 | 60 | b_last_value | high | scenario_range | SCENARIO_ONLY | 15.664 | 0.974 |
| 茄子 | 60 | b_last_value | high | prediction_interval | SCENARIO_ONLY | 18.337 | 0.836 |
| 西红柿 | 60 | m_catboost | high | prediction_interval | PRODUCTION_POINT | 15.170 | 0.708 |
| 青椒 | 60 | m_catboost | high | scenario_range | PRODUCTION_POINT | 20.316 | 0.363 |
| 韭菜 | 60 | m_extra_trees | high | scenario_range | PRODUCTION_POINT | 19.539 | 0.695 |
| 黄瓜 | 60 | m_extra_trees | high | prediction_interval | PRODUCTION_POINT | 24.685 | 0.875 |
| 土豆 | 90 | m_catboost | high | scenario_range | PRODUCTION_POINT | 8.380 | 0.552 |
| 尖椒 | 90 | m_catboost | high | scenario_range | PRODUCTION_POINT | 26.530 | 0.370 |
| 甘蓝 | 90 | m_elasticnet | high | scenario_range | PRODUCTION_POINT | 29.447 | 0.351 |
| 芸豆 | 90 | m_catboost | high | prediction_interval | PRODUCTION_POINT | 15.548 | 0.898 |
| 芹菜 | 90 | b_same_season_mean | high | scenario_range | PRODUCTION_POINT | 19.382 | 0.525 |
| 茄子 | 90 | m_elasticnet | high | scenario_range | PRODUCTION_POINT | 24.872 | 0.530 |
| 西红柿 | 90 | m_catboost | high | prediction_interval | PRODUCTION_POINT | 21.152 | 0.804 |
| 青椒 | 90 | m_catboost | high | scenario_range | PRODUCTION_POINT | 27.180 | 0.420 |
| 韭菜 | 90 | m_catboost | high | scenario_range | PRODUCTION_POINT | 26.740 | 0.682 |
| 黄瓜 | 90 | m_elasticnet | high | prediction_interval | PRODUCTION_POINT | 29.585 | 0.773 |
| 土豆 | 120 | m_extra_trees | medium | scenario_range | PRODUCTION_POINT | 9.205 | 0.532 |
| 尖椒 | 120 | m_catboost | medium | scenario_range | PRODUCTION_POINT | 34.102 | 0.435 |
| 甘蓝 | 120 | m_elasticnet | medium | scenario_range | PRODUCTION_POINT | 35.513 | 0.285 |
| 芸豆 | 120 | m_catboost | medium | scenario_range | PRODUCTION_POINT | 17.963 | 0.938 |
| 芹菜 | 120 | b_same_season_mean | medium | scenario_range | PRODUCTION_POINT | 22.179 | 0.529 |
| 茄子 | 120 | m_elasticnet | medium | scenario_range | PRODUCTION_POINT | 31.926 | 0.429 |
| 西红柿 | 120 | m_catboost | medium | scenario_range | PRODUCTION_POINT | 27.244 | 0.903 |
| 青椒 | 120 | m_catboost | medium | scenario_range | PRODUCTION_POINT | 34.749 | 0.479 |
| 韭菜 | 120 | m_extra_trees | medium | prediction_interval | PRODUCTION_POINT | 31.950 | 0.815 |
| 黄瓜 | 120 | m_elasticnet | medium | prediction_interval | PRODUCTION_POINT | 34.694 | 0.821 |
| 土豆 | 150 | m_extra_trees | medium | scenario_range | EXPLORATORY_SCENARIO_ONLY | 9.820 | 0.506 |
| 尖椒 | 150 | m_catboost | medium | scenario_range | EXPLORATORY_SCENARIO_ONLY | 40.555 | 0.435 |
| 甘蓝 | 150 | m_catboost | medium | scenario_range | EXPLORATORY_SCENARIO_ONLY | 40.041 | 0.429 |
| 芸豆 | 150 | m_catboost | medium | scenario_range | EXPLORATORY_SCENARIO_ONLY | 19.676 | 0.907 |
| 芹菜 | 150 | b_same_season_mean | medium | scenario_range | EXPLORATORY_SCENARIO_ONLY | 24.581 | 0.531 |
| 茄子 | 150 | m_catboost | medium | scenario_range | EXPLORATORY_SCENARIO_ONLY | 37.565 | 0.615 |
| 西红柿 | 150 | m_catboost | medium | prediction_interval | EXPLORATORY_SCENARIO_ONLY | 32.039 | 0.702 |
| 青椒 | 150 | m_extra_trees | medium | scenario_range | EXPLORATORY_SCENARIO_ONLY | 41.508 | 0.634 |
| 韭菜 | 150 | m_extra_trees | medium | prediction_interval | EXPLORATORY_SCENARIO_ONLY | 36.676 | 0.720 |
| 黄瓜 | 150 | m_elasticnet | medium | prediction_interval | EXPLORATORY_SCENARIO_ONLY | 38.978 | 0.845 |
| 土豆 | 180 | m_extra_trees | low | scenario_range | EXPLORATORY_SCENARIO_ONLY | 10.498 | 0.587 |
| 尖椒 | 180 | m_catboost | low | scenario_range | EXPLORATORY_SCENARIO_ONLY | 46.789 | 0.467 |
| 甘蓝 | 180 | m_catboost | low | scenario_range | EXPLORATORY_SCENARIO_ONLY | 46.640 | 0.523 |
| 芸豆 | 180 | m_catboost | low | prediction_interval | EXPLORATORY_SCENARIO_ONLY | 19.368 | 0.700 |
| 芹菜 | 180 | b_same_season_mean | low | scenario_range | EXPLORATORY_SCENARIO_ONLY | 28.168 | 0.583 |
| 茄子 | 180 | m_catboost | low | scenario_range | EXPLORATORY_SCENARIO_ONLY | 43.515 | 0.600 |
| 西红柿 | 180 | m_catboost | low | scenario_range | EXPLORATORY_SCENARIO_ONLY | 37.969 | 0.663 |
| 青椒 | 180 | m_catboost | low | scenario_range | EXPLORATORY_SCENARIO_ONLY | 47.122 | 0.590 |
| 韭菜 | 180 | m_elasticnet | low | prediction_interval | EXPLORATORY_SCENARIO_ONLY | 41.940 | 0.740 |
| 黄瓜 | 180 | m_elasticnet | low | prediction_interval | EXPLORATORY_SCENARIO_ONLY | 45.142 | 0.880 |


## 3. 口径声明

- **正式长期 target** = `full`（N 天窗口均价）。
- 长期能力一律表述为「情景化估计」；`range_type=scenario_range` 表示**未经校准**，
  **不得**称 prediction interval。
- 150/180 为探索级（`EXPLORATORY_SCENARIO_ONLY`），不得作为上线依据。
- LLM/Hybrid 未被赋「天然预测权」：本轮无真实 LLM 数值结果 → 一律 `SCENARIO_ONLY`。
