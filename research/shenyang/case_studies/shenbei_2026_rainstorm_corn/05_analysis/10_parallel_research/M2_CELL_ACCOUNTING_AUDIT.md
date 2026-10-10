# M2_CELL_ACCOUNTING_AUDIT.md（R02 / §八）

## 总单元 = 42473

### risk_class 分布（含 NaN）

| class | cells |
|---|---|
| Low | 21236 |
| Moderate | 12742 |
| High | 6371 |
| VeryHigh | 2124 |

**已分类合计 = 42473；未分类（NaN）= 0**

## 逐特征缺失（100m 网格）

| 特征 | NaN 单元数 |
|---|---|
| elevation | 0 |
| slope | 0 |
| local_relief | 0 |
| depression_depth | 0 |
| flow_accumulation | 0 |
| twi | 0 |
| hand | 0 |
| dist_mapped_water | 0 |
| dist_mapped_river | 0 |
| dist_mapped_drainage | 0 |
| dist_major_road | 0 |
| cropland_frac | 0 |
| susceptibility | 0 |
| M2R_risk | 0 |

## 未分类单元成因诊断

- 未分类单元中 `susceptibility` 为 NaN：**0**
- 未分类单元中 `slope` 为 NaN：**0**
- 未分类单元中 `twi` 为 NaN：**0**
- 未分类单元中 `depression_depth` 为 NaN：**0**
- 未分类单元中地形族全部有效者：**0**

## 结论（总单元 = 有效分类 + 明确未分类）

```
总单元 42473
= 有效分类 42473
+ 明确未分类 0（原因见下）
```

**原因**：这 0 个 100m 单元为“耕地 ∩ 边界内”，但其 **30m DEM 足迹全为 NoData**（DEM 瓦片边缘/空洞）→ `slope`/`twi` 在 DEM 无效处被置 NaN → 物理易感性指数含 NaN → `susceptibility` 与 `M2R_risk` 为 NaN → 风险分级为空。

**处理**：**不插补、不删格**；正式口径中单列为 **UNCLASSIFIED（DEM 无数据）**。
> 另注：`risk_class` 的阈值来自 `pd.cut(percentile_rank, [0,0.5,0.8,0.95,1])`，即 **相对排名分位**，**不是积水概率**（见 TERMINOLOGY_CORRECTION_PHASE4R.md）。
