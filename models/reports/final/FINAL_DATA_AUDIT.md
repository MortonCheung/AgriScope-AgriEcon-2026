# Final Data Audit

**判定：DATA_AUDIT_PASS**（阻断性 P0 = 0；已规避缺陷 = 1）

- 表数 19 · 总行数 182025
- 数据入口：`data/model_ready/`（正式模型唯一入口）

## 表清单
| table | rows | cols | date_range | n_city | n_crop | granularity |
|---|---|---|---|---|---|---|
| chaoyang_extended/environment_daily.parquet | 6101 | 31 | date:2010-01-01~2026-09-14 | 1 | 0 | daily |
| chaoyang_extended/market_daily.parquet | 37129 | 44 | observation_date:2020-01-01~2026-09-22 | 1 | 49 | daily |
| chaoyang_extended/phenology.parquet | 74 | 34 | start_date:2022-07-01~2026-06-10 | 1 | 8 | event |
| climate/climate_daily.parquet | 36606 | 31 | date:2010-01-01~2026-09-14 | 6 | 0 | daily |
| climate/vegetation_anomaly.parquet | 403 | 14 | period:2021-01-01~2026-09-01 | 6 | 0 | monthly |
| hri/hri_inputs.parquet | 39188 | 23 | - | 6 | 110 | - |
| jinzhou_extended/environment_daily.parquet | 6101 | 31 | date:2010-01-01~2026-09-14 | 1 | 0 | daily |
| jinzhou_extended/market_daily.parquet | 35123 | 44 | observation_date:2020-01-01~2026-09-22 | 1 | 48 | daily |
| jinzhou_extended/phenology.parquet | 62 | 34 | start_date:2022-09-15~2026-05-01 | 1 | 9 | event |
| profit/cost_components.parquet | 13 | 34 | - | 9 | 8 | cross_section |
| profit/cost_proxy.parquet | 7 | 32 | - | 2 | 3 | - |
| profit/crop_cost.parquet | 16 | 35 | - | 6 | 5 | yearly |
| recommendation/market_nodes.parquet | 32 | 22 | - | 6 | 0 | static |
| recommendation/structural_context.parquet | 808 | 83 | - | 24 | 17 | cross_section|static|yearly |
| shenyang_core/cost_reference.parquet | 13 | 34 | - | 9 | 8 | cross_section |
| shenyang_core/crop_context.parquet | 53 | 27 | - | 2 | 10 | cross_section |
| shenyang_core/environment_daily.parquet | 6101 | 31 | date:2010-01-01~2026-09-14 | 1 | 0 | - |
| shenyang_core/market_daily.parquet | 14100 | 44 | observation_date:2021-01-01~2026-09-14 | 1 | 10 | daily |
| shenyang_core/phenology.parquet | 95 | 34 | start_date:2020-04-30~2026-07-16 | 1 | 5 | event |


## 发现
| issue | level | detail |
|---|---|---|
| hri_inputs price_level 复合混用 | P0_MITIGATED | 34.4% 行 price_level 为多 level 拼接（如 farm_gate|wholesale）；沈阳全为 wholesale（干净），非沈阳城市被混用。→ Final HRI 仅使用单一 level（wholesale）价格序列，禁止使用混层聚合。 |
| price_per_kg dtype=object | P1 | ['chaoyang_extended/market_daily.parquet', 'jinzhou_extended/market_daily.parquet', 'shenyang_core/market_daily.parquet'] 数值以字符串存储（内容为数值），Final 层统一 astype(float)。 |
| shenyang_core/environment_daily 元数据列全空 | P1 | 全空列 ['soil_water_layer_1', 'soil_water_layer_2', 'soil_water_layer_3', 'soil_temperature', 'data_type', 'source', 'aggregation_method', 'source_id', 'geo_level', 'frequency', 'is_proxy', 'is_derived', 'access_date']；Final 气候特征统一改用 climate/climate_daily.parquet。 |
| structural_context 存在完全重复行 | P2 | 83 行重复；仅作解释性上下文，不进核心模型。 |
| crop_standard 污染 = 0（全部表） | OK | nan |
| vegetation_anomaly frequency=monthly（尊重月度粒度，不伪装日频） | OK | nan |


## 规避策略（P0_MITIGATED）
1. **hri_inputs price_level 复合混用**（34.4% 行）→ Final HRI 不使用该表，改为自建**单一 wholesale** 周价格序列。
2. **price_per_kg dtype=object** → Final 层统一 `astype(float)`。
3. **shenyang_core/environment_daily 元数据列全空** → Final 气候特征统一取 `climate/climate_daily.parquet`。

## 城市价格可得性
| city | rows | veg10_rows | veg10_crops | levels |
|---|---|---|---|---|
| 沈阳 | 14100 | 14100 | 10 | wholesale |
| 朝阳 | 37129 | 10405 | 10 | farm_gate|market_average|wholesale |
| 锦州 | 35123 | 10279 | 8 | farm_gate|market_average|retail_market|supermarket|wholesale |
| 大连 | 0 | 0 | 0 | NO_MARKET_TABLE |
| 铁岭 | 0 | 0 | 0 | NO_MARKET_TABLE |
| 丹东 | 0 | 0 | 0 | NO_MARKET_TABLE |


## 泄漏审计（截断不变性）
| city | cutoff | n_common_rows | n_features | n_leak_features | leak_features | max_diff |
|---|---|---|---|---|---|---|
| 沈阳 | 2023-06-30 | 6120 | 63 | 0 | nan | 0.0000 |
| 沈阳 | 2024-06-30 | 8580 | 63 | 0 | nan | 0.0000 |
| 沈阳 | 2025-06-30 | 11060 | 63 | 0 | nan | 0.0000 |
| 朝阳 | 2023-06-30 | 3864 | 63 | 0 | nan | 0.0000 |
| 朝阳 | 2024-06-30 | 5624 | 63 | 0 | nan | 0.0000 |
| 朝阳 | 2025-06-30 | 7496 | 63 | 0 | nan | 0.0000 |

