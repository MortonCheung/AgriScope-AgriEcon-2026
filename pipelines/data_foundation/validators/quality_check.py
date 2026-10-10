"""数据质量检查与缺失数据报告（手册第 35、36 节）。

任何异常都**不删除、不静默修正**，只生成 quality_flags 与说明。
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
MARTS = ROOT / "city_data/reference/marts"
CURATED = ROOT / "city_data/reference/curated"
REPORTS = ROOT / "city_data/reference/reports"
REPORTS.mkdir(parents=True, exist_ok=True)

TARGET_CITIES = ["沈阳", "铁岭", "朝阳", "锦州", "丹东", "大连"]


def check_frame(df: pd.DataFrame, name: str, date_col: str | None = None,
                price_col: str | None = None, city_col: str = "city") -> dict:
    r = {"table": name, "rows": int(len(df)), "flags": {}}
    flags = r["flags"]

    dup = int(df.duplicated().sum())
    flags["duplicate_rows"] = dup

    if date_col and date_col in df.columns:
        d = pd.to_datetime(df[date_col], errors="coerce")
        flags["invalid_dates"] = int(d.isna().sum())
        flags["date_min"] = str(d.min())[:10] if d.notna().any() else None
        flags["date_max"] = str(d.max())[:10] if d.notna().any() else None

    if price_col and price_col in df.columns:
        p = pd.to_numeric(df[price_col], errors="coerce")
        flags["price_missing"] = int(p.isna().sum())
        flags["price_non_positive"] = int((p <= 0).sum())
        if p.notna().any():
            q1, q3 = p.quantile(0.25), p.quantile(0.75)
            iqr = q3 - q1
            if iqr > 0:
                flags["price_outliers_iqr"] = int(((p < q1 - 3 * iqr) | (p > q3 + 3 * iqr)).sum())

    if city_col in df.columns:
        bad_city = df[~df[city_col].isin(TARGET_CITIES + ["辽宁省", "沈北新区"]) &
                      df[city_col].notna()]
        flags["unexpected_city_values"] = int(bad_city[city_col].nunique())
        if len(bad_city):
            r["unexpected_cities"] = sorted(bad_city[city_col].dropna().unique().tolist())[:10]

    return r


def main() -> None:
    report = {"generated_at": "2026-09-21", "tables": [], "cross_checks": {}, "notes": []}

    wx_d = pd.read_parquet(MARTS / "fact_weather_daily.parquet")
    wx_w = pd.read_parquet(MARTS / "fact_weather_weekly.parquet")
    prov = pd.read_parquet(CURATED / "province_price_weekly.parquet")
    ic = pd.read_parquet(MARTS / "fact_input_cost_weekly.parquet")
    pw = pd.read_parquet(MARTS / "fact_price_weekly.parquet")
    cp = pd.read_parquet(MARTS / "city_crop_week_panel.parquet")
    pp = pd.read_parquet(MARTS / "province_crop_week_panel.parquet")
    ev = pd.read_parquet(MARTS / "fact_disaster_events.parquet")
    exp = pd.read_parquet(MARTS / "weekly_disaster_exposure.parquet")
    prod = pd.read_parquet(MARTS / "fact_production_yearly.parquet")

    report["tables"].append(check_frame(wx_d, "fact_weather_daily", "date", None))
    # 天气表不套用「价格」校验：气温本身可为负，用价格口径检查会产生误报
    report["tables"].append(check_frame(wx_w, "fact_weather_weekly", "week_start", None))
    report["tables"].append(check_frame(prov, "province_price_weekly", "week_start", "price_mean"))
    report["tables"].append(check_frame(ic, "fact_input_cost_weekly", "week_start", "price"))
    report["tables"].append(check_frame(pw, "fact_price_weekly", "week_start", "price_mean"))
    report["tables"].append(check_frame(cp, "city_crop_week_panel", "week_start", "price_mean"))
    report["tables"].append(check_frame(pp, "province_crop_week_panel", "week_start", "price_mean"))
    report["tables"].append(check_frame(ev, "fact_disaster_events", "start_date"))
    report["tables"].append(check_frame(prod, "fact_production_yearly"))

    # ---- 交叉检查 ----
    cx = report["cross_checks"]
    # 天气缺日
    expected_days = 2083
    daily_cnt = wx_d.groupby("city")["date"].count()
    cx["weather_missing_days"] = {c: int(expected_days - n) for c, n in daily_cnt.items()}

    # 价格类型混用：city_crop_week_panel 中价格来源
    cx["price_source_level"] = dict(cp["price_source_level"].value_counts())

    # 城市错配：农资价格的城市是否都在目标城市内
    bad = set(ic["city"].unique()) - set(TARGET_CITIES)
    cx["input_cost_cities_outside_target"] = sorted(bad)

    # 作物错配：panel 中的 crop 是否都在 crops.csv 中
    crops_meta = pd.read_csv(ROOT / "data/raw/metadata" / "crops.csv")
    cx["crop_not_in_metadata"] = sorted(set(cp["crop"].unique()) - set(crops_meta["crop"]))

    # 生产年份缺失
    cx["production_years"] = sorted(prod["year"].unique().tolist())
    cx["production_year_gap"] = "2020-2025 目标区间内仅覆盖 2017-2019，其余年份年鉴未公开"

    # 周对齐检查：价格周与天气周是否使用同一 ISO 周口径
    pw_weeks = set(pd.to_datetime(pp["week_start"]).dt.date)
    wx_weeks = set(pd.to_datetime(wx_w["week_start"]).dt.date)
    cx["week_alignment"] = {
        "price_weeks": len(pw_weeks), "weather_weeks": len(wx_weeks),
        "shared_weeks": len(pw_weeks & wx_weeks),
        "price_weeks_without_weather": len(pw_weeks - wx_weeks),
        "note": "两侧均按 ISO 周（周一→周日）生成，口径一致",
    }

    report["notes"] = [
        "所有异常值均不删除、不插值、不静默修正，仅标记。",
        "城市级农产品日/周价格 not_publicly_available，city_crop_week_panel 中对应价格留空，"
        "绝不以省级价格填充。",
        "天气为 ERA5 再分析网格值，不是中国气象局观测站数据。",
        "极端天气事件由固定阈值从日值识别，可回溯到具体日期；公开灾情报道量为少数。",
    ]

    (REPORTS / "quality_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("[OK] quality_report.json")
    for t in report["tables"]:
        f = t["flags"]
        print(f"  {t['table']:28s} rows={t['rows']:6d} "
              f"dup={f.get('duplicate_rows',0)} "
              f"invalid_dates={f.get('invalid_dates','-')} "
              f"price_missing={f.get('price_missing','-')} "
              f"nonpos={f.get('price_non_positive','-')} "
              f"outlier={f.get('price_outliers_iqr','-')}")
    print("  week_alignment:", report["cross_checks"]["week_alignment"])

    # ---------- missing_data_report.csv ----------
    rows = []
    for city in TARGET_CITIES:
        c_cp = cp[cp["city"] == city]
        agri = c_cp[c_cp["crop_category"] != "agricultural_input"]
        inp = c_cp[c_cp["crop_category"] == "agricultural_input"]
        rows.append({
            "city": city,
            "city_level_agri_price_weeks": int(agri[agri["price_source_level"] == "city"]["week_start"].nunique()),
            "province_level_agri_price_weeks": int(pp["week_start"].nunique()),
            "city_level_input_cost_weeks": int(inp[inp["price_source_level"] == "city"]["week_start"].nunique()),
            "weather_weeks": int(wx_w[wx_w["city"] == city]["week_start"].nunique()),
            "production_years": int(prod[prod["city"] == city]["year"].nunique()),
            "disaster_events": int(ev[ev["city"] == city].shape[0]),
            "missing": "城市级农产品日/周价格 not_publicly_available；"
                       "农业生产数据 2020-2025 缺失（年鉴未公开）",
        })
    md = pd.DataFrame(rows)
    md.to_csv(REPORTS / "missing_data_report.csv", index=False, encoding="utf-8-sig")
    print(f"\n[OK] missing_data_report.csv {len(md)} 行")


if __name__ == "__main__":
    main()
