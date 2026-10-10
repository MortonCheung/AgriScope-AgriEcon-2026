# Long-Horizon Freeze Gate（Phase 21）

> 生成时间 `2026-10-08 01:10:36`；冻结数据指纹 `f04b01b9b8399c15`。
> 本文件为**判定**，不是实现说明；所有数字来自 `models/long_horizon/artifacts/` 与 `llm/artifacts/`。

## 0. 冻结判定

```
LONG_HORIZON_FROZEN_STATISTICAL = YES      # 统计长期层（30–120）已回测并进入 Registry
LONG_HORIZON_LLM = NOT_PRODUCTION          # 无真实 key → 未评估 → SCENARIO_ONLY
LONG_HORIZON_JOB = PRECOMPUTE_ONLY         # 独立 Job，前端只读
FINAL_MODEL_UNCHANGED = YES                # 未重训、未调权重、未改算法
DAILY_PIPELINE_UNCHANGED = YES
```

## 1. §104 · 30/60/90/120/150/180 的正式 OOT WAPE（target=`full`，窗口均价）

| horizon | best_method | best_method_WAPE | last_value_WAPE | same_season_median_WAPE | drift_trend90_WAPE | endpoint_best_WAPE | n_nonoverlap | exploratory |
|---|---|---|---|---|---|---|---|---|
| 7 | b_last_value | 5.331 | 5.331 | 19.392 | 6.236 | 8.254 | 201 | False |
| 14 | b_last_value | 7.926 | 7.926 | 19.514 | 10.223 | 13.114 | 100 | False |
| 30 | b_last_value | 12.015 | 12.015 | 19.809 | 18.940 | 20.438 | 68 | False |
| 60 | m_catboost | 15.912 | 17.567 | 21.544 | 38.118 | 30.551 | 34 | False |
| 90 | m_catboost | 16.522 | 22.882 | 23.948 | 62.550 | 36.341 | 22 | False |
| 120 | m_catboost | 15.947 | 27.952 | 26.663 | 94.043 | 40.632 | 17 | False |
| 150 | m_catboost | 15.558 | 32.144 | 28.838 | 137.236 | 42.320 | 13 | True |
| 180 | m_catboost | 14.695 | 36.715 | 29.914 | 207.395 | 41.961 | 11 | True |


口径：折与 Final 一致（fold1=2024 / fold2=2025 / fold3=2026 截断）；指标 = 跨 fold 平均 WAPE，
对 10 作物取平均；`endpoint_best_WAPE` 为**单点价**口径对照（用于证明窗口均价口径更稳）。
`n_nonoverlap` 为审核过的非重叠样本；150/180 标记探索级。

## 2. §105 · LLM 是否真的提高准确度

- **LLM 是否真的提高准确度：未评估（UNKNOWN）**。本轮无合法 LLM key，harness 使用确定性 stub（`is_real_llm=false`），消融全部 Δ=0.0% ⇒ 输出与上下文无关，**不能**回答该问题（§105-A/B/C 均不成立）。LLM 一律 `SCENARIO_ONLY`。

（消融表见 `LLM_ABLATION_REPORT.md`；hybrid 表见 `HYBRID_REPORT.md`。）

## 3. §106 · 最终 Method Map（60 行，完整见 `LONG_HORIZON_REGISTRY.csv`）

状态分布：

| production_status | n |
|---|---|
| EXPLORATORY_SCENARIO_ONLY | 20 |
| PRODUCTION_POINT | 28 |
| SCENARIO_ONLY | 12 |


| crop | horizon | method | confidence | range_type | production_status | baseline_last_value_WAPE |
|---|---|---|---|---|---|---|
| 土豆 | 30 | b_last_value | high | prediction_interval | SCENARIO_ONLY | 4.845 |
| 尖椒 | 30 | b_last_value | high | prediction_interval | SCENARIO_ONLY | 13.109 |
| 甘蓝 | 30 | b_last_value | high | prediction_interval | SCENARIO_ONLY | 13.762 |
| 芸豆 | 30 | m_catboost | high | prediction_interval | PRODUCTION_POINT | 10.604 |
| 芹菜 | 30 | b_last_value | high | scenario_range | SCENARIO_ONLY | 10.843 |
| 茄子 | 30 | b_last_value | high | prediction_interval | SCENARIO_ONLY | 12.209 |
| 西红柿 | 30 | b_last_value | high | prediction_interval | SCENARIO_ONLY | 9.801 |
| 青椒 | 30 | b_last_value | high | prediction_interval | SCENARIO_ONLY | 13.050 |
| 韭菜 | 30 | b_last_value | high | scenario_range | SCENARIO_ONLY | 13.354 |
| 黄瓜 | 30 | m_extra_trees | high | scenario_range | PRODUCTION_POINT | 18.574 |
| 土豆 | 60 | b_last_value | high | prediction_interval | SCENARIO_ONLY | 7.080 |
| 尖椒 | 60 | m_catboost | high | scenario_range | PRODUCTION_POINT | 19.823 |
| 甘蓝 | 60 | b_last_value | high | prediction_interval | SCENARIO_ONLY | 22.103 |
| 芸豆 | 60 | m_catboost | high | scenario_range | PRODUCTION_POINT | 12.952 |
| 芹菜 | 60 | b_last_value | high | scenario_range | SCENARIO_ONLY | 15.664 |
| 茄子 | 60 | b_last_value | high | prediction_interval | SCENARIO_ONLY | 18.337 |
| 西红柿 | 60 | m_catboost | high | prediction_interval | PRODUCTION_POINT | 15.170 |
| 青椒 | 60 | m_catboost | high | scenario_range | PRODUCTION_POINT | 20.316 |
| 韭菜 | 60 | m_extra_trees | high | scenario_range | PRODUCTION_POINT | 19.539 |
| 黄瓜 | 60 | m_extra_trees | high | prediction_interval | PRODUCTION_POINT | 24.685 |
| 土豆 | 90 | m_catboost | high | scenario_range | PRODUCTION_POINT | 8.380 |
| 尖椒 | 90 | m_catboost | high | scenario_range | PRODUCTION_POINT | 26.530 |
| 甘蓝 | 90 | m_elasticnet | high | scenario_range | PRODUCTION_POINT | 29.447 |
| 芸豆 | 90 | m_catboost | high | prediction_interval | PRODUCTION_POINT | 15.548 |
| 芹菜 | 90 | b_same_season_mean | high | scenario_range | PRODUCTION_POINT | 19.382 |
| 茄子 | 90 | m_elasticnet | high | scenario_range | PRODUCTION_POINT | 24.872 |
| 西红柿 | 90 | m_catboost | high | prediction_interval | PRODUCTION_POINT | 21.152 |
| 青椒 | 90 | m_catboost | high | scenario_range | PRODUCTION_POINT | 27.180 |
| 韭菜 | 90 | m_catboost | high | scenario_range | PRODUCTION_POINT | 26.740 |
| 黄瓜 | 90 | m_elasticnet | high | prediction_interval | PRODUCTION_POINT | 29.585 |
| 土豆 | 120 | m_extra_trees | medium | scenario_range | PRODUCTION_POINT | 9.205 |
| 尖椒 | 120 | m_catboost | medium | scenario_range | PRODUCTION_POINT | 34.102 |
| 甘蓝 | 120 | m_elasticnet | medium | scenario_range | PRODUCTION_POINT | 35.513 |
| 芸豆 | 120 | m_catboost | medium | scenario_range | PRODUCTION_POINT | 17.963 |
| 芹菜 | 120 | b_same_season_mean | medium | scenario_range | PRODUCTION_POINT | 22.179 |
| 茄子 | 120 | m_elasticnet | medium | scenario_range | PRODUCTION_POINT | 31.926 |
| 西红柿 | 120 | m_catboost | medium | scenario_range | PRODUCTION_POINT | 27.244 |
| 青椒 | 120 | m_catboost | medium | scenario_range | PRODUCTION_POINT | 34.749 |
| 韭菜 | 120 | m_extra_trees | medium | prediction_interval | PRODUCTION_POINT | 31.950 |
| 黄瓜 | 120 | m_elasticnet | medium | prediction_interval | PRODUCTION_POINT | 34.694 |
| 土豆 | 150 | m_extra_trees | medium | scenario_range | EXPLORATORY_SCENARIO_ONLY | 9.820 |
| 尖椒 | 150 | m_catboost | medium | scenario_range | EXPLORATORY_SCENARIO_ONLY | 40.555 |
| 甘蓝 | 150 | m_catboost | medium | scenario_range | EXPLORATORY_SCENARIO_ONLY | 40.041 |
| 芸豆 | 150 | m_catboost | medium | scenario_range | EXPLORATORY_SCENARIO_ONLY | 19.676 |
| 芹菜 | 150 | b_same_season_mean | medium | scenario_range | EXPLORATORY_SCENARIO_ONLY | 24.581 |
| 茄子 | 150 | m_catboost | medium | scenario_range | EXPLORATORY_SCENARIO_ONLY | 37.565 |
| 西红柿 | 150 | m_catboost | medium | prediction_interval | EXPLORATORY_SCENARIO_ONLY | 32.039 |
| 青椒 | 150 | m_extra_trees | medium | scenario_range | EXPLORATORY_SCENARIO_ONLY | 41.508 |
| 韭菜 | 150 | m_extra_trees | medium | prediction_interval | EXPLORATORY_SCENARIO_ONLY | 36.676 |
| 黄瓜 | 150 | m_elasticnet | medium | prediction_interval | EXPLORATORY_SCENARIO_ONLY | 38.978 |
| 土豆 | 180 | m_extra_trees | low | scenario_range | EXPLORATORY_SCENARIO_ONLY | 10.498 |
| 尖椒 | 180 | m_catboost | low | scenario_range | EXPLORATORY_SCENARIO_ONLY | 46.789 |
| 甘蓝 | 180 | m_catboost | low | scenario_range | EXPLORATORY_SCENARIO_ONLY | 46.640 |
| 芸豆 | 180 | m_catboost | low | prediction_interval | EXPLORATORY_SCENARIO_ONLY | 19.368 |
| 芹菜 | 180 | b_same_season_mean | low | scenario_range | EXPLORATORY_SCENARIO_ONLY | 28.168 |
| 茄子 | 180 | m_catboost | low | scenario_range | EXPLORATORY_SCENARIO_ONLY | 43.515 |
| 西红柿 | 180 | m_catboost | low | scenario_range | EXPLORATORY_SCENARIO_ONLY | 37.969 |
| 青椒 | 180 | m_catboost | low | scenario_range | EXPLORATORY_SCENARIO_ONLY | 47.122 |
| 韭菜 | 180 | m_elasticnet | low | prediction_interval | EXPLORATORY_SCENARIO_ONLY | 41.940 |
| 黄瓜 | 180 | m_elasticnet | low | prediction_interval | EXPLORATORY_SCENARIO_ONLY | 45.142 |


## 4. 区间口径（诚实性）

`range_type=prediction_interval` 仅在 **development 折学得的残差比值带在 OOT 上覆盖率落入
[0.70, 0.90]** 时给出；其余一律 `scenario_range`。**禁止**把 `scenario_range` 说成概率区间。

## 5. 样本与可行性对账

| horizon | 非重叠样本均值 | 窗口观测数均值 |
|---|---|---|
| 7.000 | 292.000 | 4.770 |
| 14.000 | 147.000 | 9.490 |
| 30.000 | 68.000 | 20.290 |
| 60.000 | 34.000 | 40.340 |
| 90.000 | 22.000 | 60.590 |
| 120.000 | 17.000 | 81.230 |
| 150.000 | 13.000 | 101.340 |
| 180.000 | 11.000 | 121.410 |


## 6. 冻结指纹（对账用）

| LONG_HORIZON_METRICS.csv | LONG_HORIZON_REGISTRY.csv | error_growth_curve.csv | llm_ablation.csv | long_horizon_snapshot |
|---|---|---|---|---|
| 5a5c06a7d0fc8236 | 8da9bdcfd248cf0a | b31e27ccf953b88c | 5b6c333ab93c2dbd | e424539908c5b77fa5d1a0c75eee4f80 |


Long-Horizon 快照：`as_of=2026-09-14`，`snapshot_hash=e424539908c5b77fa5d1a0c75eee4f80`，
条目数 `60`。

## 7. 交付物（§41）

- `LONG_HORIZON_TARGET_STUDY.md`
- `LONG_HORIZON_MODEL_REPORT.md`
- `LONG_HORIZON_METRICS.csv`
- `LONG_HORIZON_REGISTRY.csv`
- `LLM_FORECAST_REPORT.md`
- `LLM_ABLATION_REPORT.md`
- `HYBRID_REPORT.md`
- `LONG_HORIZON_FREEZE_GATE.md`

## 8. 已知限制

1. 长期能力是**「N 天窗口均价」的情景化估计**，不是第 N 天点位预测；
2. 150/180 探索级（OOT 非重叠样本 13/11，fold3 更少），不得作为上线依据；
3. 本快照基于冻结 Final 数据（anchor=数据最新观测日），与 Daily 实时快照可能不同步，
   Daily 更新后需重跑 Long-Horizon Job；
4. 城市级作物物候 `NOT_FOUND`（仅省级/区域级月粒度日历），长期机制特征未接入；
5. LLM 未评估；`fallback_used` 语义为「未走 LLM 数值链路」。
