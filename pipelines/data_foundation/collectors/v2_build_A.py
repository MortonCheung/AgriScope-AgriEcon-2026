#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Decision Engine 数据补全 V2 —— 构建脚本 A
1) 面积：并入年鉴 OCR（2023/2024）到 planting_area_crop_yearly.csv
2) 成本：蔬菜（日光温室果菜）成本、设施建设成本、区域代理
3) 农业保险赔付/保费
4) 灾损（并入 V1 事件）
5) 冷链/仓储
6) 需求端
7) 市场登记
8) 跟风事件扩展
9) 来源登记 + SHA256
所有数值均来自真实公开来源，附 source_url / source_text，禁止编造。
"""
import csv, hashlib, json, re
from pathlib import Path
from datetime import datetime

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
V1 = ROOT / "data/raw/retained_source/city_data" / "reference" / "decision_engine_supplement"
OUT = ROOT / "data/raw/retained_source/city_data" / "reference" / "decision_engine_supplement_v2"
RAW2 = ROOT / "data/raw" / "decision_engine_supplement_v2"
OUT.mkdir(parents=True, exist_ok=True)
AD = datetime.now().strftime("%Y-%m-%d")


def write(fn, cols, rows, subdir=None):
    p = (OUT / fn) if not subdir else (OUT / subdir / fn)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"[OK] {p.relative_to(OUT)}  {len(rows)} 行")


# ============ 1. 面积：并入 OCR 2023/2024（已通过粮食=分项之和校验） ============
OCR_AREA = [
 # year, city, 总, 粮, 水稻, 小麦, 玉米, 高粱, 谷子, 薯类, 大豆, 其他杂粮, 经济作物, 油料, 花生, 葵花籽, 蔬菜
 (2023,"沈阳",680.5,546.3,111.8,0.5,413.7,0.8,0.8,7.2,11.2,0.4,134.2,32.0,31.8,0.3,65.8),
 (2023,"大连",332.6,270.1,17.9,0.1,195.7,0.5,0.6,12.7,42.0,0.6,62.5,17.4,17.4,"",38.1),
 (2023,"丹东",212.9,180.9,47.4,"",120.0,0.1,3.8,9.2,0.2,"",32.0,2.8,2.8,1.4,13.5),
 (2023,"锦州",478.6,367.4,37.4,0.1,317.5,1.1,0.3,4.8,6.3,"",111.2,61.7,61.7,"",42.5),
 (2023,"铁岭",553.0,496.3,35.7,0.1,445.9,0.1,"",4.8,9.8,"",56.6,30.3,30.3,1.2,17.8),
 (2023,"朝阳",507.3,453.0,0.12,0.9,374.9,27.5,35.6,2.7,6.4,4.9,54.4,2.8,0.7,2.1,45.7),
 (2024,"沈阳",683.3,546.3,110.3,0.4,415.2,0.8,0.7,6.9,11.7,0.2,137.0,33.3,33.2,0.1,67.0),
 (2024,"大连",334.1,268.7,18.9,0.1,191.8,0.6,0.5,13.1,42.9,0.9,65.3,19.1,19.1,"",39.0),
 (2024,"丹东",212.4,180.0,47.3,0.04,119.0,0.1,0.03,4.0,9.4,0.1,32.4,3.4,3.3,1.2,13.5),
 (2024,"锦州",481.6,367.7,40.4,0.1,314.6,0.7,0.2,4.9,6.9,0.01,113.9,61.9,61.8,"",44.7),
 (2024,"铁岭",552.3,496.5,35.5,0.1,445.8,0.1,0.02,4.2,10.7,0.2,55.8,30.9,30.9,1.2,17.0),
 (2024,"朝阳",510.1,453.5,0.09,0.6,370.6,28.3,36.7,3.9,6.9,6.4,56.6,3.1,0.8,2.3,47.2),
]
FIELD = ["总播种面积","粮食作物","水稻","小麦","玉米","高粱","谷子","薯类","大豆",
         "其他杂粮","经济作物","油料","花生","葵花籽","蔬菜"]

# 读入 XLS 提取结果（长表），转宽表
xls = list(csv.DictReader((OUT/"planting_area_crop_yearly.csv").open(encoding="utf-8-sig")))
wide = {}
for r in xls:
    key = (int(r["year"]), r["city"])
    wide.setdefault(key, {"year": r["year"], "city": r["city"], "province": "辽宁省",
        "source_table": "辽宁统计年鉴 XLS 13-17/13-16 各地区农作物播种面积",
        "source_file": r["source_file"], "unit": "千公顷",
        "quality_flag": "XLS_parsed", "source_level": "S", "access_date": AD})
    col = r["column"].replace("粮食作物-", "").replace("经济作物-", "").replace("其他作物-", "")
    wide[key][col] = r["value"]

cols_area = ["year","city","province"] + FIELD + ["source_table","source_file","unit",
             "quality_flag","source_level","access_date"]
rows = list(wide.values())
for (y, c, *v) in OCR_AREA:
    r = {"year": str(y), "city": c, "province": "辽宁省",
         "source_table": "辽宁统计年鉴（2024/2025卷）13-14 各地区农作物播种面积（OCR）",
         "source_file": f"yearbook_{y+1}_ocr/13-14.jpg", "unit": "千公顷",
         "quality_flag": "OCR_derived; grain_sum_check=PASS; cross_checked_vs_bulletin",
         "source_level": "S", "access_date": AD}
    for k, val in zip(FIELD, v):
        r[k] = val
    rows.append(r)
# 补齐列
for r in rows:
    for k in cols_area:
        r.setdefault(k, "")
write("planting_area_crop_yearly.csv", cols_area, rows)

# ============ 2. 成本（含蔬菜日光温室） ============
COST = [
 # 来源：沈阳农业大学（中国蔬菜2022）东北8市日光温室果菜调研，110份问卷
 dict(year=2021, city="东北(含沈阳/朝阳/锦州/铁岭)", district="", crop="设施果菜(番茄/黄瓜)",
      cost_type="annual_operating_cost", production_system="solar_greenhouse",
      total_cost_per_mu=23840, labor_cost=10601, direct_production_cost=9967,
      depreciation_cost=3272, seed_cost=2302, fertilizer_cost=3508, pesticide_cost=1056,
      film_cost=2003, water_electricity_cost=439, other_cost=668,
      revenue_per_mu=55299, net_income_per_mu=31459,
      is_proxy="true", proxy_type="regional_proxy",
      proxy_reason="东北地区8个设施蔬菜主产市（含辽宁6市）加权平均，非单城市实测",
      original_geo_level="regional_northeast_china", geo_level="regional",
      observation_type="field_survey", source_level="A",
      source_name="余朝阁 等（沈阳农业大学园艺学院/设施园艺教育部重点实验室）中国蔬菜 2022(4)",
      source_url="https://www.cnveg.org/CN/article/downloadArticleFile.do?attachType=PDF&id=19092",
      source_text="东北地区日光温室果菜每年总收益平均达55 299元·(667m2)-1，运行成本每年为23 840元·(667m²)-1，占总收益的43.1%，每年纯收益31 459元。人工成本占44.5%、直接生产成本占41.8%、设备折旧占13.7%。",
      note="单位口径：元/667m²≈元/亩；不含日光温室基本建筑成本；成本构成：棚膜20.1%/秧苗23.1%/肥料35.2%/农药10.6%/水电4.4%/其他6.7%"),
 # 设施建设成本（一次性）
 dict(year=2023, city="朝阳", district="", crop="设施温室(建设)", cost_type="greenhouse_construction_cost",
      production_system="solar_greenhouse", total_cost_per_mu="", labor_cost="", direct_production_cost="",
      depreciation_cost="", seed_cost="", fertilizer_cost="", pesticide_cost="", film_cost="",
      water_electricity_cost="", other_cost="", revenue_per_mu="", net_income_per_mu="",
      is_proxy="false", proxy_type="", proxy_reason="", original_geo_level="city", geo_level="city",
      observation_type="official_report", source_level="S",
      source_name="朝阳市设施农业服务部 调研报告（辽宁省农业农村厅发布）",
      source_url="https://nync.ln.gov.cn/nync/index/nyyw/zsqsnyxxlb/2024041011085532390/index.shtml",
      source_text="农户自建1栋跨度9-10米、长度100米高标准温室，成本大约在20万元左右（工程招标在30万左右）",
      note="单栋口径（约1亩/栋按100m×9-10m计），非亩均年成本"),
 dict(year=2023, city="锦州", district="黑山县", crop="设施温室(建设)", cost_type="greenhouse_construction_cost",
      production_system="solar_greenhouse", total_cost_per_mu=100000, labor_cost="", direct_production_cost="",
      depreciation_cost="", seed_cost="", fertilizer_cost="", pesticide_cost="", film_cost="",
      water_electricity_cost="", other_cost="", revenue_per_mu="", net_income_per_mu="",
      is_proxy="false", proxy_type="", proxy_reason="", original_geo_level="county", geo_level="county",
      observation_type="official_reply", source_level="S",
      source_name="黑山县人民政府 人大建议答复（第18号）",
      source_url="http://www.heishan.gov.cn/info/1883/39883.htm",
      source_text="每亩日光温室成本大约在10万元左右。钢架冷棚高度在2.5米-3米，跨度10米，按目前建设标准，每亩钢架冷棚成本大约在3.2万元左右。",
      note="另有钢架冷棚 3.2 万元/亩"),
 dict(year=2023, city="沈阳", district="新民市", crop="设施温室(建设)", cost_type="greenhouse_construction_cost",
      production_system="solar_greenhouse", total_cost_per_mu=50000, labor_cost="", direct_production_cost="",
      depreciation_cost="", seed_cost="", fertilizer_cost="", pesticide_cost="", film_cost="",
      water_electricity_cost="", other_cost="", revenue_per_mu="", net_income_per_mu="",
      is_proxy="false", proxy_type="", proxy_reason="", original_geo_level="county", geo_level="county",
      observation_type="official_reply", source_level="S",
      source_name="沈阳市农业农村局 人大建议答复（第0045号）",
      source_url="https://nyncj.shenyang.gov.cn/zwgk/fdzdgknr/jyta/rdjy/202312/t20231221_4578023.html",
      source_text="新民大民屯地区目前推广建设的高标准温室，跨度11.5米，高度5.5米，长度200-300米，设施内生产面积可达4亩左右，每亩建设成本近5万元，年生产蔬菜3茬，亩效益5-6万元",
      note="建设成本（一次性），非年运行成本"),
]
COST_COLS = ["year","city","district","crop","cost_type","production_system","total_cost_per_mu",
             "labor_cost","direct_production_cost","depreciation_cost","seed_cost","fertilizer_cost",
             "pesticide_cost","film_cost","water_electricity_cost","other_cost","revenue_per_mu",
             "net_income_per_mu","is_proxy","proxy_type","proxy_reason","original_geo_level",
             "geo_level","observation_type","source_level","source_name","source_url",
             "source_text","note","access_date"]
# 并入 V1 的粮食成本
v1cost = list(csv.DictReader((V1/"crop_cost_yearly.csv").open(encoding="utf-8-sig")))
merged = []
for r in v1cost:
    merged.append({**r, "cost_type": "annual_full_cost", "production_system": "open_field",
                   "is_proxy": ("true" if r["geo_level"].startswith("neighbor") else "false"),
                   "proxy_type": ("regional_proxy" if r["geo_level"].startswith("neighbor") else ""),
                   "proxy_reason": ("邻市（辽阳）成本调查，非六城" if r["geo_level"].startswith("neighbor") else ""),
                   "original_geo_level": r["geo_level"], "observation_type": "official_cost_survey",
                   "total_cost_per_mu": r["cost_total_per_mu"]})
merged += COST
write("crop_cost_yearly_extended.csv", COST_COLS, merged)

# ============ 3. 农业保险 保费/赔付 ============
INS = [
 dict(year=2024, scope="辽宁省(辖内,含大连)", crop="全部农业保险", metric="premium_income",
      value=64.21, unit="亿元", yoy_pct=17.0, source_level="S",
      source_name="辽宁金融监管局 对省人大第1431322号建议的答复",
      source_url="https://www.nfra.gov.cn/branch/liaoning/view/pages/common/ItemDetail.html?docId=1210189&itemId=1701",
      source_text="2024年，辽宁辖内农业保险共实现保费收入64.21亿元，同比增长17%，为249.66万户次农民提供风险保障1325.94亿元",
      note="辖内口径含大连"),
 dict(year=2024, scope="辽宁省(辖内,含大连)", crop="全部农业保险", metric="risk_coverage",
      value=1325.94, unit="亿元", yoy_pct="", source_level="S",
      source_name="辽宁金融监管局（同上）", source_url="https://www.nfra.gov.cn/branch/liaoning/view/pages/common/ItemDetail.html?docId=1210189&itemId=1701",
      source_text="为249.66万户次农民提供风险保障1325.94亿元", note=""),
 dict(year=2024, scope="辽宁省(辖内,含大连)", crop="全部农业保险", metric="claim_payout",
      value=55.24, unit="亿元", yoy_pct="", source_level="S",
      source_name="辽宁金融监管局（同上）", source_url="https://www.nfra.gov.cn/branch/liaoning/view/pages/common/ItemDetail.html?docId=1210189&itemId=1701",
      source_text="2024年，辽宁农业保险累计赔款支出55.24亿元，受益农户219.42万户次", note=""),
 dict(year=2024, scope="辽宁省(不含大连)", crop="政策性农业保险", metric="premium_income",
      value=38.0, unit="亿元", yoy_pct="", source_level="S",
      source_name="辽宁省财政厅 对省人大第1322号建议的答复",
      source_url="https://czt.ln.gov.cn/czt/zfxxgk/fdzdgknr/jyta/srddbjy/sssjrdschy2025n/2025062016255583229/index.shtml",
      source_text="2024年全省（不含大连）政策性农业保险保费总规模达38亿元，其中政府补贴30亿元（同比增长5%），支持全省4262万亩粮油作物、2433万头牲畜、4116万亩森林投保，提供风险保障997亿元",
      note=""),
 dict(year=2024, scope="辽宁省(不含大连)", crop="政策性农业保险", metric="claim_payout",
      value=25.0, unit="亿元", yoy_pct="", source_level="S",
      source_name="辽宁省财政厅（同上）", source_url="https://czt.ln.gov.cn/czt/zfxxgk/fdzdgknr/jyta/srddbjy/sssjrdschy2025n/2025062016255583229/index.shtml",
      source_text="保险机构实际支付赔款25亿元，简单赔付率66%", note="赔付率66%"),
 dict(year=2024, scope="锦州市", crop="特色农产品保险", metric="premium_income",
      value=1.84, unit="亿元", yoy_pct=15.82, source_level="S",
      source_name="锦州金融监管分局（中国银行保险报）",
      source_url="http://www.cbimc.cn/m/content/2025-06/16/content_549000.html",
      source_text="2024年，锦州地区特色农产品保险保费收入1.84亿元，同比增长15.82%", note=""),
 dict(year=2024, scope="锦州市", crop="特色农产品保险", metric="claim_payout",
      value=1.67, unit="亿元", yoy_pct=6.99, source_level="S",
      source_name="锦州金融监管分局（中国银行保险报）",
      source_url="http://www.cbimc.cn/m/content/2025-06/16/content_549000.html",
      source_text="赔付支出1.67亿元，同比增长6.99%，赔付率达到90.76%", note="赔付率90.76%"),
 dict(year=2024, scope="葫芦岛/锦州/朝阳", crop="暴雨灾害(农险)", metric="claim_reported_amount",
      value=6.67, unit="亿元(估损)", yoy_pct="", source_level="S",
      source_name="辽宁金融监管局（中国银行保险报）",
      source_url="http://www.cbimc.cn/m/content/2024-09/12/content_529278.html",
      source_text="截至9月5日，农业保险报案7653件，估损金额6.67亿元；重灾区葫芦岛、锦州、朝阳共计接到强降雨出险报案1.56万件，估损2.51亿元",
      note="8·20 洪涝；估损≠赔付"),
]
write("agri_insurance_claims.csv",
      ["year","scope","crop","metric","value","unit","yoy_pct","source_level","source_name",
       "source_url","source_text","note","access_date"], INS)

# ============ 4. 灾损（并入 V1） ============
v1dis = list(csv.DictReader((V1/"disaster_loss_events.csv").open(encoding="utf-8-sig")))
for r in v1dis:
    r.setdefault("quality_flag", "official_report")
    r["source_tier"] = "S"
write("disaster_loss_crop_events.csv",
      ["event_date","end_date","city","district","disaster_type","affected_crop","affected_area",
       "affected_area_unit","disaster_area","disaster_area_unit","crop_failure_area","economic_loss",
       "economic_loss_unit","people_affected","source_level","source_name","source_url","source_text",
       "note","source_tier","quality_flag","access_date"], v1dis)

# ============ 5. 冷链/仓储 ============
COLD = [
 dict(year=2024, city="沈阳", district="新民市", facility_count=252, capacity_ton=25500,
      annual_cold_flow_ton=232000, capacity_m3="", source_level="S",
      source_name="沈阳市农业农村局（辽宁省农业农村厅转载）",
      source_url="https://nync.ln.gov.cn/nync/index/nyyw/zsqsnyxxlb/2024062110094411114/index.shtml",
      source_text="新民市现有冷藏保鲜设施252座，储藏能力达到2.55万吨，农产品年冷链流通量达23.2万吨。沈阳秋实农产品冷链物流园每日有近1500吨蔬菜销往各地",
      note="新民市获批全国农产品骨干冷链物流重点县"),
 dict(year=2024, city="沈阳", district="", facility_count="", capacity_ton="", annual_cold_flow_ton="",
      capacity_m3=165000, source_level="S", source_name="沈阳市农业农村局（同上）",
      source_url="https://nync.ln.gov.cn/nync/index/nyyw/zsqsnyxxlb/2024062110094411114/index.shtml",
      source_text="十四五以来已争取中央资金2115万元，建设产地仓储设施16.5万立方米",
      note="累计新建产地仓储设施库容"),
 dict(year=2024, city="辽宁省", district="", facility_count=949, capacity_ton="", annual_cold_flow_ton="",
      capacity_m3=234000, source_level="S", source_name="辽宁省农业农村厅 省政协提案答复",
      source_url="https://nync.ln.gov.cn/nync/zfxxgk/fdzdgknr/jyta/szxta/szxssjschy2025n/2025082810291849003/index.shtml",
      source_text="累计支持建设农产品产地冷藏保鲜设施949个，新增库容23.4万立方米",
      note="2024 新增"),
 dict(year=2024, city="辽宁省", district="", facility_count="", capacity_ton="", annual_cold_flow_ton="",
      capacity_m3=8676000, source_level="S", source_name="辽宁省商务厅《辽宁省农产品现代流通体系建设发展规划(2024-2030)》",
      source_url="https://swt.ln.gov.cn/swt/ywxx/tzgg/2024041210074077223/2024042209324921254.pdf",
      source_text="全省农产品产地冷藏保鲜冷链设施现存库容量为867.6万立方米，其中果蔬类690.4万立方米，果蔬冷藏库库容为605.9万立方米，果蔬气调库库容为23.5万立方米，通风库和贮藏窑库容为41.9万立方米。肉类冷冻库库容140万立方米，水产品冷冻库库容37万立方米",
      note="全省存量；果蔬类 690.4 万m³ 与蔬菜直接相关"),
]
write("cold_chain_capacity.csv",
      ["year","city","district","facility_count","capacity_ton","capacity_m3","annual_cold_flow_ton",
       "source_level","source_name","source_url","source_text","note","access_date"], COLD)

# ============ 6. 需求端 ============
DEM = [
 dict(year=2024, city="沈阳", indicator="常住人口", value=924.3, unit="万人", source_level="S",
      source_name="沈阳市2024年统计公报", source_url="https://www.shenyang.gov.cn/zwgk/fdzdgknr/tjxx/tjgb/202504/t20250423_4841162.html",
      source_text="年末常住人口924.3万人，其中城镇人口790.7万人，乡村人口133.6万人，城镇化率85.55%"),
 dict(year=2024, city="沈阳", indicator="城镇人口", value=790.7, unit="万人", source_level="S",
      source_name="沈阳市2024年统计公报", source_url="https://www.shenyang.gov.cn/zwgk/fdzdgknr/tjxx/tjgb/202504/t20250423_4841162.html", source_text="同上"),
 dict(year=2024, city="沈阳", indicator="蔬菜及食用菌产量", value=418.4, unit="万吨", source_level="S",
      source_name="沈阳市2024年统计公报", source_url="https://www.shenyang.gov.cn/zwgk/fdzdgknr/tjxx/tjgb/202504/t20250423_4841162.html", source_text="蔬菜及食用菌产量418.4万吨"),
 dict(year=2024, city="沈阳", indicator="居民消费价格涨幅", value=0.6, unit="%", source_level="S",
      source_name="沈阳市2024年统计公报", source_url="https://www.shenyang.gov.cn/zwgk/fdzdgknr/tjxx/tjgb/202504/t20250423_4841162.html", source_text="全年居民消费价格比上年上涨0.6%"),
 dict(year=2024, city="锦州", indicator="蔬菜及食用菌产量", value=322.8, unit="万吨", source_level="S",
      source_name="锦州市2024年统计公报", source_url="https://tjj.jz.gov.cn/info/1057/4793.htm", source_text="蔬菜及食用菌产量322.8万吨"),
 dict(year=2024, city="朝阳", indicator="蔬菜及食用菌产量", value=334.1, unit="万吨", source_level="S",
      source_name="朝阳市2024年统计公报", source_url="https://www.chaoyang.gov.cn/html/CYSZF/202505/0174669308628614.html", source_text="蔬菜及食用菌产量334.1万吨"),
 dict(year=2024, city="铁岭", indicator="蔬菜及食用菌产量", value=76.5, unit="万吨", source_level="S",
      source_name="铁岭市2024年统计公报", source_url="http://www.tieling.gov.cn/tieling/zwgk/zfxxgk/fdzdgknr/tjxx/tjgb/2025051410132752830/index.html", source_text="蔬菜及食用菌产量76.5万吨"),
]
write("demand_yearly.csv", ["year","city","indicator","value","unit","source_level","source_name","source_url","source_text","access_date"], DEM)

# ============ 7. 市场登记 ============
MKT = [
 dict(market_name="沈阳十二线蔬菜中心批发市场", market_type="wholesale", city="沈阳", address="和平区",
      lat="", lon="", annual_throughput="约50万吨", scale="占地7万㎡，800余商户", source_level="S",
      source_name="沈阳市关于部分蔬菜市场情况的调研报告（省发改委）",
      source_url="https://fgw.ln.gov.cn/fgw/xxgk/jgjc/fxyc/BFDE92662276474D98CFE6497CCD2900/index.shtml",
      note="农业部首批定点鲜活农产品中心批发市场；占沈阳蔬菜经营量约30%"),
 dict(market_name="沈阳秋实农产品冷链物流园", market_type="cold_chain_hub", city="沈阳", address="新民市大民屯镇",
      lat="", lon="", annual_throughput="日近1500吨蔬菜外销", scale="东北最大蔬菜产销对接集散地", source_level="S",
      source_name="沈阳市农业农村局（辽宁省农业农村厅）",
      source_url="https://nync.ln.gov.cn/nync/index/nyyw/zsqsnyxxlb/2024062110094411114/index.shtml", note=""),
 dict(market_name="盛发/雨润/地利 三大农产品批发市场", market_type="wholesale", city="沈阳", address="",
      lat="", lon="", annual_throughput="蔬菜日上市量超3000吨、库存超6000吨(2026-02)", scale="", source_level="S",
      source_name="农业农村部 agri.cn（沈阳 volume_observations 记录）",
      source_url="https://www.agri.cn/zx/xxlb/ln/202602/t20260213_8812401.htm", note=""),
 dict(market_name="凌源/北票 设施蔬菜生产基地与市场", market_type="production_base+market", city="朝阳",
      address="凌源市/北票市", lat="", lon="", annual_throughput="全市30多处批发市场，农业部定点4处",
      scale="2023 设施农业 67.5万亩(日光温室59.5万亩)，设施蔬菜产量219万吨", source_level="S",
      source_name="朝阳市设施农业服务部 调研报告",
      source_url="https://nync.ln.gov.cn/nync/index/nyyw/zsqsnyxxlb/2024041011085532390/index.shtml", note="北方最大日光温室黄瓜/番茄生产基地"),
 dict(market_name="黑山县五大蔬菜批发市场", market_type="wholesale", city="锦州", address="黑山县",
      lat="", lon="", annual_throughput="年蔬菜交易量40万吨、交易额15亿元",
      scale="设施蔬菜占地7.6万亩，年产量55万吨", source_level="S",
      source_name="黑山县人民政府 人大建议答复",
      source_url="http://www.heishan.gov.cn/info/1883/39883.htm", note="段家大十字、四家子等5个市场；段家大十字为农业部定点市场"),
 dict(market_name="铁岭市优质蔬菜产业带（新台子—毛家店）", market_type="production_base", city="铁岭",
      address="铁岭县新台子镇", lat="", lon="", annual_throughput="",
      scale="纵贯130km、跨越29个乡镇；设施蔬菜面积超6.67万hm²、总产超500万t", source_level="A",
      source_name="北方园艺 2023(8) 设施番茄轮作生菜绿色高效栽培技术",
      source_url="https://www.aeeisp.com/bfyy/cn/article/pdf/preview/31c7f6a6-421f-4bb5-8218-4fcf48fba24d.pdf", note=""),
]
write("market_registry_extended.csv",
      ["market_name","market_type","city","address","lat","lon","annual_throughput","scale",
       "source_level","source_name","source_url","note","access_date"], MKT)

# ============ 8. 跟风事件扩展（并入 V1） ============
v1h = list(csv.DictReader((V1/"herding_events.csv").open(encoding="utf-8-sig")))
NEW_H = [
 dict(event_id="HRD-2024-TOMATO-LN44", year=2024, city="辽宁(省域)", crop="西红柿",
      trigger_price_event="2023-2024年西红柿种植面积缩减", planting_expansion="缩减（反向案例）",
      supply_change="供给减少、品质提升",
      price_outcome="2024年第44周批发均价5.31元/公斤，环比+9.03%，同比+72.96%",
      market_outcome="价格大幅高于上年",
      evidence_type="省级官方价格监测简讯", source="辽宁省农业农村厅 2024年第44周价格简讯",
      source_url="https://nync.ln.gov.cn/nync/index/zwgk/zszdgz/ncpxx/lnsnzyscpzjg/2024110614385049055/index.shtml",
      source_text="今年我省西红柿种植面积有所缩减，农户普遍反映结果后果型表现佳、品质优势明显，因此近期西红柿批发价格持续较高，并且涨幅明显",
      confidence="高"),
 dict(event_id="HRD-2023-BAICAI-JZ", year=2023, city="锦州", crop="大白菜",
      trigger_price_event="2022年大白菜价格高位", planting_expansion="2023年北方产区扩种",
      supply_change="秋季偏暖单产+20%，露地与冷棚菜同期上市",
      price_outcome="2023年11月新发地大白菜批发价0.55元/公斤，同比-56%；辽宁锦州为主要供应地之一",
      market_outcome="局地阶段性卖难", evidence_type="农业农村部市场分析+经济日报",
      source="农业农村部蔬菜市场分析预警团队；经济日报",
      source_url="http://www.ce.cn/cysc/sp/info/202312/11/t20231211_38824047.shtml",
      source_text="11月份河北唐山、辽宁锦州和河北廊坊大白菜集中上市，北京大白菜每天交易2万吨，批发价低至每公斤0.55元，同比下跌56%",
      confidence="高"),
 dict(event_id="HRD-2024-LENGPENG-SUMMARY", year=2024, city="辽宁(省域)", crop="设施蔬菜(冷棚)",
      trigger_price_event="近年蔬菜经济作物收益较高", planting_expansion="省内冷棚扩大面积较大",
      supply_change="整体上货量过饱和、产能相对过剩",
      price_outcome="2024年第25周蔬菜批发价格指数45.38，环比-6.08%，同比-20.91%",
      market_outcome="价格整体下行", evidence_type="省级官方价格监测简讯",
      source="辽宁省农业农村厅 2024年第25周价格简讯",
      source_url="https://nync.ln.gov.cn/nync/index/zwgk/zszdgz/ncpxx/lnsnzyscpzjg/2024062816430638005/index.shtml",
      source_text="近些年来，辽宁省内冷棚扩大面积较大，农户对于种植蔬菜类经济作物兴趣较高，因此整体蔬菜上货量过饱和，产能相对过剩",
      confidence="高"),
]
for r in v1h + NEW_H:
    r.setdefault("quality_flag", "evidence_based")
    r.setdefault("evidence_type", "")
    r.setdefault("planting_change", r.get("planting_expansion", ""))
    r.setdefault("supply_change", r.get("supply_change", ""))
    r.setdefault("price_change", r.get("price_outcome", ""))
    r.setdefault("outcome", r.get("market_outcome", ""))
write("herding_events_extended.csv",
      ["event_id","year","city","crop","trigger_price_event","planting_expansion","planting_change",
       "supply_change","price_outcome","price_change","market_outcome","outcome","evidence_type",
       "source","source_url","source_text","confidence","quality_flag","access_date"],
      v1h + NEW_H)

# ============ 9. SHA256 登记 ============
man = []
for p in sorted(list(RAW2.rglob("*")) + list((V1).glob("*"))):
    if p.is_file() and p.suffix.lower() in (".csv",".json",".pdf",".jpg",".png",".txt",".html",".xls"):
        h = hashlib.sha256()
        with p.open("rb") as f:
            for ch in iter(lambda: f.read(1 << 20), b""):
                h.update(ch)
        man.append({"path": str(p.relative_to(ROOT)), "sha256": h.hexdigest(),
                    "file_size": p.stat().st_size,
                    "downloaded_at": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")})
write("FILE_SHA256_MANIFEST.csv", ["path","sha256","file_size","downloaded_at"], man)
print("\n完成脚本 A。")
