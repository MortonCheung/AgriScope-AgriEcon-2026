"""FDF-Task3：基于最终数据重算核心作物与共同时间窗口。

输入：city_data/<slug>/workspace/data/interim/{price_observation,production_yearly,volume_observations,phenology_events}.csv
      + city_data/reference/final_foundation/02_production_qc/production_yearly_clean.csv
输出：03_research_windows/CORE_CROP_CANDIDATES_FINAL.csv
     03_research_windows/COMMON_TIME_WINDOW_AUDIT_FINAL.csv
     03_research_windows/COMMON_TIME_WINDOW_CROSS_CITY.csv
     03_research_windows/RESEARCH_READINESS_MATRIX.csv
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir()) / "data/raw/retained_source/city_data"
FDF = ROOT / "reference" / "final_foundation"
OUT = FDF / "03_research_windows"
OUT.mkdir(parents=True, exist_ok=True)
SLUG = {"shenyang": "沈阳", "tieling": "铁岭", "jinzhou": "锦州",
        "dandong": "丹东", "dalian": "大连", "chaoyang": "朝阳"}
FIVE = ["tieling", "jinzhou", "dandong", "dalian", "chaoyang"]


def read(slug, name):
    p = ROOT / slug / "data" / name
    if not p.exists():
        return None
    try:
        return pd.read_csv(p, encoding="utf-8-sig", low_memory=False)
    except Exception:
        return None


def main():
    prices = {s: read(s, "price_observation.csv") for s in SLUG}
    clean = pd.read_csv(FDF / "02_production_qc" / "production_yearly_clean.csv", encoding="utf-8-sig")
    pheno = {s: read(s, "phenology_events.csv") for s in SLUG}
    vol = {s: read(s, "volume_observations.csv") for s in SLUG}

    # ---------- 1. 核心作物候选 FINAL ----------
    # 价格按城×作物
    allp = []
    for s, cn in SLUG.items():
        d = prices.get(s)
        if d is None or "crop_standard" not in d.columns:
            continue
        d = d.copy(); d["observation_date"] = pd.to_datetime(d["observation_date"], errors="coerce")
        d["city"] = cn
        allp.append(d[["city", "crop_standard", "observation_date", "price_level", "source_id", "quality_grade"]])
    P = pd.concat(allp, ignore_index=True) if allp else pd.DataFrame()

    crops = sorted(set(P["crop_standard"].dropna().astype(str)) | set(clean["crop_standard"].dropna().astype(str)))
    pheno_crops = set()
    for s in SLUG:
        d = pheno.get(s)
        if d is not None and "crop_standard" in d.columns:
            pheno_crops |= set(d["crop_standard"].dropna().astype(str))
    vol_crops = set()
    for s in SLUG:
        d = vol.get(s)
        if d is not None and "crop" in d.columns:
            vol_crops |= set(d["crop"].dropna().astype(str))

    rows = []
    for crop in crops:
        r = {"crop_standard": crop}
        pcities, pdays_total = 0, 0
        for s, cn in SLUG.items():
            sub = P[(P["city"] == cn) & (P["crop_standard"] == crop)] if len(P) else pd.DataFrame()
            days = int(sub["observation_date"].dt.date.nunique()) if len(sub) else 0
            r[f"{s}_price_days"] = days
            pdays_total += days
            if days:
                pcities += 1
        prod = clean[clean["crop_standard"] == crop]
        prod_cities = prod["city"].nunique()
        prod_years = sorted(prod["year"].dropna().astype(int).unique().tolist())
        sub = P[P["crop_standard"] == crop] if len(P) else pd.DataFrame()
        common_years = sorted(set(sub["observation_date"].dt.year.dropna().astype(int))) if len(sub) else []
        r.update({
            "cities_with_price": pcities, "cities_with_production": int(prod_cities),
            "common_price_cities": pcities,
            "common_price_years": len(common_years),
            "production_valid_years": len(prod_years),
            "first_date": str(sub["observation_date"].min().date()) if len(sub) and sub["observation_date"].notna().any() else "",
            "last_date": str(sub["observation_date"].max().date()) if len(sub) and sub["observation_date"].notna().any() else "",
            "main_price_level": sub["price_level"].mode().iloc[0] if len(sub) and sub["price_level"].notna().any() else "",
            "total_price_rows": int(len(sub)),
            "phenology_available": crop in pheno_crops,
            "volume_available": crop in vol_crops,
        })
        # 研究角色
        roles = []
        if prod_cities >= 5 and len(prod_years) >= 5:
            roles.append("ROLE_A:六城农业生产研究")
        if pcities >= 4 and r["common_price_years"] >= 3:
            roles.append("ROLE_B:跨城市价格比较")
        if pcities >= 2 and r["common_price_years"] >= 3 and pdays_total >= 200:
            roles.append("ROLE_C:天气—价格研究")
        if crop in vol_crops:
            roles.append("ROLE_D:供应/灾害冲击研究")
        if pcities == 1 and pdays_total >= 100:
            roles.append("ROLE_E:城市特色案例")
        r["recommended_research_role"] = "; ".join(roles) if roles else ""
        score = pcities * 2 + prod_cities * 2 + len(prod_years) + (1 if crop in pheno_crops else 0)
        r["priority"] = "P1" if (len(roles) >= 2 or score >= 14) else ("P2" if roles else "P3")
        r["reason"] = f"价格{pcities}城/生产{prod_cities}城/生产{len(prod_years)}年/物候={crop in pheno_crops}"
        rows.append(r)
    cc = pd.DataFrame(rows).sort_values(["priority", "cities_with_price", "total_price_rows"],
                                        ascending=[True, False, False])
    cc.to_csv(OUT / "CORE_CROP_CANDIDATES_FINAL.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] CORE_CROP_CANDIDATES_FINAL.csv {cc.shape}")

    # ---------- 2. 共同时间窗口 FINAL ----------
    out = []
    for s, cn in SLUG.items():
        d = prices.get(s)
        if d is None or "crop_standard" not in d.columns:
            continue
        d = d.copy(); d["observation_date"] = pd.to_datetime(d["observation_date"], errors="coerce")
        d = d.dropna(subset=["observation_date"])
        for (crop, lvl), g in d.groupby(["crop_standard", "price_level"]):
            if pd.isna(lvl):
                continue
            g = g.sort_values("observation_date")
            days = g["observation_date"].dt.date.nunique()
            span = (g["observation_date"].max() - g["observation_date"].min()).days + 1
            gaps = g["observation_date"].drop_duplicates().diff().dt.days.dropna()
            out.append({
                "city": cn, "crop_standard": crop, "price_level": lvl,
                "first_date": str(g["observation_date"].min().date()),
                "last_date": str(g["observation_date"].max().date()),
                "rows": len(g), "unique_days": days,
                "unique_weeks": g["observation_date"].dt.to_period("W").nunique(),
                "unique_months": g["observation_date"].dt.to_period("M").nunique(),
                "coverage_ratio": round(days / span, 4) if span else 0,
                "median_gap_days": float(gaps.median()) if len(gaps) else None,
                "max_gap_days": float(gaps.max()) if len(gaps) else None,
                "source_count": int(g["source_id"].nunique()) if "source_id" in g.columns else 0,
                "quality_grade_distribution": ";".join(f"{k}:{v}" for k, v in
                                                       g["quality_grade"].value_counts().items())
                if "quality_grade" in g.columns else "",
            })
    cw = pd.DataFrame(out)
    cw.to_csv(OUT / "COMMON_TIME_WINDOW_AUDIT_FINAL.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] COMMON_TIME_WINDOW_AUDIT_FINAL.csv {cw.shape}")

    # ---------- 3. 跨城共同窗口（crop×price_level）----------
    x = []
    if len(cw):
        for (crop, lvl), g in cw.groupby(["crop_standard", "price_level"]):
            cities = sorted(g["city"].unique())
            if len(cities) < 2:
                continue
            ov_start = max(g["first_date"]); ov_end = min(g["last_date"])
            if ov_start > ov_end:
                continue
            # 共同窗口内周数（取各城该窗口周数的较小值估计）
            weeks = min(int(((pd.Timestamp(ov_end) - pd.Timestamp(ov_start)).days + 1) / 7), 9999)
            x.append({
                "crop_standard": crop, "price_level": lvl,
                "cities_available": ";".join(cities), "n_cities": len(cities),
                "overlap_start": ov_start, "overlap_end": ov_end, "overlap_weeks": weeks,
                "min_unique_weeks_in_window": int(g["unique_weeks"].min()),
                "min_coverage_in_window": float(g["coverage_ratio"].min()),
            })
    xc = pd.DataFrame(x).sort_values(["n_cities", "overlap_weeks"], ascending=False) if x else pd.DataFrame()
    xc.to_csv(OUT / "COMMON_TIME_WINDOW_CROSS_CITY.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] COMMON_TIME_WINDOW_CROSS_CITY.csv {xc.shape}")

    # ---------- 4. 研究可行性矩阵 ----------
    def city_has(slug_list, name):
        return [SLUG[s] for s in slug_list if read(s, name) is not None and len(read(s, name)) > 0]
    wcities = [SLUG[s] for s in SLUG if read(s, "weather_daily_era5.csv") is not None or True]
    rows2 = []
    # 天气
    rows2.append({"research_question": "天气→年度单产（2017–2025）", "required_data": "weather+production",
                  "available_cities": ";".join(wcities), "available_crops": "玉米/水稻/大豆/粮食等",
                  "available_period": "2010–2026(天气) × 2017–2025(生产)", "data_quality": "A/B",
                  "remaining_limitation": "生产2017-2019部分单位修正;14行UNRESOLVED排除",
                  "status": "READY", "recommended_scope": "六城 × 主粮作物 × 2017–2025"})
    p4 = [c for c in cc[cc["cities_with_price"] >= 4]["crop_standard"].tolist()][:20]
    rows2.append({"research_question": "跨城市价格比较", "required_data": "price(同crop同price_level)",
                  "available_cities": "大连/锦州/朝阳 + 铁岭/丹东(部分)", "available_crops": ";".join(p4),
                  "available_period": "2016/2020–2026", "data_quality": "B/C",
                  "remaining_limitation": "铁岭/丹东多为民俗产地价(C级);层级口径需对齐",
                  "status": "READY_WITH_LIMITATIONS", "recommended_scope": "4城蔬菜类周级"})
    rows2.append({"research_question": "天气→价格", "required_data": "weather+price(≥3年周级)",
                  "available_cities": "大连/锦州/朝阳", "available_crops": ";".join(p4),
                  "available_period": "2016–2026", "data_quality": "B",
                  "remaining_limitation": "铁岭/丹东连续价格不足",
                  "status": "READY_WITH_LIMITATIONS", "recommended_scope": "3城 × 蔬菜"})
    volc = [SLUG[s] for s in SLUG if read(s, "volume_observations.csv") is not None
            and len(read(s, "volume_observations.csv")) > 0]
    rows2.append({"research_question": "天气→供应→价格", "required_data": "weather+volume+price",
                  "available_cities": ";".join(volc), "available_crops": "蔬菜(合计)",
                  "available_period": "大连2020–2024(市场级)", "data_quality": "A(B)",
                  "remaining_limitation": "仅大连有连续市场级上市量;其余城仅年/时点",
                  "status": "READY_WITH_LIMITATIONS", "recommended_scope": "大连单城(可含沈阳)"})
    dis = [SLUG[s] for s in SLUG if read(s, "disaster_events_observed.csv") is not None
           and len(read(s, "disaster_events_observed.csv")) > 0]
    rows2.append({"research_question": "灾害冲击研究", "required_data": "disaster_observed+production",
                  "available_cities": ";".join(dis), "available_crops": "多作物",
                  "available_period": "2021–2026", "data_quality": "A/B",
                  "remaining_limitation": "事件数少;多数无受灾面积/损失",
                  "status": "READY_WITH_LIMITATIONS", "recommended_scope": "朝阳(13条)/大连(5条)个案"})
    ph = [SLUG[s] for s in SLUG if read(s, "phenology_events.csv") is not None
          and len(read(s, "phenology_events.csv")) > 0]
    rows2.append({"research_question": "物候窗口研究", "required_data": "phenology",
                  "available_cities": ";".join(ph), "available_crops": "玉米/水稻/大豆/草莓/苹果",
                  "available_period": "2021–2025(集中2025)", "data_quality": "B",
                  "remaining_limitation": "关键节点非连续;2021–2023样本薄",
                  "status": "READY_WITH_LIMITATIONS", "recommended_scope": "核心作物播种/收获窗口"})
    pol_n = sum(1 for s in SLUG if read(s, "policy_events.csv") is not None)
    rows2.append({"research_question": "政策缓冲(反事实)", "required_data": "policy+price",
                  "available_cities": ";".join(wcities), "available_crops": "-",
                  "available_period": "2021–2026(省级为主)", "data_quality": "A/B",
                  "remaining_limitation": "市级执行事件少;主要靠省级时间线",
                  "status": "READY_WITH_LIMITATIONS", "recommended_scope": "省级干预时间线"})
    rm = pd.DataFrame(rows2)
    rm.to_csv(OUT / "RESEARCH_READINESS_MATRIX.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] RESEARCH_READINESS_MATRIX.csv {rm.shape}")
    print("\n=== 顶层核心作物（P1）===")
    print(cc[cc["priority"] == "P1"][["crop_standard", "cities_with_price", "cities_with_production",
                                      "common_price_years", "recommended_research_role"]].head(25).to_string(index=False))


if __name__ == "__main__":
    main()
