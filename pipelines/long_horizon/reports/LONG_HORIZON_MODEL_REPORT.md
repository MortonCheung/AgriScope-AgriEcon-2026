# Long-Horizon Model Report（Phase 8 + 15）

> 只读回测，未修改 Final。数据指纹 `f04b01b9b8399c15`；生成时间 `2026-10-08 01:07:55`。
> 正式 target = `full`（(t, t+N] 窗口均价，见 `LONG_HORIZON_TARGET_STUDY.md`）。
> 折定义与 Final 一致（fold1=2024 / fold2=2025 / fold3=2026 截断），同折同口径。

## 1. Error Growth Curve（7 → 180d）

| horizon | best_method | best_method_WAPE | last_value_WAPE | same_season_median_WAPE | drift_trend90_WAPE | endpoint_best_WAPE | endpoint_last_value_WAPE | n_nonoverlap | exploratory |
|---|---|---|---|---|---|---|---|---|---|
| 7 | b_last_value | 5.33 | 5.33 | 19.39 | 6.24 | 8.25 | 8.25 | 201 | False |
| 14 | b_last_value | 7.93 | 7.93 | 19.51 | 10.22 | 13.11 | 13.11 | 100 | False |
| 30 | b_last_value | 12.02 | 12.02 | 19.81 | 18.94 | 20.44 | 20.44 | 68 | False |
| 60 | m_catboost | 15.91 | 17.57 | 21.54 | 38.12 | 30.55 | 31.60 | 34 | False |
| 90 | m_catboost | 16.52 | 22.88 | 23.95 | 62.55 | 36.34 | 42.08 | 22 | False |
| 120 | m_catboost | 15.95 | 27.95 | 26.66 | 94.04 | 40.63 | 50.49 | 17 | False |
| 150 | m_catboost | 15.56 | 32.14 | 28.84 | 137.24 | 42.32 | 54.92 | 13 | True |
| 180 | m_catboost | 14.70 | 36.72 | 29.91 | 207.40 | 41.96 | 59.66 | 11 | True |


**读数**：
1. 正式 target（`full` = N 天窗口均价）下，`best_method_WAPE` 在 30d 后**趋于平台（≈15–16%）**，
   不会爆炸 —— 因为长期「均价」本身是平滑、可回归到季节中枢的量；`last_value` 则从 5.3%(7d)
   单调退化到 36.7%(180d)，`drift_trend90`（趋势外推）在 ≥90d 彻底失效（62%→207%）。
2. **端点对照**（`endpoint_*` 列，单点价口径）误差随 horizon **持续增长**，
   这正是 Phase 7 判定 `full` 优于 `endpoint` 的直接证据（详见 `LONG_HORIZON_TARGET_STUDY.md`）。
3. `n_nonoverlap` 为审核过的非重叠样本量；150/180 标记 `exploratory=True`（样本不足以支撑上线级评估）。
4. 结论：长期能力应表述为**「N 天窗口均价的情景化估计」**，**不得**表述为「第 N 天精确点位」。

## 2. 逐 (crop × horizon) 最优方法（top-3 最难）

| crop | horizon | method | mean_WAPE |
|---|---|---|---|
| 甘蓝 | 150 | m_catboost | 25.72 |
| 甘蓝 | 120 | m_elasticnet | 25.08 |
| 甘蓝 | 180 | m_catboost | 24.68 |


完整 60 行见 `artifacts/long_horizon_selection.csv`。

## 3. 样本量（诚实读数）

| horizon | 非重叠样本均值 | 观测数均值 |
|---|---|---|
| 7.00 | 292.00 | 4.77 |
| 14.00 | 147.00 | 9.49 |
| 30.00 | 68.00 | 20.29 |
| 60.00 | 34.00 | 40.34 |
| 90.00 | 22.00 | 60.59 |
| 120.00 | 17.00 | 81.23 |
| 150.00 | 13.00 | 101.34 |
| 180.00 | 11.00 | 121.41 |


## 4. 方法清单

- 行内 PIT baseline：b_last_value, b_seasonal_naive_365, b_same_season_mean, b_same_season_median, b_drift_trend90
- 训练型 baseline：m_linear, m_extra_trees, m_elasticnet, m_catboost
- 判定：`score = mean_WAPE + 0.5·std_WAPE`（跨 fold 平均 + 稳定性惩罚），与 Final 选择口径一致。
