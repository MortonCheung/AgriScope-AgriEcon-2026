# M1_DATA_VERSION.md — 数据版本与指纹

| 项 | 值 |
|---|---|
| frozen_dataset | `data/M1_dataset_frozen.csv` |
| frozen_sha256(前16) | `a568f5c3b1a502f2` |
| rows | 8 |
| year_range | 2018–2025 |
| missing_rate | 0.0 |
| generator_script | `scripts/70_p3_prepare.py` |
| primary_exposure | `repro_precip_max_5d` |

## 上游文件指纹（SHA256 前16位）
| file | sha256(前16) | rows | year_min | year_max | missing_rate |
|---|---|---|---|---|---|
| 04_marts/corn_model_dataset_annual.csv | `4c880135d04f94d4` | 8 | 2018 | 2025 | 0.0 |
| 04_marts/corn_year_weather_features.csv | `bd00ec543061475b` | 36 | 1991 | 2026 | 0.0475 |
| 03_clean/agriculture/corn_history_extended.csv | `c610b625d09536ac` | 8 | 2018 | 2025 | 0.0 |
| 04_marts/literature_parameter_library.csv | `bd4db93b9541df9f` | 7 |  |  | 0.0769 |
| 03_clean/phenology/corn_phenology_reference.csv | `977bd45edea326e5` | 8 |  |  | 0.0 |
| 03_clean/intervention/intervention_quantified.csv | `49881a7d3ba737fe` | 3 |  |  | 0.1944 |
| 03_clean/disaster/disaster_outcomes_2026.csv | `44d31b9cd018e37f` | 4 |  |  | 0.0 |
| 01_sources/DATA_SOURCE_REGISTRY.csv | `5bfcab626b9a26fe` | 30 |  |  | 0.0 |


> 目的：当模型/前端更新时，可确认“当时模型用了哪一版数据”。
