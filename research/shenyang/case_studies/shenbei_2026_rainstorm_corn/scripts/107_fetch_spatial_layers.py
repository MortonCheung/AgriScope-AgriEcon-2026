#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Package D 补充 —— 水系 / 排水设施 / 土壤

【要解决的问题（承接 Phase 4 缺口）】
- Phase 4 结论：`drainage network incomplete`，OSM 水系 67 条中 **ditch 仅 1 条**，泵站 0 条。
  → `dist_mapped_drainage` 是 M2 里最不可靠的变量（敏感性分析：去掉后正样本处易感性百分位
     从 0.547 跌到 0.415）。本轮**专项重查**排水要素。
- 土壤：Phase 4 用 SoilGrids **WCS** 返回 400 失败 → 本轮换 **REST v2.0** 接口重试。

【命名纪律】
仍然只能称 `mapped_*`，**不暗示已完整覆盖**——OSM 众源数据在中国农村地区必然不全。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "02_raw" / "spatial"
RAW.mkdir(parents=True, exist_ok=True)

# 沈北 bbox（south,west,north,east）
BBOX = "41.87854,123.27267,42.19288,123.72514"
OVERPASS = "https://overpass-api.de/api/interpreter"
UA = {"User-Agent": "shenbei-corn-research/1.0"}


def overpass(q: str, tag: str) -> dict | None:
    for a in range(3):
        try:
            r = requests.post(OVERPASS, data={"data": q}, headers=UA, timeout=180)
            if r.status_code == 200:
                return r.json()
            print(f"  [WARN] {tag} HTTP {r.status_code}")
        except Exception as e:
            print(f"  [WARN] {tag} {str(e)[:60]}")
        time.sleep(5 * (a + 1))
    return None


QUERIES = {
    # 排水专项：沟、渠、排水管、涵洞
    "drainage": f"""[out:json][timeout:180];
(
  way["waterway"~"^(ditch|drain|canal|stream|river|brook)$"]({BBOX});
  way["waterway"="drainage"]({BBOX});
  way["man_made"="drainage"]({BBOX});
  way["tunnel"="culvert"]["waterway"]({BBOX});
);
out geom tags;""",
    # 泵站 / 水利设施
    "pump": f"""[out:json][timeout:180];
(
  node["man_made"="pumping_station"]({BBOX});
  way["man_made"="pumping_station"]({BBOX});
  node["man_made"="water_well"]({BBOX});
  way["man_made"="reservoir_covered"]({BBOX});
  node["pump"]({BBOX});
  way["pump"]({BBOX});
);
out center tags;""",
    # 水体 / 水库 / 坑塘
    "waterbody": f"""[out:json][timeout:180];
(
  way["natural"="water"]({BBOX});
  way["water"="reservoir"]({BBOX});
  way["landuse"="reservoir"]({BBOX});
  way["water"="pond"]({BBOX});
  way["natural"="wetland"]({BBOX});
);
out center tags;""",
    # 水利构筑物：闸、堤、坝
    "hydraulic": f"""[out:json][timeout:180];
(
  node["waterway"="gate"]({BBOX});
  node["waterway"="weir"]({BBOX});
  way["waterway"="weir"]({BBOX});
  node["waterway"="dam"]({BBOX});
  way["waterway"="dam"]({BBOX});
  way["man_made"="dyke"]({BBOX});
  way["man_made"="embankment"]({BBOX});
);
out center tags;""",
}


def soilgrids_test() -> None:
    """重试 SoilGrids：REST v2.0（Phase 4 的 WCS 失败）"""
    url = "https://rest.isric.org/soilgrids/v2.0/properties/query"
    pts = [(123.55, 42.05)]   # 沈北代表点
    ok = 0
    for lon, lat in pts:
        try:
            p = {"lon": lon, "lat": lat, "property": "clay",
                 "depth": "0-5cm", "value": "mean"}
            r = requests.get(url, params=p, headers=UA, timeout=60)
            if r.status_code == 200:
                j = r.json()
                lyr = j.get("properties", {}).get("layers", [])
                if lyr:
                    v = lyr[0].get("depths", [{}])[0].get("values", {}).get("mean")
                    print(f"  SoilGrids REST OK: clay(0-5cm) = {v}")
                    ok += 1
                    (RAW / "soilgrids_sample.json").write_text(
                        json.dumps(j, ensure_ascii=False), encoding="utf-8")
                else:
                    print(f"  SoilGrids 返回空: {str(j)[:120]}")
            else:
                print(f"  SoilGrids HTTP {r.status_code}")
        except Exception as e:
            print(f"  SoilGrids ERR {str(e)[:80]}")
    print(f"  → SoilGrids REST {'可用' if ok else '不可用'}")


def main() -> None:
    print("=== OSM 排水/水利要素专项重查 ===")
    summary = {}
    for tag, q in QUERIES.items():
        print(f"  查询 {tag} ...")
        js = overpass(q, tag)
        if not js:
            summary[tag] = 0
            continue
        els = js.get("elements", [])
        (RAW / f"osm_{tag}.json").write_text(json.dumps(js, ensure_ascii=False), encoding="utf-8")
        summary[tag] = len(els)
        if tag == "drainage" and els:
            from collections import Counter
            c = Counter(e.get("tags", {}).get("waterway") for e in els)
            print(f"     waterway 类型分布: {dict(c)}")
            named = [e.get("tags", {}).get("name") for e in els if e.get("tags", {}).get("name")]
            print(f"     有名称要素 {len(named)} 个，例如: {named[:5]}")
        if tag == "pump" and els:
            print(f"     泵/井要素 {len(els)} 个")
    print("\n  汇总:", summary)

    print("\n=== SoilGrids 重试（REST v2.0）===")
    soilgrids_test()


if __name__ == "__main__":
    main()
