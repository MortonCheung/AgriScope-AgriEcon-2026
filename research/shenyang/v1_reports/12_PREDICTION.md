# 12 预测模型（Phase 12，§四十九~§五十三）

## 1 结论摘要

- 正式预测模型仅在此前描述 / 异常 / 滞后 / 事件 / 传导 / 异质性 / 物候 / 年度生产
  全部完成后启动（§四十九 前置条件已满足）。
- 目标：价格异常与成交量异常，各 2 种口径 x 3 种特征口径 x 6 个模型。
- **复杂模型是否比简单基线有提升**（§五十 核心问题）见第 6 节；总体判断以 test（2026）RMSE 为准。
- **关键读法（务必先看第 7 节）**：价格/成交量异常序列本身高度持续（滞后 1 期自相关
  见第 7 节），因此「用昨日异常预测今日异常」即可拿到很高的 R2；
  这部分能力**与天气无关**。判别天气是否有用的正确做法是：
  只看去掉自回归项后的 `F_wx` 口径相对均值基线的增量（第 7 节 `gain_from_weather`）。
- MAPE/SMAPE **不适用**：目标为去季节化异常（含 0 与负值），分母可为 0，全部记 NA（§五十三）。
- 数据断裂 / 覆盖限制不插补，均按 BLOCKED 登记（见 reports/BLOCKERS.md）。

## 2 切分与防泄漏（§五十一~§五十二）

| split | start | end | rows | crops | n_public_holiday |
| --- | --- | --- | --- | --- | --- |
| train | 2021-01-01 | 2024-12-31 | 9850 | 10 | 280 |
| valid | 2025-01-02 | 2025-12-31 | 2500 | 10 | 130 |
| test | 2026-01-05 | 2026-09-14 | 1750 | 10 | 50 |

- 代码中**不存在** `train_test_split` / 任何 shuffle；
- 中位数填补与标准化仅用训练集 fit（`Prep` 类），特征只用 shift 滞后列与历史异常统计；
- 特征口径定义：
  - `F_wx`：天气滞后列（lag1/3/7/14d）+ 日历控制 + 品种 FE，**无自回归项**（用于分离天气贡献）；
  - `F_lag`（**主口径**）：`F_wx` + 自回归项（昨日/前二交易日异常、昨日量价水平），全部为 t-1 及更早信息；
  - `F_now`：`F_lag` + 当日天气，属**同期临近**口径，仅作对照；
- 三口径均**不含当日价格/成交量水平**（当日价格是目标的分子，属泄漏）；
- 目标 `hist` 口径（`*_anomaly_z_hist`）与本项目前序步骤一致，但其留一年法的基线取自
  「其他年份」（含测试年之后的年份），存在跨年信息；为此额外构造 `strict` 口径
  （`*_anomaly_pct_strict`，基线**只用严格更早年份**同期中位数），作为泄漏稳健性对照。

## 3 特征

| target_kind | feature_set | feature | group | missing_rate |
| --- | --- | --- | --- | --- |
| hist | F_wx | precipitation_lag1d | weather_lag | 0.0007 |
| hist | F_wx | precip_3d_lag1d | weather_lag | 0.0007 |
| hist | F_wx | precip_7d_lag1d | weather_lag | 0.0007 |
| hist | F_wx | temp_max_lag1d | weather_lag | 0.0007 |
| hist | F_wx | vpd_lag1d | weather_lag | 0.0007 |
| hist | F_wx | soil_moisture_0_7_lag1d | weather_lag | 0.0007 |
| hist | F_wx | temp_anomaly_lag1d | weather_lag | 0.0007 |
| hist | F_wx | precipitation_lag3d | weather_lag | 0.0007 |
| hist | F_wx | precip_3d_lag3d | weather_lag | 0.0007 |
| hist | F_wx | precip_7d_lag3d | weather_lag | 0.0007 |
| hist | F_wx | temp_max_lag3d | weather_lag | 0.0007 |
| hist | F_wx | vpd_lag3d | weather_lag | 0.0007 |
| hist | F_wx | soil_moisture_0_7_lag3d | weather_lag | 0.0007 |
| hist | F_wx | precipitation_lag7d | weather_lag | 0.0035 |
| hist | F_wx | precip_3d_lag7d | weather_lag | 0.0035 |
| hist | F_wx | precip_7d_lag7d | weather_lag | 0.0035 |
| hist | F_wx | temp_max_lag7d | weather_lag | 0.0035 |
| hist | F_wx | vpd_lag7d | weather_lag | 0.0035 |
| hist | F_wx | soil_moisture_0_7_lag7d | weather_lag | 0.0035 |
| hist | F_wx | precipitation_lag14d | weather_lag | 0.0071 |
| hist | F_wx | precip_3d_lag14d | weather_lag | 0.0071 |
| hist | F_wx | precip_7d_lag14d | weather_lag | 0.0071 |
| hist | F_wx | temp_max_lag14d | weather_lag | 0.0071 |
| hist | F_wx | vpd_lag14d | weather_lag | 0.0071 |
| hist | F_wx | soil_moisture_0_7_lag14d | weather_lag | 0.0071 |
| hist | F_wx | is_public_holiday | calendar | 0.0000 |
| hist | F_wx | year_t | calendar | 0.0000 |
| hist | F_wx | m2 | calendar | 0.0000 |
| hist | F_wx | m3 | calendar | 0.0000 |
| hist | F_wx | m4 | calendar | 0.0000 |
| hist | F_wx | m5 | calendar | 0.0000 |
| hist | F_wx | m6 | calendar | 0.0000 |
| hist | F_wx | m7 | calendar | 0.0000 |
| hist | F_wx | m8 | calendar | 0.0000 |
| hist | F_wx | m9 | calendar | 0.0000 |
| hist | F_wx | m10 | calendar | 0.0000 |
| hist | F_wx | m11 | calendar | 0.0000 |
| hist | F_wx | m12 | calendar | 0.0000 |
| hist | F_wx | crop_尖椒 | crop_fixed_effect | 0.0000 |
| hist | F_wx | crop_甘蓝 | crop_fixed_effect | 0.0000 |
| hist | F_wx | crop_芸豆 | crop_fixed_effect | 0.0000 |
| hist | F_wx | crop_芹菜 | crop_fixed_effect | 0.0000 |
| hist | F_wx | crop_茄子 | crop_fixed_effect | 0.0000 |
| hist | F_wx | crop_西红柿 | crop_fixed_effect | 0.0000 |
| hist | F_wx | crop_青椒 | crop_fixed_effect | 0.0000 |
| hist | F_wx | crop_韭菜 | crop_fixed_effect | 0.0000 |
| hist | F_wx | crop_黄瓜 | crop_fixed_effect | 0.0000 |
| hist | F_lag | precipitation_lag1d | weather_lag | 0.0007 |
| hist | F_lag | precip_3d_lag1d | weather_lag | 0.0007 |
| hist | F_lag | precip_7d_lag1d | weather_lag | 0.0007 |
| hist | F_lag | temp_max_lag1d | weather_lag | 0.0007 |
| hist | F_lag | vpd_lag1d | weather_lag | 0.0007 |
| hist | F_lag | soil_moisture_0_7_lag1d | weather_lag | 0.0007 |
| hist | F_lag | temp_anomaly_lag1d | weather_lag | 0.0007 |
| hist | F_lag | precipitation_lag3d | weather_lag | 0.0007 |
| hist | F_lag | precip_3d_lag3d | weather_lag | 0.0007 |
| hist | F_lag | precip_7d_lag3d | weather_lag | 0.0007 |
| hist | F_lag | temp_max_lag3d | weather_lag | 0.0007 |
| hist | F_lag | vpd_lag3d | weather_lag | 0.0007 |
| hist | F_lag | soil_moisture_0_7_lag3d | weather_lag | 0.0007 |

## 4 测试集总体表现（test = 2026）

| target_kind | target | feature_set | model | n | mae | rmse | r2 | bias |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| hist | price | F_lag | baseline_mean | 1750 | 0.6396 | 0.8943 | -0.1921 | -0.1091 |
| hist | price | F_lag | baseline_persistence | 1750 | 0.1212 | 0.1966 | 0.9424 | 0.0086 |
| hist | price | F_lag | baseline_seasonal_naive | 1750 | 0.8237 | 1.1069 | -0.8261 | -0.1079 |
| hist | price | F_lag | elasticnet | 1750 | 0.1292 | 0.1980 | 0.9416 | 0.0145 |
| hist | price | F_lag | gam | 1750 | 0.1391 | 0.2064 | 0.9365 | -0.0035 |
| hist | price | F_lag | lightgbm | 1750 | 0.1445 | 0.2133 | 0.9322 | 0.0011 |
| hist | price | F_now | baseline_mean | 1750 | 0.6396 | 0.8943 | -0.1921 | -0.1091 |
| hist | price | F_now | baseline_persistence | 1750 | 0.1212 | 0.1966 | 0.9424 | 0.0086 |
| hist | price | F_now | baseline_seasonal_naive | 1750 | 0.8237 | 1.1069 | -0.8261 | -0.1079 |
| hist | price | F_now | elasticnet | 1750 | 0.1287 | 0.1970 | 0.9422 | 0.0018 |
| hist | price | F_now | gam | 1750 | 0.1532 | 0.2254 | 0.9243 | 0.0047 |
| hist | price | F_now | lightgbm | 1750 | 0.1392 | 0.2077 | 0.9357 | -0.0054 |
| hist | price | F_wx | baseline_mean | 1750 | 0.6396 | 0.8943 | -0.1921 | -0.1091 |
| hist | price | F_wx | baseline_persistence | 1750 | 0.1212 | 0.1966 | 0.9424 | 0.0086 |
| hist | price | F_wx | baseline_seasonal_naive | 1750 | 0.8237 | 1.1069 | -0.8261 | -0.1079 |
| hist | price | F_wx | elasticnet | 1750 | 0.7785 | 0.9812 | -0.4351 | 0.1575 |
| hist | price | F_wx | gam | 1750 | 0.7970 | 1.0170 | -0.5415 | 0.0597 |
| hist | price | F_wx | lightgbm | 1750 | 0.8561 | 1.0381 | -0.6063 | 0.2831 |
| hist | volume | F_lag | baseline_mean | 1750 | 0.9429 | 1.0960 | -1.0641 | 0.2173 |
| hist | volume | F_lag | baseline_persistence | 1750 | 0.2308 | 0.4283 | 0.6849 | 0.0006 |
| hist | volume | F_lag | baseline_seasonal_naive | 1750 | 0.9681 | 1.1870 | -1.4208 | 0.1624 |
| hist | volume | F_lag | elasticnet | 1750 | 0.2880 | 0.4225 | 0.6933 | 0.0103 |
| hist | volume | F_lag | gam | 1750 | 0.3108 | 0.4378 | 0.6707 | -0.0062 |
| hist | volume | F_lag | lightgbm | 1750 | 0.3382 | 0.4376 | 0.6710 | -0.0206 |
| hist | volume | F_now | baseline_mean | 1750 | 0.9429 | 1.0960 | -1.0641 | 0.2173 |
| hist | volume | F_now | baseline_persistence | 1750 | 0.2308 | 0.4283 | 0.6849 | 0.0006 |
| hist | volume | F_now | baseline_seasonal_naive | 1750 | 0.9681 | 1.1870 | -1.4208 | 0.1624 |
| hist | volume | F_now | elasticnet | 1750 | 0.2936 | 0.4256 | 0.6887 | 0.0189 |
| hist | volume | F_now | gam | 1750 | 0.3582 | 0.5245 | 0.5274 | -0.0482 |
| hist | volume | F_now | lightgbm | 1750 | 0.3391 | 0.4390 | 0.6688 | -0.0030 |
| hist | volume | F_wx | baseline_mean | 1750 | 0.9429 | 1.0960 | -1.0641 | 0.2173 |
| hist | volume | F_wx | baseline_persistence | 1750 | 0.2308 | 0.4283 | 0.6849 | 0.0006 |
| hist | volume | F_wx | baseline_seasonal_naive | 1750 | 0.9681 | 1.1870 | -1.4208 | 0.1624 |
| hist | volume | F_wx | elasticnet | 1750 | 0.9228 | 1.1000 | -1.0790 | -0.1003 |
| hist | volume | F_wx | gam | 1750 | 0.9999 | 1.2185 | -1.5511 | -0.0993 |
| hist | volume | F_wx | lightgbm | 1750 | 0.7229 | 0.9210 | -0.4574 | -0.2430 |
| strict | price | F_lag | baseline_mean | 1750 | 0.1657 | 0.2112 | 0.0912 | 0.0349 |
| strict | price | F_lag | baseline_persistence | 1750 | 0.0402 | 0.0691 | 0.9026 | 0.0024 |
| strict | price | F_lag | baseline_seasonal_naive | 1750 | 0.2332 | 0.3026 | -0.8665 | 0.0316 |
| strict | price | F_lag | elasticnet | 1750 | 0.0442 | 0.0692 | 0.9023 | 0.0076 |
| strict | price | F_lag | gam | 1750 | 0.0566 | 0.0818 | 0.8636 | -0.0106 |
| strict | price | F_lag | lightgbm | 1750 | 0.0548 | 0.0782 | 0.8754 | 0.0061 |
| strict | price | F_now | baseline_mean | 1750 | 0.1657 | 0.2112 | 0.0912 | 0.0349 |
| strict | price | F_now | baseline_persistence | 1750 | 0.0402 | 0.0691 | 0.9026 | 0.0024 |
| strict | price | F_now | baseline_seasonal_naive | 1750 | 0.2332 | 0.3026 | -0.8665 | 0.0316 |
| strict | price | F_now | elasticnet | 1750 | 0.0441 | 0.0691 | 0.9028 | 0.0054 |
| strict | price | F_now | gam | 1750 | 0.0591 | 0.0846 | 0.8541 | -0.0099 |
| strict | price | F_now | lightgbm | 1750 | 0.0518 | 0.0766 | 0.8805 | 0.0061 |
| strict | price | F_wx | baseline_mean | 1750 | 0.1657 | 0.2112 | 0.0912 | 0.0349 |
| strict | price | F_wx | baseline_persistence | 1750 | 0.0402 | 0.0691 | 0.9026 | 0.0024 |
| strict | price | F_wx | baseline_seasonal_naive | 1750 | 0.2332 | 0.3026 | -0.8665 | 0.0316 |
| strict | price | F_wx | elasticnet | 1750 | 0.2174 | 0.2728 | -0.5166 | 0.0720 |
| strict | price | F_wx | gam | 1750 | 0.2338 | 0.2957 | -0.7818 | 0.0547 |
| strict | price | F_wx | lightgbm | 1750 | 0.2403 | 0.2956 | -0.7811 | 0.0891 |
| strict | volume | F_lag | baseline_mean | 1750 | 0.0466 | 0.0592 | 0.5145 | 0.0130 |
| strict | volume | F_lag | baseline_persistence | 1750 | 0.0188 | 0.0320 | 0.8582 | -0.0000 |
| strict | volume | F_lag | baseline_seasonal_naive | 1750 | 0.0653 | 0.0869 | -0.0462 | -0.0024 |
| strict | volume | F_lag | elasticnet | 1750 | 0.0216 | 0.0312 | 0.8650 | 0.0009 |
| strict | volume | F_lag | gam | 1750 | 0.0329 | 0.0428 | 0.7466 | 0.0041 |
| strict | volume | F_lag | lightgbm | 1750 | 0.0309 | 0.0413 | 0.7636 | -0.0047 |

## 5 验证集表现（valid = 2025）

| target_kind | target | feature_set | model | n | mae | rmse | r2 | bias |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| hist | price | F_lag | baseline_mean | 2500 | 1.0055 | 1.3079 | -0.1266 | 0.2303 |
| hist | price | F_lag | baseline_persistence | 2500 | 0.1467 | 0.2537 | 0.9576 | -0.0088 |
| hist | price | F_lag | baseline_seasonal_naive | 2500 | 1.2556 | 1.6935 | -0.8888 | 0.0364 |
| hist | price | F_lag | elasticnet | 2500 | 0.1571 | 0.2570 | 0.9565 | -0.0024 |
| hist | price | F_lag | gam | 2500 | 0.1687 | 0.2636 | 0.9542 | -0.0186 |
| hist | price | F_lag | lightgbm | 2500 | 0.1879 | 0.2922 | 0.9438 | -0.0278 |
| hist | price | F_now | baseline_mean | 2500 | 1.0055 | 1.3079 | -0.1266 | 0.2303 |
| hist | price | F_now | baseline_persistence | 2500 | 0.1467 | 0.2537 | 0.9576 | -0.0088 |
| hist | price | F_now | baseline_seasonal_naive | 2500 | 1.2556 | 1.6935 | -0.8888 | 0.0364 |
| hist | price | F_now | elasticnet | 2500 | 0.1585 | 0.2585 | 0.9560 | -0.0154 |
| hist | price | F_now | gam | 2500 | 0.1743 | 0.2670 | 0.9531 | -0.0227 |
| hist | price | F_now | lightgbm | 2500 | 0.1985 | 0.3059 | 0.9384 | -0.0317 |
| hist | price | F_wx | baseline_mean | 2500 | 1.0055 | 1.3079 | -0.1266 | 0.2303 |
| hist | price | F_wx | baseline_persistence | 2500 | 0.1467 | 0.2537 | 0.9576 | -0.0088 |
| hist | price | F_wx | baseline_seasonal_naive | 2500 | 1.2556 | 1.6935 | -0.8888 | 0.0364 |
| hist | price | F_wx | elasticnet | 2500 | 1.2963 | 1.6278 | -0.7450 | 0.2895 |
| hist | price | F_wx | gam | 2500 | 1.3613 | 1.7051 | -0.9147 | 0.2735 |
| hist | price | F_wx | lightgbm | 2500 | 1.4124 | 1.7518 | -1.0210 | 0.5469 |
| hist | volume | F_lag | baseline_mean | 2500 | 1.0374 | 1.3053 | -0.6617 | 0.2339 |
| hist | volume | F_lag | baseline_persistence | 2500 | 0.3616 | 0.5979 | 0.6514 | -0.0009 |
| hist | volume | F_lag | baseline_seasonal_naive | 2500 | 1.0255 | 1.3792 | -0.8554 | 0.1550 |
| hist | volume | F_lag | elasticnet | 2500 | 0.4032 | 0.5844 | 0.6669 | 0.0098 |
| hist | volume | F_lag | gam | 2500 | 0.4211 | 0.5939 | 0.6559 | -0.0153 |
| hist | volume | F_lag | lightgbm | 2500 | 0.4353 | 0.6028 | 0.6456 | -0.0597 |
| hist | volume | F_now | baseline_mean | 2500 | 1.0374 | 1.3053 | -0.6617 | 0.2339 |
| hist | volume | F_now | baseline_persistence | 2500 | 0.3616 | 0.5979 | 0.6514 | -0.0009 |
| hist | volume | F_now | baseline_seasonal_naive | 2500 | 1.0255 | 1.3792 | -0.8554 | 0.1550 |
| hist | volume | F_now | elasticnet | 2500 | 0.4080 | 0.5858 | 0.6653 | 0.0185 |
| hist | volume | F_now | gam | 2500 | 0.4431 | 0.6204 | 0.6246 | -0.0501 |
| hist | volume | F_now | lightgbm | 2500 | 0.4327 | 0.5891 | 0.6615 | -0.0768 |
| hist | volume | F_wx | baseline_mean | 2500 | 1.0374 | 1.3053 | -0.6617 | 0.2339 |
| hist | volume | F_wx | baseline_persistence | 2500 | 0.3616 | 0.5979 | 0.6514 | -0.0009 |
| hist | volume | F_wx | baseline_seasonal_naive | 2500 | 1.0255 | 1.3792 | -0.8554 | 0.1550 |
| hist | volume | F_wx | elasticnet | 2500 | 1.0057 | 1.2423 | -0.5052 | 0.0775 |
| hist | volume | F_wx | gam | 2500 | 1.0322 | 1.2772 | -0.5910 | 0.0306 |
| hist | volume | F_wx | lightgbm | 2500 | 0.7903 | 0.9958 | 0.0328 | -0.2459 |
| strict | price | F_lag | baseline_mean | 2500 | 0.2594 | 0.3283 | -0.0341 | 0.0932 |
| strict | price | F_lag | baseline_persistence | 2500 | 0.0332 | 0.0534 | 0.9726 | -0.0022 |
| strict | price | F_lag | baseline_seasonal_naive | 2500 | 0.3022 | 0.4075 | -0.5935 | 0.0481 |
| strict | price | F_lag | elasticnet | 2500 | 0.0392 | 0.0577 | 0.9681 | 0.0047 |
| strict | price | F_lag | gam | 2500 | 0.0477 | 0.0652 | 0.9592 | -0.0080 |
| strict | price | F_lag | lightgbm | 2500 | 0.0564 | 0.0792 | 0.9398 | -0.0000 |
| strict | price | F_now | baseline_mean | 2500 | 0.2594 | 0.3283 | -0.0341 | 0.0932 |
| strict | price | F_now | baseline_persistence | 2500 | 0.0332 | 0.0534 | 0.9726 | -0.0022 |
| strict | price | F_now | baseline_seasonal_naive | 2500 | 0.3022 | 0.4075 | -0.5935 | 0.0481 |
| strict | price | F_now | elasticnet | 2500 | 0.0399 | 0.0584 | 0.9673 | 0.0032 |
| strict | price | F_now | gam | 2500 | 0.0511 | 0.0691 | 0.9542 | -0.0072 |
| strict | price | F_now | lightgbm | 2500 | 0.0551 | 0.0802 | 0.9383 | -0.0040 |
| strict | price | F_wx | baseline_mean | 2500 | 0.2594 | 0.3283 | -0.0341 | 0.0932 |
| strict | price | F_wx | baseline_persistence | 2500 | 0.0332 | 0.0534 | 0.9726 | -0.0022 |
| strict | price | F_wx | baseline_seasonal_naive | 2500 | 0.3022 | 0.4075 | -0.5935 | 0.0481 |
| strict | price | F_wx | elasticnet | 2500 | 0.3135 | 0.3931 | -0.4834 | 0.0895 |
| strict | price | F_wx | gam | 2500 | 0.3453 | 0.4296 | -0.7716 | 0.0924 |
| strict | price | F_wx | lightgbm | 2500 | 0.3498 | 0.4377 | -0.8387 | 0.1533 |
| strict | volume | F_lag | baseline_mean | 2500 | 0.0565 | 0.0802 | 0.4082 | 0.0191 |
| strict | volume | F_lag | baseline_persistence | 2500 | 0.0284 | 0.0434 | 0.8269 | -0.0002 |
| strict | volume | F_lag | baseline_seasonal_naive | 2500 | 0.0608 | 0.0832 | 0.3638 | 0.0024 |
| strict | volume | F_lag | elasticnet | 2500 | 0.0302 | 0.0420 | 0.8380 | 0.0005 |
| strict | volume | F_lag | gam | 2500 | 0.0367 | 0.0472 | 0.7951 | 0.0021 |
| strict | volume | F_lag | lightgbm | 2500 | 0.0351 | 0.0475 | 0.7922 | -0.0044 |

## 6 是否优于简单基线

| target_kind | target | feature_set | model | rmse_test | r2_test | best_baseline | best_baseline_rmse | beats_baseline | complex_beats_simple | mae_test | n_test |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| hist | price | F_lag | baseline_persistence | 0.1966 | 0.9424 | baseline_persistence | 0.1966 | 否 | 否 | 0.1212 | 1750 |
| hist | price | F_lag | elasticnet | 0.1980 | 0.9416 | baseline_persistence | 0.1966 | 否 | 否 | 0.1292 | 1750 |
| hist | price | F_lag | gam | 0.2064 | 0.9365 | baseline_persistence | 0.1966 | 否 | 否 | 0.1391 | 1750 |
| hist | price | F_lag | lightgbm | 0.2133 | 0.9322 | baseline_persistence | 0.1966 | 否 | 否 | 0.1445 | 1750 |
| hist | price | F_lag | baseline_mean | 0.8943 | -0.1921 | baseline_persistence | 0.1966 | 否 | 否 | 0.6396 | 1750 |
| hist | price | F_lag | baseline_seasonal_naive | 1.1069 | -0.8261 | baseline_persistence | 0.1966 | 否 | 否 | 0.8237 | 1750 |
| hist | price | F_now | baseline_persistence | 0.1966 | 0.9424 | baseline_persistence | 0.1966 | 否 | 否 | 0.1212 | 1750 |
| hist | price | F_now | elasticnet | 0.1970 | 0.9422 | baseline_persistence | 0.1966 | 否 | 否 | 0.1287 | 1750 |
| hist | price | F_now | lightgbm | 0.2077 | 0.9357 | baseline_persistence | 0.1966 | 否 | 否 | 0.1392 | 1750 |
| hist | price | F_now | gam | 0.2254 | 0.9243 | baseline_persistence | 0.1966 | 否 | 否 | 0.1532 | 1750 |
| hist | price | F_now | baseline_mean | 0.8943 | -0.1921 | baseline_persistence | 0.1966 | 否 | 否 | 0.6396 | 1750 |
| hist | price | F_now | baseline_seasonal_naive | 1.1069 | -0.8261 | baseline_persistence | 0.1966 | 否 | 否 | 0.8237 | 1750 |
| hist | price | F_wx | baseline_persistence | 0.1966 | 0.9424 | baseline_persistence | 0.1966 | 否 | 否 | 0.1212 | 1750 |
| hist | price | F_wx | baseline_mean | 0.8943 | -0.1921 | baseline_persistence | 0.1966 | 否 | 否 | 0.6396 | 1750 |
| hist | price | F_wx | elasticnet | 0.9812 | -0.4351 | baseline_persistence | 0.1966 | 否 | 否 | 0.7785 | 1750 |
| hist | price | F_wx | gam | 1.0170 | -0.5415 | baseline_persistence | 0.1966 | 否 | 否 | 0.7970 | 1750 |
| hist | price | F_wx | lightgbm | 1.0381 | -0.6063 | baseline_persistence | 0.1966 | 否 | 否 | 0.8561 | 1750 |
| hist | price | F_wx | baseline_seasonal_naive | 1.1069 | -0.8261 | baseline_persistence | 0.1966 | 否 | 否 | 0.8237 | 1750 |
| hist | volume | F_lag | elasticnet | 0.4225 | 0.6933 | baseline_persistence | 0.4283 | 是 | 是 | 0.2880 | 1750 |
| hist | volume | F_lag | baseline_persistence | 0.4283 | 0.6849 | baseline_persistence | 0.4283 | 否 | 否 | 0.2308 | 1750 |
| hist | volume | F_lag | lightgbm | 0.4376 | 0.6710 | baseline_persistence | 0.4283 | 否 | 否 | 0.3382 | 1750 |
| hist | volume | F_lag | gam | 0.4378 | 0.6707 | baseline_persistence | 0.4283 | 否 | 否 | 0.3108 | 1750 |
| hist | volume | F_lag | baseline_mean | 1.0960 | -1.0641 | baseline_persistence | 0.4283 | 否 | 否 | 0.9429 | 1750 |
| hist | volume | F_lag | baseline_seasonal_naive | 1.1870 | -1.4208 | baseline_persistence | 0.4283 | 否 | 否 | 0.9681 | 1750 |
| hist | volume | F_now | elasticnet | 0.4256 | 0.6887 | baseline_persistence | 0.4283 | 是 | 是 | 0.2936 | 1750 |
| hist | volume | F_now | baseline_persistence | 0.4283 | 0.6849 | baseline_persistence | 0.4283 | 否 | 否 | 0.2308 | 1750 |
| hist | volume | F_now | lightgbm | 0.4390 | 0.6688 | baseline_persistence | 0.4283 | 否 | 否 | 0.3391 | 1750 |
| hist | volume | F_now | gam | 0.5245 | 0.5274 | baseline_persistence | 0.4283 | 否 | 否 | 0.3582 | 1750 |
| hist | volume | F_now | baseline_mean | 1.0960 | -1.0641 | baseline_persistence | 0.4283 | 否 | 否 | 0.9429 | 1750 |
| hist | volume | F_now | baseline_seasonal_naive | 1.1870 | -1.4208 | baseline_persistence | 0.4283 | 否 | 否 | 0.9681 | 1750 |
| hist | volume | F_wx | baseline_persistence | 0.4283 | 0.6849 | baseline_persistence | 0.4283 | 否 | 否 | 0.2308 | 1750 |
| hist | volume | F_wx | lightgbm | 0.9210 | -0.4574 | baseline_persistence | 0.4283 | 否 | 否 | 0.7229 | 1750 |
| hist | volume | F_wx | baseline_mean | 1.0960 | -1.0641 | baseline_persistence | 0.4283 | 否 | 否 | 0.9429 | 1750 |
| hist | volume | F_wx | elasticnet | 1.1000 | -1.0790 | baseline_persistence | 0.4283 | 否 | 否 | 0.9228 | 1750 |
| hist | volume | F_wx | baseline_seasonal_naive | 1.1870 | -1.4208 | baseline_persistence | 0.4283 | 否 | 否 | 0.9681 | 1750 |
| hist | volume | F_wx | gam | 1.2185 | -1.5511 | baseline_persistence | 0.4283 | 否 | 否 | 0.9999 | 1750 |
| strict | price | F_lag | baseline_persistence | 0.0691 | 0.9026 | baseline_persistence | 0.0691 | 否 | 否 | 0.0402 | 1750 |
| strict | price | F_lag | elasticnet | 0.0692 | 0.9023 | baseline_persistence | 0.0691 | 否 | 否 | 0.0442 | 1750 |
| strict | price | F_lag | lightgbm | 0.0782 | 0.8754 | baseline_persistence | 0.0691 | 否 | 否 | 0.0548 | 1750 |
| strict | price | F_lag | gam | 0.0818 | 0.8636 | baseline_persistence | 0.0691 | 否 | 否 | 0.0566 | 1750 |
| strict | price | F_lag | baseline_mean | 0.2112 | 0.0912 | baseline_persistence | 0.0691 | 否 | 否 | 0.1657 | 1750 |
| strict | price | F_lag | baseline_seasonal_naive | 0.3026 | -0.8665 | baseline_persistence | 0.0691 | 否 | 否 | 0.2332 | 1750 |
| strict | price | F_now | elasticnet | 0.0691 | 0.9028 | baseline_persistence | 0.0691 | 是 | 是 | 0.0441 | 1750 |
| strict | price | F_now | baseline_persistence | 0.0691 | 0.9026 | baseline_persistence | 0.0691 | 否 | 否 | 0.0402 | 1750 |
| strict | price | F_now | lightgbm | 0.0766 | 0.8805 | baseline_persistence | 0.0691 | 否 | 否 | 0.0518 | 1750 |
| strict | price | F_now | gam | 0.0846 | 0.8541 | baseline_persistence | 0.0691 | 否 | 否 | 0.0591 | 1750 |
| strict | price | F_now | baseline_mean | 0.2112 | 0.0912 | baseline_persistence | 0.0691 | 否 | 否 | 0.1657 | 1750 |
| strict | price | F_now | baseline_seasonal_naive | 0.3026 | -0.8665 | baseline_persistence | 0.0691 | 否 | 否 | 0.2332 | 1750 |
| strict | price | F_wx | baseline_persistence | 0.0691 | 0.9026 | baseline_persistence | 0.0691 | 否 | 否 | 0.0402 | 1750 |
| strict | price | F_wx | baseline_mean | 0.2112 | 0.0912 | baseline_persistence | 0.0691 | 否 | 否 | 0.1657 | 1750 |
| strict | price | F_wx | elasticnet | 0.2728 | -0.5166 | baseline_persistence | 0.0691 | 否 | 否 | 0.2174 | 1750 |
| strict | price | F_wx | lightgbm | 0.2956 | -0.7811 | baseline_persistence | 0.0691 | 否 | 否 | 0.2403 | 1750 |
| strict | price | F_wx | gam | 0.2957 | -0.7818 | baseline_persistence | 0.0691 | 否 | 否 | 0.2338 | 1750 |
| strict | price | F_wx | baseline_seasonal_naive | 0.3026 | -0.8665 | baseline_persistence | 0.0691 | 否 | 否 | 0.2332 | 1750 |
| strict | volume | F_lag | elasticnet | 0.0312 | 0.8650 | baseline_persistence | 0.0320 | 是 | 是 | 0.0216 | 1750 |
| strict | volume | F_lag | baseline_persistence | 0.0320 | 0.8582 | baseline_persistence | 0.0320 | 否 | 否 | 0.0188 | 1750 |
| strict | volume | F_lag | lightgbm | 0.0413 | 0.7636 | baseline_persistence | 0.0320 | 否 | 否 | 0.0309 | 1750 |
| strict | volume | F_lag | gam | 0.0428 | 0.7466 | baseline_persistence | 0.0320 | 否 | 否 | 0.0329 | 1750 |
| strict | volume | F_lag | baseline_mean | 0.0592 | 0.5145 | baseline_persistence | 0.0320 | 否 | 否 | 0.0466 | 1750 |
| strict | volume | F_lag | baseline_seasonal_naive | 0.0869 | -0.0462 | baseline_persistence | 0.0320 | 否 | 否 | 0.0653 | 1750 |

## 7 持续性 vs 天气：增量分解（本次预测结果的正确读法）

### 7.1 目标序列滞后 1 期自相关

| target_kind | target | split | n | lag1_autocorr | sd |
| --- | --- | --- | --- | --- | --- |
| hist | price | train | 9840 | 0.9637 | 1.3272 |
| hist | price | test | 1750 | 0.9715 | 0.8191 |
| hist | volume | train | 9840 | 0.9062 | 1.7452 |
| hist | volume | test | 1750 | 0.8424 | 0.7629 |
| strict | price | train | 8090 | 0.9562 | 0.3782 |
| strict | price | test | 1750 | 0.9520 | 0.2215 |
| strict | volume | train | 8090 | 0.9111 | 0.1710 |
| strict | volume | test | 1750 | 0.9291 | 0.0849 |

### 7.2 增量分解（test = 2026）

`gain_from_weather` = 最优学习器（仅天气口径 F_wx）R2 - 均值基线 R2；
`gain_from_persistence` = 最优学习器（含自回归 F_lag）R2 - 最优学习器（仅天气）R2。

| target_kind | target | r2_baseline_mean | r2_persistence | r2_best_weather_only | r2_best_weather_plus_AR | rmse_baseline_mean | rmse_persistence | rmse_best_weather_only | rmse_best_weather_plus_AR | gain_from_weather | gain_from_persistence | learner_beats_persistence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| hist | price | -0.1921 | 0.9424 | -0.4351 | 0.9416 | 0.8943 | 0.1966 | 0.9812 | 0.1980 | -0.2430 | 1.3767 | 否 |
| hist | volume | -1.0641 | 0.6849 | -0.4574 | 0.6933 | 1.0960 | 0.4283 | 0.9210 | 0.4225 | 0.6067 | 1.1506 | 是 |
| strict | price | 0.0912 | 0.9026 | -0.5166 | 0.9023 | 0.2112 | 0.0691 | 0.2728 | 0.0692 | -0.6079 | 1.4189 | 否 |
| strict | volume | 0.5145 | 0.8582 | 0.1110 | 0.8650 | 0.0592 | 0.0320 | 0.0801 | 0.0312 | -0.4036 | 0.7540 | 是 |

- 若 `gain_from_persistence` 远大于 `gain_from_weather`，则结论是：
  **样本外可预测性主要来自异常序列自身的持续性，天气的边际贡献很小**；
- 若 `learner_beats_persistence` 为「否」，则即使含自回归项的学习器也**没有超过**
  单纯的「昨日值」持续基线，说明 §五十 意义上的「复杂模型优于简单基线」在本数据上不成立。

## 8 Rolling Origin 扩张窗验证

| fold | test_year | target_kind | target | feature_set | model | n | rmse | r2 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2024 | hist | price | F_lag | baseline_mean | 2480 | 1.4245 | -0.2368 |
| 2 | 2025 | hist | price | F_lag | baseline_mean | 2500 | 1.3079 | -0.1266 |
| 3 | 2026 | hist | price | F_lag | baseline_mean | 1750 | 0.8585 | -0.0985 |
| 1 | 2024 | hist | price | F_lag | baseline_persistence | 2480 | 0.4329 | 0.8858 |
| 2 | 2025 | hist | price | F_lag | baseline_persistence | 2500 | 0.2537 | 0.9576 |
| 3 | 2026 | hist | price | F_lag | baseline_persistence | 1750 | 0.1966 | 0.9424 |
| 1 | 2024 | hist | price | F_lag | baseline_seasonal_naive | 2480 | 1.7219 | -0.8070 |
| 2 | 2025 | hist | price | F_lag | baseline_seasonal_naive | 2500 | 1.6935 | -0.8888 |
| 3 | 2026 | hist | price | F_lag | baseline_seasonal_naive | 1750 | 1.2240 | -1.2330 |
| 1 | 2024 | hist | price | F_lag | elasticnet | 2480 | 0.4269 | 0.8889 |
| 2 | 2025 | hist | price | F_lag | elasticnet | 2500 | 0.2570 | 0.9565 |
| 3 | 2026 | hist | price | F_lag | elasticnet | 1750 | 0.1958 | 0.9429 |
| 1 | 2024 | hist | price | F_lag | lightgbm | 2480 | 0.4399 | 0.8821 |
| 2 | 2025 | hist | price | F_lag | lightgbm | 2500 | 0.2922 | 0.9438 |
| 3 | 2026 | hist | price | F_lag | lightgbm | 1750 | 0.2096 | 0.9345 |
| 1 | 2024 | hist | price | F_now | baseline_mean | 2480 | 1.4245 | -0.2368 |
| 2 | 2025 | hist | price | F_now | baseline_mean | 2500 | 1.3079 | -0.1266 |
| 3 | 2026 | hist | price | F_now | baseline_mean | 1750 | 0.8585 | -0.0985 |
| 1 | 2024 | hist | price | F_now | baseline_persistence | 2480 | 0.4329 | 0.8858 |
| 2 | 2025 | hist | price | F_now | baseline_persistence | 2500 | 0.2537 | 0.9576 |
| 3 | 2026 | hist | price | F_now | baseline_persistence | 1750 | 0.1966 | 0.9424 |
| 1 | 2024 | hist | price | F_now | baseline_seasonal_naive | 2480 | 1.7219 | -0.8070 |
| 2 | 2025 | hist | price | F_now | baseline_seasonal_naive | 2500 | 1.6935 | -0.8888 |
| 3 | 2026 | hist | price | F_now | baseline_seasonal_naive | 1750 | 1.2240 | -1.2330 |
| 1 | 2024 | hist | price | F_now | elasticnet | 2480 | 0.4273 | 0.8887 |
| 2 | 2025 | hist | price | F_now | elasticnet | 2500 | 0.2585 | 0.9560 |
| 3 | 2026 | hist | price | F_now | elasticnet | 1750 | 0.1954 | 0.9431 |
| 1 | 2024 | hist | price | F_now | lightgbm | 2480 | 0.4322 | 0.8861 |
| 2 | 2025 | hist | price | F_now | lightgbm | 2500 | 0.3059 | 0.9384 |
| 3 | 2026 | hist | price | F_now | lightgbm | 1750 | 0.2007 | 0.9400 |
| 1 | 2024 | hist | price | F_wx | baseline_mean | 2480 | 1.4245 | -0.2368 |
| 2 | 2025 | hist | price | F_wx | baseline_mean | 2500 | 1.3079 | -0.1266 |
| 3 | 2026 | hist | price | F_wx | baseline_mean | 1750 | 0.8585 | -0.0985 |
| 1 | 2024 | hist | price | F_wx | baseline_persistence | 2480 | 0.4329 | 0.8858 |
| 2 | 2025 | hist | price | F_wx | baseline_persistence | 2500 | 0.2537 | 0.9576 |
| 3 | 2026 | hist | price | F_wx | baseline_persistence | 1750 | 0.1966 | 0.9424 |
| 1 | 2024 | hist | price | F_wx | baseline_seasonal_naive | 2480 | 1.7219 | -0.8070 |
| 2 | 2025 | hist | price | F_wx | baseline_seasonal_naive | 2500 | 1.6935 | -0.8888 |
| 3 | 2026 | hist | price | F_wx | baseline_seasonal_naive | 1750 | 1.2240 | -1.2330 |
| 1 | 2024 | hist | price | F_wx | elasticnet | 2480 | 1.5211 | -0.4101 |
| 2 | 2025 | hist | price | F_wx | elasticnet | 2500 | 1.6278 | -0.7450 |
| 3 | 2026 | hist | price | F_wx | elasticnet | 1750 | 0.9118 | -0.2392 |
| 1 | 2024 | hist | price | F_wx | lightgbm | 2480 | 1.6729 | -0.7056 |
| 2 | 2025 | hist | price | F_wx | lightgbm | 2500 | 1.7518 | -1.0210 |
| 3 | 2026 | hist | price | F_wx | lightgbm | 1750 | 1.1241 | -0.8835 |
| 1 | 2024 | hist | volume | F_lag | baseline_mean | 2480 | 1.2217 | -1.4259 |
| 2 | 2025 | hist | volume | F_lag | baseline_mean | 2500 | 1.3053 | -0.6617 |
| 3 | 2026 | hist | volume | F_lag | baseline_mean | 1750 | 0.9490 | -0.5474 |
| 1 | 2024 | hist | volume | F_lag | baseline_persistence | 2480 | 0.6769 | 0.2554 |
| 2 | 2025 | hist | volume | F_lag | baseline_persistence | 2500 | 0.5979 | 0.6514 |
| 3 | 2026 | hist | volume | F_lag | baseline_persistence | 1750 | 0.4283 | 0.6849 |
| 1 | 2024 | hist | volume | F_lag | baseline_seasonal_naive | 2480 | 1.2992 | -1.7430 |
| 2 | 2025 | hist | volume | F_lag | baseline_seasonal_naive | 2500 | 1.3792 | -0.8554 |
| 3 | 2026 | hist | volume | F_lag | baseline_seasonal_naive | 1750 | 1.0543 | -0.9097 |
| 1 | 2024 | hist | volume | F_lag | elasticnet | 2480 | 0.6363 | 0.3420 |
| 2 | 2025 | hist | volume | F_lag | elasticnet | 2500 | 0.5844 | 0.6669 |
| 3 | 2026 | hist | volume | F_lag | elasticnet | 1750 | 0.4166 | 0.7018 |
| 1 | 2024 | hist | volume | F_lag | lightgbm | 2480 | 0.6122 | 0.3909 |
| 2 | 2025 | hist | volume | F_lag | lightgbm | 2500 | 0.6028 | 0.6456 |
| 3 | 2026 | hist | volume | F_lag | lightgbm | 1750 | 0.4212 | 0.6952 |
| 1 | 2024 | hist | volume | F_now | baseline_mean | 2480 | 1.2217 | -1.4259 |
| 2 | 2025 | hist | volume | F_now | baseline_mean | 2500 | 1.3053 | -0.6617 |
| 3 | 2026 | hist | volume | F_now | baseline_mean | 1750 | 0.9490 | -0.5474 |
| 1 | 2024 | hist | volume | F_now | baseline_persistence | 2480 | 0.6769 | 0.2554 |
| 2 | 2025 | hist | volume | F_now | baseline_persistence | 2500 | 0.5979 | 0.6514 |
| 3 | 2026 | hist | volume | F_now | baseline_persistence | 1750 | 0.4283 | 0.6849 |
| 1 | 2024 | hist | volume | F_now | baseline_seasonal_naive | 2480 | 1.2992 | -1.7430 |
| 2 | 2025 | hist | volume | F_now | baseline_seasonal_naive | 2500 | 1.3792 | -0.8554 |
| 3 | 2026 | hist | volume | F_now | baseline_seasonal_naive | 1750 | 1.0543 | -0.9097 |
| 1 | 2024 | hist | volume | F_now | elasticnet | 2480 | 0.6402 | 0.3340 |
| 2 | 2025 | hist | volume | F_now | elasticnet | 2500 | 0.5858 | 0.6653 |
| 3 | 2026 | hist | volume | F_now | elasticnet | 1750 | 0.4169 | 0.7014 |
| 1 | 2024 | hist | volume | F_now | lightgbm | 2480 | 0.6157 | 0.3838 |
| 2 | 2025 | hist | volume | F_now | lightgbm | 2500 | 0.5891 | 0.6615 |
| 3 | 2026 | hist | volume | F_now | lightgbm | 1750 | 0.4211 | 0.6953 |
| 1 | 2024 | hist | volume | F_wx | baseline_mean | 2480 | 1.2217 | -1.4259 |
| 2 | 2025 | hist | volume | F_wx | baseline_mean | 2500 | 1.3053 | -0.6617 |
| 3 | 2026 | hist | volume | F_wx | baseline_mean | 1750 | 0.9490 | -0.5474 |
| 1 | 2024 | hist | volume | F_wx | baseline_persistence | 2480 | 0.6769 | 0.2554 |
| 2 | 2025 | hist | volume | F_wx | baseline_persistence | 2500 | 0.5979 | 0.6514 |
| 3 | 2026 | hist | volume | F_wx | baseline_persistence | 1750 | 0.4283 | 0.6849 |
| 1 | 2024 | hist | volume | F_wx | baseline_seasonal_naive | 2480 | 1.2992 | -1.7430 |
| 2 | 2025 | hist | volume | F_wx | baseline_seasonal_naive | 2500 | 1.3792 | -0.8554 |
| 3 | 2026 | hist | volume | F_wx | baseline_seasonal_naive | 1750 | 1.0543 | -0.9097 |
| 1 | 2024 | hist | volume | F_wx | elasticnet | 2480 | 1.6124 | -3.2255 |
| 2 | 2025 | hist | volume | F_wx | elasticnet | 2500 | 1.2423 | -0.5052 |
| 3 | 2026 | hist | volume | F_wx | elasticnet | 1750 | 0.9671 | -0.6070 |
| 1 | 2024 | hist | volume | F_wx | lightgbm | 2480 | 1.0974 | -0.9572 |
| 2 | 2025 | hist | volume | F_wx | lightgbm | 2500 | 0.9958 | 0.0328 |
| 3 | 2026 | hist | volume | F_wx | lightgbm | 1750 | 0.7838 | -0.0556 |
| 1 | 2024 | strict | price | F_lag | baseline_mean | 2480 | 0.4169 | -0.2508 |
| 2 | 2025 | strict | price | F_lag | baseline_mean | 2500 | 0.3283 | -0.0341 |
| 3 | 2026 | strict | price | F_lag | baseline_mean | 1750 | 0.2075 | 0.1223 |
| 1 | 2024 | strict | price | F_lag | baseline_persistence | 2480 | 0.1171 | 0.9013 |
| 2 | 2025 | strict | price | F_lag | baseline_persistence | 2500 | 0.0534 | 0.9726 |
| 3 | 2026 | strict | price | F_lag | baseline_persistence | 1750 | 0.0691 | 0.9026 |
| 1 | 2024 | strict | price | F_lag | baseline_seasonal_naive | 2480 | 0.4935 | -0.7526 |
| 2 | 2025 | strict | price | F_lag | baseline_seasonal_naive | 2500 | 0.4075 | -0.5935 |
| 3 | 2026 | strict | price | F_lag | baseline_seasonal_naive | 1750 | 0.2805 | -0.6028 |
| 1 | 2024 | strict | price | F_lag | elasticnet | 2480 | 0.1180 | 0.8998 |

## 9 分层评价（§五十三）

### 9.1 灾害影响窗 vs 平常期（test = 2026）

| ('target_kind', '') | ('target', '') | ('feature_set', '') | ('model', '') | ('n', 'extreme') | ('n', 'normal') | ('rmse', 'extreme') | ('rmse', 'normal') |
| --- | --- | --- | --- | --- | --- | --- | --- |
| hist | price | F_lag | baseline_mean | 300.0000 | 1450.0000 | 0.8478 | 0.9036 |
| hist | price | F_lag | baseline_persistence | 300.0000 | 1450.0000 | 0.2245 | 0.1903 |
| hist | price | F_lag | baseline_seasonal_naive | 300.0000 | 1450.0000 | 1.0594 | 1.1164 |
| hist | price | F_lag | elasticnet | 300.0000 | 1450.0000 | 0.2366 | 0.1890 |
| hist | price | F_lag | gam | 300.0000 | 1450.0000 | 0.2529 | 0.1954 |
| hist | price | F_lag | lightgbm | 300.0000 | 1450.0000 | 0.2404 | 0.2073 |
| hist | price | F_now | baseline_mean | 300.0000 | 1450.0000 | 0.8478 | 0.9036 |
| hist | price | F_now | baseline_persistence | 300.0000 | 1450.0000 | 0.2245 | 0.1903 |
| hist | price | F_now | baseline_seasonal_naive | 300.0000 | 1450.0000 | 1.0594 | 1.1164 |
| hist | price | F_now | elasticnet | 300.0000 | 1450.0000 | 0.2320 | 0.1889 |
| hist | price | F_now | gam | 300.0000 | 1450.0000 | 0.3337 | 0.1957 |
| hist | price | F_now | lightgbm | 300.0000 | 1450.0000 | 0.2385 | 0.2007 |
| hist | price | F_wx | baseline_mean | 300.0000 | 1450.0000 | 0.8478 | 0.9036 |
| hist | price | F_wx | baseline_persistence | 300.0000 | 1450.0000 | 0.2245 | 0.1903 |
| hist | price | F_wx | baseline_seasonal_naive | 300.0000 | 1450.0000 | 1.0594 | 1.1164 |
| hist | price | F_wx | elasticnet | 300.0000 | 1450.0000 | 0.9883 | 0.9798 |
| hist | price | F_wx | gam | 300.0000 | 1450.0000 | 1.1205 | 0.9942 |
| hist | price | F_wx | lightgbm | 300.0000 | 1450.0000 | 1.0062 | 1.0446 |
| hist | volume | F_lag | baseline_mean | 300.0000 | 1450.0000 | 1.0485 | 1.1056 |
| hist | volume | F_lag | baseline_persistence | 300.0000 | 1450.0000 | 0.3671 | 0.4398 |
| hist | volume | F_lag | baseline_seasonal_naive | 300.0000 | 1450.0000 | 1.0546 | 1.2126 |
| hist | volume | F_lag | elasticnet | 300.0000 | 1450.0000 | 0.3661 | 0.4333 |
| hist | volume | F_lag | gam | 300.0000 | 1450.0000 | 0.4006 | 0.4451 |
| hist | volume | F_lag | lightgbm | 300.0000 | 1450.0000 | 0.3935 | 0.4462 |
| hist | volume | F_now | baseline_mean | 300.0000 | 1450.0000 | 1.0485 | 1.1056 |
| hist | volume | F_now | baseline_persistence | 300.0000 | 1450.0000 | 0.3671 | 0.4398 |
| hist | volume | F_now | baseline_seasonal_naive | 300.0000 | 1450.0000 | 1.0546 | 1.2126 |
| hist | volume | F_now | elasticnet | 300.0000 | 1450.0000 | 0.3586 | 0.4382 |
| hist | volume | F_now | gam | 300.0000 | 1450.0000 | 0.7698 | 0.4576 |
| hist | volume | F_now | lightgbm | 300.0000 | 1450.0000 | 0.3989 | 0.4469 |
| hist | volume | F_wx | baseline_mean | 300.0000 | 1450.0000 | 1.0485 | 1.1056 |
| hist | volume | F_wx | baseline_persistence | 300.0000 | 1450.0000 | 0.3671 | 0.4398 |
| hist | volume | F_wx | baseline_seasonal_naive | 300.0000 | 1450.0000 | 1.0546 | 1.2126 |
| hist | volume | F_wx | elasticnet | 300.0000 | 1450.0000 | 1.1505 | 1.0892 |
| hist | volume | F_wx | gam | 300.0000 | 1450.0000 | 1.5214 | 1.1459 |
| hist | volume | F_wx | lightgbm | 300.0000 | 1450.0000 | 0.9553 | 0.9137 |
| strict | price | F_lag | baseline_mean | 300.0000 | 1450.0000 | 0.2576 | 0.2002 |
| strict | price | F_lag | baseline_persistence | 300.0000 | 1450.0000 | 0.0928 | 0.0632 |
| strict | price | F_lag | baseline_seasonal_naive | 300.0000 | 1450.0000 | 0.3427 | 0.2937 |
| strict | price | F_lag | elasticnet | 300.0000 | 1450.0000 | 0.0942 | 0.0628 |
| strict | price | F_lag | gam | 300.0000 | 1450.0000 | 0.1149 | 0.0731 |
| strict | price | F_lag | lightgbm | 300.0000 | 1450.0000 | 0.1043 | 0.0716 |
| strict | price | F_now | baseline_mean | 300.0000 | 1450.0000 | 0.2576 | 0.2002 |
| strict | price | F_now | baseline_persistence | 300.0000 | 1450.0000 | 0.0928 | 0.0632 |
| strict | price | F_now | baseline_seasonal_naive | 300.0000 | 1450.0000 | 0.3427 | 0.2937 |
| strict | price | F_now | elasticnet | 300.0000 | 1450.0000 | 0.0944 | 0.0626 |
| strict | price | F_now | gam | 300.0000 | 1450.0000 | 0.1192 | 0.0755 |
| strict | price | F_now | lightgbm | 300.0000 | 1450.0000 | 0.1033 | 0.0697 |
| strict | price | F_wx | baseline_mean | 300.0000 | 1450.0000 | 0.2576 | 0.2002 |
| strict | price | F_wx | baseline_persistence | 300.0000 | 1450.0000 | 0.0928 | 0.0632 |
| strict | price | F_wx | baseline_seasonal_naive | 300.0000 | 1450.0000 | 0.3427 | 0.2937 |
| strict | price | F_wx | elasticnet | 300.0000 | 1450.0000 | 0.3312 | 0.2591 |
| strict | price | F_wx | gam | 300.0000 | 1450.0000 | 0.3723 | 0.2772 |
| strict | price | F_wx | lightgbm | 300.0000 | 1450.0000 | 0.3400 | 0.2856 |
| strict | volume | F_lag | baseline_mean | 300.0000 | 1450.0000 | 0.0733 | 0.0558 |
| strict | volume | F_lag | baseline_persistence | 300.0000 | 1450.0000 | 0.0284 | 0.0327 |
| strict | volume | F_lag | baseline_seasonal_naive | 300.0000 | 1450.0000 | 0.0836 | 0.0875 |
| strict | volume | F_lag | elasticnet | 300.0000 | 1450.0000 | 0.0284 | 0.0318 |
| strict | volume | F_lag | gam | 300.0000 | 1450.0000 | 0.0595 | 0.0384 |
| strict | volume | F_lag | lightgbm | 300.0000 | 1450.0000 | 0.0374 | 0.0421 |
| strict | volume | F_now | baseline_mean | 300.0000 | 1450.0000 | 0.0733 | 0.0558 |
| strict | volume | F_now | baseline_persistence | 300.0000 | 1450.0000 | 0.0284 | 0.0327 |
| strict | volume | F_now | baseline_seasonal_naive | 300.0000 | 1450.0000 | 0.0836 | 0.0875 |
| strict | volume | F_now | elasticnet | 300.0000 | 1450.0000 | 0.0285 | 0.0318 |
| strict | volume | F_now | gam | 300.0000 | 1450.0000 | 0.0906 | 0.0432 |
| strict | volume | F_now | lightgbm | 300.0000 | 1450.0000 | 0.0399 | 0.0420 |
| strict | volume | F_wx | baseline_mean | 300.0000 | 1450.0000 | 0.0733 | 0.0558 |
| strict | volume | F_wx | baseline_persistence | 300.0000 | 1450.0000 | 0.0284 | 0.0327 |
| strict | volume | F_wx | baseline_seasonal_naive | 300.0000 | 1450.0000 | 0.0836 | 0.0875 |
| strict | volume | F_wx | elasticnet | 300.0000 | 1450.0000 | 0.0720 | 0.0821 |
| strict | volume | F_wx | gam | 300.0000 | 1450.0000 | 0.1328 | 0.1030 |
| strict | volume | F_wx | lightgbm | 300.0000 | 1450.0000 | 0.0742 | 0.0812 |

### 9.2 逐品种 / 分季节

明细见 `model_metrics_by_crop.csv`、`model_metrics_by_season.csv`。

## 10 图表

- F39：测试集总体 R2（模型 x 特征口径 x 目标口径）
- F40：Rolling Origin 扩张窗验证
- F41：2026 测试期价格异常真实 vs 预测 + 散点
- F42：灾害影响窗与平常期 RMSE 对比

## 11 局限（必须与结论同时引用）

1. 训练集仅 4 年（2021-2024，9850 行 = 交易日 x 10 品种），测试期 2026 仅至 9 月 14 日（1750 行）；
   §四十八 红线：**禁止**据此宣称高准确率预测能力，全部结论为 Level B（统计关联）层级。
2. 天气为 ERA5/ERA5-Land 再分析（非气象站实测）。
3. `strict` 口径基线仅用更早年份，2021 年依赖单一参照年（2020），基线噪声较大。
4. 灾害影响窗按「事件起前 1 日至结束后 7 日」划定，窗口定义属研究选择，非数据事实。
5. 若样本外 R2 < 0，即表示该模型不如训练集均值，**不得**改写成「模型有效」。
6. 高 R2 若来自自回归项，**不得**表述为「天气驱动了价格」；必须与 `gain_from_weather` 同时引用。

---
生成时间：2026-09-21 23:28:52
