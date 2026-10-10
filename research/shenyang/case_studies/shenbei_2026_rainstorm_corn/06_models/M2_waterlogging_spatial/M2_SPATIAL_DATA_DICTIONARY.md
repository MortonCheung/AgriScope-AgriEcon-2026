# M2_SPATIAL_DATA_DICTIONARY.md

> 空间单元：100 m 网格（`04_marts/M2_spatial_dataset.gpkg/.csv`），坐标 EPSG:32651。
> 因果角色：PRE=PRE-EVENT、EVT=EVENT、POST=POST-EVENT（POST 不得作预测输入）。

| 变量 | 定义 | 单位 | 来源 | 空间分辨率 | 时间 | 质量 | 因果角色 |
|---|---|---|---|---|---|---|---|
| cell_id / row / col / x / y / area_m2 | 单元标识与几何 | m | 本研究 | 100 m | — | — | — |
| elevation | 填洼后高程（单元内 min） | m | Copernicus DEM 30m | 30 m | 静态 | C | PRE |
| slope | 坡度（单元均值） | ° | 同上 | 30 m | 静态 | C | PRE |
| local_relief | 5×5 邻域高差（单元 max） | m | 同上 | 30 m | 静态 | C | PRE |
| depression_depth | 原始DEM − 填洼DEM（单元 max） | m | 同上 | 30 m | 静态 | C | PRE |
| flow_accumulation | D8 汇流累积（单元均值） | 像元数 | 同上 | 30 m | 静态 | C | PRE |
| twi | 地形湿度指数 ln(a/tanβ) | — | 同上 | 30 m | 静态 | C | PRE |
| hand | 相对最近“排水像元(汇流≥200)”的高差 | m | 同上 | 30 m | 静态 | C | PRE |
| dist_mapped_water / _river / _drainage | 到 OSM 水系/河流/排水线的距离 | m | OSM | 30 m | 2026-09 | **C（不完整）** | PRE |
| drainage_density_1km | 1km 窗口内排水线像元比例 | — | OSM | 30 m | 2026-09 | **C（不完整）** | PRE |
| dist_major_road | 到主要公路的距离 | m | OSM | 30 m | 2026-09 | C | PRE |
| cropland_frac | 单元内耕地比例 | — | WorldCover 2021 | 10 m | 2021 | C | PRE |
| soil_clay_pct | 粘土含量 | % | SoilGrids | — | — | **not_available（取数失败）** | PRE |
| event_precip_mm | 事件累计降水（7-13+14） | mm | ERA5 | **单网格点** | 2026-07 | D（event-wide） | EVT |
| event_max_24h_mm | 最大24h降水 | mm | ERA5 | 单点 | 2026-07 | D | EVT |
| antecedent_7d_mm / _14d_mm | 事件前 7/14 日累计 | mm | ERA5 | 单点 | 2026-07 | D | EVT |
| vv_before / vv_after | S1 VV（GRD DN，未定标） | DN | Sentinel-1C | ~10 m→100 m | 2026-07-06/18 | D（未定标） | POST |
| delta_vv_pct | (after−before)/before | % | 同上 | 100 m | 2026-07 | D（无对照） | POST |
| sar_anomaly | ΔVV ≤ P10 标记 | 0/1 | 同上 | 100 m | 2026-07 | D | POST |
| susceptibility | 物理易涝性（机制方向等权→百分位） | 0–1 | 本研究 | 100 m | 静态 | C | 派生(PRE) |
| susceptibility_calib | 依证据点差异校准的易感性变体 | 0–1 | 本研究 | 100 m | 静态 | C | 派生(PRE) |
| evidence_proximity_m | 到最近“明确受淹”证据点距离 | m | 本研究/官方 | 100 m | 2026-07 | E（误差3–5km） | POST |
| event_exposure_rank | z(事件降水)+z(前期14d) 的秩 | 0–1 | ERA5 | 单点→常值 | 2026-07 | D | EVT |
| M2R_risk | 三层融合重建风险 | 0–1 | 本研究 | 100 m | 2026-07 | 派生 | 重建 |
| risk_class | Low/Moderate/High/VeryHigh | — | 本研究 | 100 m | 2026-07 | 派生 | 重建 |
| confidence_score / confidence_class | 观测+数据质量置信度 | 0–1 / Low/Med/High | 本研究 | 100 m | 2026-07 | 派生 | — |

## 缺失与降级说明
- `soil_clay_pct`：SoilGrids WCS 返回 400 → **not_available**（不插补）。
- 排水网络：OSM 仅 67 条水系（其中**排水沟 1 条**）→ 变量统一命名 `dist_mapped_*`，**不暗示完整覆盖**。
- 降雨：单 ERA5 网格点 → 作为 **event-wide forcing**，空间差异不来自降雨（诚实声明）。
- SAR：未做 σ⁰ 定标、无历史对照 → **仅异常证据**。
