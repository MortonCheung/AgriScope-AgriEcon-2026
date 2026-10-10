#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Data Foundation v1 · P1 来源冲突检测
产出 01_inventory/SOURCE_CONFLICTS.csv
- 价格冲突：canonical（六城） vs marts/fact_price_observation，同 (city,crop,date,price_level) 比较
- 同名表跨层行数差异：同 file_name 在不同 source_layer 行数不一致
"""
from __future__ import annotations
import csv, glob, os
from pathlib import Path
from collections import defaultdict

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
OUT = ROOT / "data" / "metadata" / "inventory"
AD = "2026-10-04"


def load_price(path, is_marts=False):
    """返回 {(city,crop,date,price_level): [values]}"""
    d = defaultdict(list)
    if not os.path.exists(path):
        return d
    with open(path, encoding="utf-8-sig", errors="replace") as fh:
        for r in csv.DictReader(fh):
            v = r.get("price_per_kg")
            try:
                v = float(v)
            except Exception:
                continue
            k = (r.get("city", "").strip(), (r.get("crop_standard") or "").strip(),
                 (r.get("observation_date") or "").strip(), (r.get("price_level") or "").strip())
            d[k].append(v)
    return d


def main():
    rows = []
    marts_p = ROOT / "archive/old_marts/marts/fact_price_observation.csv"
    if not marts_p.exists():
        marts_p = ROOT / "city_data/reference/marts/fact_price_observation.csv"
    mp = load_price(marts_p, True) if marts_p.exists() else {}
    n_compare = 0
    for cf in glob.glob(str(ROOT / "data/raw/retained_source/city_data/*/data/price_observation.csv")) \
            + glob.glob(str(ROOT / "city_data/*/data/price_observation.csv")):
        city_dir = os.path.basename(os.path.dirname(os.path.dirname(cf)))
        cp = load_price(cf)
        for k, vals in cp.items():
            if k not in mp:
                continue
            a = sum(vals) / len(vals)
            b = sum(mp[k]) / len(mp[k])
            n_compare += 1
            if abs(a - b) > max(0.05 * max(a, 1e-9), 0.01):
                rows.append({"metric": "price_per_kg", "city": k[0], "crop": k[1], "period": k[2],
                             "price_level": k[3], "source_a": f"canonical:{city_dir}/data/price_observation.csv",
                             "value_a": round(a, 4), "source_b": "marts/fact_price_observation.csv",
                             "value_b": round(b, 4), "difference_type": "value_mismatch",
                             "likely_reason": "聚合/层级/单位口径差异", "recommended_source": "canonical",
                             "reason": "canonical 为分城市原始观测层", "access_date": AD})

    # 同名表跨层行数差异
    tables = {}
    with (OUT / "ALL_TABLES.csv").open(encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            tables.setdefault(os.path.basename(r["file_path"]), []).append(r)
    for nm, ts in tables.items():
        nrows = {t["rows"] for t in ts if t["rows"] and t["rows"].isdigit()}
        layers = {t["source_layer"] for t in ts}
        if len(nrows) > 1 and len(layers) > 1:
            ts_sorted = sorted(ts, key=lambda t: -(int(t["rows"]) if (t["rows"] or "").isdigit() else 0))
            rows.append({"metric": "table_row_count", "city": "", "crop": "", "period": "",
                         "price_level": "", "source_a": f"{ts_sorted[0]['source_layer']}:{ts_sorted[0]['file_path']}",
                         "value_a": ts_sorted[0]["rows"], "source_b": f"{ts_sorted[-1]['source_layer']}:{ts_sorted[-1]['file_path']}",
                         "value_b": ts_sorted[-1]["rows"], "difference_type": "row_count_mismatch",
                         "likely_reason": "不同层/不同冻结时点/不同过滤范围", "recommended_source": "",
                         "reason": "需人工核对哪一层是 canonical", "access_date": AD})

    with (OUT / "SOURCE_CONFLICTS.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["metric", "city", "crop", "period", "price_level",
                                           "source_a", "value_a", "source_b", "value_b",
                                           "difference_type", "likely_reason", "recommended_source", "reason", "access_date"])
        w.writeheader(); w.writerows(rows)
    print(f"[OK] SOURCE_CONFLICTS.csv {len(rows)} 行（价格比对覆盖 {n_compare} 个键）")


if __name__ == "__main__":
    main()
