#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Decision Engine V3 · 遥感汇总与派生
把 remote_sensing/cache/*.json 合并为 NDVI 月度 CSV，并计算：
- 同月多年基线（baseline）与 ndvi_anomaly（z-score）
- 生长季(5-9月)均值/极值
输出：remote_sensing_ndvi_city_monthly.csv、remote_sensing_ndvi_derived.csv
"""
from __future__ import annotations
import csv, json, statistics
from pathlib import Path
from collections import defaultdict

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
CACHE = ROOT / "data/raw" / "decision_engine_supplement_v3" / "remote_sensing" / "cache"
OUT = ROOT / "data/raw/retained_source/city_data" / "reference" / "decision_engine_supplement_v3"


def main():
    rows = []
    for cf in sorted(CACHE.glob("*.json")):
        try:
            r = json.loads(cf.read_text())
        except Exception:
            continue
        if r:
            rows.append(r)
    rows.sort(key=lambda x: (x["city"], x["period"]))
    for r in rows:
        r["source_url"] = ("https://earth-search.aws.element84.com/v1/collections/"
                           "sentinel-2-l2a/items/" + r.get("scene_id", ""))
    cols = ["city", "year", "month", "period", "scene_id", "scene_date", "cloud_cover",
            "ndvi_mean", "ndvi_median", "ndvi_p10", "ndvi_p90", "valid_pixel_ratio",
            "n_valid_pixels", "quality_flag", "source_id", "source_url", "access_date"]
    with (OUT / "remote_sensing_ndvi_city_monthly.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore"); w.writeheader()
        for r in rows:
            w.writerow(r)

    # 同月基线（按 city×month 跨年）
    base = defaultdict(list)
    for r in rows:
        base[(r["city"], r["month"])].append(r["ndvi_mean"])
    stat = {k: (statistics.mean(v), statistics.pstdev(v)) for k, v in base.items()}

    derived = []
    for r in rows:
        m, sd = stat[(r["city"], r["month"])]
        z = (r["ndvi_mean"] - m) / sd if sd > 1e-6 else 0.0
        derived.append({"city": r["city"], "period": r["period"], "ndvi_mean": r["ndvi_mean"],
                        "baseline_same_month": round(m, 5), "ndvi_anomaly_z": round(z, 3),
                        "valid_pixel_ratio": r["valid_pixel_ratio"], "quality_flag": r["quality_flag"],
                        "source_id": r["source_id"], "source_url": r["source_url"],
                        "access_date": r["access_date"]})

    # 生长季(5-9月)城市×年
    gs = defaultdict(list)
    for r in rows:
        if 5 <= r["month"] <= 9:
            gs[(r["city"], r["year"])].append(r["ndvi_mean"])
    gsrows = []
    for (city, y), v in sorted(gs.items()):
        gsrows.append({"city": city, "year": y, "growing_season_months": len(v),
                       "ndvi_gs_mean": round(statistics.mean(v), 5),
                       "ndvi_gs_min": round(min(v), 5), "ndvi_gs_max": round(max(v), 5),
                       "source_id": "SRC-AWS-S2L2A",
                       "source_url": "https://earth-search.aws.element84.com/v1/collections/sentinel-2-l2a",
                       "access_date": rows[0]["access_date"] if rows else ""})

    with (OUT / "remote_sensing_ndvi_derived.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(derived[0].keys())); w.writeheader(); w.writerows(derived)
    with (OUT / "remote_sensing_ndvi_growing_season.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(gsrows[0].keys())); w.writeheader(); w.writerows(gsrows)

    print(f"[OK] NDVI 月度 {len(rows)} 行；派生 {len(derived)} 行；生长季 {len(gsrows)} 行")
    # 覆盖概览
    per = defaultdict(set)
    for r in rows:
        per[r["city"]].add(r["period"])
    for c in ["沈阳", "朝阳", "锦州", "铁岭", "丹东", "大连"]:
        ps = sorted(per.get(c, []))
        print(f"   {c}: {len(ps)} 月  {ps[0] if ps else '-'}~{ps[-1] if ps else '-'}")


if __name__ == "__main__":
    main()
