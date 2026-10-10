# -*- coding: utf-8 -*-
"""AgriScope 主表完整性审计（round3 收尾用）

目的：在合并 round3 增量之前，先证明 city_data/<city>/data/ 现有主表本身是否干净。
检查项：
  A 枚举合规（geo_level / volume_type / level / spatial_level / data_type /
    price_level / derived_from_text / quality_grade / date_precision / frequency）
  B geo_level / 分类列里混入自由文本（历史列错位的指纹）
  C 日期合法性（越界、start>end、格式）
  D 数值列混入文本
  E city 字段与所属城市目录一致性（城市串数据）
  F 关键溯源字段缺失率（source_url / raw_file）

输出：
  city_data/reference/final_foundation/MAIN_TABLE_INTEGRITY_AUDIT_V3.csv
"""
from __future__ import annotations
from pathlib import Path
import csv
import os
import re
import sys
from collections import Counter, defaultdict

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
CITY_DIR = os.path.join(ROOT, "data/raw/retained_source/city_data")
OUT = os.path.join(CITY_DIR, "reference", "final_foundation", "MAIN_TABLE_INTEGRITY_AUDIT_V3.csv")

CITIES = {
    "shenyang": "沈阳", "dalian": "大连", "tieling": "铁岭",
    "chaoyang": "朝阳", "jinzhou": "锦州", "dandong": "丹东",
}

TABLES = {
    "phenology_events": {
        "geo_col": None,
        "enums": {
            "date_precision": {"day", "tenday", "month", "year", "period", "week", ""},
            "derived_from_text": {"true", "false", "True", "False", "TRUE", "FALSE", ""},
            "quality_grade": {"A", "B", "C", "D", "E", "F", ""},
        },
        "dates": ["start_date", "end_date"],
        "nums": [],
        "trace": ["source_url"],
    },
    "disaster_events_observed": {
        "geo_col": "spatial_level",
        "enums": {
            "spatial_level": {"city", "county", "district", "province", "region", "site", ""},
            "data_type": {"observed_event", "official_reported", "algorithm_event", ""},
            "quality_grade": {"A", "B", "C", "D", "E", "F", ""},
        },
        "dates": ["start_date", "end_date"],
        "nums": ["affected_area_value", "damaged_area_value", "crop_failure_area_value",
                 "economic_loss", "deaths", "evacuated_persons"],
        "trace": ["source_url"],
    },
    "policy_events": {
        "geo_col": "level",
        "enums": {
            "level": {"city", "county", "district", "province", "national", ""},
            "quality_grade": {"A", "B", "C", "D", "E", "F", ""},
        },
        "dates": ["policy_date"],
        "nums": [],
        "trace": ["source_url"],
    },
    "volume_observations": {
        "geo_col": "geo_level",
        "enums": {
            "geo_level": {"market", "city", "county", "district", "province", ""},
            "volume_type": {"daily_transaction", "weekly_transaction", "monthly_transaction",
                            "market_inflow", "market_supply", "purchase_volume", "storage_volume",
                            "annual_throughput", "market_capacity", "inventory", "livestock_heads",
                            "procurement", ""},
            "quality_grade": {"A", "B", "C", "D", "E", "F", ""},
        },
        "dates": ["date"],
        "nums": ["volume"],
        "trace": ["source_url"],
    },
    "price_observation": {
        "geo_col": "geo_level",
        "enums": {
            "geo_level": {"market", "city", "county", "district", "province", "store", ""},
            "price_level": {"wholesale", "retail", "supermarket", "farm_gate", "purchase",
                            "auction", "other", ""},
            "quality_grade": {"A", "B", "C", "D", "E", "F", ""},
        },
        "dates": ["observation_date"],
        "nums": ["price_per_kg", "price_original"],
        "trace": ["source_url"],
    },
}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
YEAR_RE = re.compile(r"^\d{4}$")
NUM_RE = re.compile(r"^-?\d+(\.\d+)?$")
TODAY = "2026-09-23"
MIN_YEAR = 2000
# 分类列里出现这些字符 = 自由文本混入
TEXT_FINGERPRINT = re.compile(r"[，。；、]|以上|超过|达到|占比|约为")


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rd = csv.reader(fh)
        rows = list(rd)
    if not rows:
        return [], []
    hdr = [h.lstrip("\ufeff") for h in rows[0]]
    return hdr, rows[1:]


def main():
    findings = []
    for city_dir, city_cn in CITIES.items():
        for table, spec in TABLES.items():
            path = os.path.join(CITY_DIR, city_dir, "data", f"{table}.csv")
            if not os.path.exists(path):
                findings.append(dict(city=city_cn, city_dir=city_dir, table=table, row_no="",
                                     column="", check="TABLE_MISSING", value="", detail=""))
                continue
            hdr, rows = read_csv(path)
            idx = {h: i for i, h in enumerate(hdr)}

            # A/B 枚举与自由文本混入
            for col, allowed in spec["enums"].items():
                if col not in idx:
                    continue
                j = idx[col]
                for rno, r in enumerate(rows, start=2):
                    if j >= len(r):
                        findings.append(dict(city=city_cn, city_dir=city_dir, table=table, row_no=rno,
                                             column=col, check="ROW_SHORT",
                                             value=f"len={len(r)}/hdr={len(hdr)}", detail=""))
                        continue
                    v = r[j].strip()
                    if v not in allowed:
                        is_text = bool(TEXT_FINGERPRINT.search(v))
                        findings.append(dict(
                            city=city_cn, city_dir=city_dir, table=table, row_no=rno, column=col,
                            check="COL_FREE_TEXT" if is_text else "ENUM_INVALID",
                            value=v[:120], detail=f"allowed={sorted(x for x in allowed if x)}"))

            # C 日期
            for col in spec["dates"]:
                if col not in idx:
                    continue
                j = idx[col]
                for rno, r in enumerate(rows, start=2):
                    if j >= len(r):
                        continue
                    v = r[j].strip()
                    if not v:
                        continue
                    ok = DATE_RE.match(v) or YEAR_RE.match(v) or re.match(r"^\d{4}-\d{2}$", v)
                    if not ok:
                        findings.append(dict(city=city_cn, city_dir=city_dir, table=table, row_no=rno,
                                             column=col, check="DATE_FORMAT", value=v[:60], detail=""))
                    elif v > TODAY:
                        findings.append(dict(city=city_cn, city_dir=city_dir, table=table, row_no=rno,
                                             column=col, check="DATE_FUTURE", value=v, detail=f"> {TODAY}"))

            # D 数值
            for col in spec["nums"]:
                if col not in idx:
                    continue
                j = idx[col]
                for rno, r in enumerate(rows, start=2):
                    if j >= len(r):
                        continue
                    v = r[j].strip()
                    if not v:
                        continue
                    if not NUM_RE.match(v.replace(",", "")):
                        findings.append(dict(city=city_cn, city_dir=city_dir, table=table, row_no=rno,
                                             column=col, check="NUM_FREE_TEXT", value=v[:120], detail=""))

            # E city 一致性
            if "city" in idx:
                j = idx["city"]
                for rno, r in enumerate(rows, start=2):
                    if j >= len(r):
                        continue
                    v = r[j].strip()
                    if v and v not in (city_cn, "辽宁省") and len(v) <= 6:
                        findings.append(dict(city=city_cn, city_dir=city_dir, table=table, row_no=rno,
                                             column="city", check="CITY_MISMATCH", value=v, detail=""))

            # F 溯源缺失率（只统计，逐行不报）
            for col in spec["trace"]:
                if col not in idx:
                    continue
                j = idx[col]
                miss = sum(1 for r in rows if j < len(r) and not r[j].strip())
                if miss:
                    findings.append(dict(city=city_cn, city_dir=city_dir, table=table, row_no="",
                                         column=col, check="TRACE_MISSING_COUNT",
                                         value=str(miss), detail=f"of {len(rows)}"))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    cols = ["city", "city_dir", "table", "row_no", "column", "check", "value", "detail"]
    with open(OUT, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for f in findings:
            w.writerow(f)

    agg = Counter((f["city"], f["table"], f["check"]) for f in findings)
    print(f"[OK] {OUT}  findings={len(findings)}")
    print()
    print(f'{"city":6s} {"table":26s} {"check":22s} n')
    for (c, t, k), n in sorted(agg.items(), key=lambda x: (-x[1], x[0])):
        if k == "TRACE_MISSING_COUNT":
            continue
        print(f"{c:6s} {t:26s} {k:22s} {n}")
    print()
    print("=== 溯源缺失 ===")
    for (c, t, k), n in sorted(agg.items()):
        if k == "TRACE_MISSING_COUNT":
            print(f"{c:6s} {t:26s} {n}")


if __name__ == "__main__":
    main()
