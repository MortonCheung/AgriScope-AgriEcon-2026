# SPATIAL_REFERENCE.md（P4-02）

| 项 | 值 |
|---|---|
| 分析 CRS | **EPSG:32651**（UTM zone 51N） |
| 单位 | 米（距离/面积/坡度）；高程米 |
| 选择理由 | 沈北位于 123.4–123.9°E（51 带 120–126°E 中心），UTM 51N 变形最小；**不在 EPSG:4326 下算面积/距离/坡度/缓冲** |
| 分析栅格分辨率 | **30 m**（DEM/耕地/地形），研究单元 **100 m** |
| 数据原始 CRS | 沈北边界=EPSG:4326；Copernicus DEM 30m=EPSG:4326；ESA WorldCover 10m=EPSG:4326；OSM=EPSG:4326；Sentinel-1 COG=EPSG:4326 |
| 重投影过程 | 全部用 `rasterio.warp.reproject`：连续量(DEM/WorldCover)分别用 bilinear/nearest；矢量用 `pyproj.Transformer` 逐点转 UTM |
| 研究区裁剪 | 一律用沈北新区行政边界（GeoJSON，见 §P4-03） |
