"""作物选择矩阵与覆盖矩阵。

严格按手册第 3、4 节：
- 不凭印象硬编码每城 3 种作物，而是先算覆盖率再打分排序；
- 最低建模候选标准：≥2 年、≥104 个周观察；
- 达不到就标 insufficient_coverage，绝不伪造；
- 城市级农产品价格不可得时，明确记录 price_geo_level 与缺口原因。
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
MARTS = ROOT / "city_data/reference/marts"
CURATED = ROOT / "city_data/reference/curated"
META = ROOT / "data/raw/metadata"
REPORTS = ROOT / "city_data/reference/reports"
for d in (MARTS, CURATED, META, REPORTS):
    d.mkdir(parents=True, exist_ok=True)

TARGET_CITIES = ["沈阳", "铁岭", "朝阳", "锦州", "丹东", "大连"]
MIN_WEEKS = 104          # 最低建模候选：≥2 年
IDEAL_WEEKS = 156        # 理想：≥3 年


def main() -> None:
    prov = pd.read_parquet(CURATED / "province_price_weekly.parquet")
    ic = pd.read_parquet(MARTS / "fact_input_cost_weekly.parquet")
    prod = pd.read_parquet(MARTS / "fact_production_yearly.parquet")
    crops = pd.read_csv(META / "crops.csv")
    cat_map = dict(zip(crops["crop"], crops["category"]))
    season_map = dict(zip(crops["crop"], crops["active_season_coverage"]))

    # ---------- 价格覆盖 ----------
    pv = prov[prov["record_type"] == "province_avg"]
    prov_cov = pv.groupby("crop").agg(
        price_first_date=("week_start", "min"),
        price_last_date=("week_start", "max"),
        weekly_observations=("week_start", "nunique"),
        price_observations=("price_mean", "count")).reset_index()
    prov_cov["price_geo_level"] = "province"

    city_cov = ic.groupby(["city", "input_name"]).agg(
        price_first_date=("week_start", "min"),
        price_last_date=("week_start", "max"),
        weekly_observations=("week_start", "nunique"),
        price_observations=("price", "count")).reset_index()
    city_cov = city_cov.rename(columns={"input_name": "crop"})
    city_cov["price_geo_level"] = "city"

    # ---------- 生产数据 ----------
    if not prod.empty:
        prod_latest = prod.sort_values("year").groupby(["city", "crop"]).tail(1)
        prod_rank = prod_latest.copy()
        prod_rank["production_rank_in_city"] = (
            prod_rank.groupby("city")["production"].rank(ascending=False, method="min"))
    else:
        prod_latest = pd.DataFrame()
        prod_rank = pd.DataFrame()

    # ---------- 构建矩阵 ----------
    rows = []
    for city in TARGET_CITIES:
        # (a) 城市级真实序列：农资
        for _, r in city_cov[city_cov["city"] == city].iterrows():
            crop = r["crop"]
            rows.append({
                "city": city, "crop": crop, "category": cat_map.get(crop, "agricultural_input"),
                "price_geo_level": "city",
                "price_first_date": r["price_first_date"], "price_last_date": r["price_last_date"],
                "price_observations": int(r["price_observations"]),
                "weekly_observations": int(r["weekly_observations"]),
            })
        # (b) 农产品：城市级不可得，但省级有连续序列 —— 记录省级覆盖并标明缺口
        for _, r in prov_cov.iterrows():
            crop = r["crop"]
            if cat_map.get(crop) == "agricultural_input":
                continue
            rows.append({
                "city": city, "crop": crop, "category": cat_map.get(crop, "other"),
                "price_geo_level": "province_only",
                "price_first_date": r["price_first_date"], "price_last_date": r["price_last_date"],
                "price_observations": int(r["price_observations"]),
                "weekly_observations": 0,   # 城市级周观察为 0
            })

    m = pd.DataFrame(rows)

    # 覆盖率：以省级可用周数为分母，城市级用自身周数
    total_weeks = int(prov["week_start"].nunique())
    m["weekly_coverage_ratio"] = np.where(
        m["price_geo_level"] == "city",
        (m["weekly_observations"] / total_weeks).round(4),
        (prov_cov.set_index("crop")["weekly_observations"].reindex(m["crop"]).values / total_weeks).round(4))

    # 生产数据
    if not prod_rank.empty:
        pk = prod_rank.set_index(["city", "crop"])
        m["planting_area"] = [pk.loc[(c, cr), "planting_area"]
                              if (c, cr) in pk.index else np.nan
                              for c, cr in zip(m["city"], m["crop"])]
        m["production"] = [pk.loc[(c, cr), "production"]
                           if (c, cr) in pk.index else np.nan
                           for c, cr in zip(m["city"], m["crop"])]
        m["yield"] = [pk.loc[(c, cr), "yield_per_area"]
                      if (c, cr) in pk.index else np.nan
                      for c, cr in zip(m["city"], m["crop"])]
        m["production_rank_in_city"] = [pk.loc[(c, cr), "production_rank_in_city"]
                                        if (c, cr) in pk.index else np.nan
                                        for c, cr in zip(m["city"], m["crop"])]
    else:
        for c in ["planting_area", "production", "yield", "production_rank_in_city"]:
            m[c] = np.nan

    m["seasonal_crop"] = m["crop"].map(season_map)
    m["active_season_coverage"] = m["crop"].map(season_map)
    m["official_representative_evidence"] = ""
    m["evidence_source"] = np.where(
        m["price_geo_level"] == "city",
        "辽宁省农业农村厅 农资城市报价（逐市）",
        "辽宁省农业农村厅 省级周价（城市级价格不可得）")

    # ---------- 打分 ----------
    def score(r):
        # 数据完整度权重最高（0.6），生产规模（0.25），地方代表性（0.15）
        cov = float(r["weekly_observations"]) / max(MIN_WEEKS, 1)
        data_score = min(cov, 1.5) / 1.5 * 60
        prod_score = 0.0
        if pd.notna(r.get("production")) and r["production"] and r["production"] > 0:
            prod_score = 25.0 * min(float(r["production"]) / 100.0, 1.0)
        # 代表作物：玉米/水稻/大豆/花生等主粮有官方年鉴支撑
        rep = 15.0 if r["crop"] in ("玉米", "水稻", "大豆", "花生", "苹果", "梨") else 5.0
        return round(data_score + prod_score + rep, 2)

    m["candidate_score"] = m.apply(score, axis=1)

    # ---------- 选择：每城 3 种 ----------
    m["selected"] = False
    m["selection_reason"] = ""
    m["status"] = ""
    for city, g in m.groupby("city"):
        g2 = g.sort_values("candidate_score", ascending=False)
        picked, cats = [], set()
        for idx, r in g2.iterrows():
            if len(picked) >= 3:
                break
            if r["weekly_observations"] < MIN_WEEKS:
                continue
            # 尽量来自不同类别
            if r["category"] in cats and len(picked) < 2:
                continue
            picked.append(idx)
            cats.add(r["category"])
        for idx in picked:
            m.loc[idx, "selected"] = True
            m.loc[idx, "selection_reason"] = (
                f"城市级真实序列 {int(m.loc[idx,'weekly_observations'])} 周，"
                f"覆盖 {m.loc[idx,'weekly_coverage_ratio']:.0%}")
        # 状态
        for idx, r in g2.iterrows():
            if m.loc[idx, "selected"]:
                m.loc[idx, "status"] = "ready" if r["weekly_observations"] >= IDEAL_WEEKS else "usable_with_caution"
            elif r["weekly_observations"] >= MIN_WEEKS:
                m.loc[idx, "status"] = "usable_with_caution"
            else:
                m.loc[idx, "status"] = "insufficient"

    m = m.sort_values(["city", "candidate_score"], ascending=[True, False])
    cols = ["city", "crop", "category", "price_geo_level",
            "price_first_date", "price_last_date", "price_observations",
            "weekly_observations", "weekly_coverage_ratio",
            "planting_area", "production", "yield", "production_rank_in_city",
            "official_representative_evidence", "evidence_source",
            "seasonal_crop", "active_season_coverage",
            "candidate_score", "status", "selected", "selection_reason"]
    m = m[cols]
    m.to_csv(REPORTS / "crop_selection_matrix.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] crop_selection_matrix {len(m)} 行")
    print(m[m["selected"]][["city", "crop", "category", "weekly_observations", "status"]].to_string(index=False))

    # ---------- 覆盖矩阵 ----------
    wx = pd.read_parquet(MARTS / "fact_weather_weekly.parquet")
    wx = wx[wx["city"] != "沈北新区"]
    ev = pd.read_parquet(MARTS / "fact_disaster_events.parquet")
    exp = pd.read_parquet(MARTS / "weekly_disaster_exposure.parquet")

    cov_rows = []
    for city in TARGET_CITIES:
        w = wx[wx["city"] == city]
        e = ev[ev["city"] == city]
        ex = exp[exp["city"] == city]
        city_inputs = ic[ic["city"] == city]
        cov_rows.append({
            "city": city,
            "price_days_city_level": 0,   # 城市级日价格不可得
            "price_weeks_city_level": int(city_inputs["week_start"].nunique()),
            "price_records_city_level": int(len(city_inputs)),
            "price_weeks_province_level": int(prov["week_start"].nunique()),
            "price_records_province_level": int(len(prov[prov["record_type"] == "province_avg"])),
            "weather_days": int(w["observation_days"].sum()),
            "weather_weeks": int(len(w)),
            "weather_first": str(w["week_start"].min()), "weather_last": str(w["week_end"].max()),
            "production_years": int(prod["year"].nunique()) if not prod.empty else 0,
            "production_records": int(len(prod[prod["city"] == city])) if not prod.empty else 0,
            "disaster_events": int(len(e)),
            "extreme_weeks": int(ex["extreme_weather_flag"].sum()),
            "input_cost_weeks": int(city_inputs["week_start"].nunique()),
        })
    cov = pd.DataFrame(cov_rows)
    cov.to_csv(REPORTS / "coverage_matrix.csv", index=False, encoding="utf-8-sig")
    print(f"\n[OK] coverage_matrix {len(cov)} 行")
    print(cov.to_string(index=False))


if __name__ == "__main__":
    main()
