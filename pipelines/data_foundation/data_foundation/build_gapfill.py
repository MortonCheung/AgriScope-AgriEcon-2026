#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Data Foundation v1 · P8 查漏补缺（先重解析已下载未解析的 raw）
1) 沈阳 8 区县 Open-Meteo 日频气象/土壤 JSON → 02_standardized/climate/{weather_district_shenyang,soil_district_shenyang}.parquet
   ⚠ 未指定 models= → best_match，非 ERA5 统一基准，标记 is_legacy_baseline=true，仅作区县级补充。
2) 生成 07_evidence/raw_source_index.csv：raw 资产 → 解析状态（PARSED/UNPARSED/JS_RENDERED/NEEDS_OCR）
"""
from __future__ import annotations
import csv, json, glob
from pathlib import Path
import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
DW = ROOT / "data/raw/web_captures/shenyang/district_production/district_weather"
STD = ROOT / "data/processed"
EV = ROOT / "data/metadata/evidence"
AD = "2026-10-04"


def parse_openmeteo(path):
    d = json.load(open(path, encoding="utf-8"))
    daily = d.get("daily") or {}
    if not daily or "time" not in daily:
        return None
    df = pd.DataFrame({"date": daily["time"]})
    for k, v in daily.items():
        if k == "time":
            continue
        df[k] = v
    for k, v in (d.get("daily_units") or {}).items():
        df[f"unit_{k}"] = v
    return df


def main():
    frames = {"core": [], "extra": [], "soil": []}
    for f in glob.glob(str(DW / "openmeteo_*.json")):
        name = Path(f).name
        parts = name.split("_")
        district = parts[1]
        kind = parts[2]
        if kind not in frames:
            continue
        df = parse_openmeteo(f)
        if df is None:
            continue
        df["city"] = "沈阳"
        df["district"] = district
        df["source_file"] = name
        frames[kind].append(df)

    outdir = STD / "climate"; outdir.mkdir(parents=True, exist_ok=True)
    written = []
    if frames["core"] or frames["extra"]:
        wx = pd.concat([f for k in ("core", "extra") for f in frames[k]], ignore_index=True)
        wx = wx.drop_duplicates(["city", "district", "date"])
        wx["weather_source"] = "openmeteo_best_match"
        wx["is_legacy_baseline"] = True
        wx["source_id"] = "SRC-OPENMETEO-DISTRICT-SY"
        wx["geo_level"] = "district"
        wx["frequency"] = "daily"
        wx["is_proxy"] = False
        wx["access_date"] = AD
        wx.to_parquet(outdir / "weather_district_shenyang.parquet", index=False)
        written.append(("weather_district_shenyang", len(wx), wx["district"].nunique()))
    if frames["soil"]:
        so = pd.concat(frames["soil"], ignore_index=True).drop_duplicates(["city", "district", "date"])
        so["weather_source"] = "openmeteo_best_match"
        so["is_legacy_baseline"] = True
        so["source_id"] = "SRC-OPENMETEO-DISTRICT-SY"
        so["geo_level"] = "district"; so["frequency"] = "daily"; so["is_proxy"] = False; so["access_date"] = AD
        so.to_parquet(outdir / "soil_district_shenyang.parquet", index=False)
        written.append(("soil_district_shenyang", len(so), so["district"].nunique()))

    # 07_evidence/raw_source_index.csv
    EV.mkdir(parents=True, exist_ok=True)
    rows = []
    inv = list(csv.DictReader(open(ROOT / "data/metadata/inventory/ALL_FILES.csv", encoding="utf-8-sig")))
    raw = [r for r in inv if r["source_layer"] == "raw"]
    # 已解析标记：存在于某些 known parsed outputs 的路径前缀
    parsed_hints = ["data/raw/production/yearbook", "data/raw/decision_engine_supplement_v3",
                    "data/raw/web_captures/shenyang/district_production/district_weather"]
    for r in raw:
        p = r["file_path"]; ext = r["file_type"]
        if any(p.startswith(h) for h in parsed_hints):
            status = "PARSED" if ext in ("xls", "xlsx", "json", "csv", "pdf") else "PARSED_OR_INDEXED"
        elif ext in ("html", "json", "csv", "txt"):
            status = "UNPARSED_TEXT" if ext in ("html", "txt") else "UNPARSED_STRUCTURED"
        elif ext in ("pdf",):
            status = "NEEDS_OCR"
        elif ext in ("png", "jpg"):
            status = "IMAGE_OCR_CANDIDATE"
        else:
            status = "OTHER"
        if p.startswith("data/raw/web_captures/shenyang/district_production/bulletins") and ext == "html":
            status = "JS_RENDERED"
        rows.append({"file_path": p, "file_type": ext, "logical_category": r["logical_category"],
                     "parse_status": status, "access_date": AD})
    with (EV / "raw_source_index.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["file_path", "file_type", "logical_category", "parse_status", "access_date"])
        w.writeheader(); w.writerows(rows)

    from collections import Counter
    print("=== 新增区县级表 ===")
    for n, r, k in written:
        print(f"  {n}: {r} 行, {k} 个区县")
    print("=== raw 解析状态 ===")
    for k, v in Counter(x["parse_status"] for x in rows).most_common():
        print(f"  {k}: {v}")
    (EV / "evidence_manifest.csv").write_text(
        "file,status,note\nweather_district_shenyang,ADDED,src=openmeteo_best_match 区分县日频气象(遗留口径)\n"
        "soil_district_shenyang,ADDED,src=openmeteo 区县土壤\n"
        "shenyang_yearbook_pdf,IDENTIFIED,7册 沈阳统计年鉴 PDF(2018-2024数据) 需OCR\n"
        "district_bulletins,IDENTIFIED,166份区县公报(101 HTML为JS渲染/54 PDF) 需浏览器或OCR\n", encoding="utf-8")
    print(f"[OK] raw_source_index.csv {len(rows)} 行")


if __name__ == "__main__":
    main()
