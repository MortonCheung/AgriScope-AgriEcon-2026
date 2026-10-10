# M3_INPUT_CONTRACT.md（R09 / §四十四）

## 正式 M3 最低输入
| 字段 | 级别 | 类型 | 说明 | 缺失时降级 |
|---|---|---|---|---|
| cell_id | REQUIRED | str | 与 M2 空间单元对齐 | 无法接入 → 停止 |
| area | REQUIRED | m² | 单元面积（聚合用） | 用 100×100 默认 |
| crop_type | REQUIRED | enum | 至少 `maize`/`other` | 若未知 → 标 `agricultural_cropland`（不得称玉米） |
| growth_stage | REQUIRED | enum | vegetative/jointing/tasseling/silking/grain_filling | 用 GDD 估计并标 `model_estimate` |
| waterlogging_duration | **REQUIRED(核心)** | hours | 积水持续时长 | **缺失 → M3 不可运行**（只可区间情景） |
| duration_uncertainty | OPTIONAL | [lo,hi] | 时长区间 | 无 → 用情景区间 |
| water_depth | OPTIONAL | m | 水深 | 无 → 仅用时长的 M3-B/C |
| evidence_quality | REQUIRED | enum | D1/D2/D3（§五十七） | 无 → 标 unknown |

## 降级规则
- 缺 `waterlogging_duration` → **禁止输出任何沈北损伤数字**；只允许 `stage×duration` 情景区间（M3-C）。
- 缺 `variance` → 禁止加权 meta-analysis；只允许区间/先验。
- 缺 `crop_type=maize` → 结论只能写 **agricultural cropland**。

## 输出契约
`yield_ratio_distribution` / `damage_fraction_distribution`（**必须带区间**）。
