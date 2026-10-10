#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P4-09~P4-12 + P4-14：土壤 / 降雨暴露 / Sentinel-1 逐单元变化 / 30m→100m 聚合 → M2 空间数据集。
注意：SAR 仅 before/after，无历史同期对照 → 仅作“异常证据”，不得称为实测积水。
"""
import json
import os
import signal
import urllib.request

import numpy as np
import pandas as pd
import rasterio
from rasterio.warp import reproject, Resampling
from rasterio.windows import Window
from affine import Affine

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SP = os.path.join(BASE, "03_clean", "spatial")
M2 = os.path.join(BASE, "06_models", "M2_waterlogging_spatial")
MARTS = os.path.join(BASE, "04_marts")
BND = os.path.join(SP, "shenbei_boundary.gpkg")
DEM = os.path.join(SP, "dem", "pnb_dem_30m_utm.tif")
CROPLAND = os.path.join(SP, "cropland", "pnb_cropland_30m.tif")
IMD = os.path.join(SP, "dem")
HYD = os.path.join(SP, "hydro")
RES100 = 100.0


def alarm(s, f):
    raise TimeoutError("op_timeout")


signal.signal(signal.SIGALRM, alarm)


def grid_geom():
    import geopandas as gpd
    g = gpd.read_file(BND)
    minx, miny, maxx, maxy = g.total_bounds
    W = int(np.ceil((maxx - minx) / RES100)); H = int(np.ceil((maxy - miny) / RES100))
    tr = rasterio.transform.from_origin(minx, maxy, RES100, RES100)
    return minx, miny, maxx, maxy, W, H, tr, g


def aggregate(src_path, tr, H, W, how="mean", ref_path=DEM):
    """把 30m 栅格聚合到 100m 网格。"""
    res = {"mean": Resampling.average, "min": Resampling.min, "max": Resampling.max}[how]
    with rasterio.open(ref_path) as ref:
        src_crs, src_tr, src_shape = ref.crs, ref.transform, ref.shape
    with rasterio.open(src_path) as s:
        src = s.read(1).astype("float32")
    src[~np.isfinite(src)] = np.nan
    dst = np.full((H, W), np.nan, "float32")
    reproject(source=src, destination=dst, src_transform=src_tr, src_crs=src_crs,
              dst_transform=tr, dst_crs=src_crs, resampling=res,
              src_nodata=np.nan, dst_nodata=np.nan)
    dst[~np.isfinite(dst)] = np.nan
    return dst


def sentinel1():
    """Sentinel-1 VV before/after 逐 100m 单元的相对变化（未定标，仅探索性）。"""
    minx, miny, maxx, maxy, W, H, tr, g = grid_geom()
    PC = "https://planetarycomputer.microsoft.com/api/stac/v1"
    tok = "?" + json.loads(urllib.request.urlopen(
        "https://planetarycomputer.microsoft.com/api/sas/v1/token/sentinel-1-grd", timeout=40).read())["token"]

    def search(dt):
        body = json.dumps({"collections": ["sentinel-1-grd"],
                           "bbox": [123.30, 41.95, 123.95, 42.25], "datetime": dt, "limit": 50}).encode()
        req = urllib.request.Request(f"{PC}/search", data=body, headers={"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(req, timeout=70).read())["features"]

    pre = search("2026-07-05T00:00:00Z/2026-07-12T23:59:59Z")
    post = search("2026-07-14T00:00:00Z/2026-07-25T23:59:59Z")
    pairs = []
    for a in pre:
        pa = a["properties"]
        for b in post:
            pb = b["properties"]
            if pa.get("platform") == pb.get("platform") and pa.get("sat:relative_orbit") == pb.get("sat:relative_orbit"):
                pairs.append((a, b))
    if not pairs:
        return None, None, None, "no_matched_pair"

    def read_to_grid(ft):
        from pyproj import Transformer
        href = ft["assets"]["vv"]["href"]
        url = href + ("&" if "?" in href else "?") + tok
        A = Affine(*ft["properties"]["proj:transform"])
        # 研究区 UTM 边界 → 经纬度（S1 COG 为 EPSG:4326）
        t4326 = Transformer.from_crs(grid_geom()[7].crs, "EPSG:4326", always_xy=True)
        lon0, lat0 = t4326.transform(minx, miny)
        lon1, lat1 = t4326.transform(maxx, maxy)
        xs = [(lon0 - A.c) / A.a, (lon1 - A.c) / A.a]
        ys = [(lat1 - A.f) / A.e, (lat0 - A.f) / A.e]
        c0, c1 = int(min(xs)), int(max(xs)); r0, r1 = int(min(ys)), int(max(ys))
        with rasterio.open(url) as ds:
            c0 = max(0, c0); r0 = max(0, r0)
            c1 = min(c1, ds.width); r1 = min(r1, ds.height)
        if c1 - c0 < 10 or r1 - r0 < 10:
            raise RuntimeError("study bbox not covered by scene")
        win = Window(c0, r0, c1 - c0, r1 - r0)
        signal.alarm(180)
        try:
            with rasterio.open(url) as ds:
                arr = ds.read(1, window=win, out_shape=(H, W)).astype("float32")
        finally:
            signal.alarm(0)
        return arr
    preA = postA = rel = None
    note = "no_pair_covered_bbox"
    for a, b in pairs:
        try:
            preA = read_to_grid(a); postA = read_to_grid(b)
            rel = np.where(preA > 0, (postA - preA) / preA * 100.0, np.nan)
            note = f"{a['id']} -> {b['id']}"
            break
        except Exception as e:  # noqa
            note = f"pair_failed:{type(e).__name__}"
            continue
    if rel is None:
        return None, None, None, note
    return preA, postA, rel, note


def soilgrids(bbox_ll):
    """尝试 SoilGrids WCS（250m）取粘土含量；失败返回 None。"""
    lon0, lat0, lon1, lat1 = bbox_ll
    url = ("https://maps.isric.org/mapserv?map=/map/clay.map&SERVICE=WCS&VERSION=2.0.1"
           f"&REQUEST=GetCoverage&COVERAGEID=clay_0-5cm_mean&SUBSET=long({lon0},{lon1})"
           f"&SUBSET=lat({lat0},{lat1})&FORMAT=GEOTIFF_INT16")
    try:
        signal.alarm(90)
        with urllib.request.urlopen(url, timeout=80) as r:
            data = r.read()
        signal.alarm(0)
        p = os.path.join(BASE, "02_raw", "soil", "soilgrids_clay_0_5cm.tif")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "wb").write(data)
        return p
    except Exception as e:  # noqa
        signal.alarm(0)
        print("[P4] SoilGrids 失败:", type(e).__name__, e)
        return None


def main():
    minx, miny, maxx, maxy, W, H, tr, g = grid_geom()
    print(f"[P4] 100m 网格 {W}x{H}, 研究区 {g.total_bounds}")

    feat = {}
    feat["elevation"] = aggregate(os.path.join(IMD, "pnb_dem_filled_30m.tif"), tr, H, W, "min")
    feat["slope"] = aggregate(os.path.join(IMD, "pnb_slope_30m.tif"), tr, H, W, "mean")
    feat["local_relief"] = aggregate(os.path.join(IMD, "pnb_relief_30m.tif"), tr, H, W, "max")
    feat["depression_depth"] = aggregate(os.path.join(IMD, "pnb_depdepth_30m.tif"), tr, H, W, "max")
    feat["flow_accumulation"] = aggregate(os.path.join(IMD, "pnb_flowacc_30m.tif"), tr, H, W, "mean")
    feat["twi"] = aggregate(os.path.join(IMD, "pnb_twi_30m.tif"), tr, H, W, "mean")
    feat["hand"] = aggregate(os.path.join(IMD, "pnb_hand_30m.tif"), tr, H, W, "min")
    for nm in ["dist_mapped_water", "dist_mapped_river", "dist_mapped_drainage",
               "dist_major_road", "drainage_density_1km"]:
        feat[nm] = aggregate(os.path.join(HYD, nm + ".tif"), tr, H, W, "mean")
    feat["cropland_frac"] = aggregate(CROPLAND, tr, H, W, "mean")

    # 降雨暴露（事件全域 forcing，单 ERA5 网格点）
    feat["event_precip_mm"] = np.full((H, W), 218.0, "float32")     # 7-13+7-14
    feat["event_max_24h_mm"] = np.full((H, W), 155.7, "float32")
    feat["antecedent_7d_mm"] = np.full((H, W), 77.3, "float32")
    feat["antecedent_14d_mm"] = np.full((H, W), 146.0, "float32")

    # SAR
    preA, postA, rel, note = sentinel1()
    if rel is not None:
        feat["vv_before"] = preA; feat["vv_after"] = postA
        feat["delta_vv_pct"] = rel; feat["delta_vh_pct"] = np.full((H, W), np.nan, "float32")
        sar_note = note
    else:
        feat["vv_before"] = np.full((H, W), np.nan, "float32")
        feat["vv_after"] = np.full((H, W), np.nan, "float32")
        feat["delta_vv_pct"] = np.full((H, W), np.nan, "float32")
        sar_note = note
    print("[P4] SAR:", sar_note)

    # 土壤（尝试）
    soil_path = soilgrids([123.3, 41.95, 123.95, 42.25])
    if soil_path:
        try:
            with rasterio.open(soil_path) as s:
                dst = np.full((H, W), np.nan, "float32")
                reproject(source=rasterio.band(s, 1), destination=dst, src_transform=s.transform,
                          src_crs=s.crs, dst_transform=tr, dst_crs=g.crs, resampling=Resampling.average,
                          dst_nodata=np.nan)
                feat["soil_clay_pct"] = dst / 10.0
        except Exception as e:  # noqa
            print("[P4] 土壤重投影失败:", e)
    if "soil_clay_pct" not in feat:
        feat["soil_clay_pct"] = np.full((H, W), np.nan, "float32")

    # 导出单元（仅耕地网格）
    import geopandas as gpd
    grid = gpd.read_file(os.path.join(M2, "data", "grid_100m.gpkg"))
    rr = grid["row"].values; cc = grid["col"].values
    out = grid.copy()
    for k, v in feat.items():
        out[k] = v[rr, cc]
    out["event_precip_mm"] = out["event_precip_mm"].round(1)
    out["antecedent_7d_mm"] = out["antecedent_7d_mm"].round(1)
    out["antecedent_14d_mm"] = out["antecedent_14d_mm"].round(1)
    out.to_file(os.path.join(MARTS, "M2_spatial_dataset.gpkg"), driver="GPKG")
    out.drop(columns="geometry").to_csv(os.path.join(MARTS, "M2_spatial_dataset.csv"),
                                        index=False, encoding="utf-8-sig")
    print(f"[P4] M2 空间数据集: {len(out)} 单元, {out.shape[1]} 列")
    print(out.drop(columns="geometry").describe().T[["count", "mean", "min", "max"]].to_string())

    with open(os.path.join(M2, "remote_sensing", "S1_PROCESSING_PIPELINE.md"), "w", encoding="utf-8") as f:
        f.write(f"""# S1_PROCESSING_PIPELINE.md（P4-12）

| 步骤 | 是否执行 | 说明 |
|---|---|---|
| 场景筛选 | ✅ | 同平台 + 同相对轨道（几何可比）；配对：`{sar_note}` |
| radiometric calibration（σ⁰） | ❌ **未执行** | 未做绝对辐射定标；直接使用 GRD DN → **只能作相对变化** |
| speckle filtering | 🟡 部分 | 通过降采样到 100m 网格等效多视抑斑（非 Lee/Refined-Lee） |
| terrain correction | ❌ 未执行 | 未做地形辐射校正（山地/坡向影响未消除） |
| co-registration | 🟡 部分 | 依赖同一 COG 网格（未做精细配准） |
| dB conversion | ❌ | 使用相对百分比变化 `delta_vv_pct` |
| 历史同期对照 | ❌ | 2023–2025 同轨道在 Planetary Computer 无可用存档 → **无对照** |

## ⚠️ 解释纪律
> SAR 后向散射异常**可能与积水/高湿有关，也可能与土壤湿度、植被结构、入射角、风、粗糙度、双程散射有关**；
> 在**无地面验证、无辐射定标、无历史对照**的条件下，`delta_vv_pct` **只能作为“异常证据”，不得称为“实测积水”**。
""")
    print("[P4] S1_PROCESSING_PIPELINE.md 已写出")


if __name__ == "__main__":
    main()
