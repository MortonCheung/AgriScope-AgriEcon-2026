# M2_STABILITY_MAP.md（R05 / §二十四·二十五）

## 设定集合（共 8 套，均为**合理**设定，**未挑最好结果**）
- 权重族 4 套：equal / terrain-emphasis / drainage-emphasis / depression-hand-emphasis（100m, DEM30m）
- 分辨率族 3 套：网格 50 / 100 / 250 m（等权, DEM30m）
- DEM 分辨率 1 套：DEM 90 m（等权, 100m）

## 分类定义
| 类别 | 定义 |
|---|---|
| **robust_high** | 在**全部 8 套**设定下均进入 top20%（High/VeryHigh） |
| intermediate | 介于两者之间 |
| unstable | 在 ≤ 一半设定下进入 top20%（等级频繁变化） |

## 结果

| 类别 | 单元数 | 占耕地网格 |
|---|---|---|
| unstable | 34385 | 81.0% |
| robust_high | 5450 | 12.8% |
| intermediate | 2638 | 6.2% |

## 产出
- 图：`08_figures/M2/F13_stability_map.png`
- 单元表：`M2_STABILITY_MAP_cells.csv`
- GIS：`M2_STABILITY_MAP.geojson`

> ⚠️ **这不是新“真值”**，而是**模型稳健性**表达（§二十五）。
> robust_high 可作为“**无论如何设定都高易感**”的**优先关注区**；unstable 表示**结论依赖设定**，不得单独引用。
