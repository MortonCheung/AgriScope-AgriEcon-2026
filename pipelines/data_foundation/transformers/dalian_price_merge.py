"""合并大连价格观测（周度+月度）→ 统一 marts 并评估覆盖。

输入：
  city_data/reference/staging/dalian_price_weekly.csv   （发改委周报，2023-2026）
  city_data/reference/staging/dalian_price_monthly.csv  （辽宁发改委月度综述，2021-2024）
  data/raw/prices/dalian_cif/parsed_tables.json （商务预报批发表+上市量，2026-07 起）
输出：
  city_data/reference/curated/dalian_price_series.csv
  city_data/reference/marts/fact_price_dalian.csv
  city_data/reference/reports/dalian_price_coverage.md
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
STAGING = ROOT / "city_data/reference/staging"
CURATED = ROOT / "city_data/reference/curated"
MARTS = ROOT / "city_data/reference/marts"
REPORTS = ROOT / "city_data/reference/reports"
CURATED.mkdir(parents=True, exist_ok=True)
MARTS.mkdir(parents=True, exist_ok=True)
REPORTS.mkdir(parents=True, exist_ok=True)

FETCH_TIME = datetime.now().isoformat(timespec="seconds")


def main() -> None:
    frames = []
    # 1) 月度
    m = pd.read_csv(STAGING / "dalian_price_monthly.csv", encoding="utf-8-sig")
    m = m.rename(columns={"period_date": "date", "price_raw": "price"})
    m["price"] = pd.to_numeric(m["price"], errors="coerce")
    m["frequency"] = "monthly"
    m["source_layer"] = "lnfgw_monthly_review"
    frames.append(m[["date", "city", "product_standard", "product_raw", "price", "unit_raw", "frequency", "source_layer"]])

    # 2) 周度
    w = pd.read_csv(STAGING / "dalian_price_weekly.csv", encoding="utf-8-sig")
    w = w.rename(columns={"article_date": "date", "price_raw": "price"})
    w["price"] = pd.to_numeric(w["price"], errors="coerce")
    w["frequency"] = "weekly"
    w["source_layer"] = "dl_gov_weekly"
    frames.append(w[["date", "city", "product_standard", "product_raw", "price", "unit_raw", "frequency", "source_layer"]])

    # 3) 商务预报批发表
    cif = json.load(open(ROOT / "data/raw/prices/dalian_cif/parsed_tables.json", encoding="utf-8"))
    ws_rows = []
    for rec in cif:
        for r in rec.get("wholesale", []):
            ws_rows.append({"date": rec["date"], "product_standard": r["product"],
                            "product_raw": r["product"], "market_shuangxing": r["shuangxing"],
                            "market_nanguanling": r["nanguanling"],
                            "price": r["price"], "unit_raw": "元/公斤", "frequency": "weekly",
                            "source_layer": "dalian_commerce_batch"})
        for s in rec.get("supply", []):
            ws_rows.append({"date": rec["date"], "product_standard": s.get("metric", "上市量"),
                            "product_raw": s.get("metric", "上市量"), "price": s.get("value"),
                            "unit_raw": s.get("unit"), "frequency": "weekly",
                            "source_layer": "dalian_commerce_supply"})
    if ws_rows:
        wc = pd.DataFrame(ws_rows)
        wc["city"] = "大连"
        frames.append(wc)

    df = pd.concat(frames, ignore_index=True)
    df = df.dropna(subset=["price"])
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    df["year"] = df["date"].dt.year
    df["week"] = df["date"].dt.isocalendar().week.astype(int)
    df = df.sort_values(["product_standard", "date"])

    # 保存 curated / marts
    df.to_csv(CURATED / "dalian_price_series.csv", index=False, encoding="utf-8-sig")
    fact = df.rename(columns={"product_standard": "product", "product_raw": "product_raw"})
    fact["city"] = "大连"
    fact["source_id"] = "SRC-DL-PRICE-MERGED"
    fact["source_name"] = "大连发改委周报+辽宁发改委月度综述+大连商务预报"
    fact["source_url"] = "https://www.dl.gov.cn/col/col1190/index.html"
    fact["fetch_time"] = FETCH_TIME
    fact["quality_grade"] = "B"
    fact.to_csv(MARTS / "fact_price_dalian.csv", index=False, encoding="utf-8-sig")

    # 评估：每商品时间覆盖
    print("=== 大连价格覆盖评估 ===")
    print(f"总观测 {len(df)} 行, 时间 {df['date'].min().date()} ~ {df['date'].max().date()}")
    cov = df.groupby(["product_standard", "frequency"]).agg(
        n=("price", "size"), start=("date", "min"), end=("date", "max")
    ).reset_index()
    cov["span_years"] = (cov["end"] - cov["start"]).dt.days / 365.25
    print(cov.to_string(index=False))

    # 写评估报告
    lines = [
        "# 大连价格数据覆盖评估", "",
        f"生成时间：{FETCH_TIME}", "",
        f"总观测：{len(df)} 行", f"时间范围：{df['date'].min().date()} ~ {df['date'].max().date()}", "",
        "## 按商品×频率", "",
        "| 商品 | 频率 | 观测数 | 起 | 止 | 跨度(年) |",
        "|---|---|---|---|---|---|",
    ]
    for _, r in cov.iterrows():
        lines.append(f"| {r['product_standard']} | {r['frequency']} | {r['n']} | {r['start'].date()} | {r['end'].date()} | {r['span_years']:.1f} |")
    (REPORTS / "dalian_price_coverage.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[OK] 已写出:\n  {CURATED/'dalian_price_series.csv'}\n  {MARTS/'fact_price_dalian.csv'}\n  {REPORTS/'dalian_price_coverage.md'}")


if __name__ == "__main__":
    main()
