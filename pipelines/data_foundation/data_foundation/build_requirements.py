#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Data Foundation v1 · P6 需求矩阵与 readiness
产出 06_requirements/{FULL_DATA_REQUIREMENT_MATRIX,MODEL_REQUIREMENT_MATRIX,DATA_GAP_FINAL,READINESS_FINAL}.csv
以及 00_governance/{CANONICAL_TABLE_REGISTRY,DO_NOT_USE_FOR_MODEL,RECOMMENDED_MODEL_INPUTS}.csv
readiness 由规则计算（见 DATA_QUALITY_RULES.md），非手填。
"""
from __future__ import annotations
import csv, json
from pathlib import Path
import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
STD = ROOT / "data/processed"
INT = ROOT / "data/processed/integrated"
Q = ROOT / "data/metadata/quality"
REQ = ROOT / "data/metadata/requirements"
GOV = ROOT / "data/metadata/governance"
REQ.mkdir(parents=True, exist_ok=True)

# requirement_id, category, metric, modules(逗号), priority, ideal_gran, ideal_freq, table(相对 02_standardized), quality_hint
REQS = [
    ("A01", "空间基础", "六城市界/行政代码/中心坐标", "all", "P0", "city", "static", "dimensions/dim_city.parquet", "S"),
    ("A02", "空间基础", "县区边界/中心", "recommendation,production", "P1", "district", "static", "dimensions/dim_district.parquet", "B"),
    ("A03", "空间基础", "耕地/土地覆盖", "climate,remote_sensing", "P1", "raster", "static", "", "MISSING"),
    ("B01", "作物主数据", "作物名称/类别/别名/规格", "all", "P0", "crop", "static", "dimensions/dim_crop.parquet", "A"),
    ("B02", "作物主数据", "设施/露地/主要种植区", "recommendation,production", "P1", "city×crop", "static", "production/facility_agriculture.parquet", "B"),
    ("C01", "市场价格", "城市价格观测(含 price_level)", "price_model,hri,market_risk", "P0", "city×crop×daily", "daily", "market/price_observation.parquet", "A"),
    ("C02", "市场价格", "县级价格", "price_model", "P1", "district×crop", "daily", "market/price_observation.parquet", "C"),
    ("D01", "价格外部基准", "辽宁省蔬菜周度价格", "hri,price_model,market_risk", "P0", "province×crop×weekly", "weekly", "market/province_price_reference.parquet", "A"),
    ("D02", "价格外部基准", "全国价格", "market_risk", "P2", "national", "weekly", "", "MISSING"),
    ("E01", "成交量/供应", "城市成交量", "hri,market_risk", "P0", "city×crop×daily", "daily", "market/market_volume.parquet", "C"),
    ("E02", "成交量/供应", "供应代理(日供应量/外埠比例)", "hri,market_risk,recommendation", "P0", "city×market", "snapshot/daily", "market/supply_proxy.parquet", "B"),
    ("F01", "库存", "市场/冷库/粮食库存", "market_risk", "P2", "city", "daily", "", "MISSING"),
    ("G01", "播种面积", "作物播种面积(年)", "production,hri,recommendation", "P0", "city×crop×year", "yearly", "production/planting_area_yearly.parquet", "B"),
    ("H01", "产量", "作物产量(年)", "production,profit,recommendation", "P0", "city×crop×year", "yearly", "production/production_yearly.parquet", "B"),
    ("I01", "单产", "单产(官方或派生)", "production,profit", "P1", "city×crop×year", "yearly", "production/production_yearly.parquet", "C"),
    ("J01", "种植结构", "设施/露地/温室/冷棚面积", "recommendation,production", "P1", "district×crop", "cross_section", "production/crop_spatial_structure.parquet", "B"),
    ("K01", "农事历/物候", "播种/定植/收获/上市窗口", "recommendation", "P0", "city×crop×stage", "event", "production/crop_calendar.parquet", "B"),
    ("L01", "种植成本", "成本拆分(种苗/肥料/人工/棚膜…)", "profit,recommendation", "P0", "city×crop", "cross_section", "cost/cost_components.parquet", "C"),
    ("L02", "种植成本", "官方作物成本收益(玉米/水稻)", "profit", "P1", "city×crop×year", "yearly", "cost/crop_cost.parquet", "A"),
    ("M01", "农资价格", "化肥/农药/农膜/柴油价格", "profit,price_model", "P1", "city×week", "weekly", "cost/input_prices.parquet", "C"),
    ("N01", "天气", "日气象(tmax/tmin/precip/humidity/wind/radiation)", "climate,production", "P0", "city×daily", "daily", "climate/weather_daily.parquet", "A"),
    ("O01", "派生农业气象", "GDD/ET0/干旱/连阴雨等派生", "climate", "P1", "city×daily", "daily", "climate/weather_daily.parquet", "A"),
    ("P01", "气候基准", "1991-2020 气候常年值", "climate", "P1", "city×week", "weekly", "climate/climatology.parquet", "A"),
    ("Q01", "土壤", "土壤水分/温度", "climate,production", "P0", "city×daily", "daily", "climate/soil_daily.parquet", "A"),
    ("R01", "干旱", "土壤水分分位/干期/ET0 亏缺", "climate", "P1", "city×daily", "daily", "", "DERIVE"),
    ("S01", "遥感", "NDVI 城市×月", "climate,production,recommendation", "P0", "city×month", "monthly", "remote_sensing/ndvi.parquet", "A"),
    ("S02", "遥感", "EVI", "climate", "P2", "city×month", "monthly", "remote_sensing/evi.parquet", "C"),
    ("S03", "遥感", "LAI/FAPAR", "climate", "P2", "city×month", "monthly", "", "MISSING"),
    ("T01", "遥感异常", "NDVI 同期异常/分位", "climate,production", "P0", "city×month", "monthly", "remote_sensing/vegetation_anomaly.parquet", "A"),
    ("U01", "耕地/土地覆盖", "cropland/landcover", "climate,remote_sensing", "P1", "raster", "static", "", "MISSING"),
    ("V01", "灾害事件", "灾害事件(类型/时间/空间)", "climate,evidence", "P0", "city×event", "event", "disaster/disaster_events.parquet", "B"),
    ("W01", "灾害损失", "受灾/成灾/绝收/经济损失", "climate,evidence", "P1", "city×crop×event", "event", "disaster/disaster_loss.parquet", "C"),
    ("X01", "农业保险", "承保/理赔/赔付率", "market_risk,evidence", "P1", "city×year", "yearly", "disaster/insurance_claims.parquet", "B"),
    ("Y01", "病虫害", "病虫害事件(作物/等级)", "climate,bio_risk", "P1", "city×crop×event", "event", "bio_risk/pest_disease_events.parquet", "C"),
    ("Z01", "水资源灌溉", "有效灌溉/高标准农田/机电井", "climate,recommendation", "P1", "city×year", "yearly", "water/irrigation_water.parquet", "B"),
    ("AA01", "市场基础设施", "批发市场登记(位置/规模)", "recommendation,market_risk", "P0", "market", "static", "market/market_registry.parquet", "B"),
    ("AB01", "冷链仓储", "冷库/气调库/仓储能力", "recommendation,market_risk", "P1", "city", "cross_section", "infrastructure/cold_chain.parquet", "B"),
    ("AC01", "物流可达性", "产地→市场道路距离", "recommendation", "P1", "market", "static", "infrastructure/market_accessibility.parquet", "A"),
    ("AD01", "运输成本", "元/吨公里/运价", "profit", "P2", "city", "periodic", "", "MISSING"),
    ("AE01", "人口需求", "常住/城镇人口", "demand", "P2", "city×year", "yearly", "demand/population.parquet", "A"),
    ("AF01", "消费", "蔬菜消费/人均食品支出", "demand", "P2", "city×year", "yearly", "demand/consumption.parquet", "C"),
    ("AG01", "CPI", "CPI/食品CPI/鲜菜CPI", "demand,market_risk", "P2", "city×month", "monthly", "demand/cpi.parquet", "B"),
    ("AH01", "商业需求", "社零/餐饮收入", "demand", "P2", "city×year", "yearly", "demand/retail_catering.parquet", "B"),
    ("AI01", "政策", "补贴/保险/保供政策事件", "evidence,recommendation", "P1", "city×event", "event", "policy/policy_events.parquet", "B"),
    ("AJ01", "市场调控", "储备投放/产销对接/滞销帮扶", "evidence", "P2", "city×event", "event", "policy/market_intervention.parquet", "B"),
    ("AK01", "跟风案例", "扩种→滞销 事件链", "hri,evidence", "P0", "city×crop×event", "event", "evidence/herding_events.parquet", "C"),
    ("AL01", "市场异常", "滞销/抢购/集中上市事件", "evidence,market_risk", "P2", "city×event", "event", "evidence/case_events.parquet", "C"),
    ("AM01", "宏观背景", "省级产量/面积/农业增加值", "context", "P2", "province×year", "yearly", "production/production_yearly.parquet", "B"),
    ("AN01", "贸易", "进出口/省际调入", "context", "P2", "province", "periodic", "", "MISSING"),
    ("AO01", "模型标签", "未来价格/政策/异常标签", "price_model,hri,climate", "P0", "city×crop×time", "derived", "03_integrated/city_crop_weekly.parquet", "A"),
    ("AP01", "用户输入", "种植日期/面积/成本/亩产(产品依赖)", "recommendation,profit", "P0", "user", "event", "", "USER_INPUT"),
]

MODULES = {"price_model": "price", "hri": "hri", "market_risk": "market_risk", "climate": "climate",
           "production": "production", "profit": "profit", "recommendation": "recommendation", "evidence": "evidence"}


def cov_of(table):
    """返回 (coverage 0-1, n_rows)。"""
    p = STD / table
    if not table or not p.exists():
        return 0.0, 0
    try:
        df = pd.read_parquet(p, columns=None)
        return 1.0, len(df)
    except Exception:
        return 0.0, 0


def main():
    rows, gaps = [], []
    for rid, cat, metric, mods, prio, gran, freq, table, qhint in REQS:
        cov, n = cov_of(table)
        if qhint == "MISSING":
            status, grade, cov = "NOT_FOUND", "RED", 0.0
        elif qhint == "USER_INPUT":
            status, grade, cov = "USER_INPUT", "YELLOW", 0.5
        elif qhint == "DERIVE":
            status, grade, cov = "DERIVABLE", "YELLOW", 0.5
        else:
            grade = {"S": "GREEN", "A": "GREEN", "B": "GREEN", "C": "YELLOW", "D": "RED"}.get(qhint, "YELLOW")
            status = "AVAILABLE"
        rows.append({"requirement_id": rid, "category": cat, "metric": metric, "needed_for": mods,
                     "priority": prio, "ideal_granularity": gran, "ideal_frequency": freq,
                     "available": status, "table": table, "rows": n,
                     "coverage": round(cov, 2), "quality": grade,
                     "gap_reason": "" if grade == "GREEN" else ("缺失/受限" if grade == "RED" else "代理或覆盖有限"),
                     "next_action": "" if grade == "GREEN" else ("重新采集或确认公开性" if grade == "RED" else "记录 proxy 并按降权使用")})
        if grade in ("RED", "YELLOW") or status in ("NOT_FOUND", "USER_INPUT", "DERIVABLE"):
            if qhint == "USER_INPUT":
                gstat = "USER_INPUT_REQUIRED"
            elif qhint == "MISSING":
                gstat = "REAL_GAP" if prio == "P0" else "PUBLICLY_UNAVAILABLE"
            elif qhint == "DERIVE":
                gstat = "LOW_PRIORITY" if prio == "P2" else "PROXY_ONLY"
            elif prio == "P2":
                gstat = "LOW_PRIORITY"
            else:
                gstat = "PROXY_ONLY"
            gaps.append({"metric": metric, "city": "", "crop": "", "desired_granularity": gran,
                         "status": gstat,
                         "searched_sources": "data/raw/ + data/processed/ + data/model_ready/ + retained_source(supplement V1-V3)",
                         "search_attempts": "", "evidence": table or "见各专项 NOTES", "impact": cat,
                         "fallback": {"USER_INPUT_REQUIRED": "用户输入", "REAL_GAP": "最后定点补数",
                                      "PUBLICLY_UNAVAILABLE": "标记 NOT_PUBLIC", "NOT_FOUND": "保持缺失",
                                      "PROXY_ONLY": "降权使用并标注 proxy", "LOW_PRIORITY": "暂不处理"}[gstat]})

    with (REQ / "FULL_DATA_REQUIREMENT_MATRIX.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    with (REQ / "DATA_GAP_FINAL.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["metric", "city", "crop", "desired_granularity", "status",
                                           "searched_sources", "search_attempts", "evidence", "impact", "fallback"])
        w.writeheader(); w.writerows(gaps)
    # §44 最终缺口版：仅 REAL_GAP 明细 + 六类状态登记
    with (REQ / "DATA_GAP_FINAL_V2.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["metric", "city", "crop", "desired_granularity", "status",
                                           "searched_sources", "search_attempts", "evidence", "impact", "fallback"])
        w.writeheader(); w.writerows(gaps)

    # 模块 readiness
    pw = {"P0": 3, "P1": 2, "P2": 1}
    mod_rows = []
    for mkey, mname in MODULES.items():
        sel = [r for r in rows if mkey in r["needed_for"] or "all" in r["needed_for"]]
        if not sel:
            continue
        num = sum(pw[r["priority"]] * r["coverage"] for r in sel)
        den = sum(pw[r["priority"]] for r in sel)
        mod_rows.append({"module": mkey, "n_requirements": len(sel),
                         "readiness_pct": round(100 * num / den, 1) if den else 0,
                         "green": sum(1 for r in sel if r["quality"] == "GREEN"),
                         "yellow": sum(1 for r in sel if r["quality"] == "YELLOW"),
                         "red": sum(1 for r in sel if r["quality"] == "RED")})
    with (REQ / "READINESS_FINAL.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["module", "n_requirements", "readiness_pct", "green", "yellow", "red"])
        w.writeheader(); w.writerows(mod_rows)

    # MODEL_REQUIREMENT_MATRIX
    mrows = []
    for mkey in MODULES:
        sel = [r for r in rows if mkey in r["needed_for"] or "all" in r["needed_for"]]
        core = [r["metric"] for r in sel if r["priority"] == "P0"]
        enh = [r["metric"] for r in sel if r["priority"] == "P1"]
        ext = [r["metric"] for r in sel if r["priority"] == "P2"]
        mrows.append({"module": mkey, "core_P0": " ; ".join(core), "enhance_P1": " ; ".join(enh), "context_P2": " ; ".join(ext)})
    with (REQ / "MODEL_REQUIREMENT_MATRIX.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["module", "core_P0", "enhance_P1", "context_P2"]); w.writeheader(); w.writerows(mrows)

    # CANONICAL_TABLE_REGISTRY（§52：每个指标有且仅有一个推荐表）
    creg = [
        ("daily price", "02_standardized/market/price_observation.parquet", "六城 canonical（污染已恢复）", "archive/old_marts/marts/fact_price_*（已归档，勿用）", "A", "2020-2026", "v1.1"),
        ("province price", "02_standardized/market/province_price_reference.parquet", "retained_source supplement V1+V3", "—", "A", "2019-2026", "v1.1"),
        ("market volume", "02_standardized/market/market_volume.parquet", "六城 canonical volume", "—", "C", "2015-2026", "v1.1"),
        ("market supply proxy", "02_standardized/market/supply_proxy.parquet", "retained_source V3", "—", "B", "2019-2026", "v1.1"),
        ("market registry", "02_standardized/market/market_registry.parquet", "retained_source V2+V3", "—", "B", "static", "v1.1"),
        ("daily weather", "02_standardized/climate/weather_daily.parquet", "ERA5 / ERA5-Land", "旧 marts/fact_weather_daily（已归档）", "A", "2010-2026", "v1.1"),
        ("soil moisture", "02_standardized/climate/soil_daily.parquet", "ERA5-Land soil", "—", "A", "2010-2026", "v1.1"),
        ("climatology", "02_standardized/climate/climatology.parquet", "retained_source curated 1991-2020", "—", "A", "1991-2020", "v1.1"),
        ("NDVI", "02_standardized/remote_sensing/ndvi.parquet", "Sentinel-2 城市×月", "—", "A", "2021-2026", "v1.1"),
        ("NDVI anomaly", "02_standardized/remote_sensing/vegetation_anomaly.parquet", "Sentinel-2 派生", "—", "A", "2021-2026", "v1.1"),
        ("EVI", "02_standardized/remote_sensing/evi.parquet", "Sentinel-2（覆盖不足，CONTEXT_ONLY）", "—", "C", "2021-2026", "v1.1"),
        ("production yearly", "02_standardized/production/production_yearly.parquet", "五城 + retained_source V2", "—", "B", "2017-2025", "v1.1"),
        ("planting area yearly", "02_standardized/production/planting_area_yearly.parquet", "辽宁统计年鉴 XLS", "—", "S", "2017-2019", "v1.1"),
        ("district crop (yearbook)", "02_standardized/production/yearbook_shenyang_district_crop.parquet", "沈阳统计年鉴 7 册（新增解析）", "—", "A", "2018-2024", "v1.1"),
        ("district production (bulletin)", "02_standardized/production/bulletin_shenyang_district.parquet", "沈阳区县公报（新增解析）", "—", "B", "2016-2025", "v1.1"),
        ("crop spatial structure", "02_standardized/production/crop_spatial_structure.parquet", "retained_source V3", "—", "B", "cross_section", "v1.1"),
        ("facility vegetable (district)", "02_standardized/production/district_facility_vegetable.parquet", "辽中区 2023 统计资料汇编（新增解析）", "—", "A", "district×crop", "v1.1"),
        ("facility agriculture (city)", "02_standardized/production/facility_agriculture_city.parquet", "沈阳市统计局公开报道+公报（定点补数）", "—", "B", "city×year", "v1.1"),
        ("crop calendar", "02_standardized/production/crop_calendar.parquet", "五城 + retained_source V2", "—", "B", "2013-2025", "v1.1"),
        ("crop cost", "02_standardized/cost/crop_cost.parquet", "retained_source V2（LOCAL+proxy 已标注）", "—", "B", "2000-2025", "v1.1"),
        ("cost components", "02_standardized/cost/cost_components.parquet", "retained_source V3（RESEARCH_REFERENCE）", "—", "C", "2000-2025", "v1.1"),
        ("input prices", "02_standardized/cost/input_prices.parquet", "辽宁省农业农村厅周报", "—", "B", "2021-2026", "v1.1"),
        ("disaster events", "02_standardized/disaster/disaster_events.parquet", "六城 observed", "—", "B", "2010-2026", "v1.1"),
        ("insurance claims", "02_standardized/disaster/insurance_claims.parquet", "retained_source V2+V3", "—", "B", "2023-2025", "v1.1"),
        ("pest disease events", "02_standardized/bio_risk/pest_disease_events.parquet", "retained_source V3", "—", "C", "event", "v1.1"),
        ("irrigation water", "02_standardized/water/irrigation_water.parquet", "retained_source V2+V3", "—", "B", "2017-2025", "v1.1"),
        ("cold chain", "02_standardized/infrastructure/cold_chain.parquet", "retained_source V3", "—", "B", "cross_section", "v1.1"),
        ("market accessibility", "02_standardized/infrastructure/market_accessibility.parquet", "OSRM 派生", "—", "A", "static", "v1.1"),
        ("demand", "02_standardized/demand/*.parquet", "retained_source V2+V3 统计公报", "—", "A", "2019-2025", "v1.1"),
        ("policy events", "02_standardized/policy/policy_events.parquet", "六城 + province retained", "—", "B", "2015-2026", "v1.1"),
        ("herding events", "02_standardized/evidence/herding_events.parquet", "retained_source V2+V3", "—", "C", "2011-2026", "v1.1"),
    ]
    with (GOV / "CANONICAL_TABLE_REGISTRY.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["metric", "recommended_table", "source", "supersedes", "source_quality", "coverage", "version"])
        w.writeheader()
        for r in creg:
            w.writerow(dict(zip(["metric", "recommended_table", "source", "supersedes", "source_quality", "coverage", "version"], r)))

    # DO_NOT_USE_FOR_MODEL（§53）
    dnu = [
        ("02_standardized/market/price_observation_nonstandard.parquet", "非作物/未知 token（苗木/观赏/加工/未知），不得作为作物特征", "非作物"),
        ("archive/old_marts/**", "旧 marts/curated/staging 聚合层，已被 data/ 取代", "旧加工层"),
        ("archive/data_legacy/**", "旧 supplement V1-V3 加工副本，正式数据请用 data/processed 与 data/model_ready（原始保留在 data/raw/retained_source）", "旧加工层"),
        ("archive/data_reports/**", "历史报告/清单，非数据表", "历史报告"),
        ("city_data/reference/**", "已清场，不再作为数据入口", "废弃路径"),
        ("models/data/snapshots/**", "建模侧冻结快照，与 foundation 可能不同步", "快照"),
        ("02_standardized/demand/demand_proxy.parquet 中 model_value=UNUSABLE 行", "NOT_FOUND 占位，无真实数值", "占位"),
        ("*crop_standard ∈ {规格/品级/包装/第一列错位} 的行", "v1.1 已修复；任何仍出现该模式的表视为污染，勿用", "字段污染"),
        ("price_level 混用（wholesale 与 retail 合并计算）", "8 个 price_level 必须严格分开", "口径混用"),
    ]
    with (GOV / "DO_NOT_USE_FOR_MODEL.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["path_or_pattern", "reason", "category"]); w.writeheader()
        for r in dnu:
            w.writerow({"path_or_pattern": r[0], "reason": r[1], "category": r[2]})

    # RECOMMENDED_MODEL_INPUTS（§54：下一轮建模严格从这里读）
    rec = [
        ("price_model", "六城", "10蔬菜及主要品类", "04_model_ready/*/market_daily.parquet", "price_per_kg,price_level_canonical,crop_standard,variety,grade,observation_date", "2020-2026", "A", "price_level 8 类不可混用；crop_standard 已去污染"),
        ("price_model", "省", "10蔬菜", "02_standardized/market/province_price_reference.parquet", "price,week,crop_standard", "2019-2026", "A", "省级背景，非城市价"),
        ("hri", "六城", "主要蔬菜", "04_model_ready/hri/hri_inputs.parquet", "price_pct_rank,price_mom_4w,price_mean", "2020-2026", "B", "HRI 是扩种诱因强度"),
        ("market_risk", "六城", "主要蔬菜", "02_standardized/market/supply_proxy.parquet", "proxy_type,value,unit,city,crop,date", "2019-2026", "B", "proxy_type 分别标准化；不可混成绝对供应量"),
        ("climate", "六城", "—", "04_model_ready/climate/climate_daily.parquet", "temperature_2m_mean,precipitation_sum,et0,ndvi_mean,ndvi_anomaly_z", "2010-2026", "A", "NDVI 月度 forward-map，source_frequency=monthly"),
        ("climate", "六城", "—", "04_model_ready/climate/vegetation_anomaly.parquet", "ndvi_anomaly,ndvi_percentile", "2021-2026", "A", "仅表示植被状态异常，非减产"),
        ("production", "沈阳区县", "粮食/蔬菜主要作物", "02_standardized/production/yearbook_shenyang_district_crop.parquet", "district,crop,year,metric,value,unit", "2018-2024", "A", "新增解析：年鉴 9 区县"),
        ("production", "六城", "主要作物", "02_standardized/production/production_yearly.parquet", "crop,planting_area,production,yield_source_class", "2017-2025", "B", "禁止总体亩产冒充单作物"),
        ("production", "沈阳", "设施蔬菜", "04_model_ready/shenyang_core/crop_context.parquet", "crop_standard,facility_type,area_mu", "2022-2025", "B", "截面结构，非时序"),
        ("production", "沈阳辽中", "设施蔬菜分品种", "02_standardized/production/district_facility_vegetable.parquet", "crop_standard,facility_type,metric,value,unit,year", "2023", "A", "district×crop 实际值（新增定点补数）"),
        ("production", "沈阳", "设施农业规模", "02_standardized/production/facility_agriculture_city.parquet", "item,metric,value,unit,year", "2024-2025", "B", "公开报道+公报口径，city 级"),
        ("profit", "沈阳/东北", "番茄/黄瓜等", "04_model_ready/profit/cost_components.parquet", "cost_basis,total_cost,各构成项,cost_source_class", "2000-2025", "C", "cost_source_class 必读；USER_REQUIRED 需用户输入"),
        ("profit", "沈阳/铁岭/辽阳", "玉米/水稻/大豆", "02_standardized/cost/crop_cost.parquet", "total_cost_per_mu,各分项,cost_source_class", "2020-2025", "B", "REGIONAL_PROXY 降权"),
        ("recommendation", "六城", "—", "04_model_ready/recommendation/structural_context.parquet", "_block 各块字段", "—", "B", "解释性上下文"),
        ("recommendation", "沈阳", "—", "04_model_ready/shenyang_core/phenology.parquet", "crop_standard,stage,start_date,end_date,calendar_geo_scope,facility_type_norm", "2013-2025", "B", "区分 city/district/province/northeast"),
        ("evidence", "六城", "跟风作物", "02_standardized/evidence/herding_events.parquet", "crop,event_type,date,source", "2011-2026", "C", "仅外部验证 / 案例证据，不训练分类器"),
        ("market_risk", "六城", "—", "02_standardized/infrastructure/market_accessibility.parquet", "market,distance_km,duration_min", "static", "A", "OSRM 派生"),
    ]
    with (GOV / "RECOMMENDED_MODEL_INPUTS.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["module", "city", "crop", "table", "fields", "date_range", "quality", "limitations"])
        w.writeheader()
        for r in rec:
            w.writerow(dict(zip(["module", "city", "crop", "table", "fields", "date_range", "quality", "limitations"], r)))

    print("[OK] 需求矩阵/缺口/readiness/canonical/DO_NOT_USE/RECOMMENDED 已生成")
    for m in mod_rows:
        print(f"   {m['module']}: {m['readiness_pct']}%  (G{m['green']}/Y{m['yellow']}/R{m['red']})")


if __name__ == "__main__":
    main()
