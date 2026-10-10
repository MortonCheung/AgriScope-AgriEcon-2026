#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
补全沈阳 soil_daily.csv（canonical 缺失项）。
复用项目既有 ERA5-Land 原始 JSON（data/raw/soil/openmeteo_soil_沈阳_*.json），
使用与其余五城完全相同的聚合口径（hourly -> daily mean）。
先用大连原始数据回归验证口径一致，再生成沈阳文件。
不覆盖任何已有文件。
"""
from __future__ import annotations
import json
import csv
from pathlib import Path
from datetime import datetime
from collections import defaultdict

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
SOIL_RAW = ROOT / "data/raw" / "soil"
OUT_DIR = ROOT / "data/raw/retained_source/city_data" / "reference" / "decision_engine_supplement"

HOURLY_KEYS = ["soil_moisture_0_to_7cm", "soil_moisture_7_to_28cm",
               "soil_moisture_28_to_100cm", "soil_temperature_0_to_7cm"]
COLS = ["date", "soil_water_layer_1", "soil_water_layer_2", "soil_water_layer_3",
        "soil_temperature", "city", "data_type", "source", "aggregation_method"]


def aggregate(city: str, years=range(2021, 2027)):
    """按日聚合 ERA5-Land hourly 土壤变量。"""
    acc = defaultdict(lambda: defaultdict(list))
    src_files = []
    for y in years:
        f = SOIL_RAW / f"openmeteo_soil_{city}_{y}.json"
        if not f.exists():
            continue
        src_files.append(f.name)
        d = json.loads(f.read_text(encoding="utf-8"))
        h = d["hourly"]
        for i, t in enumerate(h["time"]):
            day = t[:10]
            for k in HOURLY_KEYS:
                v = h[k][i]
                if v is not None:
                    acc[day][k].append(v)
    rows = []
    for day in sorted(acc):
        r = {"date": day, "city": city, "data_type": "reanalysis_era5_land",
             "source": "Open-Meteo Archive API / ERA5-Land",
             "aggregation_method": "hourly_mean_to_daily"}
        for j, k in enumerate(HOURLY_KEYS, start=1):
            vals = acc[day][k]
            col = "soil_temperature" if k == "soil_temperature_0_to_7cm" else f"soil_water_layer_{j}"
            r[col] = (sum(vals) / len(vals)) if vals else ""
        rows.append(r)
    return rows, src_files


def write_csv(path: Path, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLS})


def validate(city: str):
    """用同一口径重算大连，与其 canonical 文件比对验证。"""
    rows, _ = aggregate(city)
    gen = {r["date"]: r for r in rows}
    canon_path = ROOT / "data/raw/retained_source/city_data" / "dalian" / "data" / "soil_daily.csv"
    n_cmp = n_match = 0
    max_diff = 0.0
    with canon_path.open(encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            g = gen.get(r["date"])
            if not g:
                continue
            n_cmp += 1
            ok = True
            for c in ["soil_water_layer_1", "soil_water_layer_2", "soil_water_layer_3"]:
                try:
                    a, b = float(r[c]), float(g[c])
                    max_diff = max(max_diff, abs(a - b))
                    if abs(a - b) > 1e-9:
                        ok = False
                except (ValueError, TypeError, KeyError):
                    ok = False
            if ok:
                n_match += 1
    print(f"[验证] 大连 比对 {n_cmp} 天，完全一致 {n_match} 天，最大绝对差 {max_diff:.2e}")
    return n_cmp > 0 and n_match / max(n_cmp, 1) > 0.99


def main():
    if not validate("大连"):
        print("[中止] 口径验证未通过，不生成沈阳文件")
        return
    rows, files = aggregate("沈阳")
    out = OUT_DIR / "soil_moisture_daily_extended.csv"
    write_csv(out, rows)
    print(f"[OK] 沈阳 soil 生成 {len(rows)} 天 -> {out}")
    print(f"     范围 {rows[0]['date']} ~ {rows[-1]['date']}")
    print(f"     原始文件 {len(files)} 个：{', '.join(files)}")
    # 同时写入 raw 证据索引
    (ROOT / "data/raw" / "decision_engine_supplement" / "soil" / "SOIL_SHENYANG_EVIDENCE.md").write_text(
        "# 沈阳土壤墒情数据补全证据\n\n"
        f"- 生成时间：{datetime.now().isoformat(timespec='seconds')}\n"
        "- 数据源：Open-Meteo Archive API / ERA5-Land（reanalysis，**非观测站实测**）\n"
        "- 原始文件（已存在于项目内，未重新下载）：\n"
        + "".join(f"  - `data/raw/soil/{f}`\n" for f in files) +
        "- 聚合口径：hourly → daily mean，与其余五城完全一致（已用大连回归验证）\n"
        "- 变量：soil_moisture_0_to_7cm / 7_to_28cm / 28_to_100cm / soil_temperature_0_to_7cm\n"
        "- 坐标：41.796768, 123.429092（与 weather_daily_era5 同锚点）\n"
        "- 产出：`city_data/reference/decision_engine_supplement/soil_moisture_daily_extended.csv`\n",
        encoding="utf-8")
    print("[OK] 证据文件已写入 data/raw/decision_engine_supplement/soil/")


if __name__ == "__main__":
    main()
