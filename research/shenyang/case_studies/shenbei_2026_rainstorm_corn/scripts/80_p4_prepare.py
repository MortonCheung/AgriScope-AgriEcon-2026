#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P4-01~P4-05：输入审计文档 / 空间参考系 / 行政边界 / 30m 分析栅格 / 耕地掩膜 / 100m 研究网格。
输出：06_models/M2_waterlogging_spatial/{M2_INPUT_AUDIT.md, SPATIAL_REFERENCE.md, ...}
     03_clean/spatial/{shenbei_boundary.gpkg, dem/pnb_dem_30m_utm.tif, cropland/pnb_cropland_30m.tif}
     06_models/M2_waterlogging_spatial/data/grid_100m.gpkg
"""
import json
import os

import numpy as np
import rasterio
from rasterio.warp import reproject, Resampling
from rasterio.features import geometry_mask
from pyproj import Transformer
import pyogrio

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
M2 = os.path.join(BASE, "06_models", "M2_waterlogging_spatial")
SP = os.path.join(BASE, "03_clean", "spatial")
for p in [os.path.join(SP, "dem"), os.path.join(SP, "cropland"), os.path.join(M2, "data"),
          os.path.join(M2, "terrain")]:
    os.makedirs(p, exist_ok=True)

CRS = "EPSG:32651"     # UTM 51N：沈北(123.4-123.9E, 42.0-42.3N) 位于 51 带(120–126E)
RES30 = 30.0
RES100 = 100.0
BND_JSON = os.path.join(BASE, "02_raw", "spatial", "pnb_210113.json")
DEM_TIF = os.path.join(BASE, "02_raw", "terrain", "Copernicus_DSM_30m_N42E123.tif")
WC_TIF = os.path.join(BASE, "02_raw", "landcover", "ESA_WorldCover_10m_2021_N42E123.tif")


def boundary_geom():
    d = json.load(open(BND_JSON, encoding="utf-8"))
    return d["features"][0]["geometry"], d["features"][0]["properties"]


def main():
    geom, props = boundary_geom()
    tr = Transformer.from_crs("EPSG:4326", CRS, always_xy=True)

    def ring_to_utm(ring):
        xs = [pt[0] for pt in ring]
        ys = [pt[1] for pt in ring]
        X, Y = tr.transform(xs, ys)
        return list(zip(X, Y))

    from shapely.geometry import Polygon, MultiPolygon, mapping
    if geom["type"] == "Polygon":
        gj = Polygon(ring_to_utm(geom["coordinates"][0]),
                     [ring_to_utm(r) for r in geom["coordinates"][1:]])
    else:
        gj = MultiPolygon([
            Polygon(ring_to_utm(p[0]), [ring_to_utm(r) for r in p[1:]]) for p in geom["coordinates"]
        ])
    gj = gj.buffer(0)
    # 保存边界
    bnd_path = os.path.join(SP, "shenbei_boundary.gpkg")
    pyogrio.write_dataframe(
        __import__("geopandas").GeoDataFrame({"name": [props["name"]], "adcode": [props["adcode"]]},
                                             geometry=[gj], crs=CRS), bnd_path)
    minx, miny, maxx, maxy = gj.bounds
    print(f"[P4] 边界(UTM): {minx:.0f},{miny:.0f} -> {maxx:.0f},{maxy:.0f} | 面积 {gj.area/1e6:.1f} km2")

    # 目标 30m 栅格
    W = int(np.ceil((maxx - minx) / RES30)); H = int(np.ceil((maxy - miny) / RES30))
    dst_transform = rasterio.transform.from_origin(minx, maxy, RES30, RES30)
    print(f"[P4] 30m 栅格 {W}x{H} = {W*H/1e6:.2f} M 像元")

    # DEM 重投影 + 裁剪
    dem = np.full((H, W), np.nan, dtype="float32")
    with rasterio.open(DEM_TIF) as src:
        reproject(source=rasterio.band(src, 1), destination=dem,
                  src_transform=src.transform, src_crs=src.crs,
                  dst_transform=dst_transform, dst_crs=CRS,
                  resampling=Resampling.bilinear, dst_nodata=np.nan)
    inside = geometry_mask([mapping(gj)], out_shape=(H, W), transform=dst_transform, invert=True)
    dem[~inside] = np.nan
    prof = dict(driver="GTiff", height=H, width=W, count=1, dtype="float32",
                crs=CRS, transform=dst_transform, nodata=np.nan, compress="deflate")
    dem_path = os.path.join(SP, "dem", "pnb_dem_30m_utm.tif")
    with rasterio.open(dem_path, "w", **prof) as dst:
        dst.write(dem, 1)
    v = dem[np.isfinite(dem)]
    print(f"[P4] DEM 30m: 有效 {v.size} 高程 {np.nanmin(v):.1f}~{np.nanmax(v):.1f} m")

    # 耕地掩膜（ESA WorldCover 2021, class 40=Cropland）
    wc = np.zeros((H, W), dtype="uint8")
    with rasterio.open(WC_TIF) as src:
        reproject(source=rasterio.band(src, 1), destination=wc,
                  src_transform=src.transform, src_crs=src.crs,
                  dst_transform=dst_transform, dst_crs=CRS,
                  resampling=Resampling.nearest, dst_nodata=0)
    crop = ((wc == 40) & inside).astype("uint8")
    crop_path = os.path.join(SP, "cropland", "pnb_cropland_30m.tif")
    with rasterio.open(crop_path, "w", **{**prof, "dtype": "uint8", "nodata": 0}) as dst:
        dst.write(crop, 1)
    print(f"[P4] 耕地(WorldCover40): {crop.sum()} 像元 @30m = {crop.sum()*RES30*RES30/1e6:.1f} km2")

    # 100m 研究网格（边界 ∩ 耕地）
    crop100 = np.zeros((int(np.ceil(H * RES30 / RES100)), int(np.ceil(W * RES30 / RES100))), dtype="float32")
    reproject(source=crop.astype("float32"), destination=crop100,
              src_transform=dst_transform, src_crs=CRS,
              dst_transform=rasterio.transform.from_origin(minx, maxy, RES100, RES100),
              dst_crs=CRS, resampling=Resampling.average)
    inside100 = geometry_mask([mapping(gj)], out_shape=crop100.shape,
                              transform=rasterio.transform.from_origin(minx, maxy, RES100, RES100),
                              invert=True)
    sel = (crop100 >= 0.5) & inside100
    rr, cc = np.where(sel)
    xs = minx + (cc + 0.5) * RES100
    ys = maxy - (rr + 0.5) * RES100
    import geopandas as gpd
    from shapely.geometry import box
    gdf = gpd.GeoDataFrame({
        "cell_id": [f"C{i:06d}" for i in range(len(rr))],
        "row": rr, "col": cc, "x": xs, "y": ys, "area_m2": RES100 * RES100,
    }, geometry=[box(x - 50, y - 50, x + 50, y + 50) for x, y in zip(xs, ys)], crs=CRS)
    gdf.to_file(os.path.join(M2, "data", "grid_100m.gpkg"), driver="GPKG")
    print(f"[P4] 100m 研究网格: {len(gdf)} 单元 = {len(gdf)*RES100*RES100/1e6:.1f} km2")

    # ---------------- 文档 ----------------
    with open(os.path.join(M2, "SPATIAL_REFERENCE.md"), "w", encoding="utf-8") as f:
        f.write(f"""# SPATIAL_REFERENCE.md（P4-02）

| 项 | 值 |
|---|---|
| 分析 CRS | **{CRS}**（UTM zone 51N） |
| 单位 | 米（距离/面积/坡度）；高程米 |
| 选择理由 | 沈北位于 123.4–123.9°E（51 带 120–126°E 中心），UTM 51N 变形最小；**不在 EPSG:4326 下算面积/距离/坡度/缓冲** |
| 分析栅格分辨率 | **30 m**（DEM/耕地/地形），研究单元 **100 m** |
| 数据原始 CRS | 沈北边界=EPSG:4326；Copernicus DEM 30m=EPSG:4326；ESA WorldCover 10m=EPSG:4326；OSM=EPSG:4326；Sentinel-1 COG=EPSG:4326 |
| 重投影过程 | 全部用 `rasterio.warp.reproject`：连续量(DEM/WorldCover)分别用 bilinear/nearest；矢量用 `pyproj.Transformer` 逐点转 UTM |
| 研究区裁剪 | 一律用沈北新区行政边界（GeoJSON，见 §P4-03） |
""")

    with open(os.path.join(M2, "M2_INPUT_AUDIT.md"), "w", encoding="utf-8") as f:
        f.write(f"""# M2_INPUT_AUDIT.md — Phase 4 事实冻结（P4-01）

## 已知
- **2026 极端降雨时间**：7-12 20:00 ~ 7-15 00:00（52h）；峰值日 **7-13**（ERA5 网格点 153.1mm）
- **高频天气**：逐小时 2015–2026（ERA5，D 级）；事件最大 1h/3h/6h/24h = 21.2/50.9/85.8/155.7 mm
- **前期累计降雨**：暴雨前 7 日 77.3mm、14 日 146.0mm（前期偏湿）
- **已知受淹地点**：兴隆台街道（万亩农田，7-14 凌晨）、新城子街道八间房村（8000 余亩，最深>1m）
- **已知排涝地点**：八间房村/北四家子村、兴隆台街道新民村、蒲河主干
- **八间房村案例**：7-14 启动、7-15 增援、7-18 排净，约 8000 余亩，**12 台 8 寸泵**
- **Sentinel-1**：已有事件前后初步变化（Phase 2：窗口均值 VV −1.75%）
- **高标准农田**：已定位 **2026 沈北 101 国道沿线高标准农田项目**（财落+兴隆台街道，大营子村等，1.55 万亩）

## 未知（不得在后续悄悄变成“模型已知输入”）
```
全区真实积水边界 / 全区真实积水深度 / 全区积水持续时间
完整排水沟渠 / 所有泵站及能力 / 河渠水位 / 田块级玉米分布
沈北区级 2026 受灾成灾绝收面积与经济损失
```

## 空间数据（本轮新增，均登记 source_registry）
- 沈北新区行政边界：DataV geoatlas（adcode 210113）→ **A/B 级**
- Copernicus DEM 30m（AWS 公开 COG）→ **D 级（全球 DSM，含建筑/树冠，非裸地 DEM）**
- ESA WorldCover 10m 2021（class 40=Cropland）→ **C/D 级**
- OSM 水系（67 条）+ 道路/铁路（1013 条）→ **C 级，且排水沟渠明显不完整**
- Sentinel-1 GRD（Planetary Computer）→ **D 级**

## 研究区与网格（本轮建立）
- 研究区 = 沈北新区行政边界 ∩ WorldCover 耕地
- 分析栅格 30 m；研究单元 **100 m**（约见 `data/grid_100m.gpkg`）
- 输出精度受**最弱数据源**约束（soil≈1km、rainfall=单网格点、SAR≈10m、DEM=30m）
""")

    print("[P4] 文档已写出：SPATIAL_REFERENCE.md, M2_INPUT_AUDIT.md")
    return dict(minx=minx, miny=miny, maxx=maxx, maxy=maxy, W=W, H=H,
                transform=dst_transform, n_cells=len(gdf))


if __name__ == "__main__":
    main()
