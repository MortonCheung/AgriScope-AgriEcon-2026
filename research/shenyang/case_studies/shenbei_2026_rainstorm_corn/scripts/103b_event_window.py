#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Package A —— 光学植被/水分指数计算（Sentinel-2 L2A，AOI 窗口化读取）

【为什么窗口化读取】
沈北 AOI 仅 813 km²，而一景 Sentinel-2 瓦片约 110×110 km。整景下载再裁剪会浪费 ~93% 流量。
本脚本直接用 rasterio 对云端 COG 读取 **AOI 窗口**，再重投影到既有 30 m 耕地栅格网格上统计。

【云处理纪律（用户明确要求）】
- 使用 SCL（Scene Classification Layer）做像元级云掩膜：
  排除 0(nodata)/1(saturated)/3(cloud shadow)/8(cloud med)/9(cloud high)/10(cirrus)/11(snow)
- **绝不因云多而把缺测插值成"观测值"**：有效像元不足时输出 NaN 并标 quality=missing。

【统计分区】
对 `03_clean/spatial/cropland/pnb_cropland_30m.tif` 掩膜内像元统计：
  全区（AOI ∩ 影像） / 耕地（cropland mask=1）
输出逐景一条记录，保留真实 acquisition date（不做日期插值）。

输出：03_clean/remote_sensing/s2_crop_indices_2026_event.csv
"""
from __future__ import annotations

import json
import time
import urllib.parse
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import requests
from rasterio.warp import reproject, Resampling
from rasterio.transform import from_bounds

ROOT = Path(__file__).resolve().parents[3]
CROP_MASK = ROOT / "03_clean" / "spatial" / "cropland" / "pnb_cropland_30m.tif"
CATALOG = ROOT / "02_raw" / "remote_sensing" / "scene_catalog_all.csv"
OUT_DIR = ROOT / "03_clean" / "remote_sensing"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SAS = "https://planetarycomputer.microsoft.com/api/sas/v1/sign"
UA = {"User-Agent": "shenbei-corn-research/1.0"}
AOI_WGS = (123.27267, 41.87854, 123.72514, 42.19288)   # minx, miny, maxx, maxy

# SCL 需要排除的类别
BAD_SCL = {0, 1, 3, 8, 9, 10, 11}


def sign(href: str) -> str:
    r = requests.get(SAS, params={"href": href}, headers=UA, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"sign fail {r.status_code}")
    return r.json()["href"]


def read_to_grid(url: str, dst_shape, dst_transform, dst_crs, nodata=0) -> np.ndarray:
    """窗口化读 COG 并重投影到目标 30 m 网格。"""
    with rasterio.open(url) as src:
        # AOI 在源 CRS 下的窗口
        from rasterio.warp import transform_bounds
        b = transform_bounds("EPSG:4326", src.crs, *AOI_WGS)
        win = src.window(*b)
        win = win.intersection(rasterio.windows.Window(0, 0, src.width, src.height))
        if win.width < 2 or win.height < 2:
            return np.full(dst_shape, np.nan, dtype="float32")
        # 关键：按目标网格分辨率抽稀读取，避免为 813 km² 传 13 GB 原生 10m 数据
        h, w = int(win.height), int(win.width)
        MAXPX = 2_000_000
        k = max(1, int(np.ceil(np.sqrt(max(h * w, 1) / MAXPX))))
        arr = src.read(1, window=win, out_shape=(max(1, h // k), max(1, w // k)),
                       boundless=True, fill_value=nodata).astype("float32")
        wtrans = src.window_transform(win)
        dst = np.full(dst_shape, np.nan, dtype="float32")
        reproject(
            source=arr, destination=dst,
            src_transform=wtrans, src_crs=src.crs, src_nodata=nodata,
            dst_transform=dst_transform, dst_crs=dst_crs,
            resampling=Resampling.average,
        )
        return dst


def main() -> None:
    if not CROP_MASK.exists() or not CATALOG.exists():
        print("[FAIL] 缺少耕地掩膜或场景编目")
        return
    with rasterio.open(CROP_MASK) as cm:
        crop = cm.read(1)
        prof = cm.profile
        dst_shape = crop.shape
        dst_transform = cm.transform
        dst_crs = cm.crs
        cropmask = (crop == 1) if crop.max() <= 1 else (crop > 0)

    cat = pd.read_csv(CATALOG)
    s2 = cat[(cat.collection == "sentinel-2-l2a")].copy()
    s2 = s2[(s2.aoi_coverage_frac >= 0.5) & (s2.date >= "2026-06-01") & (s2.date <= "2026-09-05")].sort_values("date")
    print(f"待处理 Sentinel-2 场景: {len(s2)}")

    rows = []
    for i, (_, r) in enumerate(s2.iterrows(), 1):
        try:
            hrefs = json.loads(r["hrefs"])
        except Exception:
            continue
        if not all(k in hrefs for k in ("B03", "B04", "B08", "B11", "SCL")):
            continue
        try:
            b = {k: sign(hrefs[k]) for k in ("B03", "B04", "B08", "B11", "SCL")}
            scl = read_to_grid(b["SCL"], dst_shape, dst_transform, dst_crs, nodata=0)
            g03 = read_to_grid(b["B03"], dst_shape, dst_transform, dst_crs)
            g04 = read_to_grid(b["B04"], dst_shape, dst_transform, dst_crs)
            g08 = read_to_grid(b["B08"], dst_shape, dst_transform, dst_crs)
            g11 = read_to_grid(b["B11"], dst_shape, dst_transform, dst_crs)

            clear = ~np.isin(scl, list(BAD_SCL))
            # 反射率缩放（L2A COG 为 DN，需 /10000）
            r03 = np.where(g03 > 0, g03 / 10000.0, np.nan)
            r04 = np.where(g04 > 0, g04 / 10000.0, np.nan)
            r08 = np.where(g08 > 0, g08 / 10000.0, np.nan)
            r11 = np.where(g11 > 0, g11 / 10000.0, np.nan)

            with np.errstate(invalid="ignore", divide="ignore"):
                ndvi = (r08 - r04) / (r08 + r04)
                evi = 2.5 * (r08 - r04) / (r08 + 6 * r04 - 7.5 * r03 + 1)
                ndwi = (r03 - r08) / (r03 + r08)      # McFeeters NDWI (Green-NIR)
                mndwi = (r03 - r11) / (r03 + r11)     # 徐涵秋 MNDWI (Green-SWIR)

            out = {"scene_id": r["scene_id"], "date": r["date"], "year": r["year"],
                   "cloud_cover": r["cloud_cover"]}
            for nm, arr, zone in (
                ("ndvi", ndvi, None), ("evi", evi, None),
                ("ndwi", ndwi, None), ("mndwi", mndwi, None)):
                for tag, msk in (("all", ~np.isnan(arr) & clear),
                                 ("crop", ~np.isnan(arr) & clear & cropmask)):
                    v = arr[msk]
                    out[f"{nm}_{tag}_mean"] = float(np.nanmean(v)) if v.size else np.nan
                    out[f"{nm}_{tag}_npx"] = int(v.size)
            out["clear_frac"] = float(np.nanmean(clear)) if clear.size else np.nan
            out["quality"] = "ok" if (out["ndvi_crop_npx"] or 0) > 200 else "missing"
            rows.append(out)
            if i % 10 == 0:
                print(f"  进度 {i}/{len(s2)} | {r['date']} 云{round(r['cloud_cover'],1)}% "
                      f"耕地NDVI={out.get('ndvi_crop_mean')}")
        except Exception as e:
            rows.append({"scene_id": r["scene_id"], "date": r["date"], "year": r["year"],
                         "cloud_cover": r["cloud_cover"], "quality": f"error:{str(e)[:60]}"})
            print(f"  [ERR] {r['date']}: {str(e)[:70]}")
        time.sleep(0.3)

    df = pd.DataFrame(rows)
    df.to_csv(OUT_DIR / "s2_crop_indices_2026_event.csv", index=False, encoding="utf-8-sig")
    print(f"\n[OK] 逐景指数 {len(df)} 行 -> {OUT_DIR/'s2_crop_indices_2026_event.csv'}")
    ok = df[df.quality == "ok"]
    print(f"     有效(耕地像元>200) {len(ok)} 景")
    if len(ok):
        print(ok.groupby("year")[["ndvi_crop_mean", "ndvi_crop_npx"]].agg(
            ["count", "mean"]).round(3).to_string())
        print("\n=== 2026 事件前后（6-15~8-31）===")
        w = ok[(ok.date >= "2026-06-15") & (ok.date <= "2026-08-31")]
        print(w[["date", "cloud_cover", "clear_frac", "ndvi_crop_mean", "ndvi_crop_npx"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
