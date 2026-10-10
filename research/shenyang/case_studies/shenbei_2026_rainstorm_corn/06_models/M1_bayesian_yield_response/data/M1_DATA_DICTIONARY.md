# M1_DATA_DICTIONARY.md

| 变量 | 含义 | 单位 | 来源 | 备注 |
|---|---|---|---|---|
| year | 统计年度（表内年度） | 年 | 官方年鉴 | 2018–2025 |
| yield_kg_ha | 沈北玉米单产 | kg/ha | 沈阳统计年鉴(A)/沈北区级年鉴(B,2025) | 结果变量 |
| time_index | 长期趋势变量 = year−2017 | 1..8 | 派生 | Z 标准化后入模 |
| primary_rain_exposure | 抽雄吐丝期最大连续 5 日累计降水 = `repro_precip_max_5d` | mm | ERA5 再分析(D) | 主暴露；GDD 物候定义阶段 |
| yield_quality | 单产质量等级 | 文本 | — | A / B |
| weather_quality | 气象质量 | 文本 | — | D_reanalysis_era5_gridcell |
| comparability | 行政可比性 | 文本 | ADMIN_BOUNDARY_HISTORY | DIRECTLY_COMPARABLE |
| source_ids | 来源标识 | 文本 | registry | — |
