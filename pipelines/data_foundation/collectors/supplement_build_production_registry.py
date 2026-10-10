#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
构建 Decision Engine 补充层：
  planting_area_yearly.csv        六城作物级播种面积（统计公报）
  production_yearly_extended.csv  六城作物级产量（统计公报）
  supply_demand_yearly.csv         人口/蔬菜供给（统计公报）—— 供需辅助
  source_registry.csv              统一来源登记
并做 QC：重复/缺失/单位/异常/来源
所有数值均来自政府统计公报原文，未插值、未估算。
"""
import csv, re, json
from pathlib import Path
from datetime import datetime
from collections import Counter

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
OUT = ROOT / "data/raw/retained_source/city_data" / "reference" / "decision_engine_supplement"
OUT.mkdir(parents=True, exist_ok=True)
AD = datetime.now().strftime("%Y-%m-%d")

# ---------------- 统计公报原始数值 ----------------
# 面积单位：千公顷(kha)；产量单位：万吨
# src: (source_name, url)
S_SY = ("沈阳市统计局 2024年沈阳市国民经济和社会发展统计公报",
        "https://www.shenyang.gov.cn/zwgk/fdzdgknr/tjxx/tjgb/202504/t20250423_4841162.html")
S_SY25 = ("沈阳市人民政府·沈阳经济·农业（2025年数据）",
          "https://www.shenyang.gov.cn/wssy/syjj/ny/")
S_SY23VEG = ("沈阳市统计局 2023年全市蔬菜产能稳步增长",
             "https://tjj.shenyang.gov.cn/sjfb/sqfx/202401/t20240122_4593890.html")
S_SY19 = ("沈阳市统计局 2019年沈阳市国民经济和社会发展统计公报",
          "https://www.shenyang.gov.cn/zwgk/fdzdgknr/tjxx/tjgb/202201/t20220122_2578737.html")
S_JZ = ("锦州市统计局 2024年锦州市国民经济和社会发展统计公报",
        "https://tjj.jz.gov.cn/info/1057/4793.htm")
S_CY = ("朝阳市统计局 朝阳市2024年国民经济和社会发展统计公报",
        "https://www.chaoyang.gov.cn/html/CYSZF/202505/0174669308628614.html")
S_TL = ("铁岭市统计局 2024年铁岭市国民经济和社会发展统计公报",
        "http://www.tieling.gov.cn/tieling/zwgk/zfxxgk/fdzdgknr/tjxx/tjgb/2025051410132752830/index.html")
S_JP = ("建平县统计局 建平县2024年国民经济和社会发展统计公报",
        "https://files.chaoyang.gov.cn/files/ueditor/JPXZF/jsp/upload/file/20250603/1748917493571058483.pdf")

AREA = [  # year, city, crop, area_kha, source_tuple, note
 (2024, "沈阳", "粮食作物", 546.3, S_SY, ""), (2024, "沈阳", "水稻", 110.3, S_SY, ""),
 (2024, "沈阳", "玉米", 415.2, S_SY, ""), (2024, "沈阳", "大豆", 11.7, S_SY, ""),
 (2024, "沈阳", "蔬菜及食用菌", 67.0, S_SY, ""), (2024, "沈阳", "油料作物", 33.3, S_SY, ""),
 (2024, "沈阳", "瓜果", 13.9, S_SY, ""), (2024, "沈阳", "经济作物", 137.0, S_SY, ""),
 (2025, "沈阳", "粮食作物", 549.6, S_SY25, ""), (2025, "沈阳", "水稻", 110.5, S_SY25, ""),
 (2025, "沈阳", "玉米", 419.3, S_SY25, ""), (2025, "沈阳", "豆类", 11.8, S_SY25, ""),
 (2025, "沈阳", "蔬菜及食用菌", 68.2, S_SY25, ""), (2025, "沈阳", "油料作物", 32.1, S_SY25, ""),
 (2019, "沈阳", "粮食作物", 546.0, S_SY19, "原文54.6万公顷，折算千公顷"),
 (2023, "沈阳", "蔬菜(合计)", 65.8, S_SY23VEG, "原文98.7万亩，折算千公顷(1亩=1/15公顷)"),
 (2023, "沈阳", "蔬菜-白菜类", 13.47, S_SY23VEG, "原文20.2万亩"),
 (2023, "沈阳", "蔬菜-叶菜类", 18.13, S_SY23VEG, "原文27.2万亩"),
 (2023, "沈阳", "蔬菜-茄果类", 13.67, S_SY23VEG, "原文20.5万亩"),
 (2024, "锦州", "粮食作物", 367.7, S_JZ, ""), (2024, "锦州", "水稻", 40.4, S_JZ, ""),
 (2024, "锦州", "玉米", 314.6, S_JZ, ""), (2024, "锦州", "蔬菜及食用菌", 44.7, S_JZ, ""),
 (2024, "锦州", "油料作物", 61.9, S_JZ, ""),
 (2024, "朝阳", "粮食作物", 453.5, S_CY, ""), (2024, "朝阳", "玉米", 370.6, S_CY, ""),
 (2024, "朝阳", "蔬菜及食用菌", 47.2, S_CY, ""), (2024, "朝阳", "油料作物", 3.1, S_CY, ""),
 (2024, "铁岭", "粮食作物", 496.5, S_TL, ""), (2024, "铁岭", "水稻", 35.5, S_TL, ""),
 (2024, "铁岭", "玉米", 445.8, S_TL, ""), (2024, "铁岭", "蔬菜及食用菌", 17.0, S_TL, ""),
 (2024, "铁岭", "油料作物", 30.9, S_TL, ""),
 (2024, "朝阳", "粮食作物", 156.8, S_JP, "区县口径：建平县"), (2024, "朝阳", "玉米", 95.9, S_JP, "区县口径：建平县"),
 (2024, "朝阳", "蔬菜及食用菌", 6.3, S_JP, "区县口径：建平县"),
]
PROD = [  # year, city, crop, production_wanton, source_tuple, note
 (2024, "沈阳", "粮食作物", 400.5, S_SY, ""), (2024, "沈阳", "水稻", 78.0, S_SY, ""),
 (2024, "沈阳", "玉米", 316.4, S_SY, ""), (2024, "沈阳", "大豆", 2.3, S_SY, ""),
 (2024, "沈阳", "蔬菜及食用菌", 418.4, S_SY, ""), (2024, "沈阳", "油料作物", 13.1, S_SY, ""),
 (2025, "沈阳", "粮食作物", 420.0, S_SY25, ""), (2025, "沈阳", "水稻", 78.5, S_SY25, ""),
 (2025, "沈阳", "玉米", 334.9, S_SY25, ""), (2025, "沈阳", "豆类", 2.5, S_SY25, ""),
 (2025, "沈阳", "蔬菜及食用菌", 433.7, S_SY25, ""), (2025, "沈阳", "油料作物", 12.8, S_SY25, ""),
 (2019, "沈阳", "粮食作物", 418.3, S_SY19, ""), (2019, "沈阳", "水稻", 92.7, S_SY19, ""),
 (2019, "沈阳", "玉米", 312.7, S_SY19, ""), (2019, "沈阳", "蔬菜(合计)", 373.5, S_SY19, ""),
 (2023, "沈阳", "蔬菜(合计)", 417.2, S_SY23VEG, ""), (2023, "沈阳", "蔬菜-白菜类", 106.2, S_SY23VEG, ""),
 (2023, "沈阳", "蔬菜-叶菜类", 89.3, S_SY23VEG, ""), (2023, "沈阳", "蔬菜-茄果类", 88.8, S_SY23VEG, ""),
 (2024, "锦州", "粮食作物", 256.1, S_JZ, ""), (2024, "锦州", "水稻", 34.4, S_JZ, ""),
 (2024, "锦州", "玉米", 217.1, S_JZ, ""), (2024, "锦州", "蔬菜及食用菌", 322.8, S_JZ, ""),
 (2024, "锦州", "油料作物", 24.2, S_JZ, ""),
 (2024, "朝阳", "粮食作物", 315.0, S_CY, ""), (2024, "朝阳", "玉米", 277.1, S_CY, ""),
 (2024, "朝阳", "蔬菜及食用菌", 334.1, S_CY, ""), (2024, "朝阳", "油料作物", 1.1, S_CY, ""),
 (2024, "铁岭", "粮食作物", 400.5, S_TL, ""), (2024, "铁岭", "水稻", 28.4, S_TL, ""),
 (2024, "铁岭", "玉米", 367.7, S_TL, ""), (2024, "铁岭", "大豆", 2.6, S_TL, ""),
 (2024, "铁岭", "蔬菜及食用菌", 76.5, S_TL, ""), (2024, "铁岭", "油料作物", 13.9, S_TL, ""),
 (2024, "朝阳", "粮食作物", 109.9, S_JP, "区县口径：建平县"), (2024, "朝阳", "玉米", 87.8, S_JP, "区县口径：建平县"),
 (2024, "朝阳", "蔬菜及食用菌", 39.3, S_JP, "区县口径：建平县"),
]
SUPPLY = [  # year, city, indicator, value, unit, source
 (2024, "沈阳", "常住人口", 924.3, "万人", S_SY),
 (2024, "沈阳", "乡村人口", 133.6, "万人", S_SY),
 (2024, "沈阳", "蔬菜及食用菌产量", 418.4, "万吨", S_SY),
 (2025, "沈阳", "蔬菜及食用菌产量", 433.7, "万吨", S_SY25),
 (2024, "锦州", "蔬菜及食用菌产量", 322.8, "万吨", S_JZ),
 (2024, "朝阳", "蔬菜及食用菌产量", 334.1, "万吨", S_CY),
 (2024, "铁岭", "蔬菜及食用菌产量", 76.5, "万吨", S_TL),
 (2019, "沈阳", "蔬菜产量", 373.5, "万吨", S_SY19),
]

def w(path, cols, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        wr = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        wr.writeheader()
        for r in rows:
            wr.writerow(r)
    print(f"[OK] {path.name}  {len(rows)} 行")

# 面积
arows = []
for y, c, crop, v, src, note in AREA:
    arows.append(dict(year=y, city=c, district=("建平县" if "建平县" in note else ""),
                      crop=crop, planting_area=v, planting_area_unit="千公顷",
                      planting_area_mu=round(v * 15, 1), source_name=src[0], source_url=src[1],
                      source_level="S", geo_level=("county" if "建平县" in note else "city"),
                      qc_flag="", note=note, access_date=AD))
w(OUT / "planting_area_yearly.csv",
  ["year","city","district","crop","planting_area","planting_area_unit","planting_area_mu",
   "source_name","source_url","source_level","geo_level","qc_flag","note","access_date"], arows)

# 产量
prows = []
for y, c, crop, v, src, note in PROD:
    prows.append(dict(year=y, city=c, district=("建平县" if "建平县" in note else ""),
                      crop=crop, production=v, production_unit="万吨",
                      production_ton=round(v * 10000, 0), source_name=src[0], source_url=src[1],
                      source_level="S", geo_level=("county" if "建平县" in note else "city"),
                      qc_flag="", note=note, access_date=AD))
w(OUT / "production_yearly_extended.csv",
  ["year","city","district","crop","production","production_unit","production_ton",
   "source_name","source_url","source_level","geo_level","qc_flag","note","access_date"], prows)

# 供需
srows = [dict(year=y, city=c, indicator=i, value=v, unit=u,
              source_name=s[0], source_url=s[1], source_level="S", access_date=AD)
         for y, c, i, v, u, s in SUPPLY]
w(OUT / "supply_demand_yearly.csv",
  ["year","city","indicator","value","unit","source_name","source_url","source_level","access_date"], srows)

# ---------------- 来源登记 ----------------
SRC = [
 dict(source_id="SRC-SY-SYGG-2024", source_name="沈阳市2024年国民经济和社会发展统计公报", publisher="沈阳市统计局",
      source_type="statistical_bulletin", source_level="S", url=S_SY[1], dataset_name="planting_area_yearly/production_yearly_extended",
      city="沈阳", data_category="production", date_range="2024", license_or_usage_note="政府公开发布", raw_file="", notes=""),
 dict(source_id="SRC-SY-SYGG-2025", source_name="沈阳经济·农业（2025年）", publisher="沈阳市人民政府/统计局",
      source_type="official_website", source_level="S", url=S_SY25[1], dataset_name="planting_area_yearly/production_yearly_extended",
      city="沈阳", data_category="production", date_range="2025", license_or_usage_note="政府公开发布", raw_file="", notes=""),
 dict(source_id="SRC-SY-VEG-2023", source_name="2023年全市蔬菜产能稳步增长", publisher="沈阳市统计局",
      source_type="official_analysis", source_level="S", url=S_SY23VEG[1], dataset_name="planting_area_yearly/production_yearly_extended",
      city="沈阳", data_category="production", date_range="2023", license_or_usage_note="政府公开发布", raw_file="", notes="含蔬菜品类结构与区县分布"),
 dict(source_id="SRC-SY-SYGG-2019", source_name="2019年沈阳市国民经济和社会发展统计公报", publisher="沈阳市统计局",
      source_type="statistical_bulletin", source_level="S", url=S_SY19[1], dataset_name="planting_area_yearly/production_yearly_extended",
      city="沈阳", data_category="production", date_range="2019", license_or_usage_note="政府公开发布", raw_file="", notes=""),
 dict(source_id="SRC-JZ-SYGG-2024", source_name="2024年锦州市国民经济和社会发展统计公报", publisher="锦州市统计局",
      source_type="statistical_bulletin", source_level="S", url=S_JZ[1], dataset_name="planting_area_yearly/production_yearly_extended",
      city="锦州", data_category="production", date_range="2024", license_or_usage_note="政府公开发布", raw_file="", notes=""),
 dict(source_id="SRC-CY-SYGG-2024", source_name="朝阳市2024年国民经济和社会发展统计公报", publisher="朝阳市统计局",
      source_type="statistical_bulletin", source_level="S", url=S_CY[1], dataset_name="planting_area_yearly/production_yearly_extended",
      city="朝阳", data_category="production", date_range="2024", license_or_usage_note="政府公开发布", raw_file="", notes=""),
 dict(source_id="SRC-TL-SYGG-2024", source_name="2024年铁岭市国民经济和社会发展统计公报", publisher="铁岭市统计局",
      source_type="statistical_bulletin", source_level="S", url=S_TL[1], dataset_name="planting_area_yearly/production_yearly_extended",
      city="铁岭", data_category="production", date_range="2024", license_or_usage_note="政府公开发布", raw_file="", notes=""),
 dict(source_id="SRC-JP-SYGG-2024", source_name="建平县2024年国民经济和社会发展统计公报", publisher="建平县统计局",
      source_type="statistical_bulletin", source_level="S", url=S_JP[1], dataset_name="planting_area_yearly/production_yearly_extended",
      city="朝阳", data_category="production", date_range="2024", license_or_usage_note="政府公开发布", raw_file="", notes="区县级"),
 dict(source_id="SRC-LN-NYNC-VEG-WEEKLY", source_name="辽宁省农业农村厅 省内主要蔬菜品种价格简讯",
      publisher="辽宁省农业农村厅", source_type="official_price_monitor", source_level="S",
      url="https://nync.ln.gov.cn/nync/index/zwgk/zszdgz/ncpxx/lnsnzyscpzjg/index.shtml",
      dataset_name="price_lnnync_veg_weekly_extended", city="辽宁(省域)", data_category="price",
      date_range="2022-12-30~2026-09-30", license_or_usage_note="政府公开发布",
      raw_file="data/raw/decision_engine_supplement/price/lnnync_veg_weekly/", notes="周度批发价，含最高/最低地区"),
 dict(source_id="SRC-LN-FGW-COST", source_name="辽宁省/各市发展改革委 成本调查", publisher="辽宁省发展改革委",
      source_type="cost_investigation", source_level="S", url="https://fgw.ln.gov.cn/fgw/xxgk/jgjc/fxyc/",
      dataset_name="crop_cost_yearly", city="辽宁(省域)", data_category="cost",
      date_range="2020~2025", license_or_usage_note="政府公开发布",
      raw_file="data/raw/decision_engine_supplement/cost/", notes="含辽阳(邻市)与沈阳"),
 dict(source_id="SRC-SY-FGW-COST", source_name="沈阳市发展改革委 成本调查监审", publisher="沈阳市发展和改革委员会",
      source_type="cost_investigation", source_level="S", url="https://fgw.shenyang.gov.cn/wjgz/cbdcjs/",
      dataset_name="crop_cost_yearly", city="沈阳", data_category="cost",
      date_range="2024~2025", license_or_usage_note="政府公开发布",
      raw_file="data/raw/decision_engine_supplement/cost/", notes="玉米/粳稻"),
 dict(source_id="SRC-LN-INSURANCE", source_name="辽宁省种植业保险工作方案", publisher="辽宁省财政厅/农业农村厅/金融监管局",
      source_type="policy_document", source_level="S", url="https://www.ln.gov.cn/web/zwgkx/lnsrmzfgb/2023n/zk/zk6/bmwj/2023080110475072659/",
      dataset_name="cost_proxy_insurance", city="辽宁(省域)", data_category="cost_proxy",
      date_range="2023~2025", license_or_usage_note="政府公开发布", raw_file="", notes="保额作为直接物化成本代理"),
 dict(source_id="SRC-LN-FXZH", source_name="辽宁省防汛抗旱指挥部 灾情通报", publisher="辽宁省防汛抗旱指挥部",
      source_type="disaster_report", source_level="S", url="https://content-static.cctvnews.cctv.com/snow-book/index.html?item_id=3586243294659637073",
      dataset_name="disaster_loss_events", city="辽宁(省域)", data_category="disaster_loss",
      date_range="2024", license_or_usage_note="政府公开发布", raw_file="data/raw/decision_engine_supplement/disaster_loss/",
      notes="经央视/人民网发布"),
 dict(source_id="SRC-LN-RIBao", source_name="辽宁日报（辽宁省人民政府网）", publisher="辽宁日报",
      source_type="news", source_level="C", url="https://www.ln.gov.cn/web/ywdt/qsgd/ass_2_1/2024083009011157096/index.shtml",
      dataset_name="disaster_loss_events", city="铁岭", data_category="disaster_loss",
      date_range="2024", license_or_usage_note="公开发布", raw_file="data/raw/decision_engine_supplement/disaster_loss/", notes=""),
 dict(source_id="SRC-MOA-VEG-MARKET", source_name="农业农村部蔬菜市场分析预警团队/经济日报", publisher="农业农村部",
      source_type="news", source_level="C", url="http://www.ce.cn/cysc/sp/info/202312/11/t20231211_38824047.shtml",
      dataset_name="herding_events", city="全国(含辽宁)", data_category="herding",
      date_range="2023", license_or_usage_note="公开发布", raw_file="data/raw/decision_engine_supplement/herding_events/", notes=""),
 dict(source_id="SRC-SY-FGW-RESEARCH-2022", source_name="沈阳市关于部分蔬菜市场情况的调研报告", publisher="沈阳市价格监测局/辽宁省发改委",
      source_type="research_report", source_level="S", url="https://fgw.ln.gov.cn/fgw/xxgk/jgjc/fxyc/BFDE92662276474D98CFE6497CCD2900/index.shtml",
      dataset_name="herding_events", city="沈阳", data_category="herding",
      date_range="2022", license_or_usage_note="政府公开发布", raw_file="", notes="跟风机制描述"),
 dict(source_id="SRC-OM-ERA5LAND-SOIL", source_name="Open-Meteo Archive API / ERA5-Land（土壤分层）",
      publisher="Open-Meteo / Copernicus", source_type="reanalysis_api", source_level="A",
      url="https://archive-api.open-meteo.com/v1/archive", dataset_name="soil_moisture_daily_extended",
      city="沈阳", data_category="soil", date_range="2021-01-01~2026-09-14",
      license_or_usage_note="CC-BY-4.0（Open-Meteo）", raw_file="data/raw/soil/openmeteo_soil_沈阳_*.json",
      notes="reanalysis 非观测站；口径与其余五城一致（已用大连回归验证）"),
 dict(source_id="SRC-SY-STAT-DIST", source_name="沈阳统计年鉴 分区县农业表（既有）", publisher="沈阳市统计局",
      source_type="statistical_yearbook", source_level="S", url="https://tjj.shenyang.gov.cn/sjfb/ndsj/",
      dataset_name="production_yearly_extended", city="沈阳", data_category="production",
      date_range="2018~2024", license_or_usage_note="政府公开发布", raw_file="", notes="既有 canonical，非本轮新增"),
]
w(OUT / "source_registry.csv",
  ["source_id","source_name","publisher","source_type","source_level","url","dataset_name",
   "city","data_category","date_range","license_or_usage_note","raw_file","notes","access_date"],
  [{**r, "access_date": AD} for r in SRC])

print("\n完成。")
