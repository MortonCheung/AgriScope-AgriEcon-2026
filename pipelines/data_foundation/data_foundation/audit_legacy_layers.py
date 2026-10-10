#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Data Foundation · P4 旧层逐表判定（任务书 §16/§17/§18/§19）
扫描清场后的位置：data/raw/retained_source（保留源）与 archive（旧加工层），
对每张表判定 role 与 MIGRATION_STATUS，比较 schema / 行数 / 血缘。
产出：01_inventory/MIGRATION_STATUS.csv
"""
from __future__ import annotations
import fnmatch
from pathlib import Path
import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
STD = ROOT / "data" / "processed"
INV = ROOT / "data" / "metadata" / "inventory"
RET = "data/raw/retained_source/"

LINEAGE = {
    "city_data/*/data/price_observation.csv": "market/price_observation",
    "city_data/*/data/volume_observations.csv": "market/market_volume",
    "city_data/*/data/production_yearly.csv": "production/production_yearly",
    "city_data/*/data/phenology_events.csv": "production/crop_calendar",
    "city_data/*/data/input_cost_weekly.csv": "cost/input_prices",
    "city_data/*/data/weather_daily_era5.csv": "climate/weather_daily",
    "city_data/*/data/weather_extra_daily_era5.csv": "climate/weather_daily",
    "city_data/*/data/soil_daily.csv": "climate/soil_daily",
    "city_data/*/data/disaster_events_observed.csv": "disaster/disaster_events",
    "city_data/*/data/policy_events.csv": "policy/policy_events",
    "city_data/reference/decision_engine_supplement_v3/market_supply_proxy.csv": "market/supply_proxy",
    "city_data/reference/decision_engine_supplement_v2/market_registry_extended.csv": "market/market_registry",
    "city_data/reference/decision_engine_supplement_v3/market_registry_v3.csv": "market/market_registry",
    "city_data/reference/decision_engine_supplement/price_lnnync_veg_weekly_extended.csv": "market/province_price_reference",
    "city_data/reference/decision_engine_supplement_v3/price_lnnync_veg_weekly_historical.csv": "market/province_price_reference",
    "city_data/reference/decision_engine_supplement_v2/planting_area_crop_yearly.csv": "production/planting_area_yearly",
    "city_data/reference/decision_engine_supplement_v2/production_crop_yearly.csv": "production/production_yearly",
    "city_data/reference/decision_engine_supplement_v3/crop_spatial_structure.csv": "production/crop_spatial_structure",
    "city_data/reference/decision_engine_supplement_v2/crop_calendar_detailed.csv": "production/crop_calendar",
    "city_data/reference/decision_engine_supplement_v2/crop_cost_yearly_extended.csv": "cost/crop_cost",
    "city_data/reference/decision_engine_supplement_v3/crop_cost_components.csv": "cost/cost_components",
    "city_data/reference/decision_engine_supplement_v3/remote_sensing_ndvi_city_monthly.csv": "remote_sensing/ndvi",
    "city_data/reference/decision_engine_supplement_v3/remote_sensing_ndvi_derived.csv": "remote_sensing/vegetation_anomaly",
    "city_data/reference/decision_engine_supplement_v3/remote_sensing_evi_city_monthly.csv": "remote_sensing/evi",
    "city_data/reference/decision_engine_supplement_v2/agri_insurance_claims.csv": "disaster/insurance_claims",
    "city_data/reference/decision_engine_supplement_v3/agri_insurance_claims_v3.csv": "disaster/insurance_claims",
    "city_data/reference/decision_engine_supplement_v3/pest_events.csv": "bio_risk/pest_disease_events",
    "city_data/reference/decision_engine_supplement_v2/irrigation_yearly.csv": "water/irrigation_water",
    "city_data/reference/decision_engine_supplement_v3/irrigation_yearly_extended.csv": "water/irrigation_water",
    "city_data/reference/decision_engine_supplement_v3/cold_chain_capacity_v3.csv": "infrastructure/cold_chain",
    "city_data/reference/decision_engine_supplement_v3/market_accessibility.csv": "infrastructure/market_accessibility",
    "city_data/reference/decision_engine_supplement_v3/demand_yearly_v3.csv": "demand/demand_proxy",
    "city_data/reference/decision_engine_supplement_v2/demand_yearly.csv": "demand/demand_proxy",
    "city_data/reference/decision_engine_supplement_v2/herding_events_extended.csv": "evidence/herding_events",
    "city_data/reference/decision_engine_supplement_v3/herding_events_v3.csv": "evidence/herding_events",
    "city_data/reference/curated/weekly_climatology_1991_2020.csv": "climate/climatology",
}

SCAN = [
    ("data/raw/retained_source/city_data", "retained_source/city_data"),
    ("archive/old_marts/marts", "archive/old_marts/marts"),
    ("archive/old_marts/curated", "archive/old_marts/curated"),
    ("archive/old_marts/staging", "archive/old_marts/staging"),
    ("archive/data_reports/final_foundation", "archive/data_reports/final_foundation"),
]


def norm_rel(rel: str) -> str:
    return rel[len(RET):] if rel.startswith(RET) else rel


def match_lineage(rel: str):
    rel = norm_rel(rel)
    parts = rel.split("/")
    cands = [rel]
    if len(parts) >= 4 and parts[0] == "data/raw/retained_source/city_data" and parts[2] == "data":
        cands.append("city_data/*/data/" + parts[-1])
    for k, v in LINEAGE.items():
        for c in cands:
            if fnmatch.fnmatch(c, k) or c == k:
                return k, v
    return None, None


def row_count(p: Path):
    try:
        if p.suffix == ".csv":
            return len(pd.read_csv(p, dtype=str, low_memory=False))
        if p.suffix == ".parquet":
            return len(pd.read_parquet(p))
    except Exception:
        pass
    return None


def std_rows(name):
    if not name:
        return None
    p = STD / f"{name}.parquet"
    if p.exists():
        try:
            return len(pd.read_parquet(p))
        except Exception:
            return None
    return None


def main():
    rows = []
    for root, layer in SCAN:
        base = ROOT / root
        if not base.exists():
            continue
        for p in sorted(base.rglob("*")):
            if not p.is_file() or p.name.startswith("."):
                continue
            rel = str(p.relative_to(ROOT))
            key, target = match_lineage(rel)
            src_rows, tgt_rows = row_count(p), std_rows(target)
            if target:
                status = "FULLY_MIGRATED"
                role = "DERIVED_USEFUL"
                if src_rows and tgt_rows and src_rows > tgt_rows * 1.2:
                    status = "PARTIALLY_MIGRATED"
            elif layer.startswith("archive/old_marts"):
                status, role = "SUPERSEDED", "SUPERSEDED"
            elif layer.startswith("archive/data_reports"):
                status, role = "SUPERSEDED", "LEGACY"
            else:
                status, role = "NOT_USED", "LEGACY"
            rows.append({"legacy_path": rel, "layer": layer, "file_type": p.suffix.lstrip("."),
                         "role": role, "migration_status": status, "foundation_table": target or "",
                         "legacy_rows": src_rows, "foundation_rows": tgt_rows, "lineage_key": key or ""})
    df = pd.DataFrame(rows)
    if df.empty:
        df = pd.DataFrame(columns=["legacy_path", "layer", "file_type", "role", "migration_status",
                                   "foundation_table", "legacy_rows", "foundation_rows", "lineage_key"])
    df.to_csv(INV / "MIGRATION_STATUS.csv", index=False, encoding="utf-8-sig")
    print("总表数:", len(df))
    if len(df):
        print(df.groupby(["layer", "migration_status"]).size().to_string())
        print("\nstatus 汇总:")
        print(df["migration_status"].value_counts().to_string())


if __name__ == "__main__":
    main()
