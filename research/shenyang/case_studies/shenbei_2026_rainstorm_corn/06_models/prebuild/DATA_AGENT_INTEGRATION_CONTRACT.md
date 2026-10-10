# DATA_AGENT_INTEGRATION_CONTRACT.md（R17 / §八十四~八十五）

> 目的：定义 Data Agent 补数完成后，各模型**期望接收什么**、**字段级别**要求与**校验规则**。
> 配套校验器：`scripts/validate_new_data_contract.py`（返回 PASS / WARNING / FAIL / NOT_FOUND）。
> **本文件不修改任何 Data Agent 目录**（`01_sources/ 02_raw/ 03_clean/ 04_marts/` 为只读）。

## 级别定义
`REQUIRED` 缺失即 FAIL · `OPTIONAL` 缺失为 WARNING · `NICE_TO_HAVE` 缺失忽略

---

## 1. M2 希望接收（空间渍涝）
| 数据 | 级别 | 关键字段 | CRS | 单位 | 分辨率 | 时间 | 质量 |
|---|---|---|---|---|---|---|---|
| DEM（**裸地**优先） | OPTIONAL（已用 Copernicus DSM） | elevation | EPSG:32651（或可转换） | m | ≤30m | 静态 | 垂直精度说明 |
| cropland / **corn mask** | OPTIONAL（corn 为 NICE_TO_HAVE） | class/binary | 同研究 CRS | — | ≤30m | 近年 | 分类精度 |
| **drainage network**（沟渠/灌排） | REQUIRED（当前最缺） | geometry, type(natural/irrigation/drainage) | EPSG:4326 或 32651 | m | 矢量 | 现状 | 完整性声明 |
| **pump stations** | REQUIRED | location, capacity, control_area | 同上 | m³/h, ha | 点/面 | 现状 | 能力来源 |
| soil（质地/排水级） | OPTIONAL | clay/sand/drainage_class | 同上 | %, class | ≤1km | 静态 | 来源 |
| **multi-temporal SAR** | REQUIRED（解锁时长） | date, VV/VH(σ⁰), orbit, pass | 同研究 CRS | dB | ≤20m | 2026+历史同期 | 定标/校正说明 |
| ground evidence | OPTIONAL | location, date, depth, area | EPSG:4326 | m, 亩 | 点/面 | 2026-07 | 证据等级 G1–G5 |

**invalid_condition**：CRS 缺失且无经纬度；时间戳非 ISO；负的降水/水位。
**missing_handling**：**不插补**；置 NULL 并降级到较低模型等级。

## 2. M3 希望接收（渍涝→损伤）
| 字段 | 级别 | 说明 |
|---|---|---|
| paper_id / source | REQUIRED | 可回溯 |
| growth_stage | REQUIRED | 统一映射到 5 阶段 |
| waterlogging_duration (h 或 d) | REQUIRED | **核心自变量** |
| water_depth | OPTIONAL | 若有 |
| yield_control / yield_treated 或 relative_yield / loss | REQUIRED | 结果变量 |
| SD / SE / n | OPTIONAL（**缺则禁止加权 meta**） | — |
| experiment_type / field_or_pot | REQUIRED | 可比性判断 |
| **unit_conversion**：天数↔小时 | — | 必须显式记录 |

## 3. M4 希望接收（干预→历时）
| 字段 | 级别 | 说明 |
|---|---|---|
| pump capacity (m³/h) 或 铭牌/型号 | REQUIRED | 当前仅“12 台 8 寸泵”量级 |
| pump count | REQUIRED | — |
| start / end time | REQUIRED | 干预窗口 |
| drainage infrastructure（设计排水能力） | REQUIRED | 常规 vs 应急须分开 |
| affected / drained area | OPTIONAL | — |
| storage / depth 观测 | OPTIONAL | 峰值蓄水 |

## 4. Crop-state 分支
`date` + `NDVI` / `EVI` / `SAR` / `soil_moisture` + `spatial_unit`；REQUIRED: date, spatial_unit, ≥1 指标；OPTIONAL: 云掩膜、观测角。

## 5. Market 分支
`date` + `price` + `price_type(farmgate/purchase/wholesale/retail)` + `volume` + `market` + `spatial_level`。
**REQUIRED**: date, price, price_type。**invalid**: price ≤ 0；price_type 缺失。

## 6. 接入后统一处理
1. 单位换算表逐字段显式记录（**禁止 silent conversion**）；
2. 空间数据统一到 **EPSG:32651**；时间统一 **Asia/Shanghai**；
3. 全量写入 `logs/PHASE_4R/INPUT_SNAPSHOT.md` 的**增补快照**（含 SHA256）；
4. 通过 `validate_new_data_contract.py` 后，方可用于正式校准。
