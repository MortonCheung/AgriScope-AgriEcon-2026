"""生成外部审计用数据快照包 city_data/reference/reports/REVIEW_BUNDLE/。

所有统计**从磁盘实际文件重新计算**，不引用任何旧报告结论。
不复制大型 Raw 数据，只生成摘要与索引。
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime, date
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
MARTS = ROOT / "city_data/reference/marts"
CURATED = ROOT / "city_data/reference/curated"
META = ROOT / "data/raw/metadata"
REPORTS = ROOT / "city_data/reference/reports"
OUT = REPORTS / "REVIEW_BUNDLE"
OUT.mkdir(parents=True, exist_ok=True)

TARGET6 = ["沈阳", "铁岭", "朝阳", "锦州", "丹东", "大连"]
GEN_AT = datetime.now().isoformat(timespec="seconds")


def load(name: str) -> pd.DataFrame | None:
    p = MARTS / f"{name}.parquet"
    if not p.exists():
        return None
    try:
        return pd.read_parquet(p)
    except Exception:
        return None


def date_range(df: pd.DataFrame) -> tuple[str | None, str | None, str]:
    """返回 (start, end, frequency)。年份列按整数处理，不做 to_datetime。"""
    # 真正的日期列
    for c in ["date", "week_start", "period_start", "effective_date", "start_date"]:
        if c in df.columns:
            s = pd.to_datetime(df[c], errors="coerce").dropna()
            if len(s) == 0:
                continue
            lo, hi = str(s.min())[:10], str(s.max())[:10]
            freq = "daily" if c == "date" else ("weekly" if "week" in c else "event")
            return lo, hi, freq
    # 整数年份列
    for c in ["year"]:
        if c in df.columns:
            s = pd.to_numeric(df[c], errors="coerce").dropna()
            if len(s):
                return f"{int(s.min())}", f"{int(s.max())}", "yearly"
    return None, None, "unknown"


def prod_count(df: pd.DataFrame) -> int:
    for c in ["crop", "crop_raw", "product", "input_name", "productName"]:
        if c in df.columns:
            return int(df[c].nunique())
    return 0


def cities_of(df: pd.DataFrame) -> str:
    if "city" not in df.columns:
        return ""
    return "/".join(sorted(str(x) for x in df["city"].dropna().unique()))


# 数据集 → (category, source, quality_grade, status)
META_MAP = {
    "fact_weather_daily": ("weather", "Open-Meteo ERA5 再分析", "C", "COMPLETE"),
    "fact_weather_extra_daily": ("weather", "Open-Meteo ERA5 再分析", "C", "COMPLETE"),
    "fact_weather_weekly": ("weather", "Open-Meteo ERA5 再分析(派生周)", "C", "COMPLETE"),
    "fact_soil_daily": ("soil", "Open-Meteo ERA5-Land 再分析", "C", "COMPLETE"),
    "fact_city_climate_official": ("weather", "辽宁统计年鉴 官方城市气象汇总", "A", "PARTIAL"),
    "fact_price_city": ("price", "沈阳菜篮子平台/大连价格文章", "A/B", "PARTIAL"),
    "fact_price_city_extremum_weekly": ("price", "辽宁农业农村厅 周报极值", "B", "PARTIAL"),
    "fact_shenyang_price_weekly": ("price", "沈阳菜篮子平台(派生周)", "A", "COMPLETE"),
    "fact_price_weekly": ("price", "省级基准+农资城市", "A", "COMPLETE"),
    "fact_input_cost_weekly": ("input_cost", "辽宁农业农村厅 农资周报", "A", "COMPLETE"),
    "fact_market_supply": ("supply", "沈阳菜篮子平台 volume", "A", "PARTIAL"),
    "fact_production_yearly": ("production", "辽宁统计年鉴 2017-2019", "A", "PARTIAL"),
    "fact_production_yearly_2020_2024": ("production",
        "辽宁统计年鉴2021-2025卷(扫描JPG目视转录)", "B", "PARTIAL"),
    "fact_agri_conditions": ("production", "辽宁统计年鉴 农业条件", "A", "PARTIAL"),
    "fact_yearbook_wide": ("macro", "辽宁统计年鉴 宽表", "A", "PARTIAL"),
    "fact_disaster_events": ("disaster", "气象阈值派生事件", "C", "PARTIAL"),
    "weekly_disaster_exposure": ("disaster", "派生(气象阈值周暴露)", "C", "PARTIAL"),
    "fact_disaster_reports": ("disaster", "政府网站灾情文本", "B", "PARTIAL"),
    "fact_pest_events": ("pest", "农业农村厅 病虫害文本", "B", "PARTIAL"),
    "fact_fuel_price": ("macro", "辽宁发改委 成品油公告", "A", "PARTIAL"),
    "dim_calendar": ("macro", "国务院节假日安排", "A", "COMPLETE"),
    "city_crop_week_panel": ("panel", "派生建模主表", "A/B", "PARTIAL"),
    "city_crop_year_panel": ("panel", "派生年度面板", "A", "PARTIAL"),
    "province_crop_week_panel": ("panel", "派生省级面板", "A", "COMPLETE"),
    "event_study_panel": ("panel", "派生事件研究面板", "B", "PARTIAL"),
}


def build_inventory() -> pd.DataFrame:
    rows = []
    for f in sorted(MARTS.glob("*.parquet")):
        n = f.stem
        df = load(n)
        if df is None:
            continue
        lo, hi, freq = date_range(df)
        cat, src, grade, status = META_MAP.get(n, ("other", "-", "-", "-"))
        rows.append({
            "city": cities_of(df) or "-",
            "category": cat,
            "file": f"{n}.parquet",
            "rows": len(df),
            "start_date": lo or "-",
            "end_date": hi or "-",
            "frequency": freq,
            "products": prod_count(df),
            "source": src,
            "quality_grade": grade,
            "status": status,
        })
    return pd.DataFrame(rows)


def build_price_coverage() -> pd.DataFrame:
    rows = []
    # 1) 沈阳日度（fact_price_city 中沈阳部分）
    pc = load("fact_price_city")
    if pc is not None:
        p = pc[pc["date"].astype(str).str.match(r"^\d{4}-\d{2}-\d{2}$")].copy()
        for (city, ptype), g in p.groupby(["city", "price_type"], dropna=False):
            if pd.isna(city):
                continue
            g = g.sort_values("date")
            d = pd.to_datetime(g["date"])
            cal = d.dt.isocalendar()
            weeks = int(pd.DataFrame({"y": cal.year, "w": cal.week}).drop_duplicates().shape[0])
            exp = max(len(pd.date_range(d.min(), d.max(), freq="W-MON")), 1)
            rows.append({
                "city": city, "price_type": ptype, "scope": "city",
                "products": int(g["crop_raw"].nunique()),
                "start_date": str(g["date"].min()), "end_date": str(g["date"].max()),
                "observation_days": int(d.nunique()),
                "valid_weeks": weeks,
                "frequency": "daily",
                "missing_rate": round(max(0.0, 1 - weeks / exp), 3),
                "source_file": "fact_price_city.parquet",
                "source": "沈阳菜篮子平台" if city == "沈阳" else "大连政府价格文章",
                "quality_grade": "A" if city == "沈阳" else "B",
            })
        # 省级（city 为空）
        prov = p[p["city"].isna()]
        if len(prov):
            d = pd.to_datetime(prov["date"])
            cal = d.dt.isocalendar()
            weeks = int(pd.DataFrame({"y": cal.year, "w": cal.week}).drop_duplicates().shape[0])
            exp = max(len(pd.date_range(d.min(), d.max(), freq="W-MON")), 1)
            rows.append({
                "city": "辽宁省(省级)", "price_type": "retail", "scope": "province",
                "products": int(prov["crop_raw"].nunique()),
                "start_date": str(prov["date"].min()), "end_date": str(prov["date"].max()),
                "observation_days": int(d.nunique()),
                "valid_weeks": weeks, "frequency": "daily",
                "missing_rate": round(max(0.0, 1 - weeks / exp), 3),
                "source_file": "fact_price_city.parquet",
                "source": "辽宁省发改委 每日价格", "quality_grade": "A",
            })
    # 2) 六城市极值周价（非连续，仅极值）
    ex = load("fact_price_city_extremum_weekly")
    if ex is not None:
        for city, g in ex.groupby("city", dropna=False):
            if pd.isna(city):
                continue
            d = pd.to_datetime(g["week_start"], errors="coerce").dropna()
            rows.append({
                "city": city, "price_type": "extremum(high/low)", "scope": "city",
                "products": prod_count(g),
                "start_date": str(d.min())[:10] if len(d) else "-",
                "end_date": str(d.max())[:10] if len(d) else "-",
                "observation_days": int(len(d)),
                "valid_weeks": int(d.nunique()),
                "frequency": "weekly",
                "missing_rate": None,
                "source_file": "fact_price_city_extremum_weekly.parquet",
                "source": "辽宁农业农村厅周报（最高/最低价所在地，非连续城市价）",
                "quality_grade": "B",
            })
    # 3) 省级周价基准
    pw = load("province_crop_week_panel")
    if pw is not None:
        d = pd.to_datetime(pw["week_start"], errors="coerce").dropna()
        rows.append({
            "city": "辽宁省(省级)", "price_type": "province_avg", "scope": "province",
            "products": prod_count(pw),
            "start_date": str(d.min())[:10], "end_date": str(d.max())[:10],
            "observation_days": None, "valid_weeks": int(d.nunique()),
            "frequency": "weekly", "missing_rate": None,
            "source_file": "province_crop_week_panel.parquet",
            "source": "辽宁农业农村厅省级均价", "quality_grade": "A",
        })
    # 4) 农资（城市级连续）
    ic = load("fact_input_cost_weekly")
    if ic is not None:
        for city in TARGET6:
            g = ic[ic["city"] == city]
            if not len(g):
                continue
            d = pd.to_datetime(g["week_start"], errors="coerce").dropna()
            rows.append({
                "city": city, "price_type": "input_cost", "scope": "city",
                "products": int(g["input_name"].nunique()),
                "start_date": str(d.min())[:10], "end_date": str(d.max())[:10],
                "observation_days": None, "valid_weeks": int(d.nunique()),
                "frequency": "weekly", "missing_rate": None,
                "source_file": "fact_input_cost_weekly.parquet",
                "source": "辽宁农业农村厅农资周报", "quality_grade": "A",
            })
    return pd.DataFrame(rows)


def build_production_coverage() -> pd.DataFrame:
    rows = []
    for c in TARGET6:
        rec = {"city": c}
        for label, name in [("yearbook_2017_2019", "fact_production_yearly"),
                            ("bulletin_2020_2024", "fact_production_yearly_2020_2024")]:
            df = load(name)
            if df is None:
                rec[f"{label}_years"] = 0
                rec[f"{label}_crops"] = 0
                continue
            g = df[df["city"] == c]
            if not len(g):
                rec[f"{label}_years"] = 0
                rec[f"{label}_crops"] = 0
                continue
            yrs = sorted(int(x) for x in pd.to_numeric(g["year"], errors="coerce").dropna().unique())
            # 宽表列名在不同来源间不一致：
            # 年鉴=planting_area / 2020-2024转录表=planting_area_kha, production_ton
            pa_col = next((c for c in ["planting_area", "planting_area_kha"]
                           if c in g.columns), None)
            pr_col = next((c for c in ["production", "production_ton", "output"]
                           if c in g.columns), None)
            pa = int(g.dropna(subset=[pa_col])["year"].nunique()) if pa_col else 0
            pr = int(g.dropna(subset=[pr_col])["year"].nunique()) if pr_col else 0
            if "qc_consistency" in g.columns:
                qc = g["qc_consistency"].astype(str)
                rec[f"{label}_qc_pass"] = int(qc.str.startswith("PASS").sum())
                rec[f"{label}_qc_fail"] = int((~qc.str.startswith("PASS")).sum())
            if "extraction_method" in g.columns:
                rec[f"{label}_extraction"] = str(g["extraction_method"].iloc[0])
            if "quality_grade" in g.columns:
                rec[f"{label}_grade"] = str(g["quality_grade"].iloc[0])
            rec[f"{label}_years"] = len(yrs)
            rec[f"{label}_crops"] = int(g["crop"].nunique()) if "crop" in g.columns else 0
            rec[f"{label}_planting_years"] = pa
            rec[f"{label}_production_years"] = pr
            rec[f"{label}_range"] = f"{yrs[0]}-{yrs[-1]}" if yrs else "-"
        yrs_all = []
        for k in ["yearbook_2017_2019_range", "bulletin_2020_2024_range"]:
            v = rec.get(k, "-")
            if v != "-":
                yrs_all += [int(x) for x in v.split("-")]
        rec["covered_years"] = f"{min(yrs_all)}-{max(yrs_all)}" if yrs_all else "-"
        rec["years_missing_2017_2025"] = ",".join(
            str(y) for y in range(2017, 2026)
            if not any(a <= y <= b for a, b in
                       [(int(rec.get('yearbook_2017_2019_range', '0-0').split('-')[0] or 0),
                         int(rec.get('yearbook_2017_2019_range', '0-0').split('-')[-1] or 0)),
                        (int(rec.get('bulletin_2020_2024_range', '0-0').split('-')[0] or 0),
                         int(rec.get('bulletin_2020_2024_range', '0-0').split('-')[-1] or 0))]
                       if a and b))
        rows.append(rec)
    return pd.DataFrame(rows)


def build_supply_coverage() -> pd.DataFrame:
    rows = []
    ms = load("fact_market_supply")
    if ms is not None:
        for city, g in ms.groupby("city", dropna=False):
            d = pd.to_datetime(g["date"], errors="coerce").dropna()
            rows.append({
                "city": city, "metric": "supply_volume(成交量)",
                "products": int(g["crop"].nunique()),
                "start_date": str(d.min())[:10], "end_date": str(d.max())[:10],
                "observation_days": int(d.nunique()), "frequency": "daily",
                "unit_raw": str(g["unit_raw"].iloc[0]),
                "source": "沈阳菜篮子平台 volume 字段", "quality_grade": "A",
                "status": "COMPLETE(仅沈阳)",
            })
    for c in TARGET6:
        if c == "沈阳":
            continue
        rows.append({
            "city": c, "metric": "supply_volume(成交量)", "products": 0,
            "start_date": "-", "end_date": "-", "observation_days": 0,
            "frequency": "-", "unit_raw": "-",
            "source": "-", "quality_grade": "-", "status": "NOT_FOUND",
        })
    return pd.DataFrame(rows)


def build_crop_coverage() -> pd.DataFrame:
    cal = pd.DataFrame()
    agr = pd.DataFrame()
    p1, p2 = META / "crop_calendar.csv", META / "crop_agronomy.csv"
    if p1.exists():
        cal = pd.read_csv(p1)
    if p2.exists():
        agr = pd.read_csv(p2)
    cand = pd.DataFrame()
    cp = REPORTS / "candidate_crops.csv"
    if cp.exists():
        cand = pd.read_csv(cp)

    rows = []
    crops = set()
    if len(cal):
        crops |= set(cal["crop"].dropna())
    if len(agr):
        crops |= set(agr["crop"].dropna())
    if len(cand):
        crops |= set(cand["crop"].dropna())

    for crop in sorted(crops):
        in_cal = (len(cal) and crop in set(cal["crop"].dropna()))
        in_agr = (len(agr) and crop in set(agr["crop"].dropna()))
        cities = []
        if len(cand):
            cities = sorted(cand[cand["crop"] == crop]["city"].dropna().unique())
        rows.append({
            "crop": crop,
            "is_candidate": bool(len(cand) and crop in set(cand["crop"].dropna())),
            "candidate_cities": "/".join(cities) if cities else "-",
            "has_phenology": bool(in_cal),
            "phenology_source": ("辽宁统计年鉴/农业技术资料" if in_cal else "-"),
            "has_agronomy_sensitivity": bool(in_agr),
            "sensitivity_stages": int((agr["crop"] == crop).sum()) if len(agr) else 0,
            "gap": "-" if (in_cal and in_agr) else ("缺物候" if not in_cal else "缺敏感性"),
        })
    return pd.DataFrame(rows)


def build_disaster_coverage() -> pd.DataFrame:
    rows = []
    ev = load("fact_disaster_events")
    if ev is not None:
        for city, g in ev.groupby("city", dropna=False):
            if pd.isna(city):
                continue
            d = pd.to_datetime(g["start_date"], errors="coerce").dropna()
            rows.append({
                "city": city, "dataset": "derived_weather_events(阈值派生)",
                "events": int(len(g)),
                "types": "/".join(sorted(str(x) for x in g["event_type"].dropna().unique())),
                "start_date": str(d.min())[:10] if len(d) else "-",
                "end_date": str(d.max())[:10] if len(d) else "-",
                "has_official_loss": "NO",
                "source": "Open-Meteo ERA5 日值阈值识别", "quality_grade": "C",
            })
    we = load("weekly_disaster_exposure")
    if we is not None:
        tot = int(we["extreme_weather_flag"].sum()) if "extreme_weather_flag" in we.columns else 0
        rows.append({
            "city": "/".join(TARGET6), "dataset": "weekly_disaster_exposure",
            "events": int(len(we)), "types": "extreme_week_flag",
            "start_date": str(pd.to_datetime(we["week_start"]).min())[:10],
            "end_date": str(pd.to_datetime(we["week_start"]).max())[:10],
            "has_official_loss": "NO",
            "source": "派生(气象阈值)", "quality_grade": "C",
        })
    # 官方灾情
    od = ROOT / "data/raw" / "disaster" / "official_2026" / "official_agricultural_disaster_events.json"
    if od.exists():
        try:
            data = json.loads(od.read_text(encoding="utf-8"))
        except Exception:
            data = []
        for e in data:
            rows.append({
                "city": str(e.get("city") or "辽宁省(省级，city=null)"),
                "dataset": "official_agricultural_disaster_events",
                "events": 1, "types": str(e.get("event_type")),
                "start_date": str(e.get("start_date")), "end_date": str(e.get("end_date")),
                "has_official_loss": "YES",
                "source": "辽宁省政府/农业农村部信息网/人民网辽宁", "quality_grade": "A",
            })
    dr = load("fact_disaster_reports")
    if dr is not None:
        rows.append({
            "city": "辽宁省(省级)", "dataset": "fact_disaster_reports(文本)",
            "events": int(len(dr)), "types": "text",
            "start_date": "-", "end_date": "-", "has_official_loss": "部分",
            "source": "水利厅/农业农村厅", "quality_grade": "B",
        })
    return pd.DataFrame(rows)


def project_tree() -> str:
    skip_dirs = {"node_modules", ".git", "__pycache__", ".workbuddy", "deliverables",
                 "review_bundle", "REVIEW_BUNDLE", "html", "yearbook_2018", "yearbook_2019",
                 "yearbook_2020", "shenyang_clz", "liaoning_fgw_daily", "大连_articles",
                 "official_2026", "samples"}
    lines = [f"# 项目树（生成时间 {GEN_AT}）",
             "# 说明：已排除 node_modules / .git / 缓存 / 大型 Raw 明细目录", ""]
    for dirpath, dirnames, filenames in sorted(os.walk(ROOT) if False else __import__("os").walk(ROOT)):
        rel = Path(dirpath).relative_to(ROOT)
        parts = set(rel.parts)
        if parts & skip_dirs:
            dirnames[:] = [d for d in dirnames if d not in skip_dirs]
            continue
        dirnames[:] = sorted([d for d in dirnames if d not in skip_dirs])
        depth = 0 if str(rel) == "." else len(rel.parts)
        if depth <= 3:
            label = ROOT.name if str(rel) == "." else rel.name     # 只显示末级目录名
            lines.append("  " * depth + f"[{label}/]")
        if depth <= 3:
            fs = sorted(filenames)
            if len(fs) > 40:
                fs = fs[:40] + [f"... 其余 {len(filenames)-40} 个文件略"]
            for f in fs:
                if f.startswith(".") or f.endswith((".pyc",)):
                    continue
                lines.append("  " * (depth + 1) + f)
    return "\n".join(lines)


def main() -> None:
    print("=" * 70)
    print("生成审计快照包（全部从磁盘重新计算）")
    print("=" * 70)

    inv = build_inventory()
    inv.to_csv(OUT / "02_DATA_INVENTORY.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] 02_DATA_INVENTORY.csv  {len(inv)} 个数据集")

    pc = build_price_coverage()
    pc.to_csv(OUT / "03_PRICE_COVERAGE.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] 03_PRICE_COVERAGE.csv  {len(pc)} 行")

    pr = build_production_coverage()
    pr.to_csv(OUT / "04_PRODUCTION_COVERAGE.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] 04_PRODUCTION_COVERAGE.csv  {len(pr)} 行")

    sp = build_supply_coverage()
    sp.to_csv(OUT / "05_SUPPLY_COVERAGE.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] 05_SUPPLY_COVERAGE.csv  {len(sp)} 行")

    cr = build_crop_coverage()
    cr.to_csv(OUT / "06_CROP_COVERAGE.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] 06_CROP_COVERAGE.csv  {len(cr)} 行")

    di = build_disaster_coverage()
    di.to_csv(OUT / "07_DISASTER_COVERAGE.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] 07_DISASTER_COVERAGE.csv  {len(di)} 行")

    (OUT / "09_PROJECT_TREE.txt").write_text(project_tree(), encoding="utf-8")
    print("[OK] 09_PROJECT_TREE.txt")

    # 复制报告文件
    copied = []
    for f in sorted(REPORTS.glob("*_data_collection_report.md")):
        shutil.copy2(f, OUT / f.name)
        copied.append(f.name)
    for name in ["CORE_DATA_READINESS.csv", "source_registry.csv",
                 "FIVE_CITY_DATA_MATRIX.csv", "CITY_AUDIT_MATRIX.csv"]:
        src = REPORTS / name
        if src.exists():
            shutil.copy2(src, OUT / name)
            copied.append(name)
        else:
            print(f"     [不存在，跳过] {name}")
    print(f"[OK] 复制 {len(copied)} 个文件: {copied}")


if __name__ == "__main__":
    main()
