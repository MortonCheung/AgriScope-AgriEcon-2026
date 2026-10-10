#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Decision Engine V3 · P0-1 遥感专项
用 AWS Open Data 的 Sentinel-2 L2A COG（ESA 数据，免鉴权）计算六城 NDVI 月度时间序列。
- STAC: https://earth-search.aws.element84.com/v1  (Element 84 Earth Search)
- 资产: sentinel-cogs (AWS us-west-2, 公开 HTTPS)
- 只取城市 bbox 窗口（rasterio windowed read），不下载整景
- 云掩膜: 用 SCL 波段剔除云/云影/雪
- 输出: date(yyyy-mm) × city 的 NDVI 统计 + 有效像元比
不编造；每日/月度缺测留空并记录。
"""
from __future__ import annotations
import json, time, ssl, urllib.request, urllib.error
from pathlib import Path
from datetime import datetime, date
import warnings

import numpy as np

warnings.filterwarnings("ignore")
import rasterio
from rasterio.windows import from_bounds
from rasterio.warp import transform_bounds

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "decision_engine_supplement_v3" / "remote_sensing"
OUT = ROOT / "data/raw/retained_source/city_data" / "reference" / "decision_engine_supplement_v3"
RAW.mkdir(parents=True, exist_ok=True); OUT.mkdir(parents=True, exist_ok=True)
CACHE = RAW / "cache"; CACHE.mkdir(exist_ok=True)
AD = datetime.now().strftime("%Y-%m-%d")

STAC = "https://earth-search.aws.element84.com/v1/search"
UA = {"User-Agent": "Mozilla/5.0 (AgriScope research)"}
CTX = ssl.create_default_context(); CTX.check_hostname=False; CTX.verify_mode=ssl.CERT_NONE

CITIES = {  # 收紧到各市农业核心区，减小下载体积（仍覆盖主产县区）
    "沈阳": [122.95, 41.6, 123.6, 42.2],   # 新民/辽中/沈北
    "朝阳": [119.6, 41.0, 120.9, 42.1],    # 北票/朝阳县/建平
    "锦州": [121.1, 41.0, 122.1, 41.8],    # 黑山/北镇/凌海
    "铁岭": [123.6, 42.2, 124.6, 43.1],    # 昌图/开原/铁岭县
    "丹东": [123.6, 39.9, 124.6, 40.6],    # 东港/凤城
    "大连": [121.6, 39.2, 122.5, 39.9],    # 瓦房店/普兰店/庄河
}
# SCL 有效类别：4植被 5裸地 6水体 7未分类 11雪(排除)
SCL_VALID = {4, 5, 6, 7}


def post(url, payload, retries=3):
    for a in range(retries):
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                         headers={**UA, "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60, context=CTX) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            time.sleep(3 * (a + 1))
    return None


def search_month(bbox, y, m):
    d0 = f"{y}-{m:02d}-01T00:00:00Z"
    d1 = f"{y+1}-01-01T00:00:00Z" if m == 12 else f"{y}-{m+1:02d}-01T00:00:00Z"
    p = {"collections": ["sentinel-2-l2a"], "bbox": bbox,
         "datetime": f"{d0}/{d1}", "limit": 20}
    r = post(STAC, p)
    if not r:
        return []
    feats = r.get("features", [])
    # 只保留有 scl 的低云
    out = []
    for f in feats:
        cc = f["properties"].get("eo:cloud_cover", 100)
        a = f.get("assets", {})
        if "scl" in a and "red" in a and "nir" in a:
            out.append((cc, f))
    out.sort(key=lambda x: x[0])
    return out


def ndvi_stats(red_href, nir_href, scl_href, bbox, decim=4):
    """读取窗口并计算 NDVI 统计。
    用 COG 概览金字塔降采样 decim 倍（默认 4 → 40m），大幅减小下载量。
    SCL(20m) 需最近邻对齐到 red 的降采样网格。
    """
    with rasterio.open(red_href) as rs:
        crs = rs.crs
        b = transform_bounds("EPSG:4326", crs, *bbox)
        win = from_bounds(*b, transform=rs.transform)
        oh = max(1, int(win.height) // decim); ow = max(1, int(win.width) // decim)
        red = rs.read(1, window=win, out_shape=(oh, ow), resampling=rasterio.enums.Resampling.average)
    with rasterio.open(nir_href) as ns:
        nir = ns.read(1, window=win, out_shape=(oh, ow), resampling=rasterio.enums.Resampling.average)
    with rasterio.open(scl_href) as ss:
        bs = transform_bounds("EPSG:4326", ss.crs, *bbox)
        wins = from_bounds(*bs, transform=ss.transform)
        sh = max(1, int(wins.height) // decim); sw = max(1, int(wins.width) // decim)
        scl = ss.read(1, window=wins, out_shape=(sh, sw), resampling=rasterio.enums.Resampling.nearest)
    if red.shape != nir.shape or scl.size == 0:
        return None
    if scl.shape != red.shape:
        fy = max(1, round(red.shape[0] / scl.shape[0])); fx = max(1, round(red.shape[1] / scl.shape[1]))
        scl = np.kron(scl, np.ones((fy, fx), dtype=scl.dtype))[:red.shape[0], :red.shape[1]]
        if scl.shape != red.shape:
            ph = red.shape[0] - scl.shape[0]; pw = red.shape[1] - scl.shape[1]
            if ph < 0 or pw < 0:
                return None
            scl = np.pad(scl, ((0, ph), (0, pw)), constant_values=0)
    valid = np.isin(scl, list(SCL_VALID))
    tot = scl.size
    if valid.sum() < 30:
        return None
    R = red[valid].astype("float32"); N = nir[valid].astype("float32")
    denom = (N + R)
    ok = denom > 0
    ndvi = (N[ok] - R[ok]) / denom[ok]
    if ndvi.size < 30:
        return None
    return {
        "ndvi_mean": float(np.mean(ndvi)), "ndvi_median": float(np.median(ndvi)),
        "ndvi_p10": float(np.percentile(ndvi, 10)), "ndvi_p90": float(np.percentile(ndvi, 90)),
        "valid_pixel_ratio": float(valid.sum() / tot), "n_valid_pixels": int(valid.sum()),
    }


def parse_arg(a):
    """支持 '沈阳' 或 '沈阳:0/2'（按全序列月份切分，i/n）。"""
    if ":" in a:
        city, sl = a.split(":", 1)
        i, n = (int(x) for x in sl.split("/"))
        return city, i, n
    return a, 0, 1


def main(args=None):
    rows = []
    order = ["沈阳", "朝阳", "锦州", "铁岭", "丹东", "大连"]
    specs = [parse_arg(a) for a in args] if args else [(c, 0, 1) for c in order]
    specs = [s for s in specs if s[0] in order]
    show = [s[0] for s in specs]
    for city, slice_i, slice_n in specs:
        bbox = CITIES[city]
        months = [(y, m) for y in range(2021, 2027) for m in range(1, 13)
                  if not (y == 2026 and m > 9)]
        months = [ym for idx, ym in enumerate(months) if idx % slice_n == slice_i]
        for y, m in months:
            if True:
                cf = CACHE / f"{city}_{y}{m:02d}.json"
                if cf.exists():
                    rec = json.loads(cf.read_text())
                    if rec: rows.append(rec)
                    continue
                cands = search_month(bbox, y, m)
                rec = None
                best = None
                for cc, f in cands[:8]:  # 择优：有效像元比最高者
                    a = f["assets"]
                    try:
                        st = ndvi_stats(a["red"]["href"], a["nir"]["href"], a["scl"]["href"], bbox)
                    except Exception:
                        st = None
                    if not st:
                        continue
                    cand = {"city": city, "year": y, "month": m, "period": f"{y}-{m:02d}",
                            "scene_id": f["id"], "scene_date": f["properties"]["datetime"][:10],
                            "cloud_cover": cc, **st,
                            "source_id": "SRC-AWS-S2L2A", "access_date": AD,
                            "quality_flag": "OK" if st["valid_pixel_ratio"] >= 0.35 else "LOW_VALID_PIXELS"}
                    if best is None or st["valid_pixel_ratio"] > best["valid_pixel_ratio"]:
                        best = cand
                    if st["valid_pixel_ratio"] >= 0.6:
                        break
                rec = best
                cf.write_text(json.dumps(rec, ensure_ascii=False) if rec else "null", encoding="utf-8")
                if rec:
                    rows.append(rec)
                time.sleep(0.4)
            print(f"  {city} {y} 完成，累计 {len(rows)} 条", flush=True)

    import csv
    cols = ["city","year","month","period","scene_id","scene_date","cloud_cover",
            "ndvi_mean","ndvi_median","ndvi_p10","ndvi_p90","valid_pixel_ratio",
            "n_valid_pixels","quality_flag","source_id","access_date"]
    # 分片运行只写原始目录，避免污染正式参考目录（正式合并由 v3_rs_merge_anomaly.py 完成）
    if not args:
        outfile = OUT / "remote_sensing_ndvi_city_monthly.csv"
    else:
        suffix = "_" + "_".join([f"{c}{'_'+str(i)+'of'+str(n) if n>1 else ''}" for c, i, n in specs])
        outfile = RAW / f"ndvi_partial{suffix}.csv"
    with outfile.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore"); w.writeheader()
        for r in rows: w.writerow(r)
    print(f"[OK] {outfile.name}  {len(rows)} 行")


if __name__ == "__main__":
    import sys
    main(sys.argv[1:] or None)
