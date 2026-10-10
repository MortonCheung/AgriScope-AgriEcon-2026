# DATA_LINEAGE — 数据血缘规则

## 分层与不变式

```
raw_data/<...>                        原始证据（不可变，只索引）
  ↓ (解析 + 口径判定 + 单位换算)
02_standardized/<topic>/<table>.parquet    统一口径；每行带 source_id
  ↓ (point-in-time join)
03_integrated/*.parquet               跨表整合
  ↓ (模块裁剪)
04_model_ready/<module>/*.parquet     模型输入
```

## 每张标准表必须记录（写入 CANONICAL_TABLE_REGISTRY.csv + 表内字段）

- `source_id`（指向 SOURCE_REGISTRY.csv）
- `value_raw` / `unit_raw` / `value_standard` / `unit_standard` / `conversion_rule`（凡做过换算）
- `is_proxy` / `proxy_type`、`is_derived` / `derivation`、`geo_level`、`frequency`

## FEATURE_SOURCE_MAP

`04_model_ready` 的**每一列**必须在 `FEATURE_SOURCE_MAP.csv` 中登记：
`module, table, column, source_table, source_raw, transform, pit_safe(bool), notes`

## Point-in-time（PIT）安全

任何特征对决策时点 `t` 只能使用 `t` 之前**已发布**的信息：
- 遥感：月度值 forward-map 到日级时，`source_frequency=monthly`，且只能用 `t` 所在月及之前的月。
- 年度统计（面积/产量/成本/保险）：只能在**发布年**之后可用（默认按发布滞后 +1 年处理），并标记 `pit_lag_months`。
- 禁止使用 `t` 之后的数据（含"未来价格""未来面积"）。

## 版本关系

`CANONICAL_TABLE_REGISTRY.csv` 对每个 metric 指定唯一推荐表，并记录 `supersedes`（被它取代的旧表）与 `reason`。
旧表保留可读，但标注 `DO_NOT_USE_FOR_MODEL.csv`（若确有风险）。
