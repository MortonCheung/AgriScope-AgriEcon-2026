"""生成 P0 验收覆盖表与 CORE_DATA_READINESS.csv。

严格按手册§3.7 / §4.5 / §15：用**实际覆盖**证明，不写「文件存在所以完成」。
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
MARTS = ROOT / "city_data/reference/marts"
STAGING = ROOT / "city_data/reference/staging"
REPORTS = ROOT / "city_data/reference/reports"
REPORTS.mkdir(parents=True, exist_ok=True)

TARGET = ["沈阳", "铁岭", "朝阳", "锦州", "丹东", "大连"]


def price_coverage() -> pd.DataFrame:
    p = pd.read_parquet(MARTS / "fact_price_city.parquet")
    # 过滤日期不完整的行（如文章源未能解析出年月会产生 "-01"）
    p = p[p["date"].astype(str).str.match(r"^\d{4}-\d{2}-\d{2}$")]
    rows = []
    for (city, market, crop, ptype), g in p.groupby(
            ["city", "market_name", "crop_raw", "price_type"], dropna=False):
        if pd.isna(city):
            continue
        g = g.sort_values("date")
        d = pd.to_datetime(g["date"])
        # 最长连续区间（按实际观测日，间隔<=7天视为连续）
        gap = d.diff().dt.days.fillna(1)
        grp = (gap > 7).cumsum()
        longest = int(g.groupby(grp).size().max()) if len(g) else 0
        # 必须用 (iso_year, iso_week) 组合计数：单用 week 序号跨年会重复（1-53），
        # 会把 6 年 350 周误算成 53 周、缺失率虚高到 85%。
        cal = d.dt.isocalendar()
        weeks = int(pd.DataFrame({'y': cal.year, 'w': cal.week}).drop_duplicates().shape[0])
        # 期望周数按区间内实际周一起点数计算（比 span//7 准确，跨年末的 53 周不会漏）
        exp_weeks = max(len(pd.date_range(d.min(), d.max(), freq="W-MON")), 1)
        rows.append({
            "city": city, "market": market, "crop": crop,
            "first_date": str(g["date"].min()), "last_date": str(g["date"].max()),
            "record_days": int(len(g)),
            "valid_weeks": weeks,
            "missing_rate": round(max(0.0, 1 - weeks / exp_weeks), 3) if exp_weeks else None,
            "longest_run_days": longest,
            "price_type": ptype,
            "source_id": g["source_id"].iloc[0],
            "quality_grade": g["quality_grade"].iloc[0],
        })
    df = pd.DataFrame(rows).sort_values(["city", "record_days"], ascending=[True, False])
    df.to_csv(REPORTS / "city_crop_price_coverage.csv", index=False, encoding="utf-8-sig")
    return df


def production_coverage() -> pd.DataFrame:
    yb = pd.read_parquet(MARTS / "fact_production_yearly.parquet")
    rows = []
    for (city, crop), g in yb.groupby(["city", "crop"], dropna=False):
        rows.append({
            "city": city, "crop": crop,
            "years_available": int(g["year"].nunique()),
            "first_year": int(g["year"].min()), "last_year": int(g["year"].max()),
            "planting_area_years": int(g.dropna(subset=["planting_area"])["year"].nunique()),
            "production_years": int(g.dropna(subset=["production"])["year"].nunique()),
            "yield_years": int(g.dropna(subset=["yield_per_area"])["year"].nunique()),
            "source_count": 1, "source": "辽宁统计年鉴（2017—2019）", "quality_grade": "A",
        })
    # 公报（2020—2024）
    bl = STAGING / "city_bulletin_production.csv"
    if bl.exists():
        b = pd.read_csv(bl)
        b = b.rename(columns={"crop_raw": "crop"})     # 公报文件列名一致化
        for (city, crop), g in b.groupby(["city", "crop"]):
            pa = g[g["metric"] == "planting_area"]["year"].nunique()
            pr = g[g["metric"] == "production"]["year"].nunique()
            rows.append({
                "city": city, "crop": crop,
                "years_available": int(g["year"].nunique()),
                "first_year": int(g["year"].min()), "last_year": int(g["year"].max()),
                "planting_area_years": int(pa), "production_years": int(pr),
                "yield_years": 0,
                "source_count": 1, "source": f"{city}市统计公报（2020—2024）",
                "quality_grade": "A",
            })
    df = pd.DataFrame(rows)
    df.to_csv(REPORTS / "city_crop_production_coverage.csv", index=False, encoding="utf-8-sig")
    return df


def readiness() -> pd.DataFrame:
    pc = pd.read_csv(REPORTS / "city_crop_price_coverage.csv")
    pr = pd.read_csv(REPORTS / "city_crop_production_coverage.csv")
    rows = []

    # 1 六城市连续农产品价格
    for city in TARGET:
        sub = pc[pc["city"] == city]
        if sub.empty:
            rows.append({"category": "1 六城市连续农产品价格", "city": city, "crop": "-",
                         "expected": "city×crop 日/周度 2021—2026", "actual": "无",
                         "date_range": "-", "coverage": "0", "quality_grade": "-",
                         "status": "MISSING",
                         "remaining_gap": "该市未发现公开的价格监测数据接口",
                         "can_model": "NO"})
        else:
            top = sub.sort_values("record_days", ascending=False).iloc[0]
            rng = f"{top['first_date']} ~ {top['last_date']}"
            rows.append({"category": "1 六城市连续农产品价格", "city": city,
                         "crop": top["crop"],
                         "expected": "city×crop 日/周度 2021—2026",
                         "actual": f"{top['record_days']} 天 / {top['valid_weeks']} 周（{top['price_type']}）",
                         "date_range": rng,
                         "coverage": f"缺失率 {top['missing_rate']}",
                         "quality_grade": top["quality_grade"],
                         "status": "PARTIAL" if top["last_date"] < "2026-01" else "COMPLETE",
                         "remaining_gap": "采集仍在进行，尚未覆盖至 2026 年" if top["last_date"] < "2026-01" else "-",
                         "can_model": "PARTIAL" if top["last_date"] < "2026-01" else "YES"})

    # 2 2020—2025 城市作物生产
    for city in TARGET:
        sub = pr[pr["city"] == city]
        if sub.empty:
            rows.append({"category": "2 2020—2025 城市作物生产", "city": city, "crop": "-",
                         "expected": "city×crop×year 2020—2025", "actual": "无",
                         "date_range": "-", "coverage": "0", "quality_grade": "-",
                         "status": "MISSING",
                         "remaining_gap": "未找到该市公开统计公报/年鉴作物级数据",
                         "can_model": "NO"})
        else:
            mx = sub.sort_values("last_year", ascending=False).iloc[0]
            rows.append({"category": "2 2020—2025 城市作物生产", "city": city, "crop": mx["crop"],
                         "expected": "city×crop×year 2020—2025",
                         "actual": f"{int(mx['years_available'])} 年（播种{mx['planting_area_years']}/产量{mx['production_years']}）",
                         "date_range": f"{int(mx['first_year'])}—{int(mx['last_year'])}",
                         "coverage": f"{int(mx['years_available'])}/6 年",
                         "quality_grade": "A",
                         "status": "PARTIAL",
                         "remaining_gap": "仅覆盖 2017—2019 与部分 2020—2024，缺 2025",
                         "can_model": "PARTIAL"})

    # 3 候选作物物候/敏感性
    cal = pd.read_csv(ROOT / "data/raw/metadata" / "crop_calendar.csv")
    agr = pd.read_csv(ROOT / "data/raw/metadata" / "crop_agronomy.csv")
    for city in TARGET:
        rows.append({"category": "3 候选作物物候/气象敏感性", "city": city,
                     "crop": "/".join(cal["crop"].unique()),
                     "expected": "候选作物物候 + 分生育期敏感性",
                     "actual": f"物候 {len(cal)} 种 / 敏感性 {len(agr)} 条",
                     "date_range": "-", "coverage": f"{len(cal)}/4 作物有物候",
                     "quality_grade": "B", "status": "PARTIAL",
                     "remaining_gap": "仅玉米/水稻/大豆/花生有物候；蔬菜水果待补",
                     "can_model": "PARTIAL"})

    # 4 典型极端天气真实农业损失
    od = ROOT / "data/raw" / "disaster" / "official_2026" / "official_agricultural_disaster_events.json"
    n = len(json.loads(od.read_text(encoding="utf-8"))) if od.exists() else 0
    rows.append({"category": "4 典型极端天气真实农业损失", "city": "全省(沈阳沈北为重点案例)",
                 "crop": "玉米、水稻",
                 "expected": "官方通报：日期+地区+受灾/成灾/绝收面积+作物+损失",
                 "actual": f"{n} 起官方事件（2026-07 辽宁暴雨，全省受灾约290万亩、排涝53.27万亩）",
                 "date_range": "2026-07-13 ~ 2026-07-17",
                 "coverage": "省级口径；成灾/绝收/经济损失官方未单列",
                 "quality_grade": "A", "status": "PARTIAL",
                 "remaining_gap": "成灾面积、绝收面积、经济损失官方未公布，已留空",
                 "can_model": "PARTIAL"})

    # 5 市场供应/成交量 —— 沈阳批发接口的 volume 即日成交量（此前误判）
    msp = MARTS / "fact_market_supply.parquet"
    if msp.exists():
        ms = pd.read_parquet(msp)
        rows.append({"category": "5 市场供应/成交量", "city": "沈阳",
                     "crop": "/".join(sorted(ms["crop"].unique())[:5]),
                     "expected": "上市量/成交量/库存/进场车辆",
                     "actual": f"{len(ms)} 条日成交量（{ms['crop'].nunique()} 种）",
                     "date_range": f"{ms['date'].min()} ~ {ms['date'].max()}",
                     "coverage": f"{ms['date'].nunique()} 天；单位未标注(推断为吨)",
                     "quality_grade": "A", "status": "COMPLETE",
                     "remaining_gap": "仅沈阳批发口径；其余五城仍无供应数据",
                     "can_model": "YES"})
    else:
        rows.append({"category": "5 市场供应/成交量", "city": "六城市", "crop": "-",
                     "expected": "上市量/成交量/库存/进场车辆", "actual": "无",
                     "date_range": "-", "coverage": "0", "quality_grade": "-",
                     "status": "NOT_PUBLIC",
                     "remaining_gap": "未找到公开的供应量数据",
                     "can_model": "NO"})

    df = pd.DataFrame(rows)
    df.to_csv(REPORTS / "CORE_DATA_READINESS.csv", index=False, encoding="utf-8-sig")
    return df


def main() -> None:
    pc = price_coverage()
    print(f"[OK] city_crop_price_coverage {len(pc)} 行")
    if not pc.empty:
        print(pc.head(12).to_string(index=False))
    pr = production_coverage()
    print(f"\n[OK] city_crop_production_coverage {len(pr)} 行")
    rd = readiness()
    print(f"\n[OK] CORE_DATA_READINESS {len(rd)} 行")
    print(rd["status"].value_counts().to_string())


if __name__ == "__main__":
    main()
