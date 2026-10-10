# Data Foundation v1 · QC 报告

生成：2026-10-04 ｜ 表数 69 ｜ 覆盖行 402 ｜ 缺失记录 826 ｜ 越界记录 145

## 需要关注的表（时间覆盖 < 50%）
- data/processed/bio_risk/pest_disease_events.parquet: 0.0186 (2024-04-19~2025-08-14, 9/483 天)
- data/processed/market/market_volume.parquet: 0.3852 (2015-12-14~2026-09-22, 1516/3936 天)
- data/processed/market/price_observation_nonstandard.parquet: 0.1531 (2018-04-09~2026-09-22, 473/3089 天)
- data/model_ready/jinzhou_extended/market_daily.parquet: 0.3968 (2020-01-01~2026-09-22, 975/2457 天)

## 缺失率最高的列（Top20）
- data/processed/climate/weather_daily.parquet::snow_depth_mean = 1.0
- data/processed/climate/weather_district_shenyang.parquet::soil_moisture_0_to_10cm_mean = 1.0
- data/processed/climate/weather_district_shenyang.parquet::pressure_msl_mean = 1.0
- data/processed/climate/weather_district_shenyang.parquet::surface_pressure_mean = 1.0
- data/processed/climate/weather_district_shenyang.parquet::dew_point_2m_mean = 1.0
- data/processed/climate/weather_district_shenyang.parquet::snowfall_sum = 1.0
- data/processed/climate/weather_district_shenyang.parquet::snow_depth_mean = 1.0
- data/processed/climate/weather_district_shenyang.parquet::cloud_cover_mean = 1.0
- data/processed/climate/weather_district_shenyang.parquet::vapour_pressure_deficit_max = 1.0
- data/processed/climate/weather_district_shenyang.parquet::wind_gusts_10m_max = 1.0
- data/processed/climate/weather_district_shenyang.parquet::unit_pressure_msl_mean = 1.0
- data/processed/climate/weather_district_shenyang.parquet::unit_surface_pressure_mean = 1.0
- data/processed/climate/weather_district_shenyang.parquet::unit_dew_point_2m_mean = 1.0
- data/processed/climate/weather_district_shenyang.parquet::unit_snowfall_sum = 1.0
- data/processed/climate/weather_district_shenyang.parquet::unit_snow_depth_mean = 1.0
- data/processed/climate/weather_district_shenyang.parquet::unit_cloud_cover_mean = 1.0
- data/processed/climate/weather_district_shenyang.parquet::unit_vapour_pressure_deficit_max = 1.0
- data/processed/climate/weather_district_shenyang.parquet::unit_wind_gusts_10m_max = 1.0
- data/processed/cost/cost_components.parquet::machinery_cost = 1.0
- data/processed/cost/cost_components.parquet::land_cost = 1.0

## 越界最多（3×IQR，仅标记未删除）
- data/processed/market/price_observation.parquet::price_original n=13450/143030
- data/processed/climate/weather_daily.parquet::elevation n=12202/73212
- data/processed/market/price_observation.parquet::price_per_kg n=10142/135747
- data/processed/climate/weather_daily.parquet::precipitation_sum n=6038/36606
- data/processed/integrated/city_daily_environment.parquet::precipitation_sum n=6038/36606
- data/model_ready/climate/climate_daily.parquet::precipitation_sum n=6038/36606
- data/processed/climate/weather_district_shenyang.parquet::precipitation_sum n=5233/32144
- data/model_ready/chaoyang_extended/market_daily.parquet::price_original n=4002/37129
- data/model_ready/jinzhou_extended/market_daily.parquet::price_original n=3817/35123
- data/model_ready/jinzhou_extended/market_daily.parquet::price_per_kg n=3802/34775