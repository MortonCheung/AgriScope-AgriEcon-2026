#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P4-06~P4-11：DEM 水文预处理 + 地形特征 + 水系/道路距离 + 降雨暴露 → 100m 空间数据集。
- 保留两套自变量：(a) hydrologically-corrected DEM（填洼后）用于流向/汇流；(b) raw depression depth 识别真实洼地
- 排水数据不完整 → 变量名用 distance_to_mapped_*
输出：03_clean/spatial/dem/*.tif, 03_clean/spatial/hydro/*.tif, 04_marts/M2_spatial_dataset.csv/.gpkg
"""
import heapq
import os
import time

import numpy as np
import rasterio
from rasterio.warp import reproject, Resampling
from scipy import ndimage

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SP = os.path.join(BASE, "03_clean", "spatial")
M2 = os.path.join(BASE, "06_models", "M2_waterlogging_spatial")
MARTS = os.path.join(BASE, "04_marts")
os.makedirs(os.path.join(SP, "hydro"), exist_ok=True)
DEM = os.path.join(SP, "dem", "pnb_dem_30m_utm.tif")
CROPLAND = os.path.join(SP, "cropland", "pnb_cropland_30m.tif")
RES = 30.0


def read(path):
    with rasterio.open(path) as s:
        return s.read(1), s.transform, s.crs, s.shape


def fill_nearest(a):
    mask = ~np.isfinite(a)
    if not mask.any():
        return a
    idx = ndimage.distance_transform_edt(mask, return_distances=False, return_indices=True)
    out = a[tuple(idx)]
    return out


def priority_flood(dem):
    """Barnes et al. Priority-Flood：填洼（保留真实洼地需另用 raw）。"""
    H, W = dem.shape
    valid = np.isfinite(dem)
    filled = dem.copy()
    done = np.zeros((H, W), bool)
    pq = []
    # 种子：有效像元中位于有效区边界者
    nbr = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]
    for i in range(H):
        for j in range(W):
            if not valid[i, j]:
                continue
            edge = False
            for di, dj in nbr:
                ii, jj = i + di, j + dj
                if ii < 0 or jj < 0 or ii >= H or jj >= W or not valid[ii, jj]:
                    edge = True
                    break
            if edge:
                heapq.heappush(pq, (dem[i, j], i, j))
                done[i, j] = True
    while pq:
        z, i, j = heapq.heappop(pq)
        for di, dj in nbr:
            ii, jj = i + di, j + dj
            if 0 <= ii < H and 0 <= jj < W and valid[ii, jj] and not done[ii, jj]:
                nz = max(dem[ii, jj], z)
                filled[ii, jj] = nz
                done[ii, jj] = True
                heapq.heappush(pq, (nz, ii, jj))
    return filled


def d8_flow(filled, valid):
    """D8 流向 + 汇流累积（按高程降序累加）。"""
    H, W = filled.shape
    offs = [(-1, -1, 1.4142), (-1, 0, 1.0), (-1, 1, 1.4142), (0, -1, 1.0),
            (0, 1, 1.0), (1, -1, 1.4142), (1, 0, 1.0), (1, 1, 1.4142)]
    dist = np.zeros((H, W), np.int32)  # 0..7, -1=出口
    dist[:] = -1
    slope = np.zeros((H, W), np.float32)
    for k, (di, dj, dd) in enumerate(offs):
        II = np.arange(H)[:, None] + di
        JJ = np.arange(W)[None, :] + dj
        ok = (II >= 0) & (II < H) & (JJ >= 0) & (JJ < W)
        IIc = np.broadcast_to(np.clip(II, 0, H - 1), (H, W))
        JJc = np.broadcast_to(np.clip(JJ, 0, W - 1), (H, W))
        nz = np.where(ok, filled[IIc, JJc], np.inf).astype(np.float32)
        drop = (filled - nz) / (dd * RES)
        better = drop > slope
        slope = np.where(better, drop, slope)
        dist = np.where(better, k, dist)
    slope[~valid] = np.nan
    # 汇流
    acc = np.ones((H, W), np.float32)
    order = np.argsort(-filled, axis=None)
    fi = order // W; fj = order % W
    for i, j in zip(fi, fj):
        if not valid[i, j]:
            continue
        k = dist[i, j]
        if k < 0:
            continue
        di, dj, _ = offs[k]
        ii, jj = i + di, j + dj
        if 0 <= ii < H and 0 <= jj < W and valid[ii, jj]:
            acc[ii, jj] += acc[i, j]
    return dist, slope, acc


def handle_above_drainage(filled, dist, valid, acc, thr):
    """HAND：沿 D8 下游到首个“排水像元(acc>=thr)”，HAND=高程差累积。"""
    H, W = filled.shape
    offs = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    hand = np.full((H, W), np.nan, np.float32)
    order = np.argsort(-filled, axis=None)
    fi = order // W; fj = order % W
    for i, j in zip(fi, fj):
        if not valid[i, j]:
            continue
        if acc[i, j] >= thr:
            hand[i, j] = 0.0
            continue
        k = dist[i, j]
        if k < 0:
            hand[i, j] = 0.0
            continue
        di, dj = offs[k]
        ii, jj = i + di, j + dj
        if 0 <= ii < H and 0 <= jj < W and valid[ii, jj]:
            dh = max(0.0, filled[i, j] - filled[ii, jj])
            hand[i, j] = dh + (hand[ii, jj] if np.isfinite(hand[ii, jj]) else 0.0)
        else:
            hand[i, j] = 0.0
    return hand


def rasterize_osm_lines(json_path, filt):
    """把 OSM way（out geom）栅格化成 30m 掩膜。"""
    import json as _json
    d = _json.load(open(json_path, encoding="utf-8"))
    dem, transform, crs, shape = read(DEM)
    H, W = shape
    from pyproj import Transformer
    tr = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    mask = np.zeros((H, W), np.uint8)
    with rasterio.open(DEM) as s:
        for e in d["elements"]:
            t = e.get("tags", {})
            if not filt(t):
                continue
            geom = e.get("geometry") or []
            for pt in geom:
                X, Y = tr.transform(pt["lon"], pt["lat"])
                r, c = s.index(X, Y)
                if 0 <= r < H and 0 <= c < W:
                    mask[r, c] = 1
    return mask


def main():
    t0 = time.time()
    dem, transform, crs, shape = read(DEM)
    H, W = shape
    valid = np.isfinite(dem)
    print(f"[P4] DEM {shape} 有效 {valid.sum()}")

    # 填洼 (Priority-Flood)
    t = time.time(); filled = priority_flood(dem); print(f"[P4] 填洼 {time.time()-t:.1f}s")
    dep_depth = np.where(valid, filled - dem, np.nan).astype("float32")

    # 坡度/局部起伏
    d_fill = fill_nearest(dem)
    gy, gx = np.gradient(d_fill, RES, RES)
    slope_deg = np.degrees(np.arctan(np.hypot(gx, gy))).astype("float32")
    slope_deg[~valid] = np.nan
    relief = (ndimage.maximum_filter(d_fill, 5) - ndimage.minimum_filter(d_fill, 5)).astype("float32")
    relief[~valid] = np.nan

    # D8 流向/汇流
    t = time.time(); dist, slope_rad, acc = d8_flow(filled, valid); print(f"[P4] D8汇流 {time.time()-t:.1f}s")
    # TWI = ln(a/tanβ)
    a = acc * RES * RES / RES
    tanb = np.tan(np.where(slope_rad <= 0, np.radians(0.1), slope_rad))
    twi = np.log(a / tanb).astype("float32"); twi[~valid] = np.nan

    # HAND
    thr = 200.0  # 汇流阈值(像元数)，识别“排水网络”
    t = time.time(); hand = handle_above_drainage(filled, dist, valid, acc, thr); print(f"[P4] HAND {time.time()-t:.1f}s")

    def write(path, arr):
        with rasterio.open(path, "w", driver="GTiff", height=H, width=W, count=1,
                           dtype="float32", crs=crs, transform=transform, nodata=np.nan,
                           compress="deflate") as dst:
            dst.write(arr.astype("float32"), 1)

    for nm, arr in [("pnb_dem_filled_30m", filled), ("pnb_depdepth_30m", dep_depth),
                    ("pnb_slope_30m", slope_deg), ("pnb_relief_30m", relief),
                    ("pnb_flowacc_30m", acc), ("pnb_twi_30m", twi), ("pnb_hand_30m", hand)]:
        write(os.path.join(SP, "dem", nm + ".tif"), arr)
    print("[P4] 地形特征已写出")

    # ---------------- 距离场 ----------------
    wpath = os.path.join(BASE, "02_raw", "spatial", "osm_waterway.json")
    rpath = os.path.join(BASE, "02_raw", "spatial", "osm_roads.json")

    def dist_transform(mask):
        return (ndimage.distance_transform_edt(mask == 0) * RES).astype("float32")

    m_all = rasterize_osm_lines(wpath, lambda t: True)
    m_river = rasterize_osm_lines(wpath, lambda t: t.get("waterway") == "river")
    m_drain = rasterize_osm_lines(wpath, lambda t: t.get("waterway") in ("canal", "ditch", "stream"))
    m_road = rasterize_osm_lines(rpath, lambda t: t.get("highway") in ("motorway", "trunk", "primary", "secondary"))
    have = {k: int(v.sum()) for k, v in [("all_water", m_all), ("river", m_river),
                                         ("drainage", m_drain), ("major_road", m_road)]}
    print("[P4] OSM 线栅格化像元数:", have)
    for nm, m in [("dist_mapped_water", m_all), ("dist_mapped_river", m_river),
                  ("dist_mapped_drainage", m_drain), ("dist_major_road", m_road)]:
        write(os.path.join(SP, "hydro", nm + ".tif"), dist_transform(m))
    # 排水密度（1km 窗口内排水线像元比例）
    kd = np.ones((33, 33), np.float32)
    dens = (ndimage.convolve(m_drain.astype("float32"), kd, mode="constant") / kd.sum()).astype("float32")
    write(os.path.join(SP, "hydro", "drainage_density_1km.tif"), dens)

    np.savez_compressed(os.path.join(SP, "dem", "_acc_for_grid.npz"), acc=acc.astype("float32"),
                        valid=valid)
    print(f"[P4] 全部完成 {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
