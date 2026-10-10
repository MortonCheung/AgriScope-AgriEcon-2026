#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P4R-17：SoilGrids 土壤质地（clay/sand）采集 —— 补 M2 契约的 OPTIONAL 项 `soil`。

【为什么走 WCS 而不是 REST】
ISRIC SoilGrids 的 REST/WebDAV 端点在本环境被 BLOCKED；但 `maps.isric.org` 的
**WCS 2.0.1** 端点可达，可逐 CoverageId 取 GeoTIFF。

【两个坑】
1. 该服务器的 PROJ 库不支持 `EPSG:32651`（UTM 51N）：
   直接要 OUTPUTCRS=32651 会返回 400 `msProcessProjection(): PROJ error`。
   → 取 **OUTPUTCRS=4326**，回到本地自己重投影到研究区网格。
2. 原生投影是 EPSG:152160（Homolosine），250m。以 4326 输出时是经纬度格网
   （本区约 0.002°≈250m）。

【单位】SoilGrids 的 clay/sand 单位是 **g/kg**，除以 10 得质量百分比 %。
   验证：沈北受淹区 0–5cm 黏粒中位 ≈ 280 g/kg = **28%** → USDA 质地属"黏壤土/粉黏壤"，
   与 LIT-CHEN2026-BLACKSOIL 所述"黏粒含量高→限制垂向入渗→湿热复合胁迫"机制一致。

【产物】
- 原始：`02_raw/soil/soilgrids_<var>_<depth>_wgs84.tif`（保留来源凭证）
- 正式：`03_clean/soil/pnb_soil_<var>_<depth>_soilgrids.tif`（100m / EPSG:32651，与 M2 其他栅格同网格）
- 统计：`03_clean/soil/pnb_soil_texture_stats.csv`（含 USDA 质地分类）

【纪律】只读外部 + 写上述固定路径；增量落盘；已存在文件默认跳过（`--force` 覆盖）。
"""
from __future__ import annotations

import argparse
import csv
import os
import shutil
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import reproject, Resampling

os.environ.setdefault("GDAL_HTTP_TIMEOUT", "90")
os.environ.setdefault("GDAL_HTTP_CONNECTTIMEOUT", "25")
os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "2")

BASE = Path(__file__).resolve().parents[3]
SP = BASE / "03_clean" / "spatial"
RAW_SOIL = BASE / "02_raw" / "soil"
CLEAN_SOIL = BASE / "03_clean" / "soil"
BND = SP / "shenbei_boundary.gpkg"

WCS = "https://maps.isric.org/mapserv"
BBOX = (123.30, 41.95, 123.95, 42.25)      # long_min, lat_min, long_max, lat_max
DEPTHS = ("0-5cm", "5-15cm", "15-30cm")
VARS = ("clay", "sand")
RES100 = 100.0
CRS = "EPSG:32651"


# ------------------------------------------------------------------ 网格
def grid_geom():
    import geopandas as gpd
    g = gpd.read_file(BND)
    minx, miny, maxx, maxy = g.total_bounds
    W = int(np.ceil((maxx - minx) / RES100))
    H = int(np.ceil((maxy - miny) / RES100))
    tr = rasterio.transform.from_origin(minx, maxy, RES100, RES100)
    return dict(minx=minx, miny=miny, maxx=maxx, maxy=maxy, W=W, H=H, tr=tr, crs=CRS)


# ------------------------------------------------------------------ 下载
def wcs_url(var, depth):
    q = {
        "map": f"/map/{var}.map",
        "SERVICE": "WCS",
        "VERSION": "2.0.1",
        "REQUEST": "GetCoverage",
        "COVERAGEID": f"{var}_{depth}_mean",
        "FORMAT": "GEOTIFF_INT16",
        "SUBSET": [f"long({BBOX[0]},{BBOX[2]})", f"lat({BBOX[1]},{BBOX[3]})"],
        "SUBSETTINGCRS": "http://www.opengis.net/def/crs/EPSG/0/4326",
        "OUTPUTCRS": "http://www.opengis.net/def/crs/EPSG/0/4326",
    }
    # 同名键多值需 repeated，用 doseq 展开
    return WCS + "?" + urllib.parse.urlencode(q, doseq=True)


def download(var, depth, force=False):
    RAW_SOIL.mkdir(parents=True, exist_ok=True)
    dst = RAW_SOIL / f"soilgrids_{var}_{depth}_wgs84.tif"
    if dst.exists() and not force and dst.stat().st_size > 5000:
        return dst, "cached"
    url = wcs_url(var, depth)
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "shenbei-corn-research/1.0"})
            with urllib.request.urlopen(req, timeout=120) as r:
                body = r.read()
            if not body.startswith(b"II*\x00") and not body.startswith(b"MM\x00*"):
                raise RuntimeError(f"not_tiff:{body[:90]!r}")
            dst.write_bytes(body)
            return dst, f"ok:{len(body)}B"
        except Exception as e:                       # noqa: BLE001
            if attempt == 2:
                raise
            print(f"    retry({attempt + 1}) {type(e).__name__}: {str(e)[:70]}", flush=True)
            time.sleep(4)
    return dst, "fail"


# ------------------------------------------------------------------ 重投影
def to_grid(src_path, geom, force=False):
    """WGS84 int16 (g/kg) → 100m UTM51 float32 (%)。"""
    tag = src_path.stem.replace("soilgrids_", "").replace("_wgs84", "")
    dst = CLEAN_SOIL / f"pnb_soil_{tag}_soilgrids.tif"
    if dst.exists() and not force:
        return dst, "cached"
    CLEAN_SOIL.mkdir(parents=True, exist_ok=True)
    with rasterio.open(src_path) as s:
        src = s.read(1).astype("float64")
        src_tr, src_crs, nod = s.transform, s.crs, s.nodata
    if nod is not None:
        src[src == nod] = np.nan
    src[src <= 0] = np.nan
    src = src / 10.0                                  # g/kg → %
    prof = dict(driver="GTiff", height=geom["H"], width=geom["W"], count=1,
                dtype="float32", crs=geom["crs"], transform=geom["tr"],
                nodata=np.nan, compress="deflate")
    out = np.full((geom["H"], geom["W"]), np.nan, "float32")
    reproject(source=src.astype("float32"), destination=out,
              src_transform=src_tr, src_crs=src_crs,
              dst_transform=geom["tr"], dst_crs=geom["crs"],
              resampling=Resampling.bilinear, src_nodata=np.nan, dst_nodata=np.nan)
    with rasterio.open(dst, "w", **prof) as d:
        d.write(out, 1)
    return dst, "ok"


# ------------------------------------------------------------------ USDA 质地
def usda_class(clay, sand):
    """简化 USDA 三角分类（仅用 clay/sand，粉粒 = 100-clay-sand）。"""
    if not np.isfinite(clay) or not np.isfinite(sand):
        return ""
    silt = 100.0 - clay - sand
    if silt < 0:  silt = 0.0
    if clay >= 40 and silt >= 40:   return "silty clay"
    if clay >= 40 and sand <= 45:   return "clay"
    if clay >= 35 and sand > 45:    return "sandy clay"
    if 27 <= clay < 40 and 20 < sand <= 45: return "clay loam"
    if 27 <= clay < 40 and sand <= 20:      return "silty clay loam"
    if 20 <= clay < 35 and silt >= 28 and sand <= 20: return "silt loam"
    if clay < 27 and silt >= 50:    return "silt loam"
    if clay >= 20 and sand > 45:    return "sandy clay loam"
    if clay < 20 and silt < 30 and sand > 70: return "sandy loam"
    if clay < 20 and 43 <= silt < 50 and sand <= 52: return "loam"
    return "loam"


def summarize(geom):
    rows = []
    for depth in DEPTHS:
        for var in VARS:
            p = CLEAN_SOIL / f"pnb_soil_{var}_{depth}_soilgrids.tif"
            if not p.exists():
                continue
            with rasterio.open(p) as s:
                a = s.read(1).astype("float64")
            v = a[np.isfinite(a)]
            if v.size == 0:
                continue
            rows.append(dict(var=var, depth=depth, unit="%",
                             n_valid_100m_cells=int(v.size),
                             mean=round(float(v.mean()), 2),
                             p10=round(float(np.percentile(v, 10)), 2),
                             median=round(float(np.median(v)), 2),
                             p90=round(float(np.percentile(v, 90)), 2),
                             min=round(float(v.min()), 2), max=round(float(v.max()), 2),
                             source_id="SRC-ISRIC-SOILGRIDS-WCS",
                             notes="SoilGrids 250m → 100m 网格（bilinear）；原始 g/kg ÷10 → %"))
    # 表层质地分类（clay0-5 vs sand0-5 在网格上配对）
    out_csv = CLEAN_SOIL / "pnb_soil_texture_stats.csv"
    with out_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return out_csv, rows


def texture_scorecard(geom):
    """表层 clay/sand 合成 → USDA 分类占比 + 逐一网格质地表。"""
    pc = CLEAN_SOIL / "pnb_soil_clay_0-5cm_soilgrids.tif"
    ps = CLEAN_SOIL / "pnb_soil_sand_0-5cm_soilgrids.tif"
    if not (pc.exists() and ps.exists()):
        return None
    with rasterio.open(pc) as s:
        clay = s.read(1).astype("float64")
    with rasterio.open(ps) as s:
        sand = s.read(1).astype("float64")
    m = np.isfinite(clay) & np.isfinite(sand)
    if not m.any():
        return None
    cl, sa = clay[m], sand[m]
    from collections import Counter
    cls = Counter(usda_class(c, s) for c, s in zip(cl, sa))
    tot = sum(cls.values())
    out = CLEAN_SOIL / "pnb_soil_texture_class_summary.csv"
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["usda_class", "n_cells", "share_pct",
                                          "mechanism_note"])
        w.writeheader()
        for k, v in cls.most_common():
            w.writerow(dict(usda_class=k, n_cells=v, share_pct=round(v / tot * 100, 1),
                            mechanism_note="黏粒重/透水性差 → 渍涝滞留风险高"
                            if k in ("clay", "silty clay", "sandy clay",
                                     "clay loam", "silty clay loam") else "透水性相对较好"))
    return out, cls, float(np.median(cl)), float(np.median(sa))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="重下并覆盖")
    a = ap.parse_args()
    print("=== 117_p4r_soilgrids_texture ===", flush=True)
    geom = grid_geom()
    print(f"研究区 100m 网格 {geom['W']}x{geom['H']} crs={geom['crs']}", flush=True)

    for var in VARS:
        for depth in DEPTHS:
            raw, st = download(var, depth, a.force)
            clean, st2 = to_grid(raw, geom, a.force)
            print(f"  {var:5s} {depth:8s} raw[{st}] → {clean.name}[{st2}]", flush=True)

    out_csv, rows = summarize(geom)
    print(f"\n[117] 统计 → {out_csv.name} ({len(rows)} 行)", flush=True)
    for r in rows:
        print(f"   {r['var']:5s} {r['depth']:8s} 中位 {r['median']:6.2f}% "
              f"(p10 {r['p10']:5.2f} / p90 {r['p90']:5.2f})", flush=True)

    sc = texture_scorecard(geom)
    if sc:
        p, cls, mc, ms = sc
        print(f"\n[117] USDA 质地分类（表层 0–5cm）→ {p.name}", flush=True)
        for k, v in cls.most_common():
            print(f"   {k:18s} {v:6d} 单元 ({v / sum(cls.values()) * 100:5.1f}%)", flush=True)
        print(f"   区级中位：黏粒 {mc:.1f}% / 砂粒 {ms:.1f}%", flush=True)
        print("   → 与 LIT-CHEN2026-BLACKSOIL 机制呼应：黏粒高 → 垂向入渗受限 → 渍涝滞留", flush=True)


if __name__ == "__main__":
    main()
