# Production Gate

> RC2，模型 `long_horizon_v2_rc2`，数据 `f04b01b9b8399c15`，预注册协议 `3259aaad287e25b757c62e9bb293aaf0471a0bca34ffb5fae5a82f1ef8d7affe`。
> 历史 2024/2025/2026 已参与 RC1 target/model 选择；本轮没有真正 untouched 历史段。
> 2026 指标是 **reused retrospective audit**；`untouched_metric=null`、`final_effective_n=0`。

门槛在2026 audit前预注册：绝对WAPE改善≥1pp且相对≥5%；至少3时期、≥75%时期改善；最差时期退化≤2pp；final保守exposure blocks≥12，paired block bootstrap 95% gain CI下界>0。区间另需calibration exposure blocks≥20，名义80%覆盖率独立检验在70%–90%之间。当前历史重用直接否决PRODUCTION_POINT；密集残差只能是scenario_range。

1pp/5%为预先确定的工程容差，避免0.003pp数值噪声升级，不是声称由final结果学出的最优阈值。Bootstrap按H跨度稀疏origin成对重采样，样本小于4不输出CI；现有CI仅探索性，不能作为独立显著证据。

状态：{'SCENARIO_ONLY': 80, 'EXPLORATORY_SCENARIO_ONLY': 40}。confidence全部low：缺真正未见证据、样本小、区间未独立验证，不能只凭horizon写medium/high。

未来符合冻结协议的数据到齐后可以独立评估，当前代码不自动升级；需要单独审核并发布新registry。
