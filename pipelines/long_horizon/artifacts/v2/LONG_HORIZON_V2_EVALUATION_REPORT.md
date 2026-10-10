# Long-Horizon V2 Evaluation

> RC2，模型 `long_horizon_v2_rc2`，数据 `f04b01b9b8399c15`，预注册协议 `3259aaad287e25b757c62e9bb293aaf0471a0bca34ffb5fae5a82f1ef8d7affe`。
> 历史 2024/2025/2026 已参与 RC1 target/model 选择；本轮没有真正 untouched 历史段。
> 2026 指标是 **reused retrospective audit**；`untouched_metric=null`、`final_effective_n=0`。

训练初始历史2021–2022；development2023用于候选研究，tuning2024用于模型选择，calibration2025仅确定残差范围，2026-01-01至09-14为已被查看的回顾审计。
每阶段训练必须 `label_end <= train_end`，测试目标全部 `label_end <= phase_end`，不跨阶段。选择先写锁文件，再运行calibration/audit。
比较 Last Value、target-aligned Seasonal Naive、历史同目标窗mean/median、Linear、ElasticNet、ExtraTrees、CatBoost。
年度阶段比嵌套walk-forward更易审计且校准角色独立；nested设计可以减少程序级selection optimism，却不能恢复已查看历史的独立性，且180d一年只约1–2个exposure blocks。

以下为逐作物均值的2026回顾审计，不是独立预测精度；所有phase/crop/method详细指标见CSV。

| horizon | target_type | WAPE | MAE | sMAPE | MASE | bias | direction_accuracy |
|---|---|---|---|---|---|---|---|
| 30 | cycle_market_average | 10.502 | 0.504 | 9.732 | 3.446 | 0.124 | 0.287 |
| 30 | harvest_market_price | 14.657 | 0.630 | 13.766 | 4.527 | 0.034 | 0.640 |
| 60 | cycle_market_average | 13.759 | 0.631 | 12.359 | 4.450 | 0.216 | 0.522 |
| 60 | harvest_market_price | 14.772 | 0.568 | 14.283 | 4.372 | 0.149 | 0.770 |
| 90 | cycle_market_average | 9.370 | 0.386 | 9.152 | 3.077 | -0.081 | 0.800 |
| 90 | harvest_market_price | 16.202 | 0.552 | 15.742 | 4.497 | 0.086 | 0.832 |
| 120 | cycle_market_average | 8.667 | 0.349 | 8.479 | 2.652 | -0.086 | 0.840 |
| 120 | harvest_market_price | 16.258 | 0.546 | 15.635 | 4.367 | 0.036 | 0.888 |
| 150 | cycle_market_average | 10.139 | 0.408 | 9.713 | 3.057 | 0.056 | 0.819 |
| 150 | harvest_market_price | 21.181 | 0.643 | 18.800 | 4.983 | 0.124 | 0.847 |
| 180 | cycle_market_average | 9.706 | 0.387 | 9.589 | 3.019 | -0.059 | 0.868 |
| 180 | harvest_market_price | 26.038 | 0.795 | 22.497 | 6.425 | 0.266 | 0.776 |

训练失败实际记录 `0`（逐项位于artifacts/v2/training_failures.json）。当前Final模型未改动。 production refit只在方法冻结后使用全部成熟历史标签；其权重不是历史逐阶段 evaluated model，不能拿它在旧测试段重报分数。
未来真正独立检验：协议冻结后发行不可变预测并记录模型/target/config/input hash，观察成熟上市窗口；未来资料不准用于调窗口、权重或门槛。
