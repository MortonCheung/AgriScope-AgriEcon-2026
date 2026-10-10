# STEP 22 年度生产研究（Phase 11，§四十七~§四十八）

## 0. 定位与红线

- §四十七：年度尺度数据**不得**与日度价格硬拼。本模块独立成层，不与 STEP 03-21 的日度结论合并推断。
- §四十八：2017-2025 仅约 9 个年份，**禁止**用 9 个点训练 XGBoost / 神经网络 / Random Forest 后宣称高准确率。**本模块不训练任何模型**，只做描述性趋势、anomaly、简单相关与单变量简单回归。
- 结论表述统一加注：**样本量有限，主要用于机制补充，而非高维预测**。

## 1. 数据可得性与断裂（关键）

| 项目 | 结论 |
| --- | --- |
| 蔬菜及食用菌年度序列 | 仅 4 个观测年：2017、2018、2019、2025；缺失年份 [2020, 2021, 2022, 2023, 2024]（不插补） |
| 粮食年度序列 | 2017-2025，共 9 年（完整） |
| 分作物（水稻/玉米/大豆） | 2018、2019 + 2020-2024 + 2025 = 8 年（2017 年鉴无分作物行） |
| 生长季气象 | 仅 2021-2026（`weather_daily`，ERA5/ERA5-Land 再分析） |
| 蔬菜 × 气象重叠年 | [2025] → **无法做相关分析** |
| 粮食 × 气象重叠年 | [2021, 2022, 2023, 2024, 2025]（n=5）→ 仅探索性描述 |
| 分品种蔬菜生产数据 | **不存在**（年鉴/公报仅「蔬菜及食用菌」合计）→ §四十八 的 crop panel **不可行** |

> 上述断裂与不可行项已同步写入 `reports/BLOCKERS.md`，**未做任何插补**。

## 2. shenyang_yearly_panel 结构

字段（单位显式）：`year`、`region`、`crop`、`planting_area_kha`、`production_ton`、`yield_kg_per_ha`、`season_precip_mm`、`season_temp_mean_c`、`heat_days`、`heavy_rain_days`、`soil_moisture_anomaly`、`max_3d_precip_mm`、`season_precip_pct_of_clim`、`season_complete`、`weather_available`、`source_table`、`quality_grade`。
- 生长季定义：5月、6月、7月、8月、9月（来自 `config/analysis.yaml: time.growing_season_months`）。
- 单位统一：跨表按 `unit_production` 换算（万吨 → 吨 ×10000），面积统一为千公顷，单产统一为公斤/公顷。
- 派生标记：2017 蔬菜面积官方未给，但产量与单产均为官方值，故仅登记 `planting_area_kha_implied = production / yield` 并置 `value_is_derived=True`，**不作为观测值使用**。

## 3. 描述性趋势（§四十八允许）

| 作物 | 变量 | n 年 | 年份跨度 | 首值 | 末值 | 总变化% | 线性斜率/年 | R² | 存在断裂 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 大豆 | planting_area_kha | 8 | 2018-2025 | 8.6 | 11.7 | +35.9 | +0.50 | 0.676 | 否 |
| 大豆 | production_ton | 8 | 2018-2025 | 21484.2 | 25000.0 | +16.4 | +649.09 | 0.437 | 否 |
| 大豆 | yield_kg_per_ha | 6 | 2020-2025 | 2218.0 | 2155.5 | -2.8 | -51.04 | 0.337 | 否 |
| 小麦 | planting_area_kha | 5 | 2020-2024 | 1.0 | 0.4 | -60.0 | -0.15 | 0.987 | 否 |
| 小麦 | production_ton | 5 | 2020-2024 | 6000.0 | 2000.0 | -66.7 | -900.00 | 0.750 | 否 |
| 小麦 | yield_kg_per_ha | 5 | 2020-2024 | 5942.0 | 4365.0 | -26.5 | -317.30 | 0.361 | 否 |
| 水稻 | planting_area_kha | 8 | 2018-2025 | 117.6 | 110.5 | -6.0 | -1.56 | 0.455 | 否 |
| 水稻 | production_ton | 8 | 2018-2025 | 980071.6 | 785000.0 | -19.9 | -31936.29 | 0.762 | 否 |
| 水稻 | yield_kg_per_ha | 6 | 2020-2025 | 8149.0 | 7105.5 | -12.8 | -210.10 | 0.937 | 否 |
| 油料 | planting_area_kha | 6 | 2020-2025 | 32.7 | 32.1 | -1.8 | +0.04 | 0.014 | 否 |
| 油料 | production_ton | 6 | 2020-2025 | 120574.6 | 128000.0 | +6.2 | +2384.46 | 0.593 | 否 |
| 玉米 | planting_area_kha | 8 | 2018-2025 | 397.5 | 419.3 | +5.5 | +4.23 | 0.816 | 否 |
| 玉米 | production_ton | 8 | 2018-2025 | 2576628.7 | 3349000.0 | +30.0 | +75054.02 | 0.567 | 否 |
| 玉米 | yield_kg_per_ha | 6 | 2020-2025 | 7631.0 | 7987.1 | +4.7 | +39.33 | 0.075 | 否 |
| 粮食 | planting_area_kha | 9 | 2017-2025 | 543.5 | 549.6 | +1.1 | +0.43 | 0.184 | 否 |
| 粮食 | production_ton | 9 | 2017-2025 | 3822921.6 | 4200000.0 | +9.9 | +38502.19 | 0.321 | 否 |
| 粮食 | yield_kg_per_ha | 9 | 2017-2025 | 7033.8 | 7641.9 | +8.6 | +64.66 | 0.267 | 否 |
| 花生 | planting_area_kha | 5 | 2020-2024 | 32.7 | 32.0 | -2.1 | -0.15 | 0.286 | 否 |
| 花生 | production_ton | 5 | 2020-2024 | 120414.0 | 130553.3 | +8.4 | +3214.21 | 0.721 | 否 |
| 花生 | yield_kg_per_ha | 5 | 2020-2024 | 3683.0 | 3930.0 | +6.7 | +89.30 | 0.633 | 否 |
| 蔬菜及食用菌 | planting_area_kha | 3 | 2018-2025 | 61.2 | 68.2 | +11.5 | +1.02 | 0.999 | 是 |
| 蔬菜及食用菌 | production_ton | 4 | 2017-2025 | 3480930.6 | 4337000.0 | +24.6 | +104774.90 | 0.997 | 是 |
| 蔬菜及食用菌 | yield_kg_per_ha | 4 | 2017-2025 | 60019.3 | 63592.4 | +6.0 | +515.06 | 0.919 | 是 |
| 薯类 | planting_area_kha | 5 | 2020-2024 | 10.0 | 6.9 | -31.0 | -0.76 | 0.945 | 否 |
| 薯类 | production_ton | 5 | 2020-2024 | 50000.0 | 28000.0 | -44.0 | -4900.00 | 0.696 | 否 |
| 薯类 | yield_kg_per_ha | 5 | 2020-2024 | 4992.0 | 4065.0 | -18.6 | -179.10 | 0.321 | 否 |
| 谷子 | planting_area_kha | 5 | 2020-2024 | 1.3 | 0.7 | -46.2 | -0.13 | 0.797 | 否 |
| 谷子 | production_ton | 5 | 2020-2024 | 4000.0 | 2000.0 | -50.0 | -400.00 | 0.571 | 否 |
| 谷子 | yield_kg_per_ha | 5 | 2020-2024 | 3144.0 | 3150.0 | +0.2 | -9.90 | 0.001 | 否 |
| 高粱 | planting_area_kha | 5 | 2020-2024 | 1.4 | 0.8 | -42.9 | -0.19 | 0.631 | 否 |
| 高粱 | production_ton | 5 | 2020-2024 | 7000.0 | 5000.0 | -28.6 | -600.00 | 0.243 | 否 |
| 高粱 | yield_kg_per_ha | 5 | 2020-2024 | 5162.0 | 6045.0 | +17.1 | +311.30 | 0.222 | 否 |

> 蔬菜行的「总变化%」跨越 2019→2025 的 6 年缺口，**不可解释为年际趋势**，仅表示两个可观测时点的水平差。

## 4. 简单相关（产量/单产 vs 生长季气象）

| 作物 | 目标 | 气象变量 | n | 年份 | Pearson r | Spearman r |
| --- | --- | --- | --- | --- | --- | --- |
| 大豆 | production_ton | season_precip_mm | 5 | 2021,2022,2023,2024,2025 | -0.108 | -0.154 |
| 大豆 | production_ton | season_temp_mean_c | 5 | 2021,2022,2023,2024,2025 | +0.826 | +0.821 |
| 大豆 | production_ton | heat_days | 5 | 2021,2022,2023,2024,2025 | +0.784 | +0.725 |
| 大豆 | production_ton | heavy_rain_days | 5 | 2021,2022,2023,2024,2025 | +0.038 | +0.105 |
| 大豆 | production_ton | soil_moisture_anomaly | 5 | 2021,2022,2023,2024,2025 | -0.475 | -0.462 |
| 大豆 | production_ton | max_3d_precip_mm | 5 | 2021,2022,2023,2024,2025 | -0.223 | +0.154 |
| 大豆 | yield_kg_per_ha | season_precip_mm | 5 | 2021,2022,2023,2024,2025 | -0.563 | -0.200 |
| 大豆 | yield_kg_per_ha | season_temp_mean_c | 5 | 2021,2022,2023,2024,2025 | -0.374 | -0.100 |
| 大豆 | yield_kg_per_ha | heat_days | 5 | 2021,2022,2023,2024,2025 | -0.082 | +0.354 |
| 大豆 | yield_kg_per_ha | heavy_rain_days | 5 | 2021,2022,2023,2024,2025 | -0.840 | -0.821 |
| 大豆 | yield_kg_per_ha | soil_moisture_anomaly | 5 | 2021,2022,2023,2024,2025 | +0.358 | +0.600 |
| 大豆 | yield_kg_per_ha | max_3d_precip_mm | 5 | 2021,2022,2023,2024,2025 | -0.625 | -0.700 |
| 小麦 | production_ton | season_precip_mm | 4 | 2021,2022,2023,2024 | +0.079 | +0.447 |
| 小麦 | production_ton | season_temp_mean_c | 4 | 2021,2022,2023,2024 | -0.965 | -0.894 |
| 小麦 | production_ton | heat_days | 4 | 2021,2022,2023,2024 | +nan | +nan |
| 小麦 | production_ton | heavy_rain_days | 4 | 2021,2022,2023,2024 | -0.447 | -0.447 |
| 小麦 | production_ton | soil_moisture_anomaly | 4 | 2021,2022,2023,2024 | +0.858 | +0.894 |
| 小麦 | production_ton | max_3d_precip_mm | 4 | 2021,2022,2023,2024 | -0.409 | -0.447 |
| 小麦 | yield_kg_per_ha | season_precip_mm | 4 | 2021,2022,2023,2024 | -0.060 | -0.200 |
| 小麦 | yield_kg_per_ha | season_temp_mean_c | 4 | 2021,2022,2023,2024 | +0.772 | +0.400 |
| 小麦 | yield_kg_per_ha | heat_days | 4 | 2021,2022,2023,2024 | +nan | +nan |
| 小麦 | yield_kg_per_ha | heavy_rain_days | 4 | 2021,2022,2023,2024 | +0.296 | +0.200 |
| 小麦 | yield_kg_per_ha | soil_moisture_anomaly | 4 | 2021,2022,2023,2024 | -0.450 | -0.400 |
| 小麦 | yield_kg_per_ha | max_3d_precip_mm | 4 | 2021,2022,2023,2024 | +0.542 | +0.200 |
| 水稻 | production_ton | season_precip_mm | 5 | 2021,2022,2023,2024,2025 | -0.161 | -0.200 |
| 水稻 | production_ton | season_temp_mean_c | 5 | 2021,2022,2023,2024,2025 | -0.866 | -0.600 |
| 水稻 | production_ton | heat_days | 5 | 2021,2022,2023,2024,2025 | -0.504 | -0.354 |
| 水稻 | production_ton | heavy_rain_days | 5 | 2021,2022,2023,2024,2025 | -0.497 | -0.667 |
| 水稻 | production_ton | soil_moisture_anomaly | 5 | 2021,2022,2023,2024,2025 | +0.557 | +0.600 |
| 水稻 | production_ton | max_3d_precip_mm | 5 | 2021,2022,2023,2024,2025 | -0.417 | -0.700 |
| 水稻 | yield_kg_per_ha | season_precip_mm | 5 | 2021,2022,2023,2024,2025 | -0.336 | -0.200 |
| 水稻 | yield_kg_per_ha | season_temp_mean_c | 5 | 2021,2022,2023,2024,2025 | -0.801 | -0.600 |
| 水稻 | yield_kg_per_ha | heat_days | 5 | 2021,2022,2023,2024,2025 | -0.563 | -0.354 |
| 水稻 | yield_kg_per_ha | heavy_rain_days | 5 | 2021,2022,2023,2024,2025 | -0.564 | -0.667 |
| 水稻 | yield_kg_per_ha | soil_moisture_anomaly | 5 | 2021,2022,2023,2024,2025 | +0.316 | +0.600 |
| 水稻 | yield_kg_per_ha | max_3d_precip_mm | 5 | 2021,2022,2023,2024,2025 | -0.521 | -0.700 |
| 油料 | production_ton | season_precip_mm | 5 | 2021,2022,2023,2024,2025 | -0.113 | -0.300 |
| 油料 | production_ton | season_temp_mean_c | 5 | 2021,2022,2023,2024,2025 | +0.748 | +0.600 |
| 油料 | production_ton | heat_days | 5 | 2021,2022,2023,2024,2025 | +0.185 | +0.000 |
| 油料 | production_ton | heavy_rain_days | 5 | 2021,2022,2023,2024,2025 | +0.376 | +0.410 |
| 油料 | production_ton | soil_moisture_anomaly | 5 | 2021,2022,2023,2024,2025 | -0.870 | -0.900 |
| 油料 | production_ton | max_3d_precip_mm | 5 | 2021,2022,2023,2024,2025 | +0.278 | +0.300 |
| 玉米 | production_ton | season_precip_mm | 5 | 2021,2022,2023,2024,2025 | -0.668 | -0.700 |
| 玉米 | production_ton | season_temp_mean_c | 5 | 2021,2022,2023,2024,2025 | +0.886 | +0.900 |
| 玉米 | production_ton | heat_days | 5 | 2021,2022,2023,2024,2025 | +0.587 | +0.707 |
| 玉米 | production_ton | heavy_rain_days | 5 | 2021,2022,2023,2024,2025 | -0.379 | -0.564 |
| 玉米 | production_ton | soil_moisture_anomaly | 5 | 2021,2022,2023,2024,2025 | -0.730 | -0.500 |
| 玉米 | production_ton | max_3d_precip_mm | 5 | 2021,2022,2023,2024,2025 | -0.369 | -0.500 |
| 玉米 | yield_kg_per_ha | season_precip_mm | 5 | 2021,2022,2023,2024,2025 | -0.891 | -0.600 |
| 玉米 | yield_kg_per_ha | season_temp_mean_c | 5 | 2021,2022,2023,2024,2025 | +0.608 | +0.700 |
| 玉米 | yield_kg_per_ha | heat_days | 5 | 2021,2022,2023,2024,2025 | +0.408 | +0.707 |
| 玉米 | yield_kg_per_ha | heavy_rain_days | 5 | 2021,2022,2023,2024,2025 | -0.709 | -0.718 |
| 玉米 | yield_kg_per_ha | soil_moisture_anomaly | 5 | 2021,2022,2023,2024,2025 | -0.576 | -0.200 |
| 玉米 | yield_kg_per_ha | max_3d_precip_mm | 5 | 2021,2022,2023,2024,2025 | -0.607 | -0.600 |
| 粮食 | production_ton | season_precip_mm | 5 | 2021,2022,2023,2024,2025 | -0.925 | -0.700 |
| 粮食 | production_ton | season_temp_mean_c | 5 | 2021,2022,2023,2024,2025 | +0.565 | +0.900 |
| 粮食 | production_ton | heat_days | 5 | 2021,2022,2023,2024,2025 | +0.425 | +0.707 |
| 粮食 | production_ton | heavy_rain_days | 5 | 2021,2022,2023,2024,2025 | -0.779 | -0.564 |
| 粮食 | production_ton | soil_moisture_anomaly | 5 | 2021,2022,2023,2024,2025 | -0.552 | -0.500 |
| 粮食 | production_ton | max_3d_precip_mm | 5 | 2021,2022,2023,2024,2025 | -0.714 | -0.500 |
| 粮食 | yield_kg_per_ha | season_precip_mm | 5 | 2021,2022,2023,2024,2025 | -0.960 | -0.900 |
| 粮食 | yield_kg_per_ha | season_temp_mean_c | 5 | 2021,2022,2023,2024,2025 | +0.435 | +0.300 |
| 粮食 | yield_kg_per_ha | heat_days | 5 | 2021,2022,2023,2024,2025 | +0.305 | +0.000 |
| 粮食 | yield_kg_per_ha | heavy_rain_days | 5 | 2021,2022,2023,2024,2025 | -0.837 | -0.872 |
| 粮食 | yield_kg_per_ha | soil_moisture_anomaly | 5 | 2021,2022,2023,2024,2025 | -0.497 | -0.300 |
| 粮食 | yield_kg_per_ha | max_3d_precip_mm | 5 | 2021,2022,2023,2024,2025 | -0.737 | -0.900 |
| 花生 | production_ton | season_precip_mm | 4 | 2021,2022,2023,2024 | -0.050 | -0.400 |
| 花生 | production_ton | season_temp_mean_c | 4 | 2021,2022,2023,2024 | +0.946 | +0.800 |
| 花生 | production_ton | heat_days | 4 | 2021,2022,2023,2024 | +nan | +nan |
| 花生 | production_ton | heavy_rain_days | 4 | 2021,2022,2023,2024 | +0.473 | +0.400 |
| 花生 | production_ton | soil_moisture_anomaly | 4 | 2021,2022,2023,2024 | -0.854 | -0.800 |
| 花生 | production_ton | max_3d_precip_mm | 4 | 2021,2022,2023,2024 | +0.411 | +0.400 |
| 花生 | yield_kg_per_ha | season_precip_mm | 4 | 2021,2022,2023,2024 | -0.245 | -0.400 |
| 花生 | yield_kg_per_ha | season_temp_mean_c | 4 | 2021,2022,2023,2024 | +0.801 | +0.800 |
| 花生 | yield_kg_per_ha | heat_days | 4 | 2021,2022,2023,2024 | +nan | +nan |
| 花生 | yield_kg_per_ha | heavy_rain_days | 4 | 2021,2022,2023,2024 | +0.231 | +0.400 |
| 花生 | yield_kg_per_ha | soil_moisture_anomaly | 4 | 2021,2022,2023,2024 | -0.915 | -0.800 |
| 花生 | yield_kg_per_ha | max_3d_precip_mm | 4 | 2021,2022,2023,2024 | +0.037 | +0.400 |
| 薯类 | production_ton | season_precip_mm | 4 | 2021,2022,2023,2024 | -0.296 | +0.211 |
| 薯类 | production_ton | season_temp_mean_c | 4 | 2021,2022,2023,2024 | -0.690 | -0.738 |
| 薯类 | production_ton | heat_days | 4 | 2021,2022,2023,2024 | +nan | +nan |
| 薯类 | production_ton | heavy_rain_days | 4 | 2021,2022,2023,2024 | -0.710 | -0.632 |
| 薯类 | production_ton | soil_moisture_anomaly | 4 | 2021,2022,2023,2024 | +0.628 | +0.738 |
| 薯类 | production_ton | max_3d_precip_mm | 4 | 2021,2022,2023,2024 | -0.521 | -0.632 |
| 薯类 | yield_kg_per_ha | season_precip_mm | 4 | 2021,2022,2023,2024 | +0.370 | -0.400 |
| 薯类 | yield_kg_per_ha | season_temp_mean_c | 4 | 2021,2022,2023,2024 | +0.728 | +0.800 |
| 薯类 | yield_kg_per_ha | heat_days | 4 | 2021,2022,2023,2024 | +nan | +nan |
| 薯类 | yield_kg_per_ha | heavy_rain_days | 4 | 2021,2022,2023,2024 | +0.733 | +0.400 |
| 薯类 | yield_kg_per_ha | soil_moisture_anomaly | 4 | 2021,2022,2023,2024 | -0.372 | -0.800 |
| 薯类 | yield_kg_per_ha | max_3d_precip_mm | 4 | 2021,2022,2023,2024 | +0.848 | +0.400 |
| 谷子 | production_ton | season_precip_mm | 4 | 2021,2022,2023,2024 | -0.997 | -0.894 |
| 谷子 | production_ton | season_temp_mean_c | 4 | 2021,2022,2023,2024 | +0.213 | +0.447 |
| 谷子 | production_ton | heat_days | 4 | 2021,2022,2023,2024 | +nan | +nan |
| 谷子 | production_ton | heavy_rain_days | 4 | 2021,2022,2023,2024 | -0.894 | -0.894 |
| 谷子 | production_ton | soil_moisture_anomaly | 4 | 2021,2022,2023,2024 | -0.478 | -0.447 |
| 谷子 | production_ton | max_3d_precip_mm | 4 | 2021,2022,2023,2024 | -0.834 | -0.894 |
| 谷子 | yield_kg_per_ha | season_precip_mm | 4 | 2021,2022,2023,2024 | -0.773 | -0.800 |
| 谷子 | yield_kg_per_ha | season_temp_mean_c | 4 | 2021,2022,2023,2024 | +0.654 | +0.400 |
| 谷子 | yield_kg_per_ha | heat_days | 4 | 2021,2022,2023,2024 | +nan | +nan |
| 谷子 | yield_kg_per_ha | heavy_rain_days | 4 | 2021,2022,2023,2024 | -0.472 | -0.800 |
| 谷子 | yield_kg_per_ha | soil_moisture_anomaly | 4 | 2021,2022,2023,2024 | -0.629 | -0.400 |
| 谷子 | yield_kg_per_ha | max_3d_precip_mm | 4 | 2021,2022,2023,2024 | -0.254 | -0.800 |
| 高粱 | production_ton | season_precip_mm | 4 | 2021,2022,2023,2024 | -0.517 | -0.400 |
| 高粱 | production_ton | season_temp_mean_c | 4 | 2021,2022,2023,2024 | +0.403 | +0.200 |
| 高粱 | production_ton | heat_days | 4 | 2021,2022,2023,2024 | +nan | +nan |
| 高粱 | production_ton | heavy_rain_days | 4 | 2021,2022,2023,2024 | -0.378 | -0.400 |
| 高粱 | production_ton | soil_moisture_anomaly | 4 | 2021,2022,2023,2024 | -0.229 | -0.200 |
| 高粱 | production_ton | max_3d_precip_mm | 4 | 2021,2022,2023,2024 | -0.042 | -0.400 |
| 高粱 | yield_kg_per_ha | season_precip_mm | 4 | 2021,2022,2023,2024 | +0.160 | -0.400 |
| 高粱 | yield_kg_per_ha | season_temp_mean_c | 4 | 2021,2022,2023,2024 | +0.893 | +0.800 |
| 高粱 | yield_kg_per_ha | heat_days | 4 | 2021,2022,2023,2024 | +nan | +nan |
| 高粱 | yield_kg_per_ha | heavy_rain_days | 4 | 2021,2022,2023,2024 | +0.627 | +0.400 |
| 高粱 | yield_kg_per_ha | soil_moisture_anomaly | 4 | 2021,2022,2023,2024 | -0.640 | -0.800 |
| 高粱 | yield_kg_per_ha | max_3d_precip_mm | 4 | 2021,2022,2023,2024 | +0.677 | +0.400 |

> **不作统计推断**：n≤5，任何「显著性」在此样本量下都不可解释；表中 r 仅用于观察方向与量级，`interpretation_allowed=False` 已写入表内。

## 5. 简单回归（仅粮食，单变量）

| 目标 | 气象变量 | n | 自由度 | 斜率 | 斜率SE | R² |
| --- | --- | --- | --- | --- | --- | --- |
| yield_kg_per_ha | season_precip_mm | 5 | 3 | -1.5818 | 0.2673 | 0.921 |
| yield_kg_per_ha | season_temp_mean_c | 5 | 3 | +126.4102 | 151.0153 | 0.189 |
| yield_kg_per_ha | heat_days | 5 | 3 | +51.7167 | 93.3539 | 0.093 |
| yield_kg_per_ha | heavy_rain_days | 5 | 3 | -167.2231 | 63.0880 | 0.701 |
| yield_kg_per_ha | soil_moisture_anomaly | 5 | 3 | -201.9226 | 203.4793 | 0.247 |
| production_ton | season_precip_mm | 5 | 3 | -856.4299 | 203.5685 | 0.855 |
| production_ton | season_temp_mean_c | 5 | 3 | +92286.3660 | 77749.4533 | 0.320 |
| production_ton | heat_days | 5 | 3 | +40500.0000 | 49868.8094 | 0.180 |
| production_ton | heavy_rain_days | 5 | 3 | -87423.0769 | 40655.1076 | 0.607 |
| production_ton | soil_moisture_anomaly | 5 | 3 | -125889.8905 | 109927.8572 | 0.304 |

> `inference_allowed=False`：自由度仅 3，回归系数不构成推断依据。

## 6. 结论

1. **蔬菜年度层不可用于机制检验**：仅有 4 个观测年（2017-2019、2025），且与生长季气象重叠仅 1 年 → 相关/回归**不可行**，如实登记为 **NOT SUPPORTED BY CURRENT DATA**，不插补、不外推。
2. **粮食年度层可作极弱机制补充**：9 年序列完整，但气象只有 2021-2025（n=5），相关系数与单变量回归均**不构成推断**，只能作为方向性观察。
3. **crop panel 不可行**：无分品种蔬菜生产数据，§四十八 的 crop panel 在当前数据条件下无法建立。
4. 年度层**未提供**任何可用于修正日度结论的证据；本层结论不与 STEP 03-21 合并，也不用于预测。

## 7. 输出清单与证据分级

- 数据：`data/processed/shenyang_yearly_panel.parquet`（+ `outputs/tables/shenyang_yearly_panel.csv`）
- 表：`yearly_production_long.csv`、`yearly_growing_season_weather.csv`、`yearly_trend.csv`、`yearly_anomaly.csv`、`yearly_weather_corr.csv`、`yearly_simple_regression.csv`
- 图：`F36_yearly_vegetable.png`、`F37_yearly_grain.png`、`F38_yearly_weather_scatter.png`
- 证据分级：**Level A（官方统计数据，逐年可核）** 用于生产量本身；趋势/anomaly 为 **Level C（机制补充）**；相关与回归 **不作分级推断**（样本量不足）。