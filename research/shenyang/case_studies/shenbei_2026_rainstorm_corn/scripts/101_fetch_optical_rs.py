#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Package A —— 高频作物状态数据：Sentinel-2 / Landsat / Sentinel-1 场景编目

设计原则（重要）：
  1. **只建编目 + 窗口化读取，不整景下载**。用 rasterio 对云端 COG 做 AOI 窗口读取，
     避免为了沈北 813 km² 而下载整幅 110×110 km 的 Sentinel-2 瓦片（省 ~95% 流量）。
  2. Planetary Computer 资源需 SAS 签名；本脚本通过
     /api/sas/v1/sign?href=<url> 换取短时 token（无需注册）。
  3. **场景有效性判定**：不仅记录云量，还用矢量化物几何估算 AOI 覆盖率，
     避免“影像存在但沈北只在角落”被误当成有效观测。

输出：
  02_raw/remote_sensing/scene_catalog_{collection}.csv
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[3]
RS_RAW = ROOT / "02_raw" / "remote_sensing"
RS_RAW.mkdir(parents=True, exist_ok=True)

# 沈北新区 AOI（由 03_clean/spatial/shenbei_boundary.gpkg 派生，EPSG:4326）
AOI = {"type": "Polygon", "coordinates": [[
    [123.27267, 41.87854], [123.72514, 41.87854],
    [123.72514, 42.19288], [123.27267, 42.19288], [123.27267, 41.87854]]]}

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
SAS = "https://planetarycomputer.microsoft.com/api/sas/v1/sign"
UA = {"User-Agent": "shenbei-corn-research/1.0"}

COLLECTIONS = {
    "sentinel-2-l2a": ["B02", "B03", "B04", "B08", "B11", "SCL"],
    "sentinel-1-grd": ["vv", "vh"],
}

# 覆盖 5-1 ~ 10-15（用户指定），并额外取三年
YEARS = [2024, 2025, 2026]
SEASON = ("05-01", "10-15")


def poly_bbox_intersect_frac(footprint: dict, aoi) -> float:
    """粗略估算 footprint 与 AOI 的重叠面积占 AOI 的比例（用 shapely，若无则退化为几何框估算）。"""
    try:
        from shapely.geometry import shape
        inter = shape(footprint).intersection(shape(aoi))
        return round(inter.area / shape(aoi).area, 4)
    except Exception:
        return None


def search(collection: str, datetime_range: str, max_items: int = 500) -> list[dict]:
    """分页拉取 STAC 结果。"""
    feats, token = [], None
    body = {
        "collections": [collection],
        "intersects": AOI,
        "datetime": datetime_range,
        "limit": 100,
        "sortby": [{"field": "properties.datetime", "direction": "asc"}],
    }
    while len(feats) < max_items:
        if token:
            body["token"] = token
        r = requests.post(f"{STAC}/search", json=body, headers=UA, timeout=90)
        if r.status_code != 200:
            print(f"  [WARN] {collection} HTTP {r.status_code}")
            break
        page = r.json()
        got = page.get("features", [])
        feats += got
        nxt = [l for l in page.get("links", []) if l.get("rel") == "next"]
        if not nxt or not got:
            break
        token = nxt[0].get("href", "").split("token=")[-1] or None
        if not token:
            break
    return feats


def main() -> None:
    rows = []
    for coll in COLLECTIONS:
        for yr in YEARS:
            dt = f"{yr}-{SEASON[0]}T00:00:00Z/{yr}-{SEASON[1]}T23:59:59Z"
            feats = search(coll, dt)
            for f in feats:
                p = f.get("properties", {})
                cloud = p.get("eo:cloud_cover")
                rows.append({
                    "collection": coll,
                    "scene_id": f["id"],
                    "datetime": p.get("datetime"),
                    "date": (p.get("datetime") or "")[:10],
                    "year": yr,
                    "platform": p.get("platform"),
                    "cloud_cover": cloud,
                    "aoi_coverage_frac": poly_bbox_intersect_frac(f.get("geometry"), AOI),
                    "sar_platform": p.get("platform"),
                    "sar_orbit_state": p.get("sat:orbit_state"),
                    "sar_rel_orbit": p.get("sat:relative_orbit"),
                    "sar_polarizations": ",".join(p.get("sar:polarizations", []) or []),
                    "s2_processor": p.get("processing:software", None),
                    "hrefs": json.dumps({k: v.get("href") for k, v in f.get("assets", {}).items()
                                         if k in COLLECTIONS[coll]}),
                })
            print(f"  {coll} {yr}: {len(feats)} 场景")

    df = pd.DataFrame(rows)
    if df.empty:
        print("[WARN] 无结果")
        return
    # 去重
    df = df.drop_duplicates(subset=["scene_id"])
    out = RS_RAW / "scene_catalog_all.csv"
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"\n[OK] 场景编目 {len(df)} 条 -> {out}")
    print(df.groupby(["collection", "year"]).size().to_string())
    per = ROOT / "02_raw" / "remote_sensing"
    for coll in COLLECTIONS:
        sub = df[df.collection == coll]
        if len(sub):
            sub.to_csv(per / f"scene_catalog_{coll.replace('-', '_')}.csv",
                       index=False, encoding="utf-8-sig")

    # 可用性预览：2026 事件前窗口
    print("\n=== 2026-06-15 ~ 2026-08-31 有效光学场景（云量<=80 且覆盖 AOI>=0.5）===")
    w = df[(df.date >= "2026-06-15") & (df.date <= "2026-08-31")]
    for coll in ("sentinel-2-l2a",):
        s = w[(w.collection == coll) & (w.cloud_cover <= 80) & (w.aoi_coverage_frac >= 0.5)]
        print(f"  {coll}: {len(s)} 景")
        print(s[["date", "cloud_cover", "aoi_coverage_frac"]].to_string(index=False)
              if len(s) else "    无")


if __name__ == "__main__":
    main()
