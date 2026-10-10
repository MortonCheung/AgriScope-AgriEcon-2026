# Failed / Negative Experiments（如实保留）

## 复杂模型未赢过 baseline 的作物（h=30, 沈阳）
| crop | model | mean_WAPE | baseline_WAPE | improvement_vs_baseline_pct |
|---|---|---|---|---|
| 土豆 | baseline_last_value | 4.8449 | 4.8449 | 0.0000 |
| 甘蓝 | baseline_last_value | 13.7617 | 13.7617 | 0.0000 |
| 芹菜 | baseline_last_value | 10.8425 | 10.8425 | 0.0000 |


## 城市数据不足
- 大连 / 铁岭 / 丹东：`insufficient_market_data`（model_ready 无 market_daily）。

## 蔬菜成本/亩产缺口
| crop | cost_available | n_refs | best_class | cost_reliability | cost_range |
|---|---|---|---|---|---|
| 青椒 | False | 0 | NOT_FOUND | 0.0000 | nan |
| 尖椒 | False | 0 | NOT_FOUND | 0.0000 | nan |
| 茄子 | False | 0 | NOT_FOUND | 0.0000 | nan |
| 芹菜 | False | 0 | NOT_FOUND | 0.0000 | nan |
| 甘蓝 | False | 0 | NOT_FOUND | 0.0000 | nan |


## 区间未达名义覆盖
- 最优方法实际覆盖 0.745 vs 名义 0.80 → 若 |gap|>0.05 则降级为 scenario range。

## HRI 中等/弱 horizon 与稳健性衰减（§24/§25）
- 30 天(4 周)层面 HRI 区分力弱（仅少数作物显著），HRI 主要在 60/90 天有效。
- 时间序列稳健化后显著数下降：沈阳 12w raw 9/10 → **robust（block bootstrap + HAC 双通过）5/10**。
  即「raw signal strong, conditional/incremental weaker」——如实保留，不夸大。

## 组合未优于单作物（§34/§40）→ 正式状态 NO_DIVERSIFICATION_BENEFIT
- 集中度惩罚下最优组合仍收敛到单作物（HHI=1.0）→ “多作物一定更优”不成立；已作为合法状态输出。

## 上市窗口优化失败案例（§38）→ 正式状态 NO_FEASIBLE_WINDOW
- 黄瓜在代表 cut-off 上所有窗口的悲观利润为负 → `NO_FEASIBLE_WINDOW`（带 reason/assumptions），
  如实保留，不强行给出建议。

## Scenario Range 大多数需要加宽（§21/§22）
- 逐 crop×horizon 选择方法后：部分作物区间需加宽（如实标注 widen_factor），
  极差情形降级为 `scenario_range_unreliable` / `no_range_available`，**不再用总体覆盖率掩盖**。

## 成本/亩产数据耦合
- 无作物级真实成本的作物使用 SECTOR_PROXY（明确降权），利润置信度低；亩产为情景假设。
- 因此默认排序中 Profit 按 reliability 降权；用户提供真实成本/亩产后才以 weight=1.0 参与。
