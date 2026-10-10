#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Data Foundation · P3.5 语义治理标注（任务书 §41/§42/§43）
对已标准化的成本 / 亩产 / 农事历表追加「来源等级」字段，不改数值、不删行：
  cost_source_class      ∈ LOCAL / REGIONAL_PROXY / PROVINCE_PROXY / RESEARCH_REFERENCE / USER_REQUIRED
  yield_source_class     ∈ city_crop_actual / district_crop_actual / city_aggregate / regional_proxy / reference / user_required
  calendar_geo_scope     ∈ city_specific / district_specific / province / northeast / generic
  facility_type_norm     ∈ open_field / cold_shed / greenhouse / solar_greenhouse / unknown
产出治理登记：00_governance/{COST,YIELD,PHENOLOGY}_SOURCE_CLASSIFICATION.csv
"""
from __future__ import annotations
import re, sys
from pathlib import Path
import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
STD = ROOT / "data" / "processed"
GOV = ROOT / "data" / "metadata" / "governance"
sys.path.insert(0, str(Path(__file__).parent))
from crop_lexicon import classify as lex

SIX = {"沈阳", "朝阳", "锦州", "铁岭", "丹东", "大连"}
ACAD_MEDIA = re.compile(r"大学|学院|学报|研究院|研究|技术推广站|《|论文|晚报|日报|周刊|中国农村网|一亩田|三农|新华|央视|中国经济网|新浪|央视网|网$")
OFFICIAL = re.compile(r"发展改革委|发改委|农业农村|政府|统计局|价格监测|成本调查|调查监审|粮食和|厅$|局$")


def base_city(s: str) -> str:
    return re.split(r"[(（]", str(s or ""))[0].strip()


def cost_class(r) -> str:
    city = base_city(r.get("city") or r.get("city_name") or "")
    src = str(r.get("source_name") or "")
    ot = str(r.get("observation_type") or "")
    official = bool(OFFICIAL.search(src)) or ot in ("official_cost_survey", "official_report", "official_reply")
    if city in SIX and official and ot != "field_survey":
        return "LOCAL"
    if ACAD_MEDIA.search(src):
        return "RESEARCH_REFERENCE"
    if str(r.get("proxy_type") or "") == "regional_proxy" or "东北" in str(r.get("city") or "") or city not in SIX:
        return "REGIONAL_PROXY"
    if "省" in src and str(r.get("geo_level") or "") in ("province",):
        return "PROVINCE_PROXY"
    return "RESEARCH_REFERENCE"


AGG_CROPS = {"蔬菜", "粮油", "水果", "肉蛋奶", "水产", "粮食作物", "经济作物", "其他作物", "其他杂粮",
             "16种蔬菜均价", "15种蔬菜均价", "18种蔬菜均价", "19种蔬菜均价", "12种蔬菜均价", "设施果菜(番茄/黄瓜)"}


def yield_class(city: str, crop: str, geo_level: str, source: str) -> str:
    c = base_city(city)
    crop = str(crop or "").strip()
    if not crop or crop.startswith("(") or crop in AGG_CROPS:
        return "city_aggregate"
    if geo_level == "district":
        return "district_crop_actual"
    if c in SIX and geo_level == "city":
        return "city_crop_actual"
    if c and c not in SIX:
        return "regional_proxy"
    if ACAD_MEDIA.search(source or ""):
        return "reference"
    return "city_aggregate"


FACILITY_MAP = [
    (re.compile(r"阳光温室|日光温室|sunlight"), "solar_greenhouse"),
    (re.compile(r"冷棚|冷棚|拱棚|cold_shed"), "cold_shed"),
    (re.compile(r"大棚|温室|greenhouse|frame|facility"), "greenhouse"),
    (re.compile(r"露地|open_field"), "open_field"),
]


FIELD_CROPS = {"玉米", "水稻", "大豆", "小麦", "高粱", "谷子", "花生", "薯类", "绿豆", "红豆", "马铃薯", "土豆"}
VEG_FACILITY = {"黄瓜", "西红柿", "尖椒", "青椒", "辣椒", "芹菜", "茄子", "韭菜", "芸豆", "甘蓝",
                "油菜", "菠菜", "菜花", "草莓", "洋葱", "生菜", "角瓜", "茼蒿", "香菜"}


def facility_norm(crop="", *vals) -> str:
    s = " ".join(str(v) for v in vals if v is not None and str(v) != "" and str(v) != "nan" and str(v) != "unspecified")
    for pat, name in FACILITY_MAP:
        if pat.search(s):
            return name
    c = str(crop or "").strip()
    if c in FIELD_CROPS:
        return "open_field"          # 大田作物默认露地（可推断）
    if c in VEG_FACILITY:
        return "unknown"             # 蔬菜不猜设施类型
    return "unknown"


def calendar_scope(city: str, county: str, production_system: str, src: str, geo_level: str) -> str:
    c = base_city(city)
    if county and str(county) not in ("nan", "", "None"):
        return "district_specific"
    if c in SIX:
        return "city_specific"
    if "东北" in str(city) or "东北" in (production_system or ""):
        return "northeast"
    if c and c not in SIX and "辽宁" in str(city):
        return "province"
    if "辽宁" in (src or "") or "省" in str(city):
        return "province"
    return "generic"


def process_cost():
    frames = []
    for name in ["cost/crop_cost", "cost/cost_components", "cost/cost_proxy", "cost/input_prices"]:
        p = STD / f"{name}.parquet"
        if not p.exists():
            continue
        df = pd.read_parquet(p)
        if name.endswith("input_prices"):
            # 辽宁省农业农村厅 周度投入品价格（化肥/柴油），城市口径
            df["cost_source_class"] = df["city"].map(
                lambda c: "LOCAL" if c in SIX else "PROVINCE_PROXY")
        else:
            df["cost_source_class"] = df.apply(cost_class, axis=1)
        if "crop" in df.columns:
            df["crop_standard"] = df.get("crop_standard", df["crop"]).where(
                df.get("crop_standard", pd.Series("", index=df.index)).astype(bool),
                df["crop"].map(lambda x: lex(str(x))[0]))
        df.to_parquet(p, index=False)
        frames.append(df.assign(_table=name))
    if frames:
        reg = pd.concat([f[["cost_source_class"]] for f in frames], ignore_index=True)
        reg = reg.groupby("cost_source_class").size().reset_index(name="n_rows")
        reg.to_csv(GOV / "COST_SOURCE_CLASSIFICATION.csv", index=False, encoding="utf-8-sig")
        print("cost class:\n", reg.to_string(index=False))


def process_yield():
    frames = []
    for name, gcol in [("production/production_yearly", "geo_level"),
                       ("production/planting_area_yearly", "geo_level"),
                       ("production/yearbook_shenyang_district_crop", "geo_level"),
                       ("production/bulletin_shenyang_district", "geo_level")]:
        p = STD / f"{name}.parquet"
        if not p.exists():
            continue
        df = pd.read_parquet(p)
        crop_col = "crop" if "crop" in df.columns else ("crop_standard" if "crop_standard" in df.columns else None)
        if crop_col is None:
            continue
        src = df.get("source", df.get("source_name", pd.Series("", index=df.index)))
        df["yield_source_class"] = [
            yield_class(df.at[i, "city"] if "city" in df.columns else "",
                        df.at[i, crop_col], df.at[i, gcol] if gcol in df.columns else "", src.at[i])
            for i in df.index]
        df["crop_is_valid"] = df[crop_col].map(
            lambda x: not (str(x).strip().startswith("(") or str(x).strip() in ("", "nan", "None")))
        df.to_parquet(p, index=False)
        frames.append(df)
        print(f"{name}: {df['yield_source_class'].value_counts().to_dict()}")
    if frames:
        allc = pd.concat([f[["yield_source_class"]].assign(source_table=n) for f, n in zip(frames, [""] * len(frames))], ignore_index=True)
        reg = allc.groupby("yield_source_class").size().reset_index(name="n_rows")
        reg.to_csv(GOV / "YIELD_SOURCE_CLASSIFICATION.csv", index=False, encoding="utf-8-sig")


def process_calendar():
    p = STD / "production/crop_calendar.parquet"
    if not p.exists():
        return
    df = pd.read_parquet(p)
    src = df.get("source_id", pd.Series("", index=df.index)).astype(str) + " " + df.get("source_url", pd.Series("", index=df.index)).astype(str)
    df["facility_type_norm"] = [facility_norm(df.at[i, "crop_standard"] if "crop_standard" in df.columns else "",
                                              df.at[i, "facility_or_open_field"] if "facility_or_open_field" in df.columns else "",
                                              df.at[i, "production_system"] if "production_system" in df.columns else "")
                               for i in df.index]
    df["calendar_geo_scope"] = [calendar_scope(df.at[i, "city"] if "city" in df.columns else "",
                                               df.at[i, "county"] if "county" in df.columns else "",
                                               df.at[i, "production_system"] if "production_system" in df.columns else "",
                                               src.at[i], df.at[i, "geo_level"] if "geo_level" in df.columns else "")
                                for i in df.index]
    df.to_parquet(p, index=False)
    reg = df.groupby(["calendar_geo_scope", "facility_type_norm"]).size().reset_index(name="n_rows")
    reg.to_csv(GOV / "PHENOLOGY_SCOPE_CLASSIFICATION.csv", index=False, encoding="utf-8-sig")
    print("calendar:\n", reg.to_string(index=False))


def main():
    process_cost(); process_yield(); process_calendar()
    print("[OK] annotate_governance 完成")


if __name__ == "__main__":
    main()
