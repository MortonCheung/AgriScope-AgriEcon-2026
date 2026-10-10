#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Data Foundation v1.1 · 年鉴解析 QC
校验：粮食 ≈ 谷物+豆类+薯类；谷物 ≈ 水稻+小麦+玉米+其它谷物；跨年异常。
产出 05_quality/YEARBOOK_QC.csv（失败标 OCR_QC_FAIL，保留不删）。
"""
from __future__ import annotations
import csv
from pathlib import Path
import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
Q = ROOT / "data/metadata/quality"
df = pd.read_parquet(ROOT / "data/processed/production/yearbook_shenyang_district_crop.parquet")

rows = []
def get(y, d, crop, metric):
    s = df[(df.year == y) & (df.district == d) & (df.crop_standard == crop) & (df.metric == metric)]["value_raw"]
    return float(s.iloc[0]) if len(s) else None


for metric in ["area", "production"]:
    for (y, d), g in df[df.metric == metric].groupby(["year", "district"]):
        grain = get(y, d, "粮食", metric); cereal = get(y, d, "谷物", metric)
        bean = get(y, d, "豆类", metric); tuber = get(y, d, "薯类", metric)
        rice = get(y, d, "水稻", metric); wheat = get(y, d, "小麦", metric); corn = get(y, d, "玉米", metric)
        # 检验1：粮食 ≈ 谷物+豆类+薯类
        if grain and cereal and bean is not None and tuber is not None:
            tot = cereal + bean + tuber
            rel = abs(grain - tot) / grain if grain else 0
            rows.append({"year": y, "district": d, "metric": metric, "check": "粮食=谷物+豆类+薯类",
                         "lhs": grain, "rhs": round(tot, 1), "rel_err": round(rel, 4),
                         "qc": "PASS" if rel <= 0.05 else "OCR_QC_FAIL"})
        # 检验2：谷物 ≥ 水稻+小麦+玉米
        parts = [p for p in [rice, wheat, corn] if p is not None]
        if cereal and parts:
            s = sum(parts)
            rows.append({"year": y, "district": d, "metric": metric, "check": "谷物≥水稻+小麦+玉米",
                         "lhs": cereal, "rhs": round(s, 1), "rel_err": round((cereal - s) / cereal, 4) if cereal else "",
                         "qc": "PASS" if cereal >= s * 0.98 else "OCR_QC_FAIL"})

# 跨年异常：同一 district×crop×metric 相邻年突变 > 60%
for (d, c, m), g in df.groupby(["district", "crop_standard", "metric"]):
    g = g.sort_values("year")
    vals = list(zip(g.year, g.value_raw))
    for i in range(1, len(vals)):
        a, b = vals[i - 1][1], vals[i][1]
        if a and b and abs(b - a) / a > 0.6:
            rows.append({"year": vals[i][0], "district": d, "metric": m, "check": f"跨年突变 {c}",
                         "lhs": a, "rhs": b, "rel_err": round((b - a) / a, 3), "qc": "WARN_JUMP"})

Q.mkdir(parents=True, exist_ok=True)
with (Q / "YEARBOOK_QC.csv").open("w", newline="", encoding="utf-8-sig") as fh:
    w = csv.DictWriter(fh, fieldnames=["year", "district", "metric", "check", "lhs", "rhs", "rel_err", "qc"])
    w.writeheader(); w.writerows(rows)

from collections import Counter
c = Counter(r["qc"] for r in rows)
print(f"[OK] YEARBOOK_QC.csv {len(rows)} 行：{dict(c)}")
fails = [r for r in rows if r["qc"] == "OCR_QC_FAIL"]
for r in fails[:8]:
    print("  FAIL:", r)
