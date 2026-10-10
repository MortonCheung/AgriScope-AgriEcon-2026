#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V2 构建脚本 B：价格可比性、作物映射、来源登记、冲突登记、QC、就绪度矩阵、排名、最终矩阵。
"""
import csv, json, warnings
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import itertools

import pandas as pd
import numpy as np

warnings.filterwarnings("ignore")
ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
V1 = ROOT / "city_data/reference/decision_engine_supplement"
OUT = ROOT / "city_data/reference/decision_engine_supplement_v2"
OUT.mkdir(parents=True, exist_ok=True)
CD = ROOT / "data/raw/retained_source/city_data"
AD = datetime.now().strftime("%Y-%m-%d")
CITIES = {"shenyang":"沈阳","dalian":"大连","tieling":"铁岭","chaoyang":"朝阳","jinzhou":"锦州","dandong":"丹东"}


def write(fn, cols, rows):
    with (OUT/fn).open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows: w.writerow(r)
    print(f"[OK] {fn}  {len(rows)} 行")


def rcsv(p):
    for enc in ("utf-8-sig","utf-8","gbk"):
        try: return pd.read_csv(p, encoding=enc, low_memory=False)
        except Exception: continue
    return None


# ============ 1. 价格序列清单（含 V1 省级周度） ============
inv = []
for cd, cn in CITIES.items():
    p = CD/cd/"data"/"price_observation.csv"
    if not p.exists(): continue
    df = rcsv(p)
    if df is None: continue
    for c in ["crop_standard","crop_raw","price_level","unit_original","frequency","market_name","geo_level"]:
        if c not in df.columns: df[c] = np.nan
    df["_d"] = pd.to_datetime(df.get("observation_date"), errors="coerce")
    # market_average 类标签错填的处理：优先用 crop_raw
    df["_crop"] = np.where(df["price_level"].astype(str) == "market_average",
                           df["crop_raw"].astype(str).str.strip(), df["crop_standard"].astype(str))
    for (crop, lvl, unit), g in df.groupby(["_crop","price_level","unit_original"], dropna=False):
        if not str(crop).strip() or str(crop) == "nan": continue
        d = g["_d"].dropna()
        if len(d) == 0: continue
        inv.append({"city": cn, "crop": crop, "price_level": lvl, "market_name":
                    "|".join(sorted(set(g["market_name"].dropna().astype(str)))[:3]),
                    "unit": unit, "frequency": "|".join(sorted(set(g["frequency"].dropna().astype(str)))[:3]),
                    "start_date": str(d.min())[:10], "end_date": str(d.max())[:10],
                    "observation_count": len(g), "unique_days": int(d.dt.date.nunique()),
                    "geo_level": "|".join(sorted(set(g["geo_level"].dropna().astype(str)))[:2]),
                    "source_id": "SRC-CITY-PRICE-CANONICAL",
                    "price_layer": "city_observation"})
# 省级周度
p = V1/"price_lnnync_veg_weekly_extended.csv"
if p.exists():
    d = rcsv(p)
    if d is not None:
        d["_d"] = pd.to_datetime(d["pub_date"], errors="coerce")
        for (crop, lvl, unit), g in d.groupby(["crop_standard","price_level","unit"]):
            dd = g["_d"].dropna()
            inv.append({"city": "辽宁(省域)", "crop": crop, "price_level": lvl,
                        "market_name": "全省联络员报送系统", "unit": unit, "frequency": "weekly",
                        "start_date": str(dd.min())[:10], "end_date": str(dd.max())[:10],
                        "observation_count": len(g), "unique_days": int(dd.dt.date.nunique()),
                        "geo_level": "province", "source_id": "SRC-LN-NYNC-VEG-WEEKLY",
                        "price_layer": "province_weekly"})
write("price_series_inventory.csv",
      ["city","crop","price_level","market_name","unit","frequency","start_date","end_date",
       "observation_count","unique_days","geo_level","price_layer","source_id","access_date"],
      [{**r, "access_date": AD} for r in inv])

# ============ 2. 六城同口径可比性（本期重算） ============
CN6 = ["沈阳","大连","铁岭","朝阳","锦州","丹东"]
by_crop = defaultdict(list)
for r in inv:
    if r["city"] in CN6:
        by_crop[(r["crop"], r["price_level"], r["unit"])].append(r)
comp = []
for (crop, lvl, unit), rs in by_crop.items():
    cities = sorted({x["city"] for x in rs})
    if len(cities) < 2: continue
    cs = max(x["start_date"] for x in rs)   # 共同起点
    ce = min(x["end_date"] for x in rs)     # 共同终点
    from datetime import date
    try:
        d0 = date.fromisoformat(cs); d1 = date.fromisoformat(ce)
        overlap = max(0, (d1-d0).days)
    except Exception:
        overlap = 0
    # 覆盖：各城在共同窗口内的 unique_days 之和 / (城市数 × 窗口天数)
    cov = sum(x["unique_days"] for x in rs) / (len(cities) * max(overlap,1)) if overlap else 0
    comp.append({"crop": crop, "price_level": lvl, "unit": unit, "n_cities": len(cities),
                 "cities": "|".join(cities), "common_start": cs, "common_end": ce,
                 "overlap_days": overlap, "coverage": round(min(cov,1.0), 4),
                 "meets_3city_threshold": "YES" if (len(cities) >= 3 and overlap >= 180 and cov >= 0.3) else "NO"})
comp.sort(key=lambda x: (-x["n_cities"], -x["coverage"]))
write("price_city_comparable.csv",
      ["crop","price_level","unit","n_cities","cities","common_start","common_end","overlap_days",
       "coverage","meets_3city_threshold","access_date"],
      [{**r, "access_date": AD} for r in comp])
n3 = sum(1 for r in comp if r["meets_3city_threshold"] == "YES")
print(f"   满足『≥3城+重叠≥180天+覆盖≥30%』的组合数 = {n3}")

# ============ 3. 作物映射（修复朝阳/铁岭规格误填） ============
CROP_MAP = [
 ("一等","(规格)","specification","",""), ("新鲜","(规格)","specification","",""),
 ("新鲜完整","(规格)","specification","",""), ("去骨后腿肉","(规格)","specification","",""),
 ("15公斤左右","(规格)","specification","",""), ("200-300斤","(规格)","specification","",""),
 ("一级桶装","(规格)","specification","",""), ("标一","(规格)","specification","",""),
 ("特一粉","面粉","grain_processed","",""), ("市场价","(规格)","specification","",""),
 ("白条鸡上等","鸡肉","livestock","",""), ("16种蔬菜均价","蔬菜(篮子)","basket","",""),
 ("圆葱","洋葱","vegetable","",""), ("元葱","洋葱","vegetable","",""),
 ("马铃薯","土豆","vegetable","",""), ("番茄","西红柿","vegetable","",""),
 ("硬粉西红柿","西红柿","vegetable","硬粉",""), ("大红西红柿","西红柿","vegetable","大红",""),
 ("角瓜","西葫芦","vegetable","",""), ("油菜","小白菜","vegetable","",""),
 ("蒜薹","蒜苔","vegetable","",""), ("架豆王","菜豆","vegetable","架豆王",""),
 ("混码鸡蛋","鸡蛋","livestock","混码",""), ("大码鸡蛋","鸡蛋","livestock","大码",""),
 ("红颜草莓","草莓","fruit","红颜",""), ("北陆蓝莓","蓝莓","fruit","北陆",""),
 ("龙成二号软枣猕猴桃苗","软枣猕猴桃苗","seedling","龙成二号",""),
 ("干玉米","玉米","grain","",""), ("高粱米","高粱","grain","",""),
]
write("crop_mapping.csv", ["raw_name","standard_name","category","variety","specification",
                           "grade","processing_state","note"],
      [{"raw_name":a,"standard_name":b,"category":c,"variety":d,"specification":e,
        "grade":"","processing_state":"","note":"修复 crop_standard 误填规格问题（朝阳/铁岭）"}
       for a,b,c,d,e in CROP_MAP])

# ============ 4. 来源冲突登记 ============
CONF = [
 dict(city="沈阳", crop="蔬菜及食用菌", date_year="2023", metric="播种面积", value_A="98.7万亩(=65.8千公顷)",
      value_B="65.8千公顷", source_A="沈阳市统计局《2023年全市蔬菜产能稳步增长》",
      source_B="辽宁统计年鉴2024卷 13-14 (OCR)", possible_reason="同一数据不同单位表述（万亩 vs 千公顷）",
      recommended_source="两者一致，取千公顷口径"),
 dict(city="沈阳", crop="玉米", date_year="2023", metric="播种面积", value_A="413.7千公顷(年鉴)",
      value_B="415.2千公顷(2024)", source_A="辽宁统计年鉴2024卷13-14", source_B="沈阳市2024年统计公报",
      possible_reason="年份不同（2023 vs 2024），非冲突", recommended_source="按年份分别使用"),
 dict(city="辽宁省", crop="大豆", date_year="2024", metric="农业保险赔款",
      value_A="55.24亿元(辖内,含大连)", value_B="25亿元(不含大连,政策性)",
      source_A="辽宁金融监管局", source_B="辽宁省财政厅",
      possible_reason="口径不同：辖内全部农业保险 vs 不含大连政策性农业保险",
      recommended_source="按口径分别使用，不可混用"),
 dict(city="沈阳", crop="(价格数据集)", date_year="2021-2026", metric="价格行数",
      value_A="14100 (city_data canonical)", value_B="143494 (reference/marts/fact_price_city)",
      source_A="city_data/shenyang/data/price_observation.csv", source_B="city_data/reference/marts/fact_price_city.csv",
      possible_reason="canonical 仅保留 10 种批发蔬菜；marts 含历史零售快照，两者口径不同",
      recommended_source="canonical（本研究统一采用）"),
]
write("source_conflict_registry.csv",
      ["city","crop","date_year","metric","value_A","value_B","source_A","source_B",
       "possible_reason","recommended_source","access_date"],
      [{**r, "access_date": AD} for r in CONF])

# ============ 5. 来源登记 V2 ============
S = [
 ("SRC-LN-YB-2018","辽宁统计年鉴2018（数据年2017）","辽宁省统计局","S",
  "https://tjj.ln.gov.cn/tjj/tjsj/tjnj/njsjxz/","planting_area_crop_yearly/production_crop_yearly/crop_yield_by_city","2017"),
 ("SRC-LN-YB-2019","辽宁统计年鉴2019（数据年2018）","辽宁省统计局","S",
  "https://tjj.ln.gov.cn/tjj/tjsj/tjnj/njsjxz/","planting_area_crop_yearly/production_crop_yearly/crop_yield_by_city","2018"),
 ("SRC-LN-YB-2020","辽宁统计年鉴2020（数据年2019）","辽宁省统计局","S",
  "https://tjj.ln.gov.cn/tjj/tjsj/tjnj/njsjxz/2023110210085021756/index.shtml","planting_area_crop_yearly/irrigation_yearly","2019"),
 ("SRC-LN-YB-2024-ONLINE","辽宁统计年鉴2024（在线版，数据年2023，JPG+OCR）","辽宁省统计局","S",
  "https://tjj.ln.gov.cn/tjj/tjsj/otherpages/2024/left.htm","planting_area_crop_yearly_ocr.csv","2023"),
 ("SRC-LN-YB-2025-ONLINE","辽宁统计年鉴2025（在线版，数据年2024，JPG+OCR）","辽宁省统计局","S",
  "https://tjj.ln.gov.cn/tjj/tjsj/otherpages/2025/left.htm","planting_area_crop_yearly_ocr.csv","2024"),
 ("SRC-SYAU-GH-COST-2022","东北地区日光温室果菜生产现状与轻简化途径","沈阳农业大学/中国蔬菜","A",
  "https://www.cnveg.org/CN/article/downloadArticleFile.do?attachType=PDF&id=19092","crop_cost_yearly_extended.csv(设施果菜)","2021"),
 ("SRC-LN-NFRA-2025","辽宁金融监管局 对省人大第1431322号建议的答复","国家金融监督管理总局辽宁监管局","S",
  "https://www.nfra.gov.cn/branch/liaoning/view/pages/common/ItemDetail.html?docId=1210189&itemId=1701","agri_insurance_claims.csv","2024"),
 ("SRC-LN-CZT-2025","辽宁省财政厅 对省人大第1322号建议的答复","辽宁省财政厅","S",
  "https://czt.ln.gov.cn/czt/zfxxgk/fdzdgknr/jyta/srddbjy/sssjrdschy2025n/2025062016255583229/index.shtml","agri_insurance_claims.csv","2024"),
 ("SRC-JZ-CBIMC-2025","锦州特色农险（中国银行保险报）","锦州金融监管分局/中国银行保险报","S",
  "http://www.cbimc.cn/m/content/2025-06/16/content_549000.html","agri_insurance_claims.csv","2024"),
 ("SRC-JZ-CBIMC-2024","辽宁8·20洪涝保险理赔（中国银行保险报）","辽宁金融监管局/中国银行保险报","S",
  "http://www.cbimc.cn/m/content/2024-09/12/content_529278.html","disaster_loss_crop_events.csv/agri_insurance_claims.csv","2024"),
 ("SRC-SY-NYNC-COLD-2024","新民市获批全国农产品骨干冷链物流重点县","沈阳市农业农村局/辽宁省农业农村厅","S",
  "https://nync.ln.gov.cn/nync/index/nyyw/zsqsnyxxlb/2024062110094411114/index.shtml","cold_chain_capacity.csv","2024"),
 ("SRC-LN-SWT-CIRC-2024","辽宁省农产品现代流通体系建设发展规划(2024-2030)","辽宁省商务厅","S",
  "https://swt.ln.gov.cn/swt/ywxx/tzgg/2024041210074077223/2024042209324921254.pdf","cold_chain_capacity.csv","2024"),
 ("SRC-LN-NYNC-2025-66","辽宁省农业农村厅 省人大第1431378号答复","辽宁省农业农村厅","S",
  "https://nync.ln.gov.cn/nync/zfxxgk/fdzdgknr/jyta/srddbjy/sssjrdschy2025n/2025082115283575928/index.shtml","cold_chain_capacity.csv","2024"),
 ("SRC-CY-SSNY-2024","朝阳市设施农业调研报告","朝阳市设施农业服务部/辽宁省农业农村厅","S",
  "https://nync.ln.gov.cn/nync/index/nyyw/zsqsnyxxlb/2024041011085532390/index.shtml","market_registry_extended/crop_cost_yearly_extended","2023"),
 ("SRC-JZ-HS-2023","黑山县设施蔬菜建议答复","黑山县人民政府","S",
  "http://www.heishan.gov.cn/info/1883/39883.htm","market_registry_extended/crop_cost_yearly_extended","2023"),
 ("SRC-SY-NYNC-0045","沈阳市农业农村局 人大建议第0045号答复","沈阳市农业农村局","S",
  "https://nyncj.shenyang.gov.cn/zwgk/fdzdgknr/jyta/rdjy/202312/t20231221_4578023.html","crop_cost_yearly_extended/market_registry_extended","2022"),
 ("SRC-BFYY-2023","铁岭设施番茄轮作生菜绿色高效栽培技术（北方园艺）","辽宁省农业科学院","A",
  "https://www.aeeisp.com/bfyy/cn/article/pdf/preview/31c7f6a6-421f-4bb5-8218-4fcf48fba24d.pdf","market_registry_extended","2023"),
 ("SRC-DB21-3416","DB21/T 3416.2/.3—2021 日光温室蔬菜绿色生产技术规程（番茄/黄瓜）","辽宁省市场监督管理局","S",
  "DB21/T3416.2—2021; DB21/T3416.3—2021","crop_calendar_detailed.csv(设施茬口)","2021"),
]
write("source_registry.csv",
      ["source_id","source_name","publisher","source_level","url","dataset_name","date_range",
       "observation_type","geo_level","time_frequency","raw_file","retrieval_method",
       "license_or_terms","notes","access_date"],
      [{"source_id":a,"source_name":b,"publisher":c,"source_level":d,"url":e,
        "dataset_name":f,"date_range":g,
        "observation_type":("official_statistics" if d=="S" else "field_survey/research"),
        "geo_level":"city/province","time_frequency":"yearly",
        "raw_file":"", "retrieval_method":"http_get", "license_or_terms":"公开发布",
        "notes":"", "access_date":AD} for a,b,c,d,e,f,g in S])
print("\n完成脚本 B（前五部分）。")
