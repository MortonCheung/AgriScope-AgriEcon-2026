#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Data Foundation v1 · P2 维度主数据
产出：
  00_governance/{GEO_MASTER,CROP_MASTER,CROP_MAPPING,MARKET_MASTER,UNIT_REGISTRY,SOURCE_REGISTRY}.csv
  02_standardized/dimensions/{dim_city,dim_district,dim_crop,dim_market,dim_source,dim_calendar}.csv
核心治理：把"规格/品级/数量/噪声"从 crop_standard 中剥离（任务书 §十三/十四）。
"""
from __future__ import annotations
import csv, glob, os, re, json
from pathlib import Path
from collections import Counter, defaultdict

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
GOV = ROOT / "data" / "metadata" / "governance"
DIM = ROOT / "data" / "processed" / "dimensions"
GOV.mkdir(parents=True, exist_ok=True); DIM.mkdir(parents=True, exist_ok=True)
AD = "2026-10-04"

# ---------------- 城市主数据（六城 + 坐标来自工程天气锚点） ----------------
CITY_MASTER = [
    ("SY", "沈阳", "210100", "辽宁省", 41.796768, 123.429092),
    ("CY", "朝阳", "211300", "辽宁省", 41.576759, 120.451180),
    ("JZ", "锦州", "210700", "辽宁省", 41.119270, 121.135742),
    ("TL", "铁岭", "211200", "辽宁省", 42.290585, 123.844276),
    ("DD", "丹东", "210600", "辽宁省", 40.124294, 124.383041),
    ("DL", "大连", "210200", "辽宁省", 38.914589, 121.618622),
]
CITY_ALIAS = {"沈阳市": "沈阳", "shenyang": "沈阳", "sy": "沈阳", "SY": "沈阳",
              "朝阳市": "朝阳", "chaoyang": "朝阳",
              "锦州市": "锦州", "jinzhou": "锦州",
              "铁岭市": "铁岭", "tieling": "铁岭",
              "丹东市": "丹东", "dandong": "丹东",
              "大连市": "大连", "dalian": "大连"}

# 县区规范化（去重：同一县区的不同写法）
COUNTY_FIX = {
    "庄河": "庄河市", "普兰店": "普兰店区", "甘井子": "甘井子区", "昌图": "昌图县",
    "双塔区区": "双塔区", "县": "铁岭县",  # 注意：'县' 属歧义，需按城市上下文修正（见下）
}

# ---------------- 作物主数据（统一走 crop_lexicon.py，唯一真源） ----------------
import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent))
from crop_lexicon import CROP_MASTER as _LEX_MASTER, classify as _lex_classify

CROP_MASTER = [(c, cat, list(al)) for c, cat, al in _LEX_MASTER]


def classify_crop(raw: str):
    """返回 (standard_name, category, flag)；field_role 单独取。"""
    canon, cat, role, iscrop, flag = _lex_classify(raw)
    return canon, cat, flag


def field_role(raw: str) -> str:
    return _lex_classify(raw)[2]


def norm_city(x: str) -> str:
    x = (x or "").strip()
    return CITY_ALIAS.get(x, x)


def glob_src(pattern: str):
    """检索来源目录（优先 data/raw/retained_source/，回退项目根）。"""
    out = []
    for base in (ROOT / "data/raw" / "retained_source", ROOT):
        out += glob.glob(str(base / pattern), recursive=True)
    return out


def read_src(rel: str):
    for base in (ROOT / "data/raw" / "retained_source", ROOT):
        p = base / rel
        if p.exists():
            return p
    return None


def main():
    # ---------- 读全部 canonical 价格/成交量，收集 crop/county/market ----------
    crop_cnt = Counter(); county_by_city = defaultdict(Counter); market_cnt = Counter()
    for f in glob_src("city_data/*/data/price_observation.csv"):
        city = norm_city(os.path.basename(os.path.dirname(os.path.dirname(f))))
        with open(f, encoding="utf-8-sig", errors="replace") as fh:
            for r in csv.DictReader(fh):
                for col in ["crop_raw", "specification", "sku_name", "crop_standard"]:
                    c = (r.get(col) or "").strip()
                    if c:
                        crop_cnt[c] += 1
                ct = (r.get("county") or "").strip()
                if ct:
                    county_by_city[city][ct] += 1
                mk = (r.get("market_name") or "").strip()
                if mk:
                    market_cnt[mk] += 1
    for f in glob_src("city_data/*/data/volume_observations.csv"):
        city = norm_city(os.path.basename(os.path.dirname(os.path.dirname(f))))
        with open(f, encoding="utf-8-sig", errors="replace") as fh:
            for r in csv.DictReader(fh):
                c = (r.get("crop") or "").strip()
                if c:
                    crop_cnt[c] += 1
                ct = (r.get("county") or "").strip()
                if ct:
                    county_by_city[city][ct] += 1
                mk = (r.get("market_name") or "").strip()
                if mk:
                    market_cnt[mk] += 1

    # ---------- GEO_MASTER / dim_city / dim_district ----------
    geo = [{"city_id": cid, "city_name": c, "adcode": ad, "province": prov, "lat": la, "lon": lo,
            "geo_level": "city", "parent": prov, "aliases": ""} for cid, c, ad, prov, la, lo in CITY_MASTER]
    districts = []
    seen_d = set()
    for cid, city, *_ in CITY_MASTER:
        for ct, n in county_by_city.get(city, {}).items():
            fix = COUNTY_FIX.get(ct, ct)
            if ct == "县":
                fix = {"铁岭": "铁岭县", "朝阳": "朝阳县"}.get(city, ct + "?")
            key = (city, fix)
            if key in seen_d:
                continue
            seen_d.add(key)
            districts.append({"district_id": f"{cid}-{fix}", "city_id": cid, "city_name": city,
                              "district_name": fix, "district_raw_examples": ct, "n_obs": n,
                              "canonical_fixed": (fix != ct), "geo_level": "district"})
    with (GOV / "GEO_MASTER.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["city_id", "city_name", "adcode", "province", "lat", "lon", "geo_level", "parent", "aliases"])
        w.writeheader(); w.writerows(geo)
    with (DIM / "dim_city.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["city_id", "city_name", "adcode", "province", "lat", "lon"])
        w.writeheader()
        for g in geo:
            w.writerow({k: g[k] for k in ["city_id", "city_name", "adcode", "province", "lat", "lon"]})
    with (DIM / "dim_district.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["district_id", "city_id", "city_name", "district_name", "district_raw_examples", "n_obs", "canonical_fixed", "geo_level"])
        w.writeheader(); w.writerows(sorted(districts, key=lambda x: (x["city_name"], x["district_name"])))

    # ---------- CROP_MASTER / CROP_MAPPING / dim_crop ----------
    with (GOV / "CROP_MASTER.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["crop_id", "standard_name", "category", "aliases", "is_crop"])
        w.writeheader()
        for i, (canon, cat, aliases) in enumerate(CROP_MASTER, 1):
            w.writerow({"crop_id": f"C{i:03d}", "standard_name": canon, "category": cat,
                        "aliases": "|".join(aliases), "is_crop": True})
    rows_map = []
    for raw, n in crop_cnt.most_common():
        canon, cat, flag = classify_crop(raw)
        role = field_role(raw)
        rows_map.append({"raw_name": raw, "standard_name": canon, "category": cat, "field_role": role,
                         "is_crop": bool(canon), "flag": flag, "n_obs": n})
    with (GOV / "CROP_MAPPING.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["raw_name", "standard_name", "category", "field_role", "is_crop", "flag", "n_obs"])
        w.writeheader(); w.writerows(rows_map)
    canon_crops = sorted({(m["standard_name"], m["category"]) for m in rows_map if m["is_crop"]})
    with (DIM / "dim_crop.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["crop_id", "standard_name", "category"])
        w.writeheader()
        for i, (c, cat) in enumerate(canon_crops, 1):
            w.writerow({"crop_id": f"C{i:03d}", "standard_name": c, "category": cat})

    # ---------- MARKET_MASTER / dim_market ----------
    mk_rows = [{"market_name": m, "n_obs": n, "city": "", "source": "canonical_price_volume"} for m, n in market_cnt.most_common()]
    # 合并 V3/V2 市场登记
    for extra in ["city_data/reference/decision_engine_supplement_v3/market_registry_v3.csv",
                  "city_data/reference/decision_engine_supplement_v2/market_registry_extended.csv"]:
        p = read_src(extra)
        if p is not None:
            with p.open(encoding="utf-8-sig") as fh:
                for r in csv.DictReader(fh):
                    mk_rows.append({"market_name": r.get("market_name", ""), "n_obs": "", "city": r.get("city", ""), "source": p.name})
    seen_m = {}
    for r in mk_rows:
        k = r["market_name"].strip()
        if k and k not in seen_m:
            seen_m[k] = r
    with (GOV / "MARKET_MASTER.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["market_id", "market_name", "city", "n_obs", "source"])
        w.writeheader()
        for i, r in enumerate(seen_m.values(), 1):
            w.writerow({"market_id": f"M{i:04d}", **r})
    with (DIM / "dim_market.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["market_id", "market_name", "city", "n_obs", "source"])
        w.writeheader()
        for i, r in enumerate(seen_m.values(), 1):
            w.writerow({"market_id": f"M{i:04d}", **r})

    # ---------- UNIT_REGISTRY ----------
    units = [
        ("price", "元/公斤", "元/kg", 1.0, "基"),
        ("price", "元/千克", "元/kg", 1.0, ""),
        ("price", "元/斤", "元/kg", 2.0, "1斤=0.5kg"),
        ("price", "元/500g", "元/kg", 2.0, ""),
        ("price", "元/吨", "元/kg", 0.001, ""),
        ("area", "亩", "亩", 1.0, "基"),
        ("area", "公顷", "亩", 15.0, "1ha=15亩"),
        ("area", "千公顷", "亩", 15000.0, ""),
        ("area", "万亩", "亩", 10000.0, ""),
        ("production", "kg", "kg", 1.0, "基"),
        ("production", "公斤", "kg", 1.0, ""),
        ("production", "吨", "kg", 1000.0, ""),
        ("production", "万吨", "kg", 1e7, ""),
        ("yield", "kg/亩", "kg/亩", 1.0, "基"),
        ("yield", "kg/公顷", "kg/亩", 1/15.0, ""),
        ("yield", "吨/公顷", "kg/亩", 1000/15.0, ""),
        ("temperature", "℃", "℃", 1.0, "基"),
        ("precip", "mm", "mm", 1.0, "基"),
        ("wind", "m/s", "m/s", 1.0, "基"),
        ("wind", "km/h", "m/s", 1/3.6, ""),
        ("ratio", "%", "%", 1.0, "基"),
        ("radiation", "MJ/m²", "MJ/m²", 1.0, "基"),
    ]
    with (GOV / "UNIT_REGISTRY.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["unit_type", "unit_raw", "unit_standard", "factor", "conversion_rule"])
        w.writeheader()
        for u in units:
            w.writerow({"unit_type": u[0], "unit_raw": u[1], "unit_standard": u[2], "factor": u[3], "conversion_rule": u[4]})

    # ---------- dim_calendar ----------
    cal = []
    import datetime
    d = datetime.date(2010, 1, 1)
    while d <= datetime.date(2026, 12, 31):
        iso = d.isocalendar()
        cal.append({"date": d.isoformat(), "year": d.year, "month": d.month, "day": d.day,
                    "iso_year": iso[0], "iso_week": iso[1], "weekday": d.isoweekday(),
                    "quarter": (d.month - 1) // 3 + 1, "season": (["冬", "冬", "春", "春", "春", "夏", "夏", "夏", "秋", "秋", "秋", "冬"][d.month - 1])})
        d += datetime.timedelta(days=1)
    with (DIM / "dim_calendar.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["date", "year", "month", "day", "iso_year", "iso_week", "weekday", "quarter", "season"])
        w.writeheader(); w.writerows(cal)

    # ---------- SOURCE_REGISTRY（合并所有既有登记 + 计数） ----------
    src = {}
    for f in [Path(x) for x in glob_src("city_data/reference/**/source_registry*.csv")
              + glob_src("archive/**/SOURCE_REGISTRY.csv") + glob_src("archive/**/source_registry.csv")
              + glob_src("city_data/*/data/*source*.csv")]:
        try:
            with f.open(encoding="utf-8-sig") as fh:
                for r in csv.DictReader(fh):
                    sid = (r.get("source_id") or "").strip()
                    if not sid or sid in src:
                        continue
                    src[sid] = {"source_id": sid, "source_name": r.get("source_name") or r.get("publisher", ""),
                                "publisher": r.get("publisher", ""), "source_level": r.get("source_level", ""),
                                "url": r.get("url") or r.get("source_url", ""), "access_date": r.get("access_date", ""),
                                "dataset": r.get("dataset_name", ""), "city": r.get("city", ""),
                                "category": r.get("data_category", ""), "origin_file": f.name}
        except Exception:
            continue
    with (GOV / "SOURCE_REGISTRY.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["source_id", "source_name", "publisher", "source_level", "url", "access_date", "dataset", "city", "category", "origin_file"])
        w.writeheader()
        for s in sorted(src.values(), key=lambda x: x["source_id"]):
            w.writerow(s)
    with (DIM / "dim_source.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["source_id", "source_name", "publisher", "source_level", "url", "access_date", "dataset", "city", "category", "origin_file"])
        w.writeheader()
        for s in sorted(src.values(), key=lambda x: x["source_id"]):
            w.writerow(s)

    # ---------- 统计 ----------
    flags = Counter(m["flag"] for m in rows_map)
    print("=== 作物映射结果 ===")
    print("  distinct raw:", len(rows_map))
    for k, v in flags.most_common():
        print(f"    {k}: {v}")
    mapped_rows = sum(m["n_obs"] for m in rows_map if m["is_crop"])
    total_rows = sum(m["n_obs"] for m in rows_map)
    print(f"  可映射行数占比: {mapped_rows}/{total_rows} = {100*mapped_rows/total_rows:.1f}%")
    print(f"  canonical crops: {len(canon_crops)} | districts: {len(districts)} | markets: {len(seen_m)} | sources: {len(src)}")
    print(f"[OK] 写入 00_governance/ 与 02_standardized/dimensions/")


if __name__ == "__main__":
    main()
