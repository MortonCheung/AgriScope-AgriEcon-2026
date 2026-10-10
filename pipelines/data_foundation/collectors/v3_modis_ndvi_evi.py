#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Decision Engine V3 · P0-1 遥感专项（MODIS MOD13Q1）
Microsoft Planetary Computer（免鉴权，STAC + /api/sas/v1/sign）上的 MOD13Q1 v061：
- 250m / 16天合成，NDVI + EVI + pixel_reliability
- 覆盖 2017-01 ~ 2026-09（补齐 Sentinel-2 之前的年份，并提供 EVI）
- 城市 bbox 窗口读，不下载整景
用法：python3 v3_modis_ndvi_evi.py [城市...] [--start 2017] [--end 2026]
"""
from __future__ import annotations
import json, sys, time, ssl, threading, urllib.request, urllib.parse
from pathlib import Path
from datetime import datetime, date, timedelta
from concurrent.futures import ThreadPoolExecutor

_sign_lock = threading.Lock()
_sign_last = [0.0]
SIGN_MIN_INTERVAL = 0.5   # 限速：约 2 req/s，避开 429
import warnings
import numpy as np
warnings.filterwarnings("ignore")
import rasterio
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "decision_engine_supplement_v3" / "remote_sensing"
OUT = ROOT / "data/raw/retained_source/city_data" / "reference" / "decision_engine_supplement_v3"
CACHE = RAW / "modis_cache"; CACHE.mkdir(parents=True, exist_ok=True)
AD = datetime.now().strftime("%Y-%m-%d")

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
SIGN = "https://planetarycomputer.microsoft.com/api/sas/v1/sign?href="
UA = {"User-Agent": "Mozilla/5.0 (AgriScope research)"}
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE

CITIES = {
    "沈阳": [122.95, 41.6, 123.6, 42.2],
    "朝阳": [119.6, 41.0, 120.9, 42.1],
    "锦州": [121.1, 41.0, 122.1, 41.8],
    "铁岭": [123.6, 42.2, 124.6, 43.1],
    "丹东": [123.6, 39.9, 124.6, 40.6],
    "大连": [121.6, 39.2, 122.5, 39.9],
}
SCALE = 0.0001
FILL = -3000


def _get(url, timeout=60, retries=3):
    last = None
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            return urllib.request.urlopen(req, timeout=timeout, context=CTX).read()
        except urllib.error.HTTPError:
            raise
        except Exception as e:  # 连接被重置/超时 → 重试
            last = e
            time.sleep(1.0 * (a + 1))
    raise last


def _post(url, payload, timeout=90):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={**UA, "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout, context=CTX).read())


def sign(href):
    """带全局限速与 429 退避重试的签名。"""
    for attempt in range(5):
        with _sign_lock:
            dt = time.time() - _sign_last[0]
            if dt < SIGN_MIN_INTERVAL:
                time.sleep(SIGN_MIN_INTERVAL - dt)
            _sign_last[0] = time.time()
        try:
            return json.loads(_get(SIGN + urllib.parse.quote(href, safe=""), timeout=45))["href"]
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(2.0 * (attempt + 1))
                continue
            raise
        except Exception:
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError("sign failed after retries")


def search_year(bbox, y):
    items = []
    payload = {"collections": ["modis-13Q1-061"], "bbox": bbox,
               "datetime": f"{y}-01-01T00:00:00Z/{y}-12-31T23:59:59Z", "limit": 100}
    for _ in range(6):
        r = _post(STAC, payload)
        items += r.get("features", [])
        nxt = next((l["href"] for l in r.get("links", []) if l.get("rel") == "next"
                    and l.get("method") == "POST"), None)
        body = next((l.get("body") for l in r.get("links", []) if l.get("rel") == "next"), None)
        if not nxt or not body:
            break
        payload = body
    return items


def doy_of(item):
    # id: MOD13Q1.A2021193.h27v04.061....  → A + YYYY + DDD
    try:
        a = item["id"].split(".")[1]  # A2021193
        return int(a[5:8])
    except Exception:
        return None


def tile_stats(item, bbox):
    """读取单 tile 的 NDVI/EVI/可靠性并返回该 tile 在 bbox 内的统计。"""
    a = item["assets"]
    st = {}
    try:
        sndvi = sign(a["250m_16_days_NDVI"]["href"])
        sevi = sign(a["250m_16_days_EVI"]["href"])
        srel = sign(a["250m_16_days_pixel_reliability"]["href"])
    except Exception:
        return None
    try:
        with rasterio.open(sndvi) as ds:
            crs = ds.crs
            b = transform_bounds("EPSG:4326", crs, *bbox)
            win = from_bounds(*b, transform=ds.transform)
            nd = ds.read(1, window=win)
        with rasterio.open(sevi) as es:
            b2 = transform_bounds("EPSG:4326", es.crs, *bbox)
            win2 = from_bounds(*b2, transform=es.transform)
            ev = es.read(1, window=win2)
        with rasterio.open(srel) as rs:
            b3 = transform_bounds("EPSG:4326", rs.crs, *bbox)
            win3 = from_bounds(*b3, transform=rs.transform)
            rl = rs.read(1, window=win3)
    except Exception:
        return None
    if nd.size == 0:
        return None
    # 对齐尺寸
    h = min(nd.shape[0], ev.shape[0], rl.shape[0]); w = min(nd.shape[1], ev.shape[1], rl.shape[1])
    if h == 0 or w == 0:
        return None
    nd, ev, rl = nd[:h, :w], ev[:h, :w], rl[:h, :w]
    valid = (nd != FILL) & (ev != FILL) & (rl >= 0) & (rl <= 1)
    n = int(valid.sum())
    if n < 50:
        return None
    R = nd[valid].astype("float32") * SCALE
    E = ev[valid].astype("float32") * SCALE
    return {"n": n, "tot": int(nd.size),
            "ndvi_mean": float(R.mean()), "ndvi_median": float(np.median(R)),
            "ndvi_p10": float(np.percentile(R, 10)), "ndvi_p90": float(np.percentile(R, 90)),
            "evi_mean": float(E.mean()), "evi_median": float(np.median(E)),
            "evi_p10": float(np.percentile(E, 10)), "evi_p90": float(np.percentile(E, 90))}


def merge_tiles(stats_list):
    """多 tile 按有效像元加权合并（分位数加权近似，另记 n）。"""
    ss = [s for s in stats_list if s]
    if not ss:
        return None
    tot_n = sum(s["n"] for s in ss)
    out = {"n": tot_n}
    for k in ["ndvi_mean", "ndvi_median", "ndvi_p10", "ndvi_p90", "evi_mean", "evi_median", "evi_p10", "evi_p90"]:
        out[k] = sum(s[k] * s["n"] for s in ss) / tot_n
    return out


def main(argv):
    cities = [a for a in argv if a in CITIES] or list(CITIES.keys())
    start = 2017
    end = 2026
    for i, a in enumerate(argv):
        if a == "--start" and i + 1 < len(argv):
            start = int(argv[i + 1])
        if a == "--end" and i + 1 < len(argv):
            end = int(argv[i + 1])

    rows = []
    for city in cities:
        bbox = CITIES[city]
        for y in range(start, end + 1):
            items = search_year(bbox, y)
            # 按 (doy) 分组
            groups = {}
            for it in items:
                d = doy_of(it)
                if d is None:
                    continue
                groups.setdefault(d, []).append(it)
            doys = sorted(groups)
            # 缓存
            todo = []
            for d in doys:
                cf = CACHE / f"{city}_{y}{d:03d}.json"
                if cf.exists():
                    rec = json.loads(cf.read_text())
                    if rec:
                        rows.append(rec)
                    continue
                todo.append((d, groups[d], cf))

            def work(t):
                d, its, cf = t
                sl = [tile_stats(it, bbox) for it in its]
                m = merge_tiles(sl)
                if not m:
                    return None  # 不缓存失败，便于重跑补漏
                day = date(y, 1, 1) + timedelta(days=d - 1)
                rec = {"city": city, "year": y, "doy": d, "composite_date": day.isoformat(),
                       "month": day.month, "ndvi_mean": round(m["ndvi_mean"], 5),
                       "ndvi_median": round(m["ndvi_median"], 5), "ndvi_p10": round(m["ndvi_p10"], 5),
                       "ndvi_p90": round(m["ndvi_p90"], 5), "evi_mean": round(m["evi_mean"], 5),
                       "evi_median": round(m["evi_median"], 5), "evi_p10": round(m["evi_p10"], 5),
                       "evi_p90": round(m["evi_p90"], 5), "n_valid_pixels": m["n"],
                       "tiles": len(its), "source_id": "SRC-MODIS-MOD13Q1-061",
                       "access_date": AD}
                cf.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
                return rec

            with ThreadPoolExecutor(max_workers=4) as ex:
                for rec in ex.map(work, todo):
                    if rec:
                        rows.append(rec)
            print(f"  {city} {y} 完成，累计 {len(rows)}", flush=True)

    import csv
    cols = ["city", "year", "doy", "composite_date", "month", "ndvi_mean", "ndvi_median",
            "ndvi_p10", "ndvi_p90", "evi_mean", "evi_median", "evi_p10", "evi_p90",
            "n_valid_pixels", "tiles", "source_id", "access_date"]
    suffix = "" if len(cities) == 6 else "_" + "_".join(cities)
    with (OUT / f"modis_ndvi_evi_city_16day{suffix}.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore"); w.writeheader()
        for r in sorted(rows, key=lambda x: (x["city"], x["year"], x["doy"])):
            w.writerow(r)
    print(f"[OK] modis_ndvi_evi_city_16day{suffix}.csv {len(rows)} 行")


if __name__ == "__main__":
    main(sys.argv[1:])
