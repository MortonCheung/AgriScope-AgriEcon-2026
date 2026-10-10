# M2_VARIABLE_CAUSAL_ROLE.md（P4-62）

| 变量 | 因果角色 | 说明 |
|---|---|---|
| elevation, slope, local_relief, depression_depth, flow_accumulation, twi, hand | **PRE-EVENT**（地形） | 事件前已存在；可作预测输入 |
| dist_mapped_drainage / _river / _water / drainage_density | **PRE-EVENT**（排水基础设施） | 基础设施；但 OSM 排水网络**不完整** → 命名用 `mapped_` |
| dist_major_road | **PRE-EVENT**（人工阻水候选） | 仅作候选机制，不预设致涝 |
| soil_clay_pct | **PRE-EVENT**（土壤） | 本轮 **not_available**（SoilGrids 取数失败） |
| cropland_frac | **PRE-EVENT**（土地覆盖） | WorldCover 2021 |
| event_precip_mm, event_max_24h_mm, antecedent_7d/14d | **EVENT**（2026 驱动） | 事件外强迫；本轮为**单网格点 event-wide forcing** |
| delta_vv_pct, vv_after | **POST-EVENT**（遥感） | **不得**作“预测是否会淹”的输入；仅作验证/更新证据 |
| ground evidence（受淹报道） | **POST-EVENT**（地面） | 同上 |
| intervention（12台8寸泵等） | **POST-EVENT** | **严格禁止**作预测输入（post-treatment leakage） |

## 结构拆分（P4-59/64）
- **M2a 自然/结构性易感性**：PRE-EVENT 地形+水系+土壤
- **M2b 2026 事件观测**：EVENT 驱动 + 干预
- **Predictive M2**：PRE-EVENT + EVENT（**不含** POST-EVENT）
- **Reconstruction M2R**：Predictive M2 **之后**再叠加 POST-EVENT（SAR / 地面证据）
