#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Data Foundation v1 · P6 质量与覆盖
产出 05_quality/{QC_SUMMARY.json,QC_REPORT.md,COVERAGE_CUBE.csv,MISSINGNESS.csv,OUTLIERS.csv,JOIN_CARDINALITY.csv,TIME_COVERAGE.csv}
只读；异常只标记不删除。
"""
from __future__ import annotations
import csv, json
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
STD = ROOT / "data/processed"
INT = ROOT / "data/processed/integrated"
MR = ROOT / "data/model_ready"
Q = ROOT / "data/metadata/quality"
Q.mkdir(parents=True, exist_ok=True)

DATE_COLS = ["date", "observation_date", "start_date", "end_date", "policy_date", "week_start", "composite_date"]
CITY_COL = "city"


def all_tables():
    # 结构收口后 INT 嵌套在 STD 之下（data/processed/integrated），需去重避免重复统计
    seen = set()
    for base in (STD, INT, MR):
        for p in sorted(base.rglob("*.parquet")):
            if p in seen:
                continue
            seen.add(p)
            yield p


def trend(name, df):
    for c in DATE_COLS:
        if c in df.columns:
            d = pd.to_datetime(df[c], errors="coerce").dropna()
            if len(d):
                return c, d.min().date().isoformat(), d.max().date().isoformat()
    if "period" in df.columns:
        s = sorted(df["period"].dropna().astype(str))
        if s:
            return "period", s[0], s[-1]
    if "year" in df.columns:
        y = pd.to_numeric(df["year"], errors="coerce").dropna()
        if len(y):
            return "year", str(int(y.min())), str(int(y.max()))
    return None, "", ""


def main():
    coverage, missing, outliers, timecov = [], [], [], []
    summary = {"tables": {}, "generated": "2026-10-04"}
    for p in all_tables():
        rel = str(p.relative_to(ROOT))
        try:
            df = pd.read_parquet(p)
        except Exception as e:
            summary["tables"][rel] = {"error": str(e)}
            continue
        n, nc = len(df), len(df.columns)
        summary["tables"][rel] = {"rows": n, "cols": nc}

        # 覆盖（按 city / 若可 crop）
        if CITY_COL in df.columns:
            grp = df.groupby(CITY_COL)
            for city, sub in grp:
                cov = {"table": rel, "city": city, "n_obs": len(sub)}
                if "crop_standard" in sub.columns and sub["crop_standard"].astype(bool).any():
                    cov["n_crop"] = sub["crop_standard"].replace("", np.nan).nunique()
                col, a, b = trend(rel, sub)
                cov["time_col"] = col or ""; cov["start"] = a; cov["end"] = b
                coverage.append(cov)
        else:
            col, a, b = trend(rel, df)
            coverage.append({"table": rel, "city": "", "n_obs": n, "time_col": col or "", "start": a, "end": b})

        # 缺失
        for c in df.columns:
            mr_ = float(df[c].isna().mean()) if n else 0.0
            if mr_ > 0:
                missing.append({"table": rel, "column": c, "missing_rate": round(mr_, 4),
                                "n_missing": int(df[c].isna().sum()), "rows": n})

        # 异常（3×IQR，仅数值列）
        for c in df.columns:
            if pd.api.types.is_bool_dtype(df[c]):
                continue
            s = pd.to_numeric(df[c], errors="coerce").astype("float64").dropna()
            if len(s) < 20:
                continue
            q1, q3 = s.quantile(.25), s.quantile(.75)
            iqr = q3 - q1
            if iqr <= 0:
                continue
            lo, hi = q1 - 3 * iqr, q3 + 3 * iqr
            k = int(((s < lo) | (s > hi)).sum())
            if k:
                outliers.append({"table": rel, "column": c, "n_outlier": k, "rows": len(s),
                                 "lo": round(float(lo), 4), "hi": round(float(hi), 4)})

        # 时间覆盖
        col, a, b = trend(rel, df)
        if col and a and b and col in ("date", "observation_date"):
            d = pd.to_datetime(df[col], errors="coerce").dropna()
            if len(d) > 1:
                expected = (d.max() - d.min()).days + 1
                actual = d.dt.normalize().nunique()
                timecov.append({"table": rel, "time_col": col, "start": a, "end": b,
                                "expected_days": expected, "actual_days": actual,
                                "coverage": round(actual / expected, 4) if expected else ""})

    def w(name, rows, cols):
        with (Q / name).open("w", newline="", encoding="utf-8-sig") as fh:
            wr = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            wr.writeheader()
            for r in rows:
                wr.writerow(r)

    w("COVERAGE_CUBE.csv", coverage, ["table", "city", "n_obs", "n_crop", "time_col", "start", "end"])
    w("MISSINGNESS.csv", missing, ["table", "column", "missing_rate", "n_missing", "rows"])
    w("OUTLIERS.csv", outliers, ["table", "column", "n_outlier", "rows", "lo", "hi"])
    w("TIME_COVERAGE.csv", timecov, ["table", "time_col", "start", "end", "expected_days", "actual_days", "coverage"])

    # JOIN 基数：整合表之间 city 键交集
    joins = []
    for a in (INT.glob("*.parquet")):
        for b in (INT.glob("*.parquet")):
            if a.name >= b.name:
                continue
            da, db = pd.read_parquet(a), pd.read_parquet(b)
            if "city" in da.columns and "city" in db.columns:
                ka, kb = set(da["city"]), set(db["city"])
                joins.append({"table_a": a.name, "table_b": b.name, "shared_city": len(ka & kb),
                              "only_a": len(ka - kb), "only_b": len(kb - ka)})
    w("JOIN_CARDINALITY.csv", joins, ["table_a", "table_b", "shared_city", "only_a", "only_b"])

    summary["n_tables"] = len(summary["tables"])
    summary["n_time_coverage_rows"] = len(timecov)
    summary["low_coverage_tables"] = [t for t in timecov if isinstance(t["coverage"], float) and t["coverage"] < 0.5]
    (Q / "QC_SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    md = ["# Data Foundation v1 · QC 报告", "",
          f"生成：2026-10-04 ｜ 表数 {summary['n_tables']} ｜ 覆盖行 {len(coverage)} ｜ 缺失记录 {len(missing)} ｜ 越界记录 {len(outliers)}", ""]
    md.append("## 需要关注的表（时间覆盖 < 50%）")
    for t in summary["low_coverage_tables"][:20]:
        md.append(f"- {t['table']}: {t['coverage']} ({t['start']}~{t['end']}, {t['actual_days']}/{t['expected_days']} 天)")
    md.append("\n## 缺失率最高的列（Top20）")
    for m in sorted(missing, key=lambda x: -x["missing_rate"])[:20]:
        md.append(f"- {m['table']}::{m['column']} = {m['missing_rate']}")
    md.append("\n## 越界最多（3×IQR，仅标记未删除）")
    for o in sorted(outliers, key=lambda x: -x["n_outlier"])[:10]:
        md.append(f"- {o['table']}::{o['column']} n={o['n_outlier']}/{o['rows']}")
    (Q / "QC_REPORT.md").write_text("\n".join(md), encoding="utf-8")
    print(f"[OK] QC 完成：表 {summary['n_tables']}，覆盖 {len(coverage)}，缺失 {len(missing)}，越界 {len(outliers)}，时间覆盖 {len(timecov)}")


if __name__ == "__main__":
    main()
