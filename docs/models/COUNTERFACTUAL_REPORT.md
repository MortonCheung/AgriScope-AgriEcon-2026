# COUNTERFACTUAL_REPORT — 反事实压力测试与鲁棒决策

> 定位：**参数压力测试 / what-if 情景**，不是因果推断。
> 禁止表述："暴雨导致减产 20%"；正确表述："在『亩产下降 20%』压力情景下……"

## 1. 支持的 shocks（§28）

| shock | mean_profit_delta_pct | worst_profit_delta_pct | mean_roi_delta |
|---|---|---|---|
| climate_risk_+15 | 0.000 | 0.000 | 0.000 |
| cost_+10% | -0.214 | -0.230 | -4.353 |
| cost_+20% | -0.428 | -0.450 | -7.980 |
| harvest_delay_+14d | 0.000 | 0.000 | 0.000 |
| harvest_delay_+7d | 0.000 | 0.000 | 0.000 |
| market_risk_+15 | 0.000 | 0.000 | 0.000 |
| price_+10% | 10.214 | 10.190 | 4.788 |
| price_-10% | -10.214 | -10.230 | -4.788 |
| price_-20% | -20.428 | -20.450 | -9.576 |
| yield_-10% | -10.214 | -10.230 | -4.788 |
| yield_-20% | -20.428 | -20.450 | -9.576 |

## 2. 鲁棒决策与 Minimax Regret（§30/§31）

- `regret = 同情景下最优方案利润 − 本方案利润`；Minimax Regret = 最小化最大机会损失；
- 示例 Minimax 方案：芸豆
  （max_regret = 0.0）；
- 结果表：`evaluation/optimization/stress_test_results.csv`（3 种偏好 × Top5 方案 × 11 shocks）。

## 3. 决策评分饱和提示

v1 的 decision_score 使用 ROI 线性映射，在 ROI 远高于盈亏平衡带时会饱和（分数不随价格冲击变化）。
因此压力测试同时输出 `profit_delta / profit_delta_pct / roi_delta` 作为主信号（见上表）。
