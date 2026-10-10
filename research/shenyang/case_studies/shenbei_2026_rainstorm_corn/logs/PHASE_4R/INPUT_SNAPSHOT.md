# INPUT_SNAPSHOT.md — Phase 4R 输入快照

生成时间：2026-09-23 00:53:17（Asia/Shanghai）

> 纪律：Phase 4R 期间 `01_sources/ 02_raw/ 03_clean/ 04_marts/` 视为 **READ-ONLY**；本快照为后续所有结果的唯一输入基准。

| 文件 | SHA256(16) | 大小 | mtime | 行数 | 时间范围 |
|---|---|---|---|---|---|
| 04_marts/M2_spatial_dataset.csv | `fe0db758cb063767` | 15.15MB | 2026-09-23 00:27 | 42473 |  |
| 04_marts/corn_model_dataset_annual.csv | `4c880135d04f94d4` | 0.01MB | 2026-09-22 22:45 | 8 | 2018-2025 |
| 04_marts/corn_year_weather_features.csv | `bd00ec543061475b` | 0.03MB | 2026-09-22 22:45 | 36 | 1991-2026 |
| 04_marts/rainfall_event_features.csv | `3c0a639084ab0d95` | 0.01MB | 2026-09-22 22:00 | 62 | 2026-06-15~2026-08-15 |
| 04_marts/literature_parameter_library.csv | `bd4db93b9541df9f` | 0.00MB | 2026-09-22 22:59 | 7 |  |
| 03_clean/agriculture/corn_history_extended.csv | `c610b625d09536ac` | 0.00MB | 2026-09-22 22:45 | 8 | 2018-2025 |
| 03_clean/spatial/shenbei_boundary.gpkg | `29fa63601da4b5ae` | 0.11MB | 2026-09-23 00:15 |  |  |
| 03_clean/spatial/dem/pnb_dem_30m_utm.tif | `e436d99b0e481ff5` | 2.11MB | 2026-09-23 00:15 |  |  |
| 03_clean/spatial/cropland/pnb_cropland_30m.tif | `95bf8a73e5611d07` | 0.05MB | 2026-09-23 00:15 |  |  |
| 02_raw/spatial/pnb_210113.json | `ff16b096f9096cc2` | 0.02MB | 2026-09-23 00:11 |  |  |
| 02_raw/terrain/Copernicus_DSM_30m_N42E123.tif | `054d36b7a3aa0c3e` | 44.74MB | 2026-09-23 00:11 |  |  |
| 02_raw/landcover/ESA_WorldCover_10m_2021_N42E123.tif | `ca86512be06f9188` | 80.61MB | 2026-09-23 00:11 |  |  |

## FULL_DATA_ACQUISITION_REPORT.md 检查
- 是否存在：**不存在** → **视为 Data Agent 尚未完成；不读取半成品文件**
