"""把第一阶段采集的辽宁省农业农村厅数据重新定位为数据仓库的省级基准层。

按施工手册第 8 节：
- province_avg / national_avg / province_high / province_low → province_price_weekly（省级基准）
- **province_high / province_low 不再计入「某城市连续价格覆盖」**
  （它们只是「全省最高/最低价出现在某地」，不是该城市的连续价格序列）
- 农资类城市价 → fact_input_cost_weekly（按 city × week × input_name）

时间基准统一到 ISO 周（周一→周日），以便与天气周、价格周严格对齐。
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
SRC = ROOT / "data/raw/retained_source/city_data" / "reference" / "lnnync_history" / "processed"
CURATED = ROOT / "city_data/reference/curated"
MARTS = ROOT / "city_data/reference/marts"
for d in (CURATED, MARTS):
    d.mkdir(parents=True, exist_ok=True)

CROP_CATEGORY = {
    "grain_oil": "grain",
    "vegetable": "vegetable",
    "fruit": "fruit",
    "agri_input": "agricultural_input",
}
INPUT_NAMES = {"尿素": "urea", "复合肥": "compound_fertilizer",
               "磷酸二铵": "diammonium_phosphate", "豆粕": "soybean_meal"}


def add_iso_week(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
    """按 ISO 周（周一→周日）生成 week_start / week_end / iso_year / iso_week。"""
    d = pd.to_datetime(df[date_col], errors="coerce").dt.date
    iso = d.apply(lambda x: x.isocalendar() if isinstance(x, date) else None)
    df = df.copy()
    df["iso_year"] = [i[0] if i else None for i in iso]
    df["iso_week"] = [i[1] if i else None for i in iso]
    ws = []
    for x in d:
        if isinstance(x, date):
            monday = x - timedelta(days=x.weekday())
            ws.append(monday)
        else:
            ws.append(None)
    df["week_start"] = pd.to_datetime(pd.Series(ws)).dt.date
    df["week_end"] = pd.to_datetime(pd.Series(ws)).dt.date + pd.to_timedelta(6, unit="D")
    df["week_end"] = pd.to_datetime(df["week_end"]).dt.date
    return df


def main() -> None:
    prices = pd.read_csv(SRC / "prices_long.csv")
    print(f"源数据 {len(prices)} 条")

    prices = add_iso_week(prices, "period_start")
    prices = prices.dropna(subset=["week_start"])

    # ---------- 1. 省级/国家级基准周价 ----------
    prov = prices[prices["record_type"].isin(
        ["province_avg", "national_avg", "province_high", "province_low"])].copy()
    prov["crop"] = prov["product"]
    prov["crop_category"] = prov["category_key"].map(CROP_CATEGORY)

    g = prov.groupby(["category_key", "crop_category", "crop", "product_variant",
                      "record_type", "iso_year", "iso_week", "week_start", "week_end"],
                     dropna=False)
    out = g.agg(
        price_mean=("standard_price", "mean"),
        price_min=("standard_price", "min"),
        price_max=("standard_price", "max"),
        observations=("price", "count"),
        original_unit=("original_unit", lambda s: s.mode().iloc[0] if len(s.mode()) else None),
        location_raw=("location_raw", lambda s: "|".join(sorted(set(s.dropna()))[:3])),
    ).reset_index()
    out["geo_level"] = "province"
    out["price_type"] = "province_monitor"
    out["source"] = "liaoning_agri_department"
    out.to_parquet(CURATED / "province_price_weekly.parquet", index=False)
    out.to_csv(CURATED / "province_price_weekly.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] province_price_weekly {len(out)} 行")
    print("   record_type:", dict(out["record_type"].value_counts()))

    # ---------- 2. 农资成本（城市 × 周 × 品种）----------
    inp = prices[(prices["category_key"] == "agri_input")
                 & (prices["record_type"] == "city_price")
                 & prices["city"].notna()].copy()
    inp["input_name"] = inp["product"].map(INPUT_NAMES).fillna(inp["product"])
    g2 = inp.groupby(["city", "week_start", "week_end", "iso_year", "iso_week",
                      "input_name"], dropna=False)
    ic = g2.agg(
        price=("price", "mean"),
        unit=("original_unit", lambda s: s.mode().iloc[0] if len(s.mode()) else None),
        price_min=("price", "min"),
        price_max=("price", "max"),
        observations=("price", "count"),
    ).reset_index()
    ic["source"] = "liaoning_agri_department"
    ic.to_parquet(MARTS / "fact_input_cost_weekly.parquet", index=False)
    ic.to_csv(MARTS / "fact_input_cost_weekly.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] fact_input_cost_weekly {len(ic)} 行")
    print("   城市:", dict(ic["city"].value_counts()))

    # ---------- 3. 城市级真实价格序列盘点（仅农资）----------
    city_series = (inp.groupby(["city", "input_name"])
                   .agg(weeks=("iso_week", "nunique"),
                        observations=("price", "count"),
                        first=("week_start", "min"),
                        last=("week_start", "max"))
                   .reset_index())
    city_series.to_csv(CURATED / "city_price_series_inventory.csv",
                       index=False, encoding="utf-8-sig")
    print("[OK] city_price_series_inventory")

    # ---------- 4. 覆盖统计（区分省级基准与真实城市价）----------
    cov = prices.groupby(["category_key"]).apply(
        lambda d: pd.Series({
            "province_avg": int((d["record_type"] == "province_avg").sum()),
            "province_high": int((d["record_type"] == "province_high").sum()),
            "province_low": int((d["record_type"] == "province_low").sum()),
            "national_avg": int((d["record_type"] == "national_avg").sum()),
            "city_price": int((d["record_type"] == "city_price").sum()),
            "county_price": int((d["record_type"] == "county_price").sum()),
        }), include_groups=False).reset_index()
    cov.to_csv(CURATED / "liaoning_agri_coverage.csv", index=False, encoding="utf-8-sig")
    print("[OK] liaoning_agri_coverage")
    print(cov.to_string(index=False))


if __name__ == "__main__":
    main()
