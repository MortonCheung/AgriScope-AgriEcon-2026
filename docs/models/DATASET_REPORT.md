# DATASET_REPORT — Decision Dataset v1（沈阳 10 批发蔬菜）

> 数据快照：`models/data/snapshots/v1`（冻结，见 `data/manifests/input_manifest.csv`）
> 生成脚本：`scripts/build_dataset.py`

## 0. 一句话

Decision Dataset v1 = **14,100 行 × 107 列**，沈阳 10 种批发蔬菜 × **1,410 个观测日**
（2021-01-01 00:00:00 ~ 2026-09-14 00:00:00），价格单位 **元/斤 → 元/kg**，成交量仅相对口径（unit=unknown）。

## 1. 观测频率的实测事实（重要）

- 1410 个观测日 **不是连续自然日**：周六/周日不发布（各缺 298 天），另有 77 个工作日缺失（节假日等）；
- 因此 lag/rolling 一律使用「**观测滞后（observation lag）**」语义，并在特征字典中注明；
- 10 种作物的观测日期集合**完全一致**（已用集合运算验证）。

## 2. join 校验（price × volume）

| price_rows | volume_rows | price_dup_keys | volume_dup_keys | matched_rows | price_only_rows | volume_only_rows | row_inflation |
|---|---|---|---|---|---|---|---|
| 14100 | 14100 | 0 | 0 | 14100 | 0 | 0 | 0 | 

结论：matched=14100，两表键唯一、无未匹配、**无行数膨胀**。

## 3. 价格单位验证

- `price_raw` / `price_per_500g` = 官方原始值（元/斤，wholesale）；
- `price_per_kg` = price_per_500g × 2；
- `price_kg_check` 列对 canonical `price_per_kg` 逐行校验，**全部通过**（见 `tests/test_units.py`）。

## 4. 逐作物样本与价格范围

| crop | n | start | end | price_min | price_max | price_med |
|---|---|---|---|---|---|---|
| 土豆 | 1410 | 2021-01-01 00:00:00 | 2026-09-14 00:00:00 | 1.280 | 3.860 | 2.200 |
| 尖椒 | 1410 | 2021-01-01 00:00:00 | 2026-09-14 00:00:00 | 2.160 | 13.560 | 4.800 |
| 甘蓝 | 1410 | 2021-01-01 00:00:00 | 2026-09-14 00:00:00 | 0.780 | 5.860 | 1.770 |
| 芸豆 | 1410 | 2021-01-01 00:00:00 | 2026-09-14 00:00:00 | 4.860 | 20.260 | 8.260 |
| 芹菜 | 1410 | 2021-01-01 00:00:00 | 2026-09-14 00:00:00 | 1.800 | 8.500 | 3.300 |
| 茄子 | 1410 | 2021-01-01 00:00:00 | 2026-09-14 00:00:00 | 1.160 | 10.000 | 3.860 |
| 西红柿 | 1410 | 2021-01-01 00:00:00 | 2026-09-14 00:00:00 | 2.500 | 10.360 | 4.700 |
| 青椒 | 1410 | 2021-01-01 00:00:00 | 2026-09-14 00:00:00 | 2.160 | 14.760 | 5.160 |
| 韭菜 | 1410 | 2021-01-01 00:00:00 | 2026-09-14 00:00:00 | 2.060 | 12.260 | 5.030 |
| 黄瓜 | 1410 | 2021-01-01 00:00:00 | 2026-09-14 00:00:00 | 1.700 | 12.260 | 4.300 |

## 5. 缺失率 Top15 列

| column | missing_rate |
|---|---|
| price_vs_seasonal_p50 | 0.348 |
| seasonal_p10 | 0.348 |
| seasonal_p50 | 0.348 |
| seasonal_p90 | 0.348 |
| same_season_price_percentile | 0.173 |
| same_month_price_percentile | 0.162 |
| price_return_90 | 0.064 |
| price_lag_obs_90 | 0.064 |
| price_ma90 | 0.063 |
| price_std90 | 0.063 |
| price_momentum_90 | 0.063 |
| price_lag_obs_60 | 0.043 |
| price_return_60 | 0.043 |
| price_lag_cal_90 | 0.043 |
| price_ma60 | 0.042 |

> 大缺失列均为结构性：前期窗口不足（MA90/slope）、季节分位首年不可用（2021）、
> 成交量事件行不适用。**不插值、不补未来**，由模型（HistGB/EBM 原生支持 NaN；线性模型走中位数 imputer）处理。

## 6. 特征字典

- 共 80 条，字段：feature / group / definition / window / pit_rule / missing_policy；
- 文件：`models/data/manifests/feature_dictionary.csv`；
- 目标列（target_*）仅作标签，**禁止进入 X**（自动测试保证）。

## 7. 快照清单

- 输入文件：见 `data/manifests/input_manifest.csv`（45 个文件，含 SHA256 / 行数 / 时间范围）；
- 建模全过程仅读快照，不触碰 canonical 原始文件。
