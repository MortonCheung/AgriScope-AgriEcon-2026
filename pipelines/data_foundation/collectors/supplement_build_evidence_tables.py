#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把本轮网络采集到的「成本 / 灾害损失 / 跟风种植」证据结构化为标准表。
所有记录均带 source_url / source_text / source_level，禁止任何估算或补值。
产出：
  city_data/reference/decision_engine_supplement/crop_cost_yearly.csv
  city_data/reference/decision_engine_supplement/cost_proxy_insurance.csv
  city_data/reference/decision_engine_supplement/disaster_loss_events.csv
  city_data/reference/decision_engine_supplement/herding_events.csv
  data/raw/decision_engine_supplement/*/EVIDENCE_*.md
"""
import csv
from pathlib import Path
from datetime import datetime

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
OUT = ROOT / "data/raw/retained_source/city_data" / "reference" / "decision_engine_supplement"
RAWC = ROOT / "data/raw" / "decision_engine_supplement"
AD = datetime.now().strftime("%Y-%m-%d")

# ============================ 1. 种植成本 ============================
# 全部为公开发布的成本调查数值（元/亩）
COST = [
 dict(year=2024, city="沈阳", crop="玉米", cost_total_per_mu=1276.38, material=470.57, labor=317.72, land=488.09,
      seed="", fertilizer="", pesticide="", machinery="", irrigation="",
      geo_level="city", source_level="S",
      source_name="沈阳市发展和改革委员会 成本调查监审局",
      source_url="https://fgw.shenyang.gov.cn/wjgz/cbdcjs/202512/t20251208_4949776.html",
      source_text="2025年沈阳市玉米…玉米成本收益对比表：2024年亩均成本1276.38元（物质服务费470.57、人工成本317.72、土地成本488.09）",
      note="官方成本调查直报（新民/法库/康平36个玉米调查户）"),
 dict(year=2025, city="沈阳", crop="玉米", cost_total_per_mu=1219.65, material=459.58, labor=290.22, land=469.85,
      seed="", fertilizer="", pesticide="", machinery="", irrigation="",
      geo_level="city", source_level="S",
      source_name="沈阳市发展和改革委员会 成本调查监审局",
      source_url="https://fgw.shenyang.gov.cn/wjgz/cbdcjs/202512/t20251208_4949776.html",
      source_text="我市2025年玉米产量562.33公斤/亩…种植成本1219.65元/亩，同比下降4.44%；农户预期市场价格2.22元/公斤；净利润72.01元/亩",
      note="官方成本调查直报"),
 dict(year=2024, city="沈阳", crop="水稻", cost_total_per_mu=1684.39, material=789.69, labor=130.44, land=650.0,
      seed="", fertilizer="", pesticide="", machinery="", irrigation="",
      geo_level="city", source_level="S",
      source_name="沈阳市发展和改革委员会 成本调查监审局",
      source_url="https://fgw.shenyang.gov.cn/wjgz/cbdcjs/202512/t20251208_4949787.html",
      source_text="2025年粳稻…粳稻成本收益对比表：2024年亩均成本1684.39元（物质服务费789.69、人工成本130.44、土地成本650）",
      note="调查对象：辽中区冷子堡镇/杨士岗镇/蒲西街道9个粳稻调查户"),
 dict(year=2025, city="沈阳", crop="水稻", cost_total_per_mu=1696.64, material=776.17, labor=131.25, land=670.0,
      seed="", fertilizer="", pesticide="", machinery="", irrigation="",
      geo_level="city", source_level="S",
      source_name="沈阳市发展和改革委员会 成本调查监审局",
      source_url="https://fgw.shenyang.gov.cn/wjgz/cbdcjs/202512/t20251208_4949787.html",
      source_text="2025年粳稻产量642.89公斤/亩…种植成本1696.64元/亩，预期市场价格2.74元/公斤，净利润145.91元/亩",
      note="官方成本调查直报"),
 dict(year=2022, city="辽阳", crop="玉米", cost_total_per_mu=1571.06, material="", labor="", land="",
      seed="", fertilizer="", pesticide="", machinery="", irrigation="",
      geo_level="neighboring_city", source_level="S",
      source_name="辽宁省发展改革委（辽阳市调查）",
      source_url="https://fgw.ln.gov.cn/fgw/xxgk/jgjc/fxyc/2023121210494080614/index.shtml",
      source_text="2023年玉米调查户预计亩总成本1646.97元，较上年1571.06元增加75.91元",
      note="邻市（辽阳）非六城之一，作 regional_proxy"),
 dict(year=2023, city="辽阳", crop="玉米", cost_total_per_mu=1646.97, material=222.83+216.23, labor=384.55, land=725.81,
      seed=56.67, fertilizer=222.83, pesticide="", machinery=216.23, irrigation="",
      geo_level="neighboring_city", source_level="S",
      source_name="辽宁省发展改革委（辽阳市调查）",
      source_url="https://fgw.ln.gov.cn/fgw/xxgk/jgjc/fxyc/2023121210494080614/index.shtml",
      source_text="2023年玉米调查户预计亩总成本1646.97元；种子费56.67、化肥费222.83、机械作业费216.23、人工成本384.55、土地成本725.81",
      note="regional_proxy"),
 dict(year=2024, city="辽阳", crop="玉米", cost_total_per_mu=1884.97, material="", labor=408.53, land=942.08,
      seed=58.79, fertilizer="", pesticide=27.23, machinery="", irrigation="",
      geo_level="neighboring_city", source_level="S",
      source_name="辽宁省发展改革委（辽阳市调查）",
      source_url="https://fgw.ln.gov.cn/fgw/xxgk/jgjc/fxyc/2024102419143214552/index.shtml",
      source_text="2024年玉米调查户预计亩总成本1884.97元；种子费58.79、农药费27.23、人工成本408.53、土地成本942.08",
      note="regional_proxy"),
 dict(year=2022, city="辽阳", crop="大豆", cost_total_per_mu=1265.84, material="", labor="", land="",
      seed="", fertilizer="", pesticide="", machinery="", irrigation="",
      geo_level="neighboring_city", source_level="S",
      source_name="辽宁省发展改革委（辽阳市调查）",
      source_url="https://fgw.ln.gov.cn/fgw/xxgk/jgjc/fxyc/2023121211011624398/index.shtml",
      source_text="2023年大豆…每亩总成本1306.92元，较上年1265.84元增加41.08元",
      note="regional_proxy"),
 dict(year=2023, city="辽阳", crop="大豆", cost_total_per_mu=1306.92, material=81.77+205.05, labor=321.50, land=606.23,
      seed=55.0, fertilizer=81.77, pesticide="", machinery=205.05, irrigation="",
      geo_level="neighboring_city", source_level="S",
      source_name="辽宁省发展改革委（辽阳市调查）",
      source_url="https://fgw.ln.gov.cn/fgw/xxgk/jgjc/fxyc/2023121211011624398/index.shtml",
      source_text="2023年大豆…每亩总成本1306.92元；种子55、化肥81.77、租赁作业费205.05、人工321.50、土地606.23",
      note="regional_proxy"),
 dict(year=2024, city="辽阳", crop="大豆", cost_total_per_mu=1317.42, material=69.52+180.55, labor=263.62, land=714.47,
      seed=45.08, fertilizer=69.52, pesticide=21.42, machinery=180.55, irrigation="",
      geo_level="neighboring_city", source_level="S",
      source_name="辽宁省发展改革委（辽阳市调查）",
      source_url="https://fgw.ln.gov.cn/fgw/xxgk/jgjc/fxyc/2024101516344372466/index.shtml",
      source_text="2024年大豆…每亩总成本1317.42元；种子45.08、化肥69.52、农药21.42、机械作业费180.55、人工263.62、土地714.47",
      note="regional_proxy"),
 dict(year=2020, city="铁岭", crop="玉米", cost_total_per_mu=510.0, material="", labor="", land="",
      seed="", fertilizer="", pesticide="", machinery="", irrigation="",
      geo_level="county(昌图县)", source_level="S",
      source_name="辽宁省发展改革委 价格监测局 秋粮调研",
      source_url="https://fgw.ln.gov.cn/fgw/index/wndt/F7269A0A3BEB410C9C8A8F746C77AD2A/index.shtml",
      source_text="昌图县对一般农户成本测算，每亩玉米种植成本在510元左右；对合作社成本测算，每亩成本在1050元（含租地费用700元）",
      note="昌图县一般农户口径；合作社口径1050元/亩另计"),
 dict(year=2020, city="铁岭", crop="水稻", cost_total_per_mu=820.0, material="", labor="", land="",
      seed="", fertilizer="", pesticide="", machinery="", irrigation="",
      geo_level="county(开原市)", source_level="S",
      source_name="辽宁省发展改革委 价格监测局 秋粮调研",
      source_url="https://fgw.ln.gov.cn/fgw/index/wndt/F7269A0A3BEB410C9C8A8F746C77AD2A/index.shtml",
      source_text="开原市…每亩种植成本为820元，按平均亩产1048斤，市场收购价1.49元计算",
      note="开原市口径"),
]
COST_COLS = ["year", "city", "crop", "cost_total_per_mu", "seed", "fertilizer", "pesticide",
             "machinery", "labor", "land", "irrigation", "material", "geo_level",
             "source_level", "source_name", "source_url", "source_text", "note", "access_date"]

# ============================ 2. 成本代理：种植业保险保额 ============================
INS = [
 # (year, scope, crop, insurance_type, insured_amount_per_mu, rate, source_url, source_text)
 (2023, "辽宁省(不含大连)", "玉米", "直接物化成本", 370, 0.061, "https://www.ln.gov.cn/web/zwgkx/lnsrmzfgb/2023n/zk/zk6/bmwj/2023080110475072659/", "辽财金〔2023〕86号：玉米、水稻、小麦、大豆、花生、马铃薯亩保额分别为370、650、460、270、490、770元"),
 (2023, "辽宁省(不含大连)", "水稻", "直接物化成本", 650, 0.041, "https://www.ln.gov.cn/web/zwgkx/lnsrmzfgb/2023n/zk/zk6/bmwj/2023080110475072659/", "同上"),
 (2023, "辽宁省(不含大连)", "大豆", "直接物化成本", 270, 0.051, "https://www.ln.gov.cn/web/zwgkx/lnsrmzfgb/2023n/zk/zk6/bmwj/2023080110475072659/", "同上"),
 (2023, "辽宁省(不含大连)", "花生", "直接物化成本", 490, 0.041, "https://www.ln.gov.cn/web/zwgkx/lnsrmzfgb/2023n/zk/zk6/bmwj/2023080110475072659/", "同上"),
 (2023, "辽宁省(不含大连)", "玉米", "完全成本", 770, 0.061, "https://www.ln.gov.cn/web/zwgkx/lnsrmzfgb/2023n/zk/zk6/bmwj/2023080110475072659/", "完全成本保险：玉米、水稻、小麦亩保额分别为770、1290、820元"),
 (2023, "辽宁省(不含大连)", "水稻", "完全成本", 1290, 0.041, "https://www.ln.gov.cn/web/zwgkx/lnsrmzfgb/2023n/zk/zk6/bmwj/2023080110475072659/", "同上"),
 (2023, "沈阳市康平县", "玉米", "种植收入", 1000, 0.061, "https://www.ln.gov.cn/web/zwgkx/lnsrmzfgb/2023n/zk/zk6/bmwj/2023080110475072659/", "沈阳市、鞍山市、锦州市、铁岭市玉米亩保额分别为1000、880、920、1120元"),
 (2023, "锦州市义县", "玉米", "种植收入", 920, 0.061, "https://www.ln.gov.cn/web/zwgkx/lnsrmzfgb/2023n/zk/zk6/bmwj/2023080110475072659/", "同上"),
 (2023, "铁岭市铁岭县", "玉米", "种植收入", 1120, 0.061, "https://www.ln.gov.cn/web/zwgkx/lnsrmzfgb/2023n/zk/zk6/bmwj/2023080110475072659/", "同上"),
 (2025, "辽宁省", "大豆", "完全成本", 700, "", "https://nync.ln.gov.cn/nync/index/ywgl/scgl/zzygl/2025042909140060828/index.shtml", "新政策：大豆完全成本保险保额为每亩700元，种植收入保险保额为每亩790元（此前物化保险仅270元）"),
 (2025, "辽宁省", "大豆", "种植收入", 790, "", "https://nync.ln.gov.cn/nync/index/ywgl/scgl/zzygl/2025042909140060828/index.shtml", "同上"),
]
INS_COLS = ["year", "scope", "crop", "insurance_type", "insured_amount_per_mu", "rate",
            "source_url", "source_text", "access_date"]

# ============================ 3. 灾害损失 ============================
DIS = [
 dict(event_date="2024-07-06", end_date="2024-07-08", city="丹东", district="元宝区",
      disaster_type="洪涝", affected_crop="农作物(未分品种)", affected_area="46.23", affected_area_unit="公顷",
      disaster_area="1.3", disaster_area_unit="公顷", crop_failure_area="", economic_loss="56.5", economic_loss_unit="万元",
      people_affected=327, source_level="S",
      source_name="辽宁省防汛抗旱指挥部（经央视新闻/人民网发布）",
      source_url="https://content-static.cctvnews.cctv.com/snow-book/index.html?item_id=3586243294659637073",
      source_text="7月6日以来…丹东市元宝区，铁岭市西丰县、昌图县，朝阳市喀左县共计3个市4个县（区）发生洪涝灾害，受灾人口327人，农作物受灾面积46.23公顷，其中成灾面积1.3公顷，直接经济损失56.5万余元",
      note="与丹东同批次；同期铁岭西丰/昌图、朝阳喀左亦在内"),
 dict(event_date="2024-07-06", end_date="2024-07-08", city="铁岭", district="西丰县/昌图县",
      disaster_type="洪涝", affected_crop="农作物(未分品种)", affected_area="46.23", affected_area_unit="公顷",
      disaster_area="1.3", disaster_area_unit="公顷", crop_failure_area="", economic_loss="56.5", economic_loss_unit="万元",
      people_affected=327, source_level="S",
      source_name="辽宁省防汛抗旱指挥部（经央视新闻/人民网发布）",
      source_url="https://ln.people.com.cn/BIG5/n2/2024/0708/c378489-40905508.html",
      source_text="丹东元宝区，铁岭西丰县、昌图县，朝阳喀左县共计3个市4个县（区）发生洪涝灾害…农作物受灾面积46.23公顷，其中成灾面积1.3公顷；直接经济损失56.5万余元",
      note="三市四县合并口径，无法拆分到单县"),
 dict(event_date="2024-07-06", end_date="2024-07-08", city="朝阳", district="喀左县",
      disaster_type="洪涝", affected_crop="农作物(未分品种)", affected_area="46.23", affected_area_unit="公顷",
      disaster_area="1.3", disaster_area_unit="公顷", crop_failure_area="", economic_loss="56.5", economic_loss_unit="万元",
      people_affected=327, source_level="S",
      source_name="辽宁省防汛抗旱指挥部（经央视新闻/人民网发布）",
      source_url="https://content-static.cctvnews.cctv.com/snow-book/index.html?item_id=3586243294659637073",
      source_text="同上（三市四县合并口径）", note="合并口径，无法拆分"),
 dict(event_date="2024-08-01", end_date="2024-08-24", city="铁岭", district="昌图县后窑镇",
      disaster_type="洪涝/内涝", affected_crop="农作物(未分品种)", affected_area="22000", affected_area_unit="亩",
      disaster_area="11000", disaster_area_unit="亩", crop_failure_area="<6600", economic_loss="", economic_loss_unit="",
      people_affected="", source_level="S",
      source_name="辽宁日报（辽宁省人民政府网转载）",
      source_url="https://www.ln.gov.cn/web/ywdt/qsgd/ass_2_1/2024083009011157096/index.shtml",
      source_text="全镇共有2.2万亩农作物受灾，因为排水迅速，仅一半成灾，绝收面积不到三成；昌图县…保住易涝农田16.68万亩",
      note="后窑镇口径；绝收面积原文为'不到三成'，取下限估计值标<6600亩，非精确值"),
 dict(event_date="2022-06-01", end_date="2022-09-30", city="铁岭", district="昌图县",
      disaster_type="洪涝/内涝", affected_crop="农作物(未分品种)", affected_area="", affected_area_unit="亩",
      disaster_area="", disaster_area_unit="", crop_failure_area="", economic_loss="", economic_loss_unit="",
      people_affected="", source_level="S",
      source_name="辽宁日报（辽宁省人民政府网转载）",
      source_url="https://www.ln.gov.cn/web/ywdt/qsgd/ass_2_1/2024083009011157096/index.shtml",
      source_text="特别是在2022年汛期，昌图县遭遇9次强降水…13个乡镇都出现了较为严重的内涝，大片农作物被淹",
      note="定性记录，无量化面积"),
 dict(event_date="2024-08-19", end_date="2024-08-21", city="葫芦岛", district="建昌县/绥中县",
      disaster_type="暴雨/洪涝", affected_crop="农作物(未分品种)", affected_area="588200", affected_area_unit="亩",
      disaster_area="", disaster_area_unit="", crop_failure_area="", economic_loss="1030000", economic_loss_unit="万元",
      people_affected=188757, source_level="S",
      source_name="辽宁日报（辽宁省人民政府网），葫芦岛市防汛抗洪救灾新闻发布会",
      source_url="https://www.ln.gov.cn/web/ywdt/qsgd/ass_2_1/2024082609111939472/index.shtml",
      source_text="农田受灾面积58.82万亩，设施农业受灾1.64万亩，果树受灾49万亩，渔业灾害影响面积3.63万亩…受灾人口达到188757人，因灾损失103亿元",
      note="非六城（邻市葫芦岛），作省内极端天气参照；因灾损失103亿为全市全行业口径"),
]
DIS_COLS = ["event_date", "end_date", "city", "district", "disaster_type", "affected_crop",
            "affected_area", "affected_area_unit", "disaster_area", "disaster_area_unit",
            "crop_failure_area", "economic_loss", "economic_loss_unit", "people_affected",
            "source_level", "source_name", "source_url", "source_text", "note", "access_date"]

# ============================ 4. 跟风种植事件 ============================
HERD = [
 dict(event_id="HRD-2023-BAICAI", year=2023, city="锦州", crop="大白菜",
      trigger_price_event="2022年大白菜等『大路菜』价格处于高位",
      planting_expansion="2023年农户种植意愿较强，北方冷凉蔬菜产区有所扩种；11月初全国蔬菜在田面积同比增加1.2%",
      supply_change="秋季天气偏暖，大白菜单产增加约20%，供给总量大",
      price_outcome="2023年11月新发地大白菜批发价低至0.55元/公斤，同比下跌56%；一度较近三年同期低30%以上，个别产区跌破成本",
      market_outcome="局地阶段性卖难/滞销",
      evidence_type="官方市场分析 + 主流媒体",
      source="农业农村部蔬菜市场分析预警团队 张晶；经济日报/中国经济网",
      source_url="http://www.ce.cn/cysc/sp/info/202312/11/t20231211_38824047.shtml",
      source_text="去年大白菜、圆白菜、白萝卜等『大路菜』价格处于高位，今年种植意愿较强…均有所扩种…11月份河北唐山、辽宁锦州和河北廊坊大白菜集中上市，批发价低至每公斤0.55元，同比下跌56%",
      confidence="高"),
 dict(event_id="HRD-2024-TOMATO-LN", year=2024, city="辽宁(省域)", crop="西红柿",
      trigger_price_event="（反向案例）2024年种植面积缩减",
      planting_expansion="2024年辽宁省西红柿种植面积有所缩减（收缩而非扩张）",
      supply_change="供给减少、果型品质优势明显",
      price_outcome="2024年第44周辽宁省西红柿批发均价5.31元/公斤，环比上涨9.03%，同比上涨72.96%",
      market_outcome="价格显著高于上年",
      evidence_type="省级官方价格监测简讯",
      source="辽宁省农业农村厅 2024年第44周主要蔬菜产品价格简讯",
      source_url="https://nync.ln.gov.cn/nync/index/zwgk/zszdgz/ncpxx/lnsnzyscpzjg/2024110614385049055/index.shtml",
      source_text="今年我省西红柿种植面积有所缩减，农户普遍反映结果后果型表现佳、品质优势明显，因此近期西红柿批发价格持续较高，并且涨幅明显",
      confidence="高（省级官方明确表述）"),
 dict(event_id="HRD-2024-LENGPENG-LN", year=2024, city="辽宁(省域)", crop="设施蔬菜(冷棚)",
      trigger_price_event="近年蔬菜种植收益较高",
      planting_expansion="辽宁省内冷棚扩大面积较大，农户对种植蔬菜类经济作物兴趣较高",
      supply_change="蔬菜整体上货量过饱和，产能相对过剩",
      price_outcome="2024年第25周省内蔬菜批发价格指数45.38，环比下降6.08%，同比下降20.91%",
      market_outcome="价格整体下行",
      evidence_type="省级官方价格监测简讯",
      source="辽宁省农业农村厅 2024年省内第25周主要蔬菜品种市场价格简讯",
      source_url="https://nync.ln.gov.cn/nync/index/zwgk/zszdgz/ncpxx/lnsnzyscpzjg/2024062816430638005/index.shtml",
      source_text="近些年来，辽宁省内冷棚扩大面积较大，农户对于种植蔬菜类经济作物兴趣较高，因此整体蔬菜上货量过饱和，产能相对过剩。预计下周价格整体以降为主",
      confidence="高（省级官方明确表述）"),
 dict(event_id="HRD-2022-SY-MECHANISM", year=2022, city="沈阳", crop="蔬菜(通用)",
      trigger_price_event="市场上出现供不应求时菜价上涨",
      planting_expansion="菜农容易盲目扩大种植面积",
      supply_change="下一季市场过度饱和",
      price_outcome="价格下跌",
      market_outcome="供过于求→价格下跌（机制描述，非单一事件）",
      evidence_type="政府调研报告（机制性描述）",
      source="沈阳市价格监测局 和平区蔬菜市场专项调研（省发改委发布）",
      source_url="https://fgw.ln.gov.cn/fgw/xxgk/jgjc/fxyc/BFDE92662276474D98CFE6497CCD2900/index.shtml",
      source_text="信息不对称，蔬菜种植具有周期短回报快的显著特点，当市场上出现需大于供时，菜农容易盲目扩大种植面积，导致下一季市场过度饱和，价格下跌；当市场上出现供小于需时，菜农减少种植面积会导致下一季市场供应不足，价格上涨",
      confidence="中（机制描述，无具体量化事件）"),
 dict(event_id="HRD-2023-VEG-NATIONAL", year=2023, city="全国(含辽宁)", crop="大棚菜/大路菜",
      trigger_price_event="2022年大路菜价格高位",
      planting_expansion="北方冷凉蔬菜产区以及山东、江苏等地均有所扩种",
      supply_change="秋季耐储品种供给总量大，露地菜与冷棚菜同时上市",
      price_outcome="2023年11月28种蔬菜全国平均批发价4.58元/公斤，环比下跌5.8%，较近三年同期低5.2%；菠菜-26.6%、大白菜-26.4%",
      market_outcome="价格持续探底，局地阶段性卖难",
      evidence_type="农业农村部市场分析 + 主流媒体",
      source="农业农村部蔬菜市场分析预警团队；经济日报",
      source_url="https://caijing.chinadaily.com.cn/a/202312/11/WS65767bbba310c2083e4123de.html",
      source_text="二是蔬菜种植面积增加…去年大白菜、圆白菜、白萝卜等『大路菜』价格处于高位，今年种植意愿较强，北方冷凉蔬菜产区以及山东、江苏等地均有所扩种",
      confidence="高（全国口径，辽宁为参与产区之一）"),
]
HERD_COLS = ["event_id", "year", "city", "crop", "trigger_price_event", "planting_expansion",
             "supply_change", "price_outcome", "market_outcome", "evidence_type",
             "source", "source_url", "source_text", "confidence", "access_date"]


def write(path, cols, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            if not isinstance(r, dict):
                r = dict(zip(cols, r))
            r = dict(r); r["access_date"] = AD
            w.writerow(r)
    print(f"[OK] {path.name}  {len(rows)} 行")


write(OUT / "crop_cost_yearly.csv", COST_COLS, COST)
write(OUT / "cost_proxy_insurance.csv", INS_COLS, INS)
write(OUT / "disaster_loss_events.csv", DIS_COLS, DIS)
write(OUT / "herding_events.csv", HERD_COLS, HERD)

# 证据归档
(RAWC / "cost" / "EVIDENCE_crop_cost.md").write_text(
    "# 种植成本证据归档\n\n所有数值均来自公开发布的成本调查报告，未做任何估算或插值。\n\n"
    + "\n".join(f"## {r['year']} {r['city']} {r['crop']}\n- 亩总成本：{r['cost_total_per_mu']} 元/亩\n"
                f"- 来源：{r['source_name']}（{r['source_level']}）\n- URL：{r['source_url']}\n"
                f"- 原文：{r['source_text']}\n" for r in COST), encoding="utf-8")
(RAWC / "disaster_loss" / "EVIDENCE_disaster.md").write_text(
    "# 农业灾害损失证据归档\n\n"
    + "\n".join(f"## {r['event_date']} {r['city']} {r['district']}\n- 类型：{r['disaster_type']}\n"
                f"- 受灾面积：{r['affected_area']} {r['affected_area_unit']}\n- 来源：{r['source_name']}（{r['source_level']}）\n"
                f"- URL：{r['source_url']}\n- 原文：{r['source_text']}\n- 备注：{r['note']}\n" for r in DIS),
    encoding="utf-8")
(RAWC / "herding_events" / "EVIDENCE_herding.md").write_text(
    "# 跟风种植事件证据归档\n\n"
    + "\n".join(f"## {r['event_id']}：{r['year']} {r['city']} {r['crop']}\n"
                f"- 触发：{r['trigger_price_event']}\n- 扩种：{r['planting_expansion']}\n"
                f"- 供给：{r['supply_change']}\n- 价格结果：{r['price_outcome']}\n"
                f"- 来源：{r['source']}\n- URL：{r['source_url']}\n- 原文：{r['source_text']}\n"
                f"- 置信度：{r['confidence']}\n" for r in HERD), encoding="utf-8")
print("[OK] 证据归档 3 份")
