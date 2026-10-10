"""生成五城缺口矩阵 city_data_gap_matrix.csv。

统计口径：
- **已入库** = city_data/reference/marts/ 统一事实表（fact_price_city / fact_production_yearly / ...）
- **已发现未入库** = city_data/reference/staging/（已采集但尚未进入统一事实表）
两者分开统计，避免把 staging 当成已完成。

dataset_type: price / transaction_volume / production / planting_area / yield /
              weather / phenology / disaster / policy / market_supply
"""
from __future__ import annotations

import glob
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
MARTS = ROOT / "city_data/reference/marts"
STAGING = ROOT / "city_data/reference/staging"
REPORTS = ROOT / "city_data/reference/reports"
REPORTS.mkdir(parents=True, exist_ok=True)

FIVE = ["大连", "铁岭", "朝阳", "锦州", "丹东"]       # 搜索漏斗顺序
TARGET6 = ["沈阳", "铁岭", "朝阳", "锦州", "丹东", "大连"]
START, END = "2021-01-01", "2026-09-21"


def load(name: str) -> pd.DataFrame | None:
    p = MARTS / f"{name}.parquet"
    return pd.read_parquet(p) if p.exists() else None


def freq_of(df: pd.DataFrame) -> str:
    for c in ["date"]:
        if c in df.columns:
            return "daily"
    for c in ["week_start"]:
        if c in df.columns:
            return "weekly"
    if "year" in df.columns:
        return "yearly"
    return "event"


# ---------- 统计各层 ----------
def layer_stats() -> dict[str, pd.DataFrame]:
    out = {}
    out["price"] = load("fact_price_city")
    out["transaction_volume"] = load("fact_market_supply")
    out["production"] = load("fact_production_yearly")
    out["production_2020_2024"] = load("fact_production_yearly_2020_2024")
    out["weather"] = load("fact_weather_daily")
    out["disaster"] = load("fact_disaster_events")
    out["pest"] = load("fact_pest_events")
    return out


def staging_stats() -> pd.DataFrame:
    rows = []
    for f in sorted(glob.glob(str(STAGING / "*.csv"))):
        n = Path(f).name
        try:
            d = pd.read_csv(f)
        except Exception as e:
            rows.append({"file": n, "rows": None, "error": str(e)[:60]})
            continue
        city = ""
        for c in ["city", "city_name"]:
            if c in d.columns:
                v = list(d[c].dropna().unique())
                city = "/".join(str(x) for x in v[:3])
                break
        dcol = next((c for c in ["period_date", "article_date", "publish_date",
                                 "date", "year"] if c in d.columns), None)
        lo = hi = None
        if dcol:
            try:
                s = pd.to_datetime(d[dcol], errors="coerce").dropna()
                if len(s):
                    lo, hi = str(s.min())[:10], str(s.max())[:10]
            except Exception:
                if dcol == "year":
                    s = pd.to_numeric(d[dcol], errors="coerce").dropna()
                    if len(s):
                        lo, hi = str(int(s.min())), str(int(s.max()))
        kind = "production" if "production" in n or "prod" in n else (
            "price" if "price" in n else "other")
        rows.append({"file": n, "rows": len(d), "error": "", "city": city,
                     "kind": kind, "start": lo, "end": hi})
    return pd.DataFrame(rows)


def main() -> None:
    L = layer_stats()
    st = staging_stats()

    # 各层每日/每周期望记录数（用于算缺失）
    n_days = (pd.Timestamp(END) - pd.Timestamp(START)).days + 1
    n_weeks = n_days // 7
    n_years = 9          # 2017-2025

    rows = []
    # ---------- price ----------
    pc = L["price"]
    for city in TARGET6:
        if pc is None:
            continue
        g = pc[pc["city"] == city] if "city" in pc.columns else pd.DataFrame()
        # staging 中该城市价格
        sg = st[(st["kind"] == "price") & (st["city"].astype(str).str.contains(city, na=False))]
        st_rows = int(sg["rows"].fillna(0).sum())
        actual = len(g)
        rows.append({
            "city": city, "dataset_type": "price", "crop": "-",
            "start_date": str(g["date"].min()) if len(g) else "-",
            "end_date": str(g["date"].max()) if len(g) else "-",
            "expected_frequency": "daily", "actual_frequency": freq_of(g) if len(g) else "-",
            "expected_records": n_days, "actual_records": actual,
            "staging_unmerged": st_rows,
            "missing_periods": f"{n_days - actual} 天" if actual else f"全部 {n_days} 天",
            "source_status": "COMPLETE" if actual > 1000 else (
                "PARTIAL" if actual > 0 else ("STAGING_ONLY" if st_rows else "NOT_FOUND")),
            "current_source": ("沈阳菜篮子平台" if city == "沈阳" else
                               ("大连政府文章" if actual else
                                "; ".join(sg["file"].tolist()[:3]))),
            "quality_grade": "A" if actual > 1000 else ("B" if actual else "-"),
            "next_search_priority": 0 if actual > 1000 else (1 if st_rows else 2),
        })
    # ---------- transaction_volume ----------
    ms = L["transaction_volume"]
    for city in TARGET6:
        g = ms[ms["city"] == city] if (ms is not None and "city" in ms.columns) else pd.DataFrame()
        rows.append({
            "city": city, "dataset_type": "transaction_volume", "crop": "-",
            "start_date": str(g["date"].min()) if len(g) else "-",
            "end_date": str(g["date"].max()) if len(g) else "-",
            "expected_frequency": "daily", "actual_frequency": "daily" if len(g) else "-",
            "expected_records": n_days, "actual_records": len(g), "staging_unmerged": 0,
            "missing_periods": f"{n_days - len(g)} 天" if len(g) else f"全部 {n_days} 天",
            "source_status": "COMPLETE" if len(g) > 1000 else ("NOT_FOUND" if not len(g) else "PARTIAL"),
            "current_source": "沈阳菜篮子平台 volume" if len(g) else "-",
            "quality_grade": "A" if len(g) else "-",
            "next_search_priority": 0 if len(g) > 1000 else 2,
        })
    # ---------- production / planting_area / yield ----------
    py, py2 = L["production"], L["production_2020_2024"]
    for city in TARGET6:
        for dtype, col in [("production", "production"), ("planting_area", "planting_area"),
                           ("yield", "yield_per_area")]:
            a = len(py[(py["city"] == city) & py[col].notna()]) if py is not None and col in py.columns else 0
            b = 0
            if py2 is not None:
                c2 = {"production": "production_ton", "planting_area": "planting_area_kha",
                      "yield": "yield_kg_per_ha"}.get(dtype)
                if c2 and c2 in py2.columns:
                    b = len(py2[(py2["city"] == city) & py2[c2].notna()])
            tot = a + b
            sg = st[(st["kind"] == "production") & (st["city"].astype(str).str.contains(city, na=False))]
            st_rows = int(sg["rows"].fillna(0).sum())
            rows.append({
                "city": city, "dataset_type": dtype, "crop": "-",
                "start_date": "2017" if a else ("2020" if b else "-"),
                "end_date": "2019" if a else ("2024" if b else "-"),
                "expected_frequency": "yearly", "actual_frequency": "yearly" if tot else "-",
                "expected_records": n_years, "actual_records": tot,
                "staging_unmerged": st_rows,
                "missing_periods": f"缺 {n_years - tot} 年（2025 起未覆盖）" if tot else f"全部 {n_years} 年",
                "source_status": "PARTIAL" if tot else ("STAGING_ONLY" if st_rows else "NOT_FOUND"),
                "current_source": "统计年鉴(2017-19)+扫描转录(2020-24)",
                "quality_grade": "A/B",
                "next_search_priority": 3,
            })
    # ---------- weather ----------
    w = L["weather"]
    for city in TARGET6:
        g = w[w["city"] == city] if w is not None else pd.DataFrame()
        rows.append({
            "city": city, "dataset_type": "weather", "crop": "-",
            "start_date": str(g["date"].min()) if len(g) else "-",
            "end_date": str(g["date"].max()) if len(g) else "-",
            "expected_frequency": "daily", "actual_frequency": "daily" if len(g) else "-",
            "expected_records": n_days, "actual_records": len(g), "staging_unmerged": 0,
            "missing_periods": "无" if len(g) >= 2000 else f"{n_days - len(g)} 天",
            "source_status": "COMPLETE", "current_source": "Open-Meteo ERA5 再分析",
            "quality_grade": "C", "next_search_priority": 9,
        })
    # ---------- phenology ----------
    cal = ROOT / "data/raw/metadata" / "crop_calendar.csv"
    n_cal = len(pd.read_csv(cal)) if cal.exists() else 0
    for city in TARGET6:
        rows.append({
            "city": city, "dataset_type": "phenology", "crop": "玉米/水稻/大豆/花生(仅粮油)",
            "start_date": "-", "end_date": "-", "expected_frequency": "yearly(生育期)",
            "actual_frequency": "static" if n_cal else "-",
            "expected_records": 10, "actual_records": n_cal, "staging_unmerged": 0,
            "missing_periods": "蔬菜类作物全部缺物候" if n_cal else "全缺",
            "source_status": "PARTIAL" if n_cal else "NOT_FOUND",
            "current_source": "统计年鉴/农业技术资料", "quality_grade": "B",
            "next_search_priority": 4,
        })
    # ---------- disaster ----------
    dv = L["disaster"]
    for city in TARGET6:
        g = dv[dv["city"] == city] if dv is not None else pd.DataFrame()
        rows.append({
            "city": city, "dataset_type": "disaster", "crop": "-",
            "start_date": str(g["start_date"].min()) if len(g) else "-",
            "end_date": str(g["start_date"].max()) if len(g) else "-",
            "expected_frequency": "event", "actual_frequency": "event" if len(g) else "-",
            "expected_records": None, "actual_records": len(g), "staging_unmerged": 0,
            "missing_periods": "无真实农业损失字段（成灾/绝收/经济损失官方未公布）",
            "source_status": "PARTIAL(阈值派生)", "current_source": "ERA5 日值阈值识别",
            "quality_grade": "C", "next_search_priority": 5,
        })
    # ---------- market_supply / policy ----------
    for city in TARGET6:
        for dtype in ["market_supply", "policy"]:
            rows.append({
                "city": city, "dataset_type": dtype, "crop": "-",
                "start_date": "-", "end_date": "-", "expected_frequency": "daily/event",
                "actual_frequency": "-", "expected_records": None, "actual_records": 0,
                "staging_unmerged": 0, "missing_periods": "未建立",
                "source_status": "NOT_FOUND", "current_source": "-", "quality_grade": "-",
                "next_search_priority": 6,
            })

    df = pd.DataFrame(rows)
    df = df.sort_values(["city", "next_search_priority", "dataset_type"])
    df.to_csv(REPORTS / "city_data_gap_matrix.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] city_data_gap_matrix.csv {len(df)} 行")
    print()
    print("=== 五城关键缺口（按搜索优先级）===")
    for city in FIVE:
        sub = df[df["city"] == city]
        print(f"\n【{city}】")
        for _, r in sub.iterrows():
            flag = "✅" if r["source_status"] == "COMPLETE" else (
                "⚠️" if "PARTIAL" in str(r["source_status"]) else
                ("📥" if "STAGING" in str(r["source_status"]) else "❌"))
            print(f"  {flag} {r['dataset_type']:20s} 已入库={r['actual_records']:>6}  "
                  f"staging待入库={r['staging_unmerged']:>5}  状态={r['source_status']}")


if __name__ == "__main__":
    main()
