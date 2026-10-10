# RECOMMENDER_BACKTEST_REPORT — 历史推荐回测与政策基准

## 1. 回测设计（§40-§42）

- 每个历史 cutoff 只使用 ≤ T 的数据（as_of 机制，复用 v1 replay 口径）；
- 流程：生成候选 → 评估 → 排序 → 推荐 → 等未来真实结果 → 对比；
- 回测情景假设：面积 60.0 亩、
  预算 300000.0 元（非真实经营规模，已在报告中标注）。

## 2. 政策基准（§45）

| policy | rank | realized_profit_mean | downside_gap_mean | hit_rate | mean_regret | HRI_mean | market_risk_mean | confidence_mean | n_cutoffs | city |
|---|---|---|---|---|---|---|---|---|---|---|
| C_agriscope_balanced | top1 | 2637858.64 | 483015.09 | 0.50 | 56951.79 | 61.67 | 47.87 | 75.02 | 12 | 朝阳 |
| A_profit_only | top1 | 2153061.47 | 375230.24 | 0.50 | 12906.83 | 54.50 | 48.97 | 74.57 | 22 | 朝阳 |
| A_profit_only | top1 | 1959611.76 | 366359.45 | 0.61 | 185187.72 | 49.15 | 40.97 | 87.81 | 23 | 沈阳 |
| C_agriscope_balanced | top1 | 1879195.44 | 262440.09 | 0.65 | 265604.04 | 51.67 | 39.10 | 87.67 | 23 | 沈阳 |
| D_naive_highest_price | top1 | 1699927.07 | 265214.40 | 0.70 | 444872.41 | 53.59 | 42.07 | 87.81 | 23 | 沈阳 |
| Random | top1 | 1577874.83 | 504444.66 | 0.67 | 526816.50 | 51.74 | 44.63 | 71.68 | 21 | 朝阳 |
| D_naive_highest_price | top1 | 1534831.24 | 391944.95 | 0.65 | 572783.14 | 57.51 | 49.10 | 73.23 | 23 | 朝阳 |
| B_risk_only | top1 | 1505906.13 | 443673.98 | 0.55 | 1177737.27 | 52.15 | 36.48 | 70.95 | 11 | 朝阳 |
| Random | top1 | 1283571.17 | 294857.48 | 0.71 | 816610.50 | 51.49 | 46.18 | 84.88 | 21 | 沈阳 |
| B_risk_only | top1 | 1115611.64 | 427712.13 | 0.59 | 1200059.45 | 40.32 | 31.85 | 83.11 | 17 | 沈阳 |
| A_profit_only | top3 | 2084884.89 | 340597.08 | 0.52 | 22729.50 | 52.56 | 48.63 | 74.54 | 23 | 朝阳 |
| C_agriscope_balanced | top3 | 2077276.64 | 332988.83 | 0.52 | 30337.74 | 52.56 | 48.63 | 74.54 | 23 | 朝阳 |
| A_profit_only | top3 | 1928948.83 | 381987.70 | 0.57 | 215850.65 | 49.15 | 40.97 | 87.81 | 23 | 沈阳 |
| C_agriscope_balanced | top3 | 1863717.08 | 323438.19 | 0.68 | 281082.40 | 51.02 | 37.76 | 87.62 | 23 | 沈阳 |
| D_naive_highest_price | top3 | 1697320.50 | 272502.43 | 0.72 | 447478.98 | 53.59 | 42.07 | 87.81 | 23 | 沈阳 |
| D_naive_highest_price | top3 | 1503886.23 | 360999.94 | 0.64 | 603728.15 | 57.51 | 49.10 | 73.23 | 23 | 朝阳 |
| Random | top3 | 1457902.44 | 334416.69 | 0.75 | 632548.88 | 54.82 | 47.49 | 72.18 | 24 | 朝阳 |
| B_risk_only | top3 | 1344968.38 | 375007.80 | 0.63 | 757471.98 | 45.64 | 41.48 | 71.41 | 23 | 朝阳 |
| Random | top3 | 1101559.43 | 301302.23 | 0.74 | 1043240.06 | 48.98 | 41.36 | 84.06 | 23 | 沈阳 |
| B_risk_only | top3 | 982957.40 | 342886.01 | 0.57 | 1161842.08 | 36.81 | 31.28 | 83.24 | 23 | 沈阳 |

> 政策：A=只追求预测利润；B=只追求低风险；C=AgriScope Balanced；D=naive（当期价格最高）；
> Random（固定种子）；每政策同时给出 Top1 与 Top3 平均。

## 3. 跟风抑制评估（§43/§44）

| policy | high_hri_rate | mean_HRI | n | threshold_used | note | city |
|---|---|---|---|---|---|---|
| A_profit_only | 0.087 | 49.152 | 23 | 73.200 | High-HRI 推荐率 = 推荐方案 HRI 处于批次 P90 以上的比例；用于检验是否抑制盲目追高 | 沈阳 |
| B_risk_only | 0.000 | 40.318 | 17 | 73.200 | High-HRI 推荐率 = 推荐方案 HRI 处于批次 P90 以上的比例；用于检验是否抑制盲目追高 | 沈阳 |
| C_agriscope_balanced | 0.130 | 51.670 | 23 | 73.200 | High-HRI 推荐率 = 推荐方案 HRI 处于批次 P90 以上的比例；用于检验是否抑制盲目追高 | 沈阳 |
| D_naive_highest_price | 0.174 | 53.591 | 23 | 73.200 | High-HRI 推荐率 = 推荐方案 HRI 处于批次 P90 以上的比例；用于检验是否抑制盲目追高 | 沈阳 |
| Random | 0.190 | 51.486 | 21 | 73.200 | High-HRI 推荐率 = 推荐方案 HRI 处于批次 P90 以上的比例；用于检验是否抑制盲目追高 | 沈阳 |
| A_profit_only | 0.182 | 54.505 | 22 | 83.300 | High-HRI 推荐率 = 推荐方案 HRI 处于批次 P90 以上的比例；用于检验是否抑制盲目追高 | 朝阳 |
| B_risk_only | 0.000 | 52.155 | 11 | 83.300 | High-HRI 推荐率 = 推荐方案 HRI 处于批次 P90 以上的比例；用于检验是否抑制盲目追高 | 朝阳 |
| C_agriscope_balanced | 0.250 | 61.675 | 12 | 83.300 | High-HRI 推荐率 = 推荐方案 HRI 处于批次 P90 以上的比例；用于检验是否抑制盲目追高 | 朝阳 |
| D_naive_highest_price | 0.174 | 57.509 | 23 | 83.300 | High-HRI 推荐率 = 推荐方案 HRI 处于批次 P90 以上的比例；用于检验是否抑制盲目追高 | 朝阳 |
| Random | 0.048 | 51.743 | 21 | 83.300 | High-HRI 推荐率 = 推荐方案 HRI 处于批次 P90 以上的比例；用于检验是否抑制盲目追高 | 朝阳 |

> High-HRI 推荐率 = 推荐方案 HRI 处于批次 P90 以上的比例。若 profit-only(A) 明显高于
> balanced(C)，说明 HRI/市场风险确实抑制了盲目追高；若两者接近，则如实报告"抑制效果有限"。

## 4. 推荐稳定性（§46）

| city | policy | n_cutoffs | crop_retention_rate | n_distinct_crops | top1_crop_mode |
|---|---|---|---|---|---|
| 朝阳 | A_profit_only | 22 | 1.000 | 1 | 黄瓜 |
| 朝阳 | B_risk_only | 11 | 0.300 | 3 | 芹菜 |
| 朝阳 | C_agriscope_balanced | 12 | 1.000 | 1 | 黄瓜 |
| 朝阳 | D_naive_highest_price | 23 | 0.591 | 3 | 青椒 |
| 朝阳 | Random | 21 | 0.350 | 3 | 黄瓜 |
| 沈阳 | A_profit_only | 23 | 0.636 | 3 | 芸豆 |
| 沈阳 | B_risk_only | 17 | 0.312 | 7 | 土豆 |
| 沈阳 | C_agriscope_balanced | 23 | 0.818 | 2 | 芸豆 |
| 沈阳 | D_naive_highest_price | 23 | 0.773 | 4 | 芸豆 |
| 沈阳 | Random | 21 | 0.000 | 8 | 芸豆 |

## 5. 案例（§63：≥10 真实案例 + 1 失败案例）

| case_type | city | cutoff | policy | crops | realized_profit | hit_rate |
|---|---|---|---|---|---|---|
| recommendation | 朝阳 | 2025-02-26 | A_profit_only | 黄瓜 | 1543723.680 | 1.000 |
| recommendation | 朝阳 | 2024-07-01 | A_profit_only | 黄瓜 | 1699623.480 | 0.000 |
| recommendation | 沈阳 | 2024-08-30 | A_profit_only | 黄瓜 | 1708342.080 | 0.000 |
| recommendation | 沈阳 | 2025-09-24 | D_naive_highest_price | 芸豆 | 2182115.170 | 1.000 |
| recommendation | 朝阳 | 2025-06-26 | C_agriscope_balanced | 黄瓜 | 3658021.920 | 0.000 |
| recommendation | 朝阳 | 2026-01-22 | A_profit_only | 黄瓜 | 1663989.240 | 1.000 |
| recommendation | 沈阳 | 2025-08-25 | B_risk_only | 芸豆 | 2234972.340 | 1.000 |
| recommendation | 沈阳 | 2025-05-27 | A_profit_only | 西红柿 | 1673524.650 | 1.000 |
| recommendation | 沈阳 | 2024-08-30 | D_naive_highest_price | 芸豆 | 2492829.580 | 1.000 |
| recommendation | 朝阳 | 2025-09-24 | C_agriscope_balanced | 黄瓜 | 2992001.010 | 1.000 |
| failure | 沈阳 | 2026-01-22 | Random | 甘蓝 | -26347.010 | 1.000 |

推荐示例（不同约束）：见 `recommendation_examples_10.csv`。
