#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Decision Engine V3 · 增量 QC
- 合并各 agent 的 source_registry_*.csv → source_registry.csv
- 对 city_data/reference/decision_engine_supplement_v3/*.csv 做 source/unit/geo/time/crop/dup/missing/range 检查
- 输出 qc_summary_v3.json / QC_REPORT_v3.md / qc_flags_v3.csv
不修改任何数据文件。
"""
from __future__ import annotations
import csv, json, glob, re
from pathlib import Path
from collections import Counter, defaultdict

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "decision_engine_supplement_v3"
REF = ROOT / "data/raw/retained_source/city_data" / "reference" / "decision_engine_supplement_v3"

# 自然键（用于重复检查）
KEY_MAP = {
    "price_lnnync_veg_weekly_historical.csv": ["year", "week", "crop_standard"],
    "price_lnnync_veg_weekly_extended.csv": ["year", "week", "crop_standard"],
    "crop_spatial_structure.csv": ["city", "district", "crop_standard", "facility_type", "year_or_period", "area_mu"],
    "crop_cost_components.csv": ["year", "city", "crop_standard", "cost_basis", "source_name"],
    "market_supply_proxy.csv": ["city", "market_name", "metric", "period_value", "value"],
    "market_registry_v3.csv": ["market_name"],
    "cold_chain_capacity_v3.csv": ["city", "facility_name", "capacity_ton", "capacity_m3", "year"],
    "agri_insurance_claims_v3.csv": ["year", "scope", "city", "crop", "metric"],
    "pest_events.csv": ["date", "city", "district", "crop", "pest", "disease"],
    "irrigation_yearly_extended.csv": ["year", "city", "metric"],
    "demand_yearly_v3.csv": ["year", "city", "metric"],
    "herding_events_v3.csv": ["event_id"],
    "market_accessibility.csv": ["from_node", "to_market"],
    "remote_sensing_ndvi_city_monthly.csv": ["city", "period"],
}
CITY_CANON = {"沈阳", "朝阳", "锦州", "大连", "铁岭", "丹东"}


def merge_registry():
    out = []
    seen = set()
    header = None
    for f in sorted(RAW.rglob("source_registry_*.csv")):
        with f.open(encoding="utf-8-sig") as fh:
            rd = csv.DictReader(fh)
            if header is None:
                header = rd.fieldnames
            for r in rd:
                key = (r.get("url", ""), r.get("source_name", ""))
                if key in seen:
                    continue
                seen.add(key)
                r["_registry_file"] = f.name
                out.append(r)
    if header:
        header = header + ["_registry_file"]
        with (REF / "source_registry.csv").open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=header, extrasaction="ignore")
            w.writeheader()
            for r in out:
                w.writerow(r)
    return len(out)


def num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except Exception:
        return None


def main():
    n_reg = merge_registry()
    report = []
    summary = {"access_date": "2026-10-04", "source_registry_rows": n_reg, "files": {}}
    flags = []

    SKIP = {"source_registry.csv", "qc_flags_v3.csv", "model_value_classification.csv"}
    for f in sorted(REF.glob("*.csv")):
        if f.name in SKIP or "of2.csv" in f.name:
            continue
        with f.open(encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh))
        fn = f.name
        n = len(rows)
        cols = list(rows[0].keys()) if rows else []
        # source
        url_cols = [c for c in cols if c and "url" in c.lower()]
        src_missing = sum(1 for r in rows if not any((r.get(c) or "").strip() for c in url_cols)) if url_cols else n
        # missingness
        miss = {c: round(sum(1 for r in rows if not (r.get(c) or "").strip()) / n, 3) for c in cols} if n else {}
        # units
        unit_cols = [c for c in cols if c and ("unit" in c.lower() or c in ("cost_basis", "price_level", "geo_level", "facility_type", "metric", "source_level"))]
        units = {c: dict(Counter((r.get(c) or "∅") for r in rows).most_common(12)) for c in unit_cols}
        # duplicates
        key = KEY_MAP.get(fn)
        dups = 0
        if key and all(k in cols for k in key):
            seen = Counter(tuple((r.get(k) or "") for k in key) for r in rows)
            dups = sum(v - 1 for v in seen.values() if v > 1)
        # city canon
        bad_city = []
        if "city" in cols:
            bad_city = sorted({(r.get("city") or "") for r in rows if (r.get("city") or "") and (r.get("city") or "") not in CITY_CANON})
        # range flags (numeric columns: IQR)
        nrange = 0
        for c in cols:
            vals = [num(r.get(c)) for r in rows]
            vals = [v for v in vals if v is not None]
            if len(vals) < 8:
                continue
            vals_sorted = sorted(vals)
            q1 = vals_sorted[len(vals_sorted) // 4]
            q3 = vals_sorted[(3 * len(vals_sorted)) // 4]
            iqr = q3 - q1
            if iqr <= 0:
                continue
            lo, hi = q1 - 3 * iqr, q3 + 3 * iqr
            for r in rows:
                v = num(r.get(c))
                if v is not None and (v < lo or v > hi):
                    nrange += 1
                    flags.append({"file": fn, "column": c, "value": v, "flag": "RANGE_OUTLIER",
                                  "lo": round(lo, 2), "hi": round(hi, 2),
                                  "ident": "|".join((r.get(k) or "") for k in (key or cols[:3]))})
        summary["files"][fn] = {"rows": n, "cols": len(cols), "rows_missing_source_url": src_missing,
                                "duplicate_rows_by_key": dups, "range_outliers": nrange,
                                "non_canonical_city_values": bad_city, "key_used": key,
                                "high_missing_cols": {c: v for c, v in miss.items() if v >= 0.5}}
        report.append(f"### {fn}\n- 行数 {n}，列 {len(cols)}；缺 source_url {src_missing}；按自然键重复 {dups}；数值越界(3×IQR) {nrange}")
        if bad_city:
            report.append(f"- ⚠ 非规范城市值：{bad_city}")
        hm = {c: v for c, v in miss.items() if v >= 0.5}
        if hm:
            report.append(f"- 高缺失列(≥50%)：{hm}")
        if units:
            report.append("- 单位/口径分布：")
            for c, u in units.items():
                report.append(f"    - {c}: {u}")
        report.append("")

    (REF / "qc_summary_v3.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with (REF / "qc_flags_v3.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["file", "column", "value", "flag", "lo", "hi", "ident"])
        w.writeheader()
        for r in flags:
            w.writerow(r)
    md = ["# Decision Engine V3 · 增量 QC 报告", "", f"生成日期：2026-10-04；合并来源登记 {n_reg} 条；越界标记 {len(flags)} 条（仅标记不删除）", ""]
    md += report
    (REF / "QC_REPORT_v3.md").write_text("\n".join(md), encoding="utf-8")
    print(f"[OK] source_registry.csv {n_reg} 行; QC 完成 {len(summary['files'])} 文件; flags {len(flags)}")


if __name__ == "__main__":
    main()
