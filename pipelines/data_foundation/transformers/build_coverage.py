"""覆盖矩阵、数据清单、质量评级与作物候选（手册第 46、50、57、58、59 节）。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
MARTS = ROOT / "city_data/reference/marts"
CURATED = ROOT / "city_data/reference/curated"
META = ROOT / "data/raw/metadata"
REPORTS = ROOT / "city_data/reference/reports"
REPORTS.mkdir(parents=True, exist_ok=True)

TARGET_CITIES = ["沈阳", "铁岭", "朝阳", "锦州", "丹东", "大连"]


def sha256_of(path: Path, limit: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        read = 0
        while True:
            b = fh.read(1024 * 1024)
            if not b or read > limit:
                break
            h.update(b)
            read += len(b)
    return h.hexdigest()


def build_manifest() -> pd.DataFrame:
    rows = []
    for p in sorted(list(MARTS.glob("*")) + list(CURATED.glob("*")) + list(META.glob("*"))):
        if p.is_dir() or p.name.startswith("."):
            continue
        if p.suffix not in (".csv", ".parquet", ".json"):
            continue
        rec = {"filename": p.name, "layer": p.parent.name,
               "size_bytes": p.stat().st_size, "sha256": sha256_of(p)}
        try:
            df = pd.read_parquet(p) if p.suffix == ".parquet" else (
                pd.read_csv(p, nrows=200000, low_memory=False) if p.suffix == ".csv"
                else pd.DataFrame([json.loads(p.read_text(encoding="utf-8"))]).explode(list(
                    json.loads(p.read_text(encoding="utf-8")).keys()) if isinstance(
                    json.loads(p.read_text(encoding="utf-8")), dict) else []))
            rec["row_count"] = len(df)
            rec["column_count"] = df.shape[1]
            for c in ("date", "week_start", "period_start", "year", "effective_date"):
                if c in df.columns:
                    s = pd.to_datetime(df[c], errors="coerce")
                    rec["date_min"], rec["date_max"] = str(s.min())[:10], str(s.max())[:10]
                    break
            if "city" in df.columns:
                rec["city_count"] = int(df["city"].nunique())
            if "crop" in df.columns:
                rec["crop_count"] = int(df["crop"].nunique())
        except Exception:
            rec.update({"row_count": None, "column_count": None})
        rows.append(rec)
    return pd.DataFrame(rows)


def main() -> None:
    cp = pd.read_parquet(MARTS / "city_crop_week_panel.parquet")
    pp = pd.read_parquet(MARTS / "province_crop_week_panel.parquet")
    wx_d = pd.read_parquet(MARTS / "fact_weather_daily.parquet")
    wx_w = pd.read_parquet(MARTS / "fact_weather_weekly.parquet")
    ic = pd.read_parquet(MARTS / "fact_input_cost_weekly.parquet")
    ev = pd.read_parquet(MARTS / "fact_disaster_events.parquet")
    prod = pd.read_parquet(MARTS / "fact_production_yearly.parquet")
    cond = pd.read_parquet(MARTS / "fact_agri_conditions.parquet")
    crops = pd.read_csv(META / "crops.csv")
    cal = pd.read_csv(META / "crop_calendar.csv")

    pest_n, soil_days = 0, 0
    pj = ROOT / "data/raw" / "pests" / "pest_articles.jsonl"
    if pj.exists():
        pest_n = sum(1 for l in pj.open(encoding="utf-8") if l.strip())
    sp = MARTS / "fact_soil_daily.parquet"
    if sp.exists():
        soil_days = int(pd.read_parquet(sp)["date"].nunique())

    # ---------- 六城市覆盖 ----------
    rows = []
    for city in TARGET_CITIES:
        c_inp = ic[ic["city"] == city]
        rows.append({
            "city": city,
            "price_days": 0,                       # 城市级日价格不可得
            "price_weeks": int(c_inp["week_start"].nunique()),
            "price_records": int(len(c_inp)),
            "province_price_weeks": int(pp["week_start"].nunique()),
            "weather_days": int(wx_d[wx_d["city"] == city].shape[0]),
            "weather_weeks": int(wx_w[wx_w["city"] == city].shape[0]),
            "soil_days": soil_days,
            "production_years": int(prod[prod["city"] == city]["year"].nunique()),
            "agri_condition_records": int(len(cond[cond["city"] == city])),
            "disaster_events": int(len(ev[ev["city"] == city])),
            "pest_articles": pest_n,               # 省级栏目，非按城市拆分
            "market_supply_days": 0,               # not_publicly_available
            "input_cost_weeks": int(c_inp["week_start"].nunique()),
            "logistics_events": 0,                 # not_publicly_available（见 NOT_ACQUIRED.md）
        })
    city_cov = pd.DataFrame(rows)
    city_cov.to_csv(REPORTS / "city_data_coverage.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] city_data_coverage {len(city_cov)} 行")

    # ---------- 作物覆盖 ----------
    cal_crops = set(cal["crop"])
    rows = []
    for city in TARGET_CITIES:
        for _, r in crops.iterrows():
            crop = r["crop"]
            pc = pp[pp["crop"] == crop]
            if pc.empty:
                continue
            rows.append({
                "city": city, "crop": crop, "category": r["category"],
                "price_geo_level": "province_only",
                "price_first_date": str(pc["week_start"].min())[:10],
                "price_last_date": str(pc["week_start"].max())[:10],
                "price_days": 0,
                "price_weeks": int(pc["week_start"].nunique()),
                "production_years": int(prod[(prod["city"] == city) & (prod["crop"] == crop)]["year"].nunique()),
                "pest_records": 0,
                "crop_calendar_available": int(crop in cal_crops),
            })
    crop_cov = pd.DataFrame(rows)
    crop_cov.to_csv(REPORTS / "crop_data_coverage.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] crop_data_coverage {len(crop_cov)} 行")

    # ---------- 作物候选（每城 5 个）----------
    cand_rows = []
    for city in TARGET_CITIES:
        sub = crop_cov[crop_cov["city"] == city].copy()
        prod_city = prod[prod["city"] == city].drop_duplicates("crop")
        pmap = dict(zip(prod_city["crop"], prod_city["planting_area"]))
        sub["planting_area"] = sub["crop"].map(pmap)
        sub["has_production"] = sub["planting_area"].notna()
        sub["score"] = (sub["price_weeks"].clip(upper=300) / 300 * 60
                        + sub["has_production"].astype(int) * 25
                        + sub["crop"].isin(["玉米", "水稻", "大豆", "花生"]).astype(int) * 15)
        sub = sub.sort_values("score", ascending=False).head(5).reset_index(drop=True)
        for i, r in sub.iterrows():
            cand_rows.append({
                "city": city, "candidate_rank": i + 1, "crop": r["crop"],
                "category": r["category"], "price_geo_level": r["price_geo_level"],
                "price_weeks": r["price_weeks"],
                "price_first_date": r["price_first_date"], "price_last_date": r["price_last_date"],
                "production_years": r["production_years"],
                "planting_area_kha": r["planting_area"],
                "crop_calendar_available": r["crop_calendar_available"],
                "note": "最终选定需由用户与 ChatGPT 共同决定，此处仅为候选（手册第59节）",
            })
    cand = pd.DataFrame(cand_rows)
    cand.to_csv(REPORTS / "candidate_crops.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] candidate_crops {len(cand)} 行（每城 5 个候选）")

    # ---------- 数据质量评级（手册第 50 节）----------
    grades = [
        ("fact_weather_daily/weekly", "A", "官方机构再分析产品，结构化、连续、单位明确（非观测站，已标注）"),
        ("province_crop_price_weekly", "A", "政府网站结构化发布，周度连续，2021-2026"),
        ("fact_input_cost_weekly", "A", "政府网站逐市报价，周度连续"),
        ("fact_production_yearly", "A", "统计局年鉴 Excel，结构化（年份仅 2017-2019）"),
        ("fact_agri_conditions", "A", "统计局年鉴 Excel，结构化（年份仅 2017-2019）"),
        ("fact_fuel_price", "A", "发改委官方公告 PDF，结构化提取（仅近期 6 期）"),
        ("fact_disaster_events", "C", "基于再分析日值的阈值识别，非官方事件通报"),
        ("fact_disaster_reports", "B", "官方页面文本解析，量少且多为外省转载"),
        ("pest_articles", "B", "官方页面文本解析，未结构化到城市级"),
        ("dim_calendar", "A", "国务院办公厅公布的法定节假日安排"),
        ("crop_calendar / crop_agronomy", "B", "政府农业技术资料整理，粒度仅到旬/月"),
        ("fact_price_daily", "—", "not_publicly_available"),
        ("fact_market_supply", "—", "not_publicly_available"),
        ("fact_logistics_events", "—", "not_publicly_available"),
        ("remote_sensing", "—", "未采集（增强层，见 NOT_ACQUIRED.md）"),
    ]
    gdf = pd.DataFrame(grades, columns=["dataset", "grade", "reason"])
    gdf["grade_meaning"] = gdf["grade"].map({
        "A": "政府/官方 + 结构化 + 连续 + 单位清晰",
        "B": "官方但经文本/新闻解析",
        "C": "官方再分析或算法派生",
        "D": "第三方可信数据",
        "—": "未取得",
    })
    gdf.to_csv(REPORTS / "data_quality_grades.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] data_quality_grades {len(gdf)} 行")

    # ---------- data_manifest ----------
    mani = build_manifest()
    mani.to_csv(REPORTS / "data_manifest.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] data_manifest {len(mani)} 个文件")


if __name__ == "__main__":
    main()
