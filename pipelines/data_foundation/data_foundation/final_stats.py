#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Data Foundation · 收口统计（供最终报告引用，只读）"""
from __future__ import annotations
import json, os
from pathlib import Path
import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
STD = ROOT / "data/processed"
INT = ROOT / "data/processed/integrated"
MR = ROOT / "data/model_ready"
Q = ROOT / "data/metadata/quality"
out = {}

# 行数/表数 + proxy
tot = 0; ntab = 0; proxy_rows = 0; proxy_tables = 0
for base in (STD, INT, MR):
    for p in sorted(base.rglob("*.parquet")):
        try:
            df = pd.read_parquet(p)
        except Exception:
            continue
        ntab += 1; tot += len(df)
        if "is_proxy" in df.columns:
            k = int(df["is_proxy"].astype(str).str.lower().isin(["true", "1", "yes"]).sum())
            if k:
                proxy_rows += k; proxy_tables += 1
out["standardized_integrated_modelready_rows"] = tot
out["tables"] = ntab
out["proxy_rows"] = proxy_rows
out["proxy_tables"] = proxy_tables

# 污染治理
try:
    r = pd.read_csv(Q / "CROP_POLLUTION_REMEDIATION.csv")
    out["remediation"] = r.set_index("key").to_dict()["n_rows"]
except Exception:
    pass

# 快照
snap = sorted((ROOT / "data/metadata/snapshots").rglob("*snapshot*"))
out["snapshot_files"] = [s.name for s in snap]

# 重复删除
try:
    m = pd.read_csv(ROOT / "data/metadata/inventory/DELETED_DUPLICATES_MANIFEST.csv")
    out["deleted_dupes"] = len(m)
    out["deleted_bytes"] = int(m["size"].sum())
except Exception:
    pass

# 迁移
try:
    ms = pd.read_csv(ROOT / "data/metadata/inventory/MIGRATION_STATUS.csv")
    out["migration"] = ms["migration_status"].value_counts().to_dict()
except Exception:
    pass

# 路径依赖
try:
    pd_ = pd.read_csv(ROOT / "data/metadata/inventory/PATH_DEPENDENCY_AUDIT.csv")
    out["path_dep_refs"] = len(pd_)
    out["path_dep_files"] = pd_["source_file"].nunique()
except Exception:
    pass

# 缺口 / readiness
try:
    g = pd.read_csv(ROOT / "data/metadata/requirements/DATA_GAP_FINAL_V2.csv")
    out["gap_status"] = g["status"].value_counts().to_dict()
except Exception:
    pass
try:
    r = pd.read_csv(ROOT / "data/metadata/requirements/READINESS_FINAL.csv")
    out["readiness"] = r.set_index("module")["readiness_pct"].to_dict()
except Exception:
    pass

# 来源
try:
    out["sources"] = len(pd.read_csv(ROOT / "data/metadata/governance/SOURCE_REGISTRY.csv"))
except Exception:
    pass
try:
    out["feature_source_map_rows"] = len(pd.read_csv(MR / "FEATURE_SOURCE_MAP.csv"))
except Exception:
    pass

# 关键表行数
KEY = ["market/price_observation", "market/price_observation_nonstandard", "production/yearbook_shenyang_district_crop",
       "production/bulletin_shenyang_district", "production/district_facility_vegetable",
       "production/facility_agriculture_city", "remote_sensing/ndvi", "climate/weather_daily"]
kk = {}
for t in KEY:
    p = STD / f"{t}.parquet"
    if p.exists():
        kk[t] = len(pd.read_parquet(p))
out["key_tables"] = kk

# NOT_AVAILABLE
na = [p.name for p in STD.rglob("*NOT_AVAILABLE.json")]
out["not_available_markers"] = na

(ROOT / "data/metadata/quality/FINAL_STATS.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False, indent=2))
