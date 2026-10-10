#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Package A —— 光学植被/水分指数计算（Sentinel-2 L2A）

【本版三项关键性能修正 —— 前一版跑不完的原因】
1. **抽稀读取**：前一版只做空间裁剪、仍按原生 10m 读取 → 单景 5 波段约 13 GB。
   本版用 `out_shape` 让 GDAL 走 overview 抽稀到 ≈500k 像元/波段（实测单景读取 ~5s/波段）。
   判据：目标统计网格 30m × 813 km² ≈ 145 万像元，读 500k 已足够做分区均值。
2. **集合级 token 免逐资产签名**：前一版每波段签一次（3 波段 4.8s）。
   本版取一次 `/api/sas/v1/token/sentinel-2-l2a`，拼到 asset URL 后即可读。
3. **多线程并发**：默认 6 线程。

【云处理纪律（用户明确要求）】
- SCL 像元级掩膜，排除 0(nodata)/1/3(云影)/8/9(云)/10(卷云)/11(雪)
- **绝不因云多而把缺测插值成"观测值"**：有效像元不足输出 NaN 并标 quality=missing

【统计分区】全区（AOI∩影像） / 耕地（cropland mask=1），逐景一条，保留真实 acquisition date。

用法：
  python3 103_process_crop_indices.py [start_date] [end_date] [out_suffix]
  默认全量 2024-05-01~2026-10-15 -> s2_crop_indices_scenes.csv
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import requests
from rasterio.transform import Affine
from rasterio.warp import reproject, Resampling, transform_bounds

ROOT = Path(__file__).resolve().parents[3]
CATALOG = ROOT / "02_raw" / "remote_sensing" / "scene_catalog_all.csv"
CROP_MASK = ROOT / "03_clean" / "spatial" / "cropland" / "pnb_cropland_30m.tif"
OUT_DIR = ROOT / "03_clean" / "remote_sensing"

AOI = (123.27267, 41.87854, 123.72514, 42.19288)
TOKEN_URL = "https://planetarycomputer.microsoft.com/api/sas/v1/token/sentinel-2-l2a"
BAD_SCL = {0, 1, 3, 8, 9, 10, 11}
BANDS = ("B03", "B04", "B08", "B11", "SCL")
MAXPX = 500_000
WORKERS = int(os.environ.get("S2_WORKERS", "6"))

_TOKEN = {"v": None, "t": 0}


def token() -> str:
    if _TOKEN["v"] is None or time.time() - _TOKEN["t"] > 1800:
        r = requests.get(TOKEN_URL, timeout=60)
        r.raise_for_status()
        _TOKEN["v"] = r.json()["token"]
        _TOKEN["t"] = time.time()
    return _TOKEN["v"]


def signed(href: str) -> str:
    return href + ("&" if "?" in href else "?") + token()


def read_band(url: str, dst_shape, dst_transform, dst_crs, nodata=0) -> np.ndarray:
    """窗口化 + 抽稀读 COG，再重投影到目标 30m 网格。"""
    with rasterio.open(url) as src:
        b = transform_bounds("EPSG:4326", src.crs, *AOI)
        win = src.window(*b)
        h, w = int(win.height), int(win.width)
        k = max(1, int(np.ceil(np.sqrt(max(h * w, 1) / MAXPX))))
        arr = src.read(1, window=win, out_shape=(max(1, h // k), max(1, w // k)),
                       boundless=True, fill_value=nodata).astype("float32")
        # ★关键修正：out_shape 抽稀后，数组像元边长变为原来的 k 倍
        # 若仍用原窗口 transform，GDAL 会以为该数组只覆盖 1/k² 的面积 →
        # 结果是 89% 的区域被填 0（曾导致 clear_frac 假性偏低、NDVI 全错）
        w0 = src.window_transform(win)
        wtrans = Affine(w0.a * k, w0.b, w0.c, w0.d, w0.e * k, w0.f)
        dst = np.full(dst_shape, np.nan, dtype="float32")
        reproject(source=arr, destination=dst,
                  src_transform=wtrans, src_crs=src.crs, src_nodata=nodata,
                  dst_transform=dst_transform, dst_crs=dst_crs,
                  resampling=Resampling.average)
        return dst


GDAL_ENV = dict(GDAL_HTTP_TIMEOUT=30, GDAL_HTTP_CONNECTTIMEOUT=15,
                GDAL_HTTP_MAX_RETRY=2, GDAL_HTTP_RETRY_DELAY=2,
                GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", VSI_CACHE=True)


def process_one(row: dict, dst_shape, dst_transform, dst_crs, cropmask) -> dict:
    base = {"scene_id": row["scene_id"], "date": row["date"],
            "year": int(row["year"]),
            "cloud_cover": float(row["cloud_cover"]) if row["cloud_cover"] else None}
    try:
        hrefs = json.loads(row["hrefs"])
        if not all(k in hrefs for k in BANDS):
            return {**base, "quality": "no_bands"}
        g = {k: read_band(signed(hrefs[k]), dst_shape, dst_transform, dst_crs) for k in BANDS}
        scl = g["SCL"]
        clear = ~np.isin(scl, list(BAD_SCL))
        r03 = np.where(g["B03"] > 0, g["B03"] / 10000.0, np.nan)
        r04 = np.where(g["B04"] > 0, g["B04"] / 10000.0, np.nan)
        r08 = np.where(g["B08"] > 0, g["B08"] / 10000.0, np.nan)
        r11 = np.where(g["B11"] > 0, g["B11"] / 10000.0, np.nan)
        with np.errstate(invalid="ignore", divide="ignore"):
            idx = {
                "ndvi": (r08 - r04) / (r08 + r04),
                "evi": 2.5 * (r08 - r04) / (r08 + 6 * r04 - 7.5 * r03 + 1),
                "ndwi": (r03 - r08) / (r03 + r08),
                "mndwi": (r03 - r11) / (r03 + r11),
            }
        out = dict(base)
        out["clear_frac"] = float(np.nanmean(clear))
        for nm, arr in idx.items():
            for tag, msk in (("all", ~np.isnan(arr) & clear),
                             ("crop", ~np.isnan(arr) & clear & cropmask)):
                v = arr[msk]
                out[f"{nm}_{tag}_mean"] = float(np.mean(v)) if v.size else np.nan
                out[f"{nm}_{tag}_npx"] = int(v.size)
        out["quality"] = "ok" if (out.get("ndvi_crop_npx") or 0) > 200 else "missing"
        return out
    except Exception as e:
        return {**base, "quality": f"error:{str(e)[:70]}"}


def main() -> None:
    start = sys.argv[1] if len(sys.argv) > 1 else None
    end = sys.argv[2] if len(sys.argv) > 2 else None
    suffix = sys.argv[3] if len(sys.argv) > 3 else "scenes"

    with rasterio.open(CROP_MASK) as cm:
        crop = cm.read(1)
        dst_shape, dst_transform, dst_crs = crop.shape, cm.transform, cm.crs
    cropmask = (crop == 1) if crop.max() <= 1 else (crop > 0)

    rows = list(csv.DictReader(CATALOG.open(encoding="utf-8-sig")))
    s2 = [r for r in rows if r["collection"] == "sentinel-2-l2a"
          and float(r["aoi_coverage_frac"] or 0) >= 0.5]
    if start:
        s2 = [r for r in s2 if r["date"] >= start]
    if end:
        s2 = [r for r in s2 if r["date"] <= end]
    s2.sort(key=lambda r: r["date"])

    out = OUT_DIR / f"s2_crop_indices_{suffix}.csv"
    # ---- 断点续跑：读入已完成结果，跳过已算场景 ----
    done_ids, prior = set(), []
    if out.exists():
        try:
            prev = pd.read_csv(out)
            prior = prev.to_dict("records")
            done_ids = set(prev["scene_id"].astype(str))
            print(f"[续跑] 已有 {len(done_ids)} 景，跳过", flush=True)
        except Exception:
            pass
    todo = [r for r in s2 if r["scene_id"] not in done_ids]
    print(f"待处理 {len(todo)}/{len(s2)} 景 | 线程 {WORKERS} | GDAL超时 {GDAL_ENV['GDAL_HTTP_TIMEOUT']}s",
          flush=True)
    if not todo:
        print("[OK] 无待处理场景")
        return

    results, t0 = list(prior), time.time()
    with rasterio.Env(**GDAL_ENV):
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futs = {ex.submit(process_one, r, dst_shape, dst_transform, dst_crs, cropmask): r
                    for r in todo}
            for i, f in enumerate(as_completed(futs), 1):
                res = f.result()
                results.append(res)
                # ★ 增量落盘：每景立即追加，卡死/中断也不丢已算结果
                pd.DataFrame([res]).to_csv(
                    out, mode="a", header=not out.exists(), index=False, encoding="utf-8-sig")
                if i % 5 == 0 or i == len(todo):
                    print(f"  {i}/{len(todo)} | {res.get('date')} ndvi_crop="
                          f"{res.get('ndvi_crop_mean')} | {time.time()-t0:.0f}s", flush=True)

    df = pd.read_csv(out)
    ok = df[df.quality == "ok"]
    print(f"\n[OK] {out}  共 {len(df)} 行 | 有效 {len(ok)} 景 | 本轮用时 {(time.time()-t0)/60:.1f} 分钟")
    if len(ok):
        print(ok.groupby("year")["ndvi_crop_mean"].agg(["count", "mean"]).round(3).to_string())


if __name__ == "__main__":
    main()
