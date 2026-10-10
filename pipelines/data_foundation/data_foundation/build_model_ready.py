#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Data Foundation v1 · P5 model-ready
产出 04_model_ready/{shenyang_core,chaoyang_extended,jinzhou_extended,hri,climate,profit,recommendation}/
以及 04_model_ready/FEATURE_SOURCE_MAP.csv（每一列的血缘）。
"""
from __future__ import annotations
import csv
from pathlib import Path
import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
STD = ROOT / "data/processed"
INT = ROOT / "data/processed/integrated"
MR = ROOT / "data/model_ready"
MAP = []


def rp(base, sub, name):
    p = base / sub / f"{name}.parquet"
    return pd.read_parquet(p) if p.exists() else None


def save(df, folder, name, src, pit=True, note=""):
    d = MR / folder; d.mkdir(parents=True, exist_ok=True)
    df.to_parquet(d / f"{name}.parquet", index=False)
    for c in df.columns:
        MAP.append({"module": folder, "table": f"{name}.parquet", "column": c,
                    "source_table": src, "source_raw": "data/raw/ (仅索引)",
                    "transform": note or "直接/聚合", "pit_safe": pit})


def city_block(city, folder):
    pr = rp(STD, "market", "price_observation")
    if pr is not None:
        p = pr[pr["city"] == city].copy()
        if len(p):
            p.to_parquet(MR / folder / "market_daily.parquet", index=False)
            for c in p.columns:
                MAP.append({"module": folder, "table": "market_daily.parquet", "column": c,
                            "source_table": "02_standardized/market/price_observation", "source_raw": "data/raw/city_data canonical",
                            "transform": "城市过滤", "pit_safe": True})
    env = rp(INT, "", "city_daily_environment")
    if env is not None:
        e = env[env["city"] == city].copy()
        if len(e):
            e.to_parquet(MR / folder / "environment_daily.parquet", index=False)
            for c in e.columns:
                MAP.append({"module": folder, "table": "environment_daily.parquet", "column": c,
                            "source_table": "03_integrated/city_daily_environment",
                            "source_raw": "ERA5 / soil / Sentinel-2", "transform": "城市过滤", "pit_safe": True})
    cal = rp(STD, "production", "crop_calendar")
    if cal is not None:
        c = cal[cal["city"] == city].copy() if "city" in cal.columns else cal.copy()
        if len(c):
            c.to_parquet(MR / folder / "phenology.parquet", index=False)
            for col in c.columns:
                MAP.append({"module": folder, "table": "phenology.parquet", "column": col,
                            "source_table": "02_standardized/production/crop_calendar",
                            "source_raw": "官方农事历/物候", "transform": "城市过滤", "pit_safe": True})
    cs = rp(STD, "production", "crop_spatial_structure")
    if cs is not None and city == "沈阳":
        cs.to_parquet(MR / folder / "crop_context.parquet", index=False)
        for c in cs.columns:
            MAP.append({"module": folder, "table": "crop_context.parquet", "column": c,
                        "source_table": "02_standardized/production/crop_spatial_structure",
                        "source_raw": "政府答复/年鉴/论文", "transform": "官方结构信息", "pit_safe": True, })
    cost = rp(STD, "cost", "cost_components")
    if cost is not None and city == "沈阳":
        cost.to_parquet(MR / folder / "cost_reference.parquet", index=False)
        for c in cost.columns:
            MAP.append({"module": folder, "table": "cost_reference.parquet", "column": c,
                        "source_table": "02_standardized/cost/cost_components",
                        "source_raw": "论文/成本调查", "transform": "reference（proxy 已标）", "pit_safe": True})


def main():
    for folder in ["shenyang_core", "chaoyang_extended", "jinzhou_extended"]:
        (MR / folder).mkdir(parents=True, exist_ok=True)
    city_block("沈阳", "shenyang_core")
    city_block("朝阳", "chaoyang_extended")
    city_block("锦州", "jinzhou_extended")

    # hri：价格分位/momentum 输入
    wk = rp(INT, "", "city_crop_weekly")
    if wk is not None:
        d = MR / "hri"; d.mkdir(exist_ok=True)
        h = wk.copy()
        h["price_pct_rank"] = h.groupby(["city", "crop_standard"])["price_mean"].rank(pct=True)
        h["price_mom_4w"] = h.groupby(["city", "crop_standard"])["price_mean"].pct_change(4)
        h.to_parquet(d / "hri_inputs.parquet", index=False)
        for c in h.columns:
            MAP.append({"module": "hri", "table": "hri_inputs.parquet", "column": c,
                        "source_table": "03_integrated/city_crop_weekly", "source_raw": "canonical price",
                        "transform": "rank/pct_change", "pit_safe": True})

    # climate
    env = rp(INT, "", "city_daily_environment")
    va = rp(STD, "remote_sensing", "vegetation_anomaly")
    if env is not None or va is not None:
        d = MR / "climate"; d.mkdir(exist_ok=True)
        if env is not None:
            env.to_parquet(d / "climate_daily.parquet", index=False)
            for c in env.columns:
                MAP.append({"module": "climate", "table": "climate_daily.parquet", "column": c,
                            "source_table": "03_integrated/city_daily_environment", "source_raw": "ERA5/soil/S2",
                            "transform": "整合", "pit_safe": True})
        if va is not None:
            va.to_parquet(d / "vegetation_anomaly.parquet", index=False)
            for c in va.columns:
                MAP.append({"module": "climate", "table": "vegetation_anomaly.parquet", "column": c,
                            "source_table": "02_standardized/remote_sensing/vegetation_anomaly",
                            "source_raw": "Sentinel-2", "transform": "派生(z 异常)", "pit_safe": True})

    # profit
    d = MR / "profit"; d.mkdir(exist_ok=True)
    for sub, nm in [("cost", "cost_components"), ("cost", "crop_cost"), ("cost", "cost_proxy")]:
        df = rp(STD, sub, nm)
        if df is not None:
            df.to_parquet(d / f"{nm}.parquet", index=False)
            for c in df.columns:
                MAP.append({"module": "profit", "table": f"{nm}.parquet", "column": c,
                            "source_table": f"02_standardized/{sub}/{nm}", "source_raw": "论文/发改委调查",
                            "transform": "口径区分（见 cost_basis）", "pit_safe": True})

    # recommendation
    d = MR / "recommendation"; d.mkdir(exist_ok=True)
    sc = rp(INT, "", "city_structural_context")
    if sc is not None:
        sc.to_parquet(d / "structural_context.parquet", index=False)
        for c in sc.columns:
            MAP.append({"module": "recommendation", "table": "structural_context.parquet", "column": c,
                        "source_table": "03_integrated/city_structural_context", "source_raw": "多源",
                        "transform": "长表 _block", "pit_safe": True})
    mk = rp(STD, "market", "market_registry")
    if mk is not None:
        mk.to_parquet(d / "market_nodes.parquet", index=False)
        for c in mk.columns:
            MAP.append({"module": "recommendation", "table": "market_nodes.parquet", "column": c,
                        "source_table": "02_standardized/market/market_registry", "source_raw": "政府/调研",
                        "transform": "静态", "pit_safe": True})

    with (MR / "FEATURE_SOURCE_MAP.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["module", "table", "column", "source_table", "source_raw", "transform", "pit_safe"])
        w.writeheader(); w.writerows(MAP)
    print(f"[OK] FEATURE_SOURCE_MAP.csv {len(MAP)} 行")
    for f in sorted(MR.rglob("*.parquet")):
        print("  ", f.relative_to(MR))


if __name__ == "__main__":
    main()
