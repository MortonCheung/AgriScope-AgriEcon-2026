#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Decision Engine V3 · P0-1 遥感（EVI 补充）
复用 Sentinel-2 NDVI 已选中的城市×月 scene_id（保证与 NDVI 同场景、同口径），
从 Earth Search 取 blue/red/nir/scl 窗口，计算 EVI 统计，输出 EVI 月度序列。
EVI = 2.5*(NIR-RED)/(NIR+6*RED-7.5*BLUE+1)，反射率=DN/10000，SCL∈{4,5,6,7} 有效。
用法：python3 v3_s2_evi_backfill.py
"""
from __future__ import annotations
import json, time, ssl, threading, urllib.request, urllib.parse
from pathlib import Path
from datetime import datetime
import warnings
import numpy as np
warnings.filterwarnings("ignore")
import rasterio
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RS = ROOT / "data/raw" / "decision_engine_supplement_v3" / "remote_sensing"
N_CACHE = RS / "cache"                    # NDVI 缓存（含 scene_id）
E_CACHE = RS / "evi_cache"; E_CACHE.mkdir(exist_ok=True)
OUT = ROOT / "data/raw/retained_source/city_data" / "reference" / "decision_engine_supplement_v3"
AD = datetime.now().strftime("%Y-%m-%d")
UA = {"User-Agent": "Mozilla/5.0 (AgriScope research)"}
CTX = ssl.create_default_context(); CTX.check_hostname=False; CTX.verify_mode=ssl.CERT_NONE
SCL_VALID = {4, 5, 6, 7}
CITIES = {
    "沈阳": [122.95, 41.6, 123.6, 42.2], "朝阳": [119.6, 41.0, 120.9, 42.1],
    "锦州": [121.1, 41.0, 122.1, 41.8], "铁岭": [123.6, 42.2, 124.6, 43.1],
    "丹东": [123.6, 39.9, 124.6, 40.6], "大连": [121.6, 39.2, 122.5, 39.9],
}


_lock = threading.Lock()
_last = [0.0]
MIN_INTERVAL = 0.2


def item_assets(sid, retries=6):
    u = f"https://earth-search.aws.element84.com/v1/collections/sentinel-2-l2a/items/{urllib.parse.quote(sid)}"
    for a in range(retries):
        with _lock:
            dt = time.time() - _last[0]
            if dt < MIN_INTERVAL:
                time.sleep(MIN_INTERVAL - dt)
            _last[0] = time.time()
        try:
            req = urllib.request.Request(u, headers=UA)
            return json.loads(urllib.request.urlopen(req, timeout=60, context=CTX).read())["assets"]
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(3.0 * (a + 1)); continue
            time.sleep(1.5 * (a + 1))
        except Exception:
            time.sleep(1.5 * (a + 1))
    return None


def read_ds(href, bbox, decim, resampling):
    with rasterio.open(href) as ds:
        b = transform_bounds("EPSG:4326", ds.crs, *bbox)
        win = from_bounds(*b, transform=ds.transform)
        oh = max(1, int(win.height) // decim); ow = max(1, int(win.width) // decim)
        return ds.read(1, window=win, out_shape=(oh, ow), resampling=resampling)


def evi_stats(a, bbox, decim=4):
    blue = read_ds(a["blue"]["href"], bbox, decim, rasterio.enums.Resampling.average)
    red = read_ds(a["red"]["href"], bbox, decim, rasterio.enums.Resampling.average)
    nir = read_ds(a["nir"]["href"], bbox, decim, rasterio.enums.Resampling.average)
    scl = read_ds(a["scl"]["href"], bbox, decim, rasterio.enums.Resampling.nearest)
    h = min(blue.shape[0], red.shape[0], nir.shape[0], scl.shape[0])
    w = min(blue.shape[1], red.shape[1], nir.shape[1], scl.shape[1])
    if h == 0 or w == 0:
        return None
    blue, red, nir, scl = blue[:h, :w], red[:h, :w], nir[:h, :w], scl[:h, :w]
    if scl.shape != red.shape:
        fy = max(1, round(red.shape[0] / scl.shape[0])); fx = max(1, round(red.shape[1] / scl.shape[1]))
        scl = np.kron(scl, np.ones((fy, fx), dtype=scl.dtype))[:red.shape[0], :red.shape[1]]
        if scl.shape != red.shape:
            return None
    valid = np.isin(scl, list(SCL_VALID))
    if valid.sum() < 30:
        return None
    B = blue[valid].astype("float32") / 10000.0
    R = red[valid].astype("float32") / 10000.0
    N = nir[valid].astype("float32") / 10000.0
    den = N + 6.0 * R - 7.5 * B + 1.0
    ok = np.abs(den) > 1e-6
    evi = 2.5 * (N[ok] - R[ok]) / den[ok]
    evi = evi[(evi > -1.5) & (evi < 1.5)]
    if evi.size < 30:
        return None
    return {"evi_mean": float(evi.mean()), "evi_median": float(np.median(evi)),
            "evi_p10": float(np.percentile(evi, 10)), "evi_p90": float(np.percentile(evi, 90)),
            "valid_pixel_ratio": float(valid.sum() / scl.size), "n_valid_pixels": int(valid.sum())}


def one(rec):
    """处理单个月份：取 item 资产 → 计算 EVI → 写缓存。返回记录或 None。带一次整体重试。"""
    city, period = rec["city"], rec["period"]
    out = E_CACHE / f"{city}_{period}.json"
    if out.exists():
        try:
            r = json.loads(out.read_text())
            if r:
                return r
        except Exception:
            pass
    for attempt in range(2):
        a = item_assets(rec["scene_id"])
        if not a or "blue" not in a:
            continue
        try:
            st = evi_stats(a, CITIES[city])
        except Exception:
            st = None
        if not st:
            continue
        r = {"city": city, "year": rec["year"], "month": rec["month"], "period": period,
             "scene_id": rec["scene_id"], "scene_date": rec.get("scene_date"),
             **st, "source_id": "SRC-AWS-S2L2A-EVI", "access_date": AD}
        out.write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
        return r
    return None


def main():
    import sys
    from concurrent.futures import ThreadPoolExecutor
    want = [a for a in sys.argv[1:] if a in CITIES]
    recs = []
    for cf in sorted(N_CACHE.glob("*.json")):
        try:
            rec = json.loads(cf.read_text())
        except Exception:
            continue
        if not rec or rec.get("city") not in CITIES:
            continue
        if want and rec["city"] not in want:
            continue
        recs.append(rec)
    with ThreadPoolExecutor(max_workers=2) as ex:
        got = 0
        for i, r in enumerate(ex.map(one, recs)):
            if r:
                got += 1
            if i % 40 == 0:
                print(f"  ...{i}/{len(recs)} 累计 {got}", flush=True)

    # 输出始终汇总全部已缓存的 EVI（含此前其它城市），保证 CSV 累积完整
    rows = []
    for cf in sorted(E_CACHE.glob("*.json")):
        try:
            r = json.loads(cf.read_text())
            if r:
                rows.append(r)
        except Exception:
            pass

    import csv
    for r in rows:
        r["source_url"] = ("https://earth-search.aws.element84.com/v1/collections/"
                           "sentinel-2-l2a/items/" + r.get("scene_id", ""))
    cols = ["city", "year", "month", "period", "scene_id", "scene_date", "evi_mean", "evi_median",
            "evi_p10", "evi_p90", "valid_pixel_ratio", "n_valid_pixels", "source_id",
            "source_url", "access_date"]
    with (OUT / "remote_sensing_evi_city_monthly.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore"); w.writeheader()
        for r in sorted(rows, key=lambda x: (x["city"], x["period"])):
            w.writerow(r)
    print(f"[OK] remote_sensing_evi_city_monthly.csv {len(rows)} 行")


if __name__ == "__main__":
    main()
