#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Data Foundation v1 · P3 标准化
把 canonical / supplement V2 / V3 / curated / marts 整理为统一标准表（parquet），写入 02_standardized/。
规则：保留 value_raw/unit_raw；加 source_id / geo_level / is_proxy / is_derived / frequency；
作物统一走 CROP_MAPPING（规格/品级/噪声被剥离，标记 crop_flag）。
不编造；缺失的主题写 _NOT_AVAILABLE.json。
"""
from __future__ import annotations
import csv, glob, json, os
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
STD = ROOT / "data" / "processed"
AD = "2026-10-04"
CITIES = {"shenyang": "沈阳", "chaoyang": "朝阳", "jinzhou": "锦州",
          "tieling": "铁岭", "dandong": "丹东", "dalian": "大连"}
LOG = []


def rd(p, **kw):
    """读取来源；优先 data/raw/retained_source/<p>，回退旧 <p>（§51 保留源）。"""
    rel = str(p)
    for base in (ROOT / "data/raw" / "retained_source", ROOT):
        pp = base / rel if not rel.startswith("/") else Path(rel)
        if pp.exists():
            try:
                return pd.read_csv(pp, dtype=str, low_memory=False, encoding="utf-8-sig", **kw)
            except Exception as e:
                LOG.append(f"READ_FAIL {pp}: {e}")
                return None
    return None


def wr(df, sub, name, note=""):
    d = STD / sub
    d.mkdir(parents=True, exist_ok=True)
    out = d / f"{name}.parquet"
    df.to_parquet(out, index=False)
    LOG.append(f"WRITE {out.relative_to(ROOT)}  rows={len(df)} cols={len(df.columns)}  {note}")
    return out


def na(sub, name, reason):
    d = STD / sub
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}_NOT_AVAILABLE.json").write_text(
        json.dumps({"table": name, "status": "NOT_AVAILABLE", "reason": reason,
                    "searched": "data/raw/ + city_data/ + supplements", "access_date": AD},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    LOG.append(f"[NA] {sub}/{name}: {reason}")


def load_crop_map():
    m = {}
    p = ROOT / "data/metadata/governance/CROP_MAPPING.csv"
    with p.open(encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            m[r["raw_name"]] = (r["standard_name"], r["flag"])
    return m


CROP_MAP = load_crop_map()


def _lex():
    import sys as _s
    _s.path.insert(0, str(Path(__file__).parent))
    from crop_lexicon import classify
    return classify


_LEX_CLASSIFY = _lex()

PRICE_COLS = ["crop_raw", "crop_standard", "sku_name", "specification"]


def standardize_price(df: pd.DataFrame) -> pd.DataFrame:
    """把价格行拆成 crop_standard / variety / specification_norm / grade / package / processing_state。
    规则：crop_standard = 4 列中第一个 field_role==crop 的 canonical；
         其余列按 field_role 归位；原值一律保留（crop_standard_original 等）。"""
    df = df.copy()
    df["crop_standard_original"] = df.get("crop_standard", pd.Series("", index=df.index))
    out = {k: [] for k in ["crop_standard", "variety", "specification_norm", "grade", "package",
                           "processing_state", "crop_recovery_flag"]}
    priority = ["crop_raw", "sku_name", "specification", "crop_standard_original"]
    for _, r in df.iterrows():
        cls = {c: _LEX_CLASSIFY(str(r.get(c) or "")) for c in priority if c in df.columns}
        canon, canon_col, role_of = "", "", {}
        for c in priority:
            if c not in cls:
                continue
            role_of[c] = cls[c][2]
            if not canon and cls[c][2] == "crop":
                canon, canon_col = cls[c][0], c
        variety = ""
        if canon:
            cr = str(r.get("crop_raw") or "").strip()
            sk = str(r.get("sku_name") or "").strip()
            nonname = {"grade", "specification", "package", "seedling", "ornamental",
                       "processed_food", "livestock_part", "agric_input", "non_crop", "empty"}
            if cr and cr != canon and cls.get("crop_raw", ("", "", "empty", False, ""))[2] not in nonname:
                variety = cr
            elif sk and sk != canon and cls.get("sku_name", ("", "", "empty", False, ""))[2] not in nonname:
                variety = sk
        spec_v = grade_v = pack_v = proc_v = ""
        for c in priority:
            if c not in cls:
                continue
            role = cls[c][2]
            val = str(r.get(c) or "").strip()
            if role == "specification" and not spec_v:
                spec_v = val
            elif role == "grade" and not grade_v:
                grade_v = val
            elif role == "package" and not pack_v:
                pack_v = val
            elif role in ("processed_food",) and not proc_v:
                proc_v = val
        # 原 crop_standard 列若为规格/品级（朝阳类型列错位）→ 归位并标 RECOVERABLE
        orig = str(r.get("crop_standard_original") or "").strip()
        if orig and canon and orig != canon and not spec_v and not grade_v:
            orole = _LEX_CLASSIFY(orig)[2]
            if orole == "grade":
                grade_v = orig
            elif orole in ("specification", "package"):
                spec_v = orig
        flag = "OK"
        if not canon:
            nons = [cls[c][2] for c in priority if c in cls]
            if any(x in ("seedling", "ornamental", "processed_food", "livestock_part", "agric_input", "non_crop") for x in nons):
                flag = "TRUE_NON_CROP"
            elif any(x in ("grade", "specification", "package", "spec") for x in nons):
                flag = "TRUE_NON_CROP"
            else:
                flag = "UNKNOWN"
        elif orig and orig != canon and _LEX_CLASSIFY(orig)[2] != "crop":
            flag = "RECOVERABLE"
        out["crop_standard"].append(canon)
        out["variety"].append(variety)
        out["specification_norm"].append(spec_v)
        out["grade"].append(grade_v)
        out["package"].append(pack_v)
        out["processing_state"].append(proc_v)
        out["crop_recovery_flag"].append(flag)
    for k, v in out.items():
        df[k] = v
    df["is_crop"] = df["crop_standard"].astype(bool)
    return df


def apply_crop(df, col):
    df = df.copy()
    df["crop_raw"] = df[col].fillna("").astype(str)
    df["crop_standard"] = df["crop_raw"].map(lambda x: CROP_MAP.get(x, ("", "unmapped"))[0])
    df["crop_flag"] = df["crop_raw"].map(lambda x: CROP_MAP.get(x, ("", "unmapped"))[1])
    df["is_crop"] = df["crop_standard"].astype(bool)
    return df


def tag(df, source_id, geo_level, frequency, is_proxy=False, is_derived=False):
    df = df.copy()
    df["source_id"] = source_id
    df["geo_level"] = geo_level
    df["frequency"] = frequency
    df["is_proxy"] = is_proxy
    df["is_derived"] = is_derived
    df["access_date"] = AD
    return df


def concat(frames):
    frames = [f for f in frames if f is not None]
    if not frames:
        return None
    return pd.concat(frames, ignore_index=True)


# ============================== market ==============================
def build_market():
    # 1) price_observation
    fr = []
    for d, city in CITIES.items():
        p = f"city_data/{d}/data/price_observation.csv"
        df = rd(p)
        if df is None:
            LOG.append(f"MISS price_observation {city}")
            continue
        df["city"] = city
        fr.append(df)
    df = concat(fr)
    if df is not None:
        df = standardize_price(df)
        df = tag(df, "SRC-CANONICAL-PRICE", "multi", "daily")
        df["price_level_canonical"] = df.get("price_level", pd.Series("", index=df.index)).fillna("").astype(str).str.strip()
        crop_mask = df["crop_standard"].astype(bool)
        wr(df[crop_mask].copy(), "market", "price_observation", "作物价格（crop_standard 污染已恢复）")
        wr(df[~crop_mask].copy(), "market", "price_observation_nonstandard", "TRUE_NON_CROP / UNKNOWN（保留审计，不进模型）")
        # 污染治理统计（回答 §12/§62-5）
        rec = df["crop_recovery_flag"].value_counts()
        lvl = df["price_level_canonical"].value_counts()
        rows = []
        for k, v in rec.items():
            rows.append({"dimension": "crop_recovery_flag", "key": k, "n_rows": int(v),
                         "pct": round(100 * v / len(df), 3)})
        for k, v in lvl.items():
            rows.append({"dimension": "price_level", "key": k, "n_rows": int(v),
                         "pct": round(100 * v / len(df), 3)})
        pd.DataFrame(rows).to_csv(ROOT / "data/metadata/quality/CROP_POLLUTION_REMEDIATION.csv",
                                  index=False, encoding="utf-8-sig")
        LOG.append(f"[REMEDIATION] 价格 {len(df)} 行 → 作物 {int(crop_mask.sum())} / 非作物 {int((~crop_mask).sum())}；"
                   f"RECOVERABLE {int(rec.get('RECOVERABLE', 0))}")

    # 2) market_volume
    fr = []
    for d, city in CITIES.items():
        df = rd(f"city_data/{d}/data/volume_observations.csv")
        if df is None:
            continue
        df["city"] = city
        fr.append(df)
    df = concat(fr)
    if df is not None:
        df = apply_crop(df, "crop")
        df = tag(df, "SRC-CANONICAL-VOLUME", "multi", "daily")
        wr(df, "market", "market_volume")

    # 3) supply_proxy
    df = rd("city_data/reference/decision_engine_supplement_v3/market_supply_proxy.csv")
    if df is not None:
        df = tag(df, "SRC-V3-MARKET-SUPPLY", "city", "mixed", is_proxy=True)
        wr(df, "market", "supply_proxy")

    # 4) market_registry
    a = rd("city_data/reference/decision_engine_supplement_v3/market_registry_v3.csv")
    b = rd("city_data/reference/decision_engine_supplement_v2/market_registry_extended.csv")
    df = concat([a, b])
    if df is not None:
        df = tag(df, "SRC-MARKET-REGISTRY", "city", "static")
        wr(df, "market", "market_registry")

    # 5) province_price_reference
    a = rd("city_data/reference/decision_engine_supplement_v3/price_lnnync_veg_weekly_historical.csv")
    b = rd("city_data/reference/decision_engine_supplement/price_lnnync_veg_weekly_extended.csv")
    df = concat([a, b])
    if df is not None:
        df = df.drop(columns=[c for c in ["is_proxy", "is_derived"] if c in df.columns])
        df = apply_crop(df, "crop_standard")
        df = tag(df, "SRC-LN-NYNC-VEG-WEEKLY", "province", "weekly")
        wr(df, "market", "province_price_reference")


# ============================== production ==============================
def build_production():
    a = rd("city_data/reference/decision_engine_supplement_v2/planting_area_crop_yearly.csv")
    if a is not None:
        wr(tag(a, "SRC-LN-YEARBOOK-AREA", "city", "yearly"), "production", "planting_area_yearly")
    else:
        na("production", "planting_area_yearly", "无来源")

    fr = []
    for d, city in CITIES.items():
        df = rd(f"city_data/{d}/data/production_yearly.csv")
        if df is not None:
            df["city"] = city
            fr.append(df)
    b = rd("city_data/reference/decision_engine_supplement_v2/production_crop_yearly.csv")
    if b is not None:
        fr.append(b)
    df = concat(fr)
    if df is not None:
        wr(tag(df, "SRC-PRODUCTION-MERGED", "city", "yearly"), "production", "production_yearly")
    else:
        na("production", "production_yearly", "无来源")

    c = rd("city_data/reference/decision_engine_supplement_v3/crop_spatial_structure.csv")
    if c is not None:
        df = apply_crop(c, "crop_standard")
        df["is_derived"] = False
        wr(tag(df.drop(columns=["is_proxy"] if "is_proxy" in df.columns else []), "SRC-V3-CROP-STRUCTURE", "district", "cross_section"),
           "production", "crop_spatial_structure")
        fac = df[df.get("facility_type", "").astype(str).str.contains("greenhouse|frame|sunlight|facility", case=False, na=False)]
        wr(fac, "production", "facility_agriculture")
    else:
        na("production", "crop_spatial_structure", "无来源"); na("production", "facility_agriculture", "无来源")

    fr = []
    for d, city in CITIES.items():
        df = rd(f"city_data/{d}/data/phenology_events.csv")
        if df is not None:
            df["city"] = city
            fr.append(df)
    e = rd("city_data/reference/decision_engine_supplement_v2/crop_calendar_detailed.csv")
    if e is not None:
        fr.append(e)
    df = concat(fr)
    if df is not None:
        col = "crop_standard" if "crop_standard" in df.columns else "crop_raw"
        df = apply_crop(df, col)
        wr(tag(df, "SRC-PHENOLOGY-MERGED", "city", "event"), "production", "crop_calendar")
    else:
        na("production", "crop_calendar", "无来源")

    na("production", "yield_yearly", "由 planting_area_yearly × production_yearly 在 03_integrated 派生（避免重复口径）")


# ============================== cost ==============================
def build_cost():
    a = rd("city_data/reference/decision_engine_supplement_v2/crop_cost_yearly_extended.csv")
    if a is not None:
        wr(tag(a, "SRC-COST-MERGED", "mixed", "yearly"), "cost", "crop_cost")
    else:
        na("cost", "crop_cost", "无来源")
    b = rd("city_data/reference/decision_engine_supplement_v3/crop_cost_components.csv")
    if b is not None:
        wr(tag(b, "SRC-V3-COST-COMPONENTS", "mixed", "cross_section"), "cost", "cost_components")
    else:
        na("cost", "cost_components", "无来源")
    if a is not None:
        pr = a[a.get("is_proxy", "").astype(str).str.lower().isin(["true", "1", "yes"])]
        wr(pr, "cost", "cost_proxy", "仅代理行")

    fr = []
    for d, city in CITIES.items():
        df = rd(f"city_data/{d}/data/input_cost_weekly.csv")
        if df is not None:
            df["city"] = city
            fr.append(df)
    df = concat(fr)
    if df is not None:
        wr(tag(df, "SRC-INPUT-COST-WEEKLY", "city", "weekly"), "cost", "input_prices")
    else:
        na("cost", "input_prices", "无来源")


# ============================== climate ==============================
def build_climate():
    fr = []
    for d, city in CITIES.items():
        for suffix in ["weather_daily_era5.csv", "weather_extra_daily_era5.csv"]:
            df = rd(f"city_data/{d}/data/{suffix}")
            if df is not None:
                df["city"] = city
                fr.append(df)
    df = concat(fr)
    if df is not None:
        wr(tag(df, "SRC-ERA5", "city", "daily", is_derived=False), "climate", "weather_daily")
    else:
        na("climate", "weather_daily", "无来源")

    cl = rd("city_data/reference/curated/weekly_climatology_1991_2020.csv")
    if cl is not None:
        wr(tag(cl, "SRC-CLIMATOLOGY-1991-2020", "city", "weekly"), "climate", "climatology")
    else:
        na("climate", "climatology", "无来源")

    fr = []
    for d, city in CITIES.items():
        df = rd(f"city_data/{d}/data/soil_daily.csv")
        if df is not None:
            df["city"] = city
            fr.append(df)
    df = concat(fr)
    if df is not None:
        wr(tag(df, "SRC-SOIL-DAILY", "city", "daily"), "climate", "soil_daily")
    else:
        na("climate", "soil_daily", "无来源")


# ============================== remote_sensing ==============================
def build_rs():
    v3 = "city_data/reference/decision_engine_supplement_v3/"
    a = rd(v3 + "remote_sensing_ndvi_city_monthly.csv")
    if a is not None:
        wr(tag(a, "SRC-AWS-S2L2A", "city", "monthly"), "remote_sensing", "ndvi")
    else:
        na("remote_sensing", "ndvi", "无来源")
    b = rd(v3 + "remote_sensing_ndvi_derived.csv")
    if b is not None:
        wr(tag(b, "SRC-AWS-S2L2A", "city", "monthly", is_derived=True), "remote_sensing", "vegetation_anomaly")
    else:
        na("remote_sensing", "vegetation_anomaly", "无来源")
    c = rd(v3 + "remote_sensing_evi_city_monthly.csv")
    if c is not None:
        wr(tag(c, "SRC-AWS-S2L2A-EVI", "city", "monthly"), "remote_sensing", "evi")
    else:
        na("remote_sensing", "evi", "无来源")
    na("remote_sensing", "lai", "MODIS 通道受限，未取得（见 MODIS_EVI_ATTEMPT.md）")
    na("remote_sensing", "fapar", "MODIS 通道受限，未取得")
    na("remote_sensing", "cropland_landcover", "尚未采集耕地/土地覆盖栅格")


# ============================== disaster / bio_risk / water ==============================
def build_disaster():
    fr = []
    for d, city in CITIES.items():
        df = rd(f"city_data/{d}/data/disaster_events_observed.csv")
        if df is not None:
            df["city"] = city
            fr.append(df)
    df = concat(fr)
    if df is not None:
        wr(tag(df, "SRC-DISASTER-OBSERVED", "city", "event"), "disaster", "disaster_events")
        loss_cols = [c for c in ["economic_loss", "affected_area_value", "damaged_area_value",
                                 "crop_failure_area_value", "yield_loss_ton"] if c in df.columns]
        wr(df[loss_cols + ["city"]].copy(), "disaster", "disaster_loss", "损失列子集")
    else:
        na("disaster", "disaster_events", "无来源"); na("disaster", "disaster_loss", "无来源")

    a = rd("city_data/reference/decision_engine_supplement_v2/agri_insurance_claims.csv")
    b = rd("city_data/reference/decision_engine_supplement_v3/agri_insurance_claims_v3.csv")
    df = concat([a, b])
    if df is not None:
        wr(tag(df, "SRC-INSURANCE-MERGED", "province", "yearly"), "disaster", "insurance_claims")
    else:
        na("disaster", "insurance_claims", "无来源")


def build_bio_water():
    p = rd("city_data/reference/decision_engine_supplement_v3/pest_events.csv")
    if p is not None:
        wr(tag(p, "SRC-V3-PEST", "city", "event"), "bio_risk", "pest_disease_events")
    else:
        na("bio_risk", "pest_disease_events", "无来源")

    a = rd("city_data/reference/decision_engine_supplement_v2/irrigation_yearly.csv")
    b = rd("city_data/reference/decision_engine_supplement_v3/irrigation_yearly_extended.csv")
    df = concat([a, b])
    if df is not None:
        wr(tag(df, "SRC-IRRIGATION-MERGED", "city", "yearly"), "water", "irrigation_water")
    else:
        na("water", "irrigation_water", "无来源")


# ============================== infrastructure ==============================
def build_infra():
    a = rd("city_data/reference/decision_engine_supplement_v3/cold_chain_capacity_v3.csv")
    if a is not None:
        wr(tag(a, "SRC-V3-COLDCHAIN", "city", "cross_section"), "infrastructure", "cold_chain")
        wr(a.copy(), "infrastructure", "storage")
    else:
        na("infrastructure", "cold_chain", "无来源"); na("infrastructure", "storage", "无来源")
    b = rd("city_data/reference/decision_engine_supplement_v3/market_accessibility.csv")
    if b is not None:
        wr(tag(b, "SRC-OSRM-DERIVED", "city", "static", is_derived=True), "infrastructure", "market_accessibility")
    else:
        na("infrastructure", "market_accessibility", "无来源")
    reg = rd("city_data/reference/decision_engine_supplement_v3/market_registry_v3.csv")
    if reg is not None:
        wr(tag(reg, "SRC-MARKET-REGISTRY", "city", "static", is_derived=True), "infrastructure", "logistics_reference")
    else:
        na("infrastructure", "logistics_reference", "无来源")


# ============================== demand ==============================
def build_demand():
    a = rd("city_data/reference/decision_engine_supplement_v3/demand_yearly_v3.csv")
    b = rd("city_data/reference/decision_engine_supplement_v2/demand_yearly.csv")
    df = concat([a, b])
    if df is None:
        for n in ["population", "consumption", "cpi", "retail_catering", "demand_proxy"]:
            na("demand", n, "无来源")
        return
    m = df.get("metric", pd.Series("", index=df.index)).astype(str)
    groups = {
        "population": m.str.contains("人口|城镇化"),
        "cpi": m.str.contains("CPI|价格涨幅|价格指数", case=False),
        "retail_catering": m.str.contains("零售|餐饮"),
        "consumption": m.str.contains("消费支出|消费"),
    }
    used = pd.Series(False, index=df.index)
    for name, mask in groups.items():
        sub = df[mask & ~used]
        used = used | mask
        if len(sub):
            wr(tag(sub.copy(), "SRC-DEMAND-MERGED", "city", "yearly"), "demand", name)
        else:
            na("demand", name, "无匹配 metric")
    wr(tag(df.copy(), "SRC-DEMAND-MERGED", "city", "yearly"), "demand", "demand_proxy", "全量背景（含 UNUSABLE）")


# ============================== policy / evidence ==============================
def build_policy_evidence():
    fr = []
    for d, city in CITIES.items():
        df = rd(f"city_data/{d}/data/policy_events.csv")
        if df is not None:
            df["city"] = city
            fr.append(df)
    df = concat(fr)
    if df is not None:
        wr(tag(df, "SRC-POLICY-EVENTS", "city", "event"), "policy", "policy_events")
        wr(df.copy(), "policy", "market_intervention", "政策事件（含调控类）")
    else:
        na("policy", "policy_events", "无来源"); na("policy", "market_intervention", "无来源")

    a = rd("city_data/reference/decision_engine_supplement_v2/herding_events_extended.csv")
    b = rd("city_data/reference/decision_engine_supplement_v3/herding_events_v3.csv")
    df = concat([a, b])
    if df is not None:
        wr(tag(df, "SRC-HERDING-EVIDENCE", "city", "event"), "evidence", "herding_events")
    else:
        na("evidence", "herding_events", "无来源")
    # case_events: 灾害事件作为案例
    p = ROOT / "data/processed/disaster/disaster_events.parquet"
    if p.exists():
        ev = pd.read_parquet(p)
        wr(ev.copy(), "evidence", "case_events", "灾害案例（从 disaster_events 复制）")
    else:
        na("evidence", "case_events", "无来源")


def main():
    build_market(); build_production(); build_cost(); build_climate(); build_rs()
    build_disaster(); build_bio_water(); build_infra(); build_demand(); build_policy_evidence()
    (ROOT / "data" / "metadata" / "quality").mkdir(parents=True, exist_ok=True)
    (ROOT / "data" / "metadata" / "quality" / "build_standardized.log").write_text("\n".join(LOG), encoding="utf-8")
    for l in LOG:
        print(l)


if __name__ == "__main__":
    main()
