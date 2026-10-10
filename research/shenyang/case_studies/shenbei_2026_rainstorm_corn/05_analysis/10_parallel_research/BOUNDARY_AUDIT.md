# BOUNDARY_AUDIT.md（R02 / §十三）

| 检查 | 结果 |
|---|---|
| 来源 | DataV.GeoAtlas（阿里云公开），**非政府法定测绘数据** |
| adcode | 210113（沈北新区） |
| 几何合法性 (shapely.is_valid) | **True** |
| 面积（UTM 51N 计算） | **813.1 km²** |
| 与公开官方面积对照 | 沈北新区常见公开面积约 819 km²；本边界 **≈813 km²**，量级一致（差 ~0.8%） |
| geom 类型 | Polygon |

## 术语规范（强制）
> 统一标记为 **public administrative boundary representation**（公开行政边界表示），
> **不得**宣称“官方行政边界”，除非取得政府法定测绘/民政部门 GIS 数据。
