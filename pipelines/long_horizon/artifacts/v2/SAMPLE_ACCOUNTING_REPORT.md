# Sample Accounting

> RC2，模型 `long_horizon_v2_rc2`，数据 `f04b01b9b8399c15`，预注册协议 `3259aaad287e25b757c62e9bb293aaf0471a0bca34ffb5fae5a82f1ef8d7affe`。
> 历史 2024/2025/2026 已参与 RC1 target/model 选择；本轮没有真正 untouched 历史段。
> 2026 指标是 **reused retrospective audit**；`untouched_metric=null`、`final_effective_n=0`。

冻结数据 2021-01-01 至 2026-09-14，每作物 1410 观测；缺失日不生成价格。
唯一数量来源 `LONG_HORIZON_SAMPLE_ACCOUNTING.csv`。calendar_candidates=阶段内理论成熟日历origin；observed_candidates=有真实origin且目标质控通过；nonoverlap_samples=target价格窗不相交的贪心样本；effective_test_samples=origin间距至少max(H,target_end_offset)的保守exposure blocks。后者不是已证明统计独立，不能扩大成window14每14天就是独立120d预测。full_history_nonoverlap单列，不能代替evaluation count。

| horizon | target | observed_candidates | nonoverlap_samples | retrospective_exposure_blocks | actual_independent_samples |
|---|---|---|---|---|---|
| 30 | cycle_market_average | 154.000 | 8.000 | 8.000 | 0 |
| 30 | harvest_market_price | 144.000 | 15.000 | 5.000 | 0 |
| 60 | cycle_market_average | 133.000 | 4.000 | 4.000 | 0 |
| 60 | harvest_market_price | 124.000 | 13.000 | 3.000 | 0 |
| 90 | cycle_market_average | 112.000 | 2.000 | 2.000 | 0 |
| 90 | harvest_market_price | 103.000 | 11.000 | 2.000 | 0 |
| 120 | cycle_market_average | 90.000 | 2.000 | 2.000 | 0 |
| 120 | harvest_market_price | 82.000 | 9.000 | 1.000 | 0 |
| 150 | cycle_market_average | 72.000 | 1.000 | 1.000 | 0 |
| 150 | harvest_market_price | 62.000 | 7.000 | 1.000 | 0 |
| 180 | cycle_market_average | 50.000 | 1.000 | 1.000 | 0 |
| 180 | harvest_market_price | 41.000 | 5.000 | 1.000 | 0 |

跨作物同日价格共同市场波动，不把10作物倍增为10倍独立时间样本。当前全部actual independent final samples为0。
