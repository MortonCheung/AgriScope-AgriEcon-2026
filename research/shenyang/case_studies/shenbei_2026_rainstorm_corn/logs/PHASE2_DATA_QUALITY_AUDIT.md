# PHASE2_DATA_QUALITY_AUDIT.md — Phase 2 数据质量审计

> 对 Phase 2 新增产出统一审计（行数/范围/重复/缺失/单位/来源）。明细：`logs/phase2_data_quality_audit.csv`

| 数据集 | 路径 | 行 | 列 | 重复行 | 缺失率 | 时间范围 | 单位 | 来源 |
|---|---|---|---|---|---|---|---|---|
| 玉米历史(扩展) | 03_clean/agriculture/corn_history_extended.csv | 8 | 11 | 0 | 0.00 | 2018–2025 | ha/t/kg·ha | 沈阳统计年鉴 + 沈北区级年鉴 |
| 年度生育期天气特征 | 04_marts/corn_year_weather_features.csv | 36 | 165 | 0 | 0.048 | 1991–2026 | mm/℃/天 | ERA5（D） |
| 统一建模数据集 | 04_marts/corn_model_dataset_annual.csv | 8 | 179 | 0 | 0.00 | 2018–2025 | 混合 | 官方+ERA5 |
| CORE 特征集 | 04_marts/corn_model_dataset_annual_CORE.csv | 8 | 18 | 0 | 0.00 | 2018–2025 | 混合 | 官方+ERA5 |
| 文献参数库 | 04_marts/literature_parameter_library.csv | 7 | 13 | 0 | 0.077 | — | 减产% | 4 篇论文 |
| 2026 灾损结果变量 | 03_clean/disaster/disaster_outcomes_2026.csv | 4 | 13 | 0 | 0.00（多为 not_available） | 2026-07 | 亩/元 | 官方/媒体 |
| 干预量化 | 03_clean/intervention/intervention_quantified.csv | 3 | 24 | 0 | 0.194 | 2026-07 | 台/h/亩 | 官方/媒体 |
| 物候参考 | 03_clean/phenology/corn_phenology_reference.csv | 8 | 9 | 0 | 0.00 | 2026 | 日期 | 官方窗+GDD |
| 遥感影像清单 | 03_clean/remote_sensing/rs_scene_manifest.csv | 93 | 9 | 0 | 0.111 | 2026-05-01~09-09 | — | PC STAC |
| S1 后向散射(探索) | 03_clean/remote_sensing/rs_s1_backscatter_exploratory.csv | 2 | 10 | 0 | 0.40 | 2026-07 | DN/% | PC STAC |
| 气象源校验 | 05_analysis/02_climate_baseline/weather_source_validation.csv | 10 | 2 | 0 | 0.00 | 2021–2026 | 指标 | ERA5 vs NASA |
| 逐年 GDD 物候 | 05_analysis/05_phenology/corn_phenology_yearly_gdd.csv | 36 | 10 | 0 | 0.017 | 1991–2026 | 日期/GDD | ERA5 推算 |

## 检查结论
1. **无重复行**（全部 dup=0）；**无静默合并**。
2. 缺失率高的两处均为**“应有而未公开”**导致（灾损/干预的 `not_available`、遥感对照缺景），已显式留空，**未插补**。
3. 单位已统一与标注；`mm/h` 与累计 `mm` 严格区分（见 `PHASE1_UNIT_AND_TIME_REAUDIT.md`）。
4. 全部新增数据集均可通过 `source_id` 回溯（`DATA_SOURCE_REGISTRY.csv`，本轮新增 9 条来源）。
5. 未做任何插值、外推、编造；所有模型输出标注 `EXPLORATORY`。
