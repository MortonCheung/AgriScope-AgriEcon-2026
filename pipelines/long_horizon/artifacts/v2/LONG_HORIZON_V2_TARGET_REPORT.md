# Long-Horizon V2 Target

> RC2，模型 `long_horizon_v2_rc2`，数据 `f04b01b9b8399c15`，预注册协议 `3259aaad287e25b757c62e9bb293aaf0471a0bca34ffb5fae5a82f1ef8d7affe`。
> 历史 2024/2025/2026 已参与 RC1 target/model 选择；本轮没有真正 untouched 历史段。
> 2026 指标是 **reused retrospective audit**；`untouched_metric=null`、`final_effective_n=0`。

`cycle_market_average` = 决策后 `(t,t+H]` 已观测批发价算术均值，回答周期市场中枢。
`harvest_market_price` = `harvest_post_14`，回答预计上市时点附近实际销售窗口的批发市场价。
物候没有可信沈阳日粒度依据；H/预计上市日必须来自用户，不按作物猜测。

所有窗口按整数日偏移程序定义：centered14 = `[t+H-7,t+H+7)`，共14日；post14 = `[t+H,t+H+14)`，共14日。
7/30日同样使用半开区间；奇数 centered7 = `[H-3,H+4)`。endpoint 采用 H 日最近向前观测，最大回退3日。
目标仅取已有观测，不插值。窗口必须完整成熟，观测覆盖至少50%，内部断档不超过10日。

选择只使用 development2023+tuning2024。30日窗保留研究对照，但默认销售持续整月缺乏用户确认，不能仅因平滑导致误差低就成为默认Harvest。合格7/14日窗取平均baseline WAPE最低，2%相对容差内按预锁定业务偏好 post14/centered14/post7/centered7。

| candidate | business_eligible | mean_WAPE |
|---|---|---|
| cycle_market_average | False | 23.975 |
| endpoint | False | 33.990 |
| harvest_centered_14 | True | 33.825 |
| harvest_centered_30 | False | 33.148 |
| harvest_centered_7 | True | 33.876 |
| harvest_post_14 | True | 34.311 |
| harvest_post_30 | False | 34.516 |
| harvest_post_7 | True | 34.092 |
