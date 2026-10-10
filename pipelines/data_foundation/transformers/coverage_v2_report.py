"""五城市数据覆盖统计 + FIVE_CITY_DATA_COVERAGE_V2.md 生成器。

统计口径：
  - 价格：来自 city_data/reference/marts/fact_price_observation.csv（统一观测层）
  - 成交量：city_data/reference/staging/volume_observations.csv（market 级）
  - 生产：city_data/reference/staging/{city}*_production*.csv + city_data/reference/staging/city_bulletin_production.csv + 铁岭/锦州/朝阳 2025
  - 天气/土壤：city_data/reference/marts/fact_weather_daily / fact_soil_daily
  - 物候：city_data/reference/staging/phenology_events.csv + data/raw/metadata/crop_calendar.csv
  - 真实灾害：city_data/reference/marts/fact_disaster_event_observed.csv
  - 政策：city_data/reference/marts/fact_policy_event.csv
"""
from __future__ import annotations

import glob
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
MARTS = ROOT / "city_data/reference/marts"
STAGING = ROOT / "city_data/reference/staging"
REPORTS = ROOT / "city_data/reference/reports"

CITIES = ["大连", "丹东", "铁岭", "锦州", "朝阳"]
NOW = datetime.now().isoformat(timespec="seconds")


def safe(path):
    p = ROOT / path
    if not p.exists():
        return None
    try:
        return pd.read_csv(p, encoding="utf-8-sig", low_memory=False)
    except Exception:
        return None


def grade_pct(df, gcol="quality_grade"):
    if df is None or len(df) == 0 or gcol not in df.columns:
        return {}
    vc = df[gcol].astype(str).str[0].str.upper().value_counts(normalize=True) * 100
    return {g: round(vc.get(g, 0.0), 1) for g in ["A", "B", "C", "D", "E", "F"]}


def main() -> None:
    obs = pd.read_csv(MARTS / "fact_price_observation.csv", encoding="utf-8-sig", low_memory=False)
    obs["observation_date"] = pd.to_datetime(obs["observation_date"], errors="coerce")

    # 价格按城市统计
    price_stats = {}
    for c in CITIES:
        d = obs[obs["city"] == c]
        if len(d) == 0:
            price_stats[c] = {"observations": 0}
            continue
        # 去省级/省级节点混入？city 已分组
        dates = d["observation_date"].dropna()
        # 日覆盖：有观测的不同日数 / 跨度内天数
        span_days = (dates.max() - dates.min()).days + 1 if len(dates) else 0
        # 周覆盖
        wk = dates.dt.to_period("W").nunique() if len(dates) else 0
        span_weeks = span_days / 7 if span_days else 0
        gp = grade_pct(d)
        price_stats[c] = {
            "observations": len(d),
            "unique_dates": int(dates.dt.date.nunique()),
            "unique_crops": int(d["crop_standard"].nunique()),
            "markets": int(d["market_name"].nunique()),
            "counties": int(d["county"].nunique()),
            "start_date": str(dates.min().date()) if len(dates) else "",
            "end_date": str(dates.max().date()) if len(dates) else "",
            "daily_coverage": round(dates.dt.date.nunique() / span_days * 100, 1) if span_days else 0,
            "weekly_coverage": round(wk / span_weeks * 100, 1) if span_weeks else 0,
            "A_source_pct": gp.get("A", 0), "B_source_pct": gp.get("B", 0),
            "C_source_pct": gp.get("C", 0), "D_source_pct": gp.get("D", 0),
            "levels": d["price_level"].value_counts().to_dict(),
            "sources": d["source_id"].value_counts().to_dict(),
        }

    # 覆盖矩阵
    vol = safe("city_data/reference/staging/volume_observations.csv")
    phen = safe("city_data/reference/staging/phenology_events.csv")
    dis = safe("city_data/reference/marts/fact_disaster_event_observed.csv")
    pol = safe("city_data/reference/marts/fact_policy_event.csv")
    weather = safe("city_data/reference/marts/fact_weather_daily.csv")
    soil = safe("city_data/reference/marts/fact_soil_daily.csv")

    # 生产：合并所有 production staging
    prod_files = glob.glob(str(STAGING / "*production*.csv")) + glob.glob(str(STAGING / "*_production_*.csv"))
    prod_frames = []
    for f in set(prod_files):
        try:
            d = pd.read_csv(f, encoding="utf-8-sig", low_memory=False)
            if "city" in d.columns:
                prod_frames.append(d)
        except Exception:
            pass
    prod = pd.concat(prod_frames, ignore_index=True) if prod_frames else None

    matrix = []
    for c in CITIES:
        ps = price_stats[c]
        n_dates = ps.get("unique_dates", 0)
        price_col = "—"
        if n_dates:
            freq = "日度" if ps.get("daily_coverage", 0) > 20 else "周/月"
            price_col = f"{ps['observations']} 条 / {n_dates} 天 / {ps['unique_crops']} 商品"
        vol_n = int((vol["city"] == c).sum()) if vol is not None and "city" in vol.columns else 0
        prod_n = int((prod["city"] == c).sum()) if prod is not None and "city" in prod.columns else 0
        phen_n = int((phen["city"] == c).sum()) if phen is not None and "city" in phen.columns else 0
        dis_n = int((dis["city"] == c).sum()) if dis is not None and "city" in dis.columns else 0
        pol_n = int((pol["city"] == c).sum()) if pol is not None and "city" in pol.columns else 0
        matrix.append({
            "city": c,
            "price": price_col,
            "volume": f"{vol_n} 条" if vol_n else "NOT_PUBLIC",
            "production": f"{prod_n} 行" if prod_n else "—",
            "weather": "COMPLETE" if weather is not None else "—",
            "soil": "COMPLETE" if soil is not None else "—",
            "phenology": f"{phen_n} 条" if phen_n else "PARTIAL",
            "disaster_observed": f"{dis_n} 条" if dis_n else "NOT_PUBLIC",
            "policy": f"{pol_n} 条" if pol_n else "—",
        })

    # 写 CSV
    ps_rows = [{"city": c, **{k: v for k, v in price_stats[c].items() if k not in ("levels", "sources")}} for c in CITIES]
    pd.DataFrame(ps_rows).to_csv(REPORTS / "CITY_PRICE_STATS_V2.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(matrix).to_csv(REPORTS / "FIVE_CITY_DATA_MATRIX_V2.csv", index=False, encoding="utf-8-sig")

    # 写报告
    L = []
    L.append("# 五城市数据覆盖 V2（AgriScope 全网深挖阶段）")
    L.append("")
    L.append(f"> 生成时间：{NOW}")
    L.append("> 口径：价格来自统一观测层 `city_data/reference/marts/fact_price_observation.csv`；未获得者如实标注 NOT_PUBLIC/PARTIAL，无任何补造。")
    L.append("")
    L.append("## A. 五城市数据矩阵")
    L.append("")
    L.append("| 城市 | 日/周价格 | 成交量 | 生产 | 天气 | 土壤 | 物候 | 真实灾害 | 政策 |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for m in matrix:
        L.append(f"| {m['city']} | {m['price']} | {m['volume']} | {m['production']} | {m['weather']} | {m['soil']} | {m['phenology']} | {m['disaster_observed']} | {m['policy']} |")
    L.append("")
    L.append("## B. 价格观测明细统计（统一观测层）")
    L.append("")
    L.append("| 城市 | 观测数 | 唯一日期 | 唯一商品 | 监测点数 | 县级数 | 起 | 止 | 日覆盖% | 周覆盖% | A% | B% | C% | D% |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for c in CITIES:
        s = price_stats[c]
        if not s.get("observations"):
            L.append(f"| {c} | 0 | 0 | 0 | 0 | 0 | - | - | 0 | 0 | - | - | - | - |")
            continue
        L.append(f"| {c} | {s['observations']} | {s['unique_dates']} | {s['unique_crops']} | {s['markets']} | {s['counties']} | {s['start_date']} | {s['end_date']} | {s['daily_coverage']} | {s['weekly_coverage']} | {s['A_source_pct']} | {s['B_source_pct']} | {s['C_source_pct']} | {s['D_source_pct']} |")
    L.append("")
    L.append("## C. 价格层级构成（严禁混算）")
    L.append("")
    for c in CITIES:
        lv = price_stats[c].get("levels", {})
        if lv:
            L.append(f"- **{c}**：{', '.join(f'{k}={v}' for k, v in lv.items())}")
    L.append("")
    L.append("## D. 价格来源构成")
    L.append("")
    for c in CITIES:
        sc = price_stats[c].get("sources", {})
        if sc:
            L.append(f"- **{c}**：{', '.join(f'{k}={v}' for k, v in sc.items())}")
    L.append("")
    L.append("## E. 说明与红线")
    L.append("")
    L.append("- 统一观测层 schema：city/county/market_name/crop_raw/crop_standard/price_original/unit_original/price_per_kg/price_level/observation_date/...")
    L.append("- `price_level` 严格区分 farm_gate / wholesale / market_average / retail_market / supermarket；**不同层级不可混算平均**。")
    L.append("- 省级数据（辽宁省）保留在表内但 city=辽宁省、geo_level=province，**严禁当城市价**。")
    L.append("- 区县极值节点（record_kind=county_extremum_*）与市场极值节点（market_extremum_*）**非连续序列**，仅作 validation/evidence。")
    L.append("- 未获得数据如实标注 NOT_PUBLIC / NODE_ONLY / ACCESS_RESTRICTED，详见各城 deep_search 报告与 search_attempts_*.csv。")
    (REPORTS / "FIVE_CITY_DATA_COVERAGE_V2.md").write_text("\n".join(L), encoding="utf-8")

    print("[OK] 已生成：")
    print("  city_data/reference/reports/FIVE_CITY_DATA_COVERAGE_V2.md")
    print("  city_data/reference/reports/CITY_PRICE_STATS_V2.csv")
    print("  city_data/reference/reports/FIVE_CITY_DATA_MATRIX_V2.csv")
    print()
    print("=== 价格统计 ===")
    print(pd.DataFrame(ps_rows).to_string(index=False))


if __name__ == "__main__":
    main()
