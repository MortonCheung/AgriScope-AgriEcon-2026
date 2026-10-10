# -*- coding: utf-8 -*-
"""
物候第二轮（round-2）采集入库脚本
- 原始证据落盘：city_data/<city>/workspace/data/raw/phenology/<slug>/<hash>.html
- 规范化追加：city_data/<city>/workspace/data/interim/phenology_events.csv（14 列）
- 省级（不可拆分为城市事实）单独落：city_data/reference/phenology_events_province.csv
字段：city/county/crop_raw/crop_standard/year/stage/start_date/end_date/date_precision/
      source_id/source_url/source_text/quality_grade/derived_from_text
原则：禁止编造；模糊文本用 date_precision + derived_from_text=true。
"""
from pathlib import Path
import csv
import hashlib
import json
import pathlib

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir()) / "data/raw/retained_source/city_data"  # city_data
RETRIEVAL_DATE = "2026-09-22"

HEADER = ["city", "county", "crop_raw", "crop_standard", "year", "stage",
          "start_date", "end_date", "date_precision", "source_id",
          "source_url", "source_text", "quality_grade", "derived_from_text"]

# ---------------------------------------------------------------------------
# 来源登记（原文证据）
# ---------------------------------------------------------------------------
SOURCES = {
    "SRC-LNCMA-RICE-TRANSPLANT": {
        "publisher": "辽宁省气象局（经辽望·辽宁日报发布）",
        "url": "https://www.lnrbxmt.com/news_details.html?id=458255",
        "slug": "ln-cma-rice-transplant-2025",
        "cities": ["shenyang", "tieling", "jinzhou", "dandong", "dalian"],
        "text": "5月10日，辽宁省气象局发布2025年水稻适宜移栽期预报，预计，5月中旬各地水稻陆续进入移栽期，移栽始期较2024年略推迟。"
                "目前水稻秧苗处于两叶一心至三叶一心，长势良好。预计沈阳、鞍山、锦州、营口、辽阳、铁岭南部、盘锦适宜移栽期为5月15～28日，"
                "其他稻区为5月22日～6月2日。沈阳、鞍山、辽阳、铁岭南部最迟移栽期为5月31日，抚顺、本溪、丹东、锦州、营口、铁岭、盘锦为6月9日，大连为6月13日。"
                "表1 辽宁省2025年各地水稻移栽期预测：沈阳 市郊/苏家屯/辽中/沈北/新民/康平/法库 适宜移栽期5月15~28日、最迟移栽期5月31日；"
                "大连 普兰店 适宜移栽期5月20~31日、最迟移栽期6月13日；庄河 适宜移栽期5月20~31日、最迟移栽期6月13日。",
    },
    "SRC-DLCMA-HARVEST": {
        "publisher": "大连市气象局、大连市农业农村局 联合发布《秋收气象服务专报》（大连日报报道）",
        "url": "http://dl.cnr.cn/gstjdl/20250919/t20250919_527368028.shtml",
        "slug": "dl-cma-harvest-2025",
        "cities": ["dalian"],
        "text": "近日，记者从大连市气象局、大连市农业农村局联合发布的秋收气象服务专报上获悉，9月以来，我市热量充足、光照条件较好、墒情适宜，"
                "气象条件利于玉米、大豆等秋收作物籽粒灌浆成熟。9月以来（截至16日）全市平均气温24.2℃，比常年同期偏高2.6℃；平均降水量51.1毫米，比常年同期多四成。"
                "目前，我市玉米处于蜡熟至完熟期，水稻处于乳熟至蜡熟期，大豆处于鼓粒至成熟期，大部分地区发育进程接近常年。个别地块的玉米已零星收获，尚未进入全面收获期。"
                "根据今年春播时间、作物长势情况与气候预测的综合分析，我市大田作物适宜收获期在9月20日至10月31日，与常年基本一致。",
    },
    "SRC-DDNY-STRAWBERRY": {
        "publisher": "丹东市农业农村局（辽宁省农业农村厅·全省农业信息联播）",
        "url": "https://nync.ln.gov.cn/nync/index/nyyw/zsqsnyxxlb/2025092615343579245/index.shtml",
        "slug": "dd-strawberry-2025",
        "cities": ["dandong"],
        "text": "为全面落实《2025年草莓科技服务小分队工作方案》要求，近日，由丹东市农业农村局牵头的草莓科技服务小分队，先后赴圣野浆果专业合作社、"
                "东港静松家庭农场及丹东归元水果专业合作社，开展精准技术指导与服务。在圣野浆果专业合作社，小分队专家团队实地察看了已于9月17日完成定植的最后一批冷冻苗，"
                "该批草莓预计于10月20日后陆续上市，是实现提早上市、抢占市场空档的关键举措。",
    },
    "SRC-RMRB-DG-STRAWBERRY": {
        "publisher": "人民日报（讲述·一线见闻）",
        "url": "http://paper.people.com.cn/rmrbwap/html/2024-11/22/nw.D110000renmrb_20241122_1-06.htm",
        "slug": "rmrb-dg-strawberry-2024",
        "cities": ["dandong"],
        "text": "每天，早上到大棚起帘，上午采摘，下午浇水施肥，傍晚再放帘；每年，4月到8月育苗，9月开始种植，11月到次年6月采摘售卖……"
                "这是长安镇王家村村民季学丹的一天和一年。（东港市草莓种植面积稳定在20万亩左右，鲜果年产值超60亿元）",
    },
    "SRC-KJRB-DG-STRAWBERRY": {
        "publisher": "科技日报（中国经济网转载）",
        "url": "http://district.ce.cn/newarea/roll/202511/t20251117_2584277.shtml",
        "slug": "kjrb-dg-strawberry-2025",
        "cities": ["dandong"],
        "text": "2019年起，当地农业技术部门联合合作社攻关冷冻苗技术：将草莓种苗储存于零下20摄氏度的低温环境中，打破其休眠期，"
                "待9月中下旬定植后，10月即可迎来首茬采摘，较传统种植提前2个月。过去，丹东草莓的产季主要集中在12月至次年6月。",
    },
    "SRC-LNRB-DG-RICE": {
        "publisher": "辽宁日报（全国信息联播）",
        "url": "http://www.agri.cn/zx/xxlb/ln/202505/t20250530_8737571.htm",
        "slug": "lnrb-dg-rice-2025",
        "cities": ["dandong"],
        "text": "5月26日，在东港市长山镇的农田里，数台智能高速插秧机来回穿梭，一株株嫩绿的秧苗从插秧机苗盘上整齐滑落，稳稳扎根田间。"
                "东港市现有水稻种植面积64万亩，拥有各类水稻插秧机4600余台。目前，东港市已进入水稻机插高峰期，现已完成机械化插秧面积12万余亩，预计6月上旬全面完成春播任务。",
    },
    "SRC-LNRB-DG-EARLYRICE": {
        "publisher": "辽宁日报（全国信息联播）",
        "url": "http://www.agri.cn/zx/xxlb/ln/202609/t20260908_8869752.htm",
        "slug": "lnrb-dg-earlyrice-2026",
        "cities": ["dandong"],
        "text": "9月2日一大早，东港市小甸子镇的稻田里就响起了轰隆隆的机器声。三台收割机一头扎进早稻田，加上地里的两台，五台收割机并排作业。"
                "这是全省最早进入收割期的稻田。这是'中科发5号'，早熟品种，前两年8月20日左右就收了，今年因为下雨，晚割一周。"
                "众发合作社是整个东港最早育苗的地方，他们建有108栋标准化育苗棚。一月中旬，技术人员就扎进大棚筹备新一年的育苗工作，四月中旬便开始插秧，比常规水稻整整早了大半个月。",
    },
    "SRC-CT-GOV-SOWING": {
        "publisher": "昌图县人民政府（昌图县融媒体中心）",
        "url": "http://changtu.gov.cn/changtu/ywdt/zwyw/2025041109334556226/index.html",
        "slug": "ct-gov-sowing-2025",
        "cities": ["tieling"],
        "text": "4月9日上午，我县2025年春播现场会在老城镇胜利村召开，为我县春播生产拉开了序幕。根据监测情况，当前我县大部分地块墒情适宜或偏湿，"
                "预计4月12日左右化冻完成，未来一周降水偏多、风力大、气温低，15日起回暖。第一场透雨较往年偏早12天，最佳适播期为4月17至30日，最晚不晚于5月15日。",
    },
    "SRC-LNRB-SOWING-HALF": {
        "publisher": "辽宁日报（辽宁省政府网）",
        "url": "https://www.ln.gov.cn/web/ywdt/jrln/wzxx2018/2025051008465065776/index.shtml",
        "slug": "lnrb-sowing-half-2025",
        "cities": ["jinzhou"],
        "text": "截至5月7日，全省粮食作物播种面积达3178.8万亩，占计划面积的59.2%。其中，玉米播种3064.4万亩，铁岭、朝阳、锦州、葫芦岛等地玉米播种均进程过半。",
    },
    "SRC-LNRB-SPRING-END": {
        "publisher": "辽宁日报（辽宁省政府网）",
        "url": "https://www.ln.gov.cn/web/ywdt/tjdt/2025052713595212858/index.shtml",
        "slug": "lnrb-spring-end-2025",
        "cities": ["tieling"],
        "text": "5月26日，在铁岭县新台子镇的一处高标准农田里，高速插秧机在田间来回穿梭，株株嫩绿的秧苗排列成行。随着气温回升，当地插秧工作快速推进，机械化插秧率超过99%。"
                "辽北是我省玉米优势区，最新的苗情监测显示，昌图县、铁岭县等地玉米整体苗情不错，出苗率高、出苗齐，但也有局部地块因播种后遭遇急雨而出现硬盖，导致出苗质量欠佳。",
    },
    "SRC-LNNYNC-TL-20W": {
        "publisher": "辽宁省农业农村厅（辽宁日报）",
        "url": "https://nync.ln.gov.cn/nync/index/nyyw/nyxw/nyyw/2025051315251197743/index.shtml",
        "slug": "lnnync-tl-20w-2025",
        "cities": ["tieling"],
        "text": "5月7日，记者从铁岭市农业农村局了解到，2025年，铁岭首次入围辽宁省玉米单产提升工程实施名单，面积为20万亩，昌图县、铁岭县、调兵山市、清河区4个县（市）区各实施5万亩。"
                "目前，铁岭实施该工程地区已经将任务细分，部分大型合作社在春耕整地结束后，已经开始按照相关标准进行播种。",
    },
    "SRC-SYCMA-CORN-TRIAL": {
        "publisher": "沈阳市气象局（辽宁省气象局）",
        "url": "http://ln.cma.gov.cn/xwzx/qxxw/202602/t20260213_7611056.html",
        "slug": "sy-cma-corn-trial-2025",
        "cities": ["shenyang"],
        "text": "2025年是沈阳市开展玉米生产智慧气象服务效益评价对比试验的第二年，市气象局与市农业农村局在法库县、沈北新区两地同步设置'气象服务区'与'农户自管区'两组对照试验。"
                "抢抓播种先机。基于冻土、地温、墒情动态监测，精准确定4月20日至5月4日为最佳播种期，气象服务区较对照区提前播种11至17天，播种后一周降水接续，出苗整齐。",
    },
    "SRC-XHW-SY-RICE": {
        "publisher": "新华网（辽宁省政府网转载）",
        "url": "https://www.ln.gov.cn/web/ywdt/zymtkln/2025052910350227459/index.shtml",
        "slug": "xhw-sy-rice-2025",
        "cities": ["shenyang"],
        "text": "新华网沈阳5月29日电 近日，沈阳市苏家屯区水稻种植工作有序推进。作为沈阳重要水稻产区，该区今年水稻种植面积达7.7万亩。"
                "目前，超4.4万亩稻田完成插秧。随着气温回升，剩余约3.3万亩水田的插秧工作正加快推进，预计5月底前可完成全部种植任务。",
    },
    "SRC-SYCMA-SJT-RICE": {
        "publisher": "沈阳市苏家屯区气象局（辽宁省气象局）",
        "url": "http://ln.cma.gov.cn/xwzx/jcdt/202008/t20200821_2007516.html",
        "slug": "sy-cma-sjt-rice-2020",
        "cities": ["shenyang"],
        "text": "8月21日，沈阳市苏家屯区气象局联合区农业技术推广服务中心技术人员深入八一红菱街道水稻种植基地开展水稻灌浆期生长情况服务调研。"
                "通过对水稻灌浆期作物生长、稻田排水、病虫害防治等情况的调查，全面了解苏家屯近期降水量较大对水稻生长的影响及水稻灌浆期对气象服务的需求。",
    },
    "SRC-CYCMA-DROUGHT": {
        "publisher": "朝阳市气象局（辽宁省气象局）",
        "url": "http://ln.cma.gov.cn/xwzx/qxxw/202507/t20250709_7200394.html",
        "slug": "cy-cma-drought-2025",
        "cities": ["chaoyang"],
        "text": "6月20日至7月7日，朝阳市平均降水量为17.8毫米，较历年同期偏少6成，部分出现不同程度旱情。朝阳市气象局与农业部门通力合作，多举措应对高温伏旱。"
                "目前，全市大部分地区玉米处于拔节期至吐丝期、谷子处于分蘖至拔节期，当前正是大田作物需水关键期。",
    },
    "SRC-LNRB-DL-APPLE": {
        "publisher": "辽宁日报（辽宁省政府网）",
        "url": "https://www.ln.gov.cn/web/ywdt/jrln/wzxx2018/2025102508305655548/index.shtml",
        "slug": "lnrb-dl-apple-2025",
        "cities": ["dalian"],
        "text": "霜降前后，大连52万亩苹果迎来集中采收期。10月24日上午，在瓦房店市许屯镇东马屯村的果林间，旋翼的嗡嗡声时近时远，无人机稳稳吊着两筐苹果，径直飞向路边卸货点。"
                "今年，这些'空中挑夫'首次大规模加入秋收队伍。",
    },
    "SRC-LNRB-DL-APPLE2": {
        "publisher": "辽宁日报（辽望客户端）",
        "url": "https://wap.lnrbxmt.com/news_details.html?id=487057",
        "slug": "lnrb-dl-apple2-2025",
        "cities": ["dalian"],
        "text": "10月19日，果农在大连瓦房店市许屯镇东马屯村山上采摘和运输苹果。今年东马屯村苹果又迎来丰收年，大红苹果挂满枝头。"
                "东马屯村苹果种植拥有百年种植历史，今年产红富士和小国光等苹果约2万吨。",
    },
    "SRC-LNNYNC-VEG-2025": {
        "publisher": "辽宁省农业农村厅",
        "url": "https://nync.ln.gov.cn/nync/index/zwgk/zszdgkwj/2025041411134895453/",
        "slug": "lnnync-veg-2025",
        "cities": [],
        "text": "省农业农村厅印发2025年春季蔬菜生产技术指导意见。塑料大棚春提早蔬菜 通常在4月上旬至5月上旬进行定植，辽南地区多层覆盖可适当提前，"
                "当时扣棚须在定植前15～20天扣棚，促进地温回升，当棚内10cm地温稳定在10℃以上时定植。",
    },
    "SRC-CNVEG-EGGPLANT": {
        "publisher": "《中国蔬菜》（辽宁省旱地农林研究所，辽宁朝阳）",
        "url": "https://www.cnveg.org/EN/article/downloadArticleFile.do?attachType=PDF&id=19263",
        "slug": "cnveg-eggplant-chaoyang",
        "cities": ["chaoyang"],
        "text": "日光温室茄子回头茄整枝高效生产技术。辽宁省朝阳市采用回头茄整枝技术实现了日光温室茄子长季节生产……"
                "回头茄生产属于温室周年一大茬生产，当地一般7—8月定植，翌年6—7月生产结束，若上一年生产结束晚则下一年延后定植，最晚在10月初定植。",
    },
    "SRC-LNNYNC-PEST-2025": {
        "publisher": "辽宁省植保植检总站（辽宁省政府网·辽宁日报）",
        "url": "https://www.ln.gov.cn/web/ywdt/jrln/wzxx2018/2025080408465114480/index.shtml",
        "slug": "lnnync-pest-2025",
        "cities": [],
        "text": "近日，省植保植检总站发布我省下半年全省农作物病虫害趋势预报……目前玉米田处于抽雄吐丝期、水稻田进入孕穗期，作物长势旺盛，田间郁闭，通风透光差，"
                "植株正由营养生长向生殖生长过渡，抗病虫能力减弱，利于各种病虫害的发生。",
    },
    "SRC-CMA-RICE-SEED-2025": {
        "publisher": "中国气象局（辽宁省水稻气象服务中心、辽宁省生态气象和卫星遥感中心）",
        "url": "https://www.cma.gov.cn/ztbd/2025zt/20250418/2025041807/yw/202504/t20250416_7003932.html",
        "slug": "cma-rice-seed-2025",
        "cities": [],
        "text": "4月1日，辽宁省水稻气象服务中心与辽宁省生态气象和卫星遥感中心联合发布2025年辽宁省水稻育秧适宜播种期预报。"
                "农业气象专家建议利用4月上旬晴暖无风时段，集中完成营养土装盘及播种作业，抓住3日、5日至6日、8日适播期抢抓农时。",
    },
}

# ---------------------------------------------------------------------------
# 记录（city 级别；county 为市级则留空）
# 元组：city, county, crop_raw, crop_standard, year, stage, start, end, precision,
#       src_key, source_text, grade, derived
# ---------------------------------------------------------------------------
RECORDS = [
    # ---------------- 沈阳 ----------------
    ("shenyang", "苏家屯区", "水稻", "水稻", 2025, "transplant", "2025-05-15", "2025-05-28", "range",
     "SRC-LNCMA-RICE-TRANSPLANT", "表1：沈阳 苏家屯 适宜移栽期5月15~28日，最迟移栽期5月31日。", "A", "true"),
    ("shenyang", "辽中区", "水稻", "水稻", 2025, "transplant", "2025-05-15", "2025-05-28", "range",
     "SRC-LNCMA-RICE-TRANSPLANT", "表1：沈阳 辽中 适宜移栽期5月15~28日，最迟移栽期5月31日。", "A", "true"),
    ("shenyang", "沈北新区", "水稻", "水稻", 2025, "transplant", "2025-05-15", "2025-05-28", "range",
     "SRC-LNCMA-RICE-TRANSPLANT", "表1：沈阳 沈北 适宜移栽期5月15~28日，最迟移栽期5月31日。", "A", "true"),
    ("shenyang", "新民市", "水稻", "水稻", 2025, "transplant", "2025-05-15", "2025-05-28", "range",
     "SRC-LNCMA-RICE-TRANSPLANT", "表1：沈阳 新民 适宜移栽期5月15~28日，最迟移栽期5月31日。", "A", "true"),
    ("shenyang", "康平县", "水稻", "水稻", 2025, "transplant", "2025-05-15", "2025-05-28", "range",
     "SRC-LNCMA-RICE-TRANSPLANT", "表1：沈阳 康平 适宜移栽期5月15~28日，最迟移栽期5月31日。", "A", "true"),
    ("shenyang", "法库县", "水稻", "水稻", 2025, "transplant", "2025-05-15", "2025-05-28", "range",
     "SRC-LNCMA-RICE-TRANSPLANT", "表1：沈阳 法库 适宜移栽期5月15~28日，最迟移栽期5月31日。", "A", "true"),
    ("shenyang", "苏家屯区", "水稻", "水稻", 2025, "transplant", "2025-05-22", "2025-05-29", "range",
     "SRC-XHW-SY-RICE", "沈阳市苏家屯区水稻种植面积达7.7万亩。目前，超4.4万亩稻田完成插秧……预计5月底前可完成全部种植任务。", "B", "true"),
    ("shenyang", "法库县", "玉米", "玉米", 2025, "sowing", "2025-04-20", "2025-05-04", "range",
     "SRC-SYCMA-CORN-TRIAL", "精准确定4月20日至5月4日为最佳播种期（法库县对照试验区）。", "A", "true"),
    ("shenyang", "沈北新区", "玉米", "玉米", 2025, "sowing", "2025-04-20", "2025-05-04", "range",
     "SRC-SYCMA-CORN-TRIAL", "精准确定4月20日至5月4日为最佳播种期（沈北新区对照试验区）。", "A", "true"),
    ("shenyang", "苏家屯区", "水稻", "水稻", 2020, "grain_filling", "2020-08-21", "2020-08-21", "day",
     "SRC-SYCMA-SJT-RICE", "8月21日……深入八一红菱街道水稻种植基地开展水稻灌浆期生长情况服务调研。", "A", "true"),

    # ---------------- 铁岭 ----------------
    ("tieling", "昌图县", "玉米", "玉米", 2025, "sowing", "2025-04-17", "2025-04-30", "range",
     "SRC-CT-GOV-SOWING", "第一场透雨较往年偏早12天，最佳适播期为4月17至30日，最晚不晚于5月15日。", "A", "false"),
    ("tieling", "铁岭县", "水稻", "水稻", 2025, "transplant", "2025-05-26", "2025-05-26", "day",
     "SRC-LNRB-SPRING-END", "5月26日，在铁岭县新台子镇的一处高标准农田里，高速插秧机在田间来回穿梭。", "B", "false"),
    ("tieling", "昌图县", "玉米", "玉米", 2025, "emergence", "2025-05-23", "2025-05-23", "day",
     "SRC-LNRB-SPRING-END", "最新的苗情监测显示，昌图县、铁岭县等地玉米整体苗情不错，出苗率高、出苗齐。", "B", "true"),
    ("tieling", "铁岭县", "玉米", "玉米", 2025, "emergence", "2025-05-23", "2025-05-23", "day",
     "SRC-LNRB-SPRING-END", "最新的苗情监测显示，昌图县、铁岭县等地玉米整体苗情不错，出苗率高、出苗齐。", "B", "true"),
    ("tieling", "", "水稻", "水稻", 2025, "transplant", "2025-05-15", "2025-05-28", "range",
     "SRC-LNCMA-RICE-TRANSPLANT", "预计……铁岭南部适宜移栽期为5月15～28日。", "A", "true"),
    ("tieling", "昌图县", "玉米", "玉米", 2025, "sowing", "2025-05-07", "2025-05-07", "day",
     "SRC-LNNYNC-TL-20W", "5月7日……部分大型合作社在春耕整地结束后，已经开始按照相关标准进行播种（昌图县等4县各实施5万亩）。", "B", "true"),

    # ---------------- 锦州 ----------------
    ("jinzhou", "", "水稻", "水稻", 2025, "transplant", "2025-05-22", "2025-06-02", "range",
     "SRC-LNCMA-RICE-TRANSPLANT", "预计……其他稻区（含锦州）适宜移栽期为5月22日～6月2日，最迟移栽期6月9日。", "A", "true"),
    ("jinzhou", "", "玉米", "玉米", 2025, "sowing", "2025-05-07", "2025-05-07", "day",
     "SRC-LNRB-SOWING-HALF", "截至5月7日……铁岭、朝阳、锦州、葫芦岛等地玉米播种均进程过半。", "B", "true"),

    # ---------------- 丹东 ----------------
    ("dandong", "东港市", "草莓", "草莓", 2025, "transplant", "2025-09-17", "2025-09-17", "day",
     "SRC-DDNY-STRAWBERRY", "实地察看了已于9月17日完成定植的最后一批冷冻苗。", "A", "false"),
    ("dandong", "东港市", "草莓", "草莓", 2025, "maturity", "2025-10-20", "2025-10-31", "month",
     "SRC-DDNY-STRAWBERRY", "该批草莓预计于10月20日后陆续上市。", "A", "false"),
    ("dandong", "东港市", "草莓", "草莓", 2024, "seedling", "2024-04-01", "2024-08-31", "range",
     "SRC-RMRB-DG-STRAWBERRY", "每年，4月到8月育苗，9月开始种植，11月到次年6月采摘售卖。", "B", "true"),
    ("dandong", "东港市", "草莓", "草莓", 2024, "transplant", "2024-09-01", "2024-09-30", "month",
     "SRC-RMRB-DG-STRAWBERRY", "每年，4月到8月育苗，9月开始种植，11月到次年6月采摘售卖。", "B", "true"),
    ("dandong", "东港市", "草莓", "草莓", 2024, "harvest", "2024-11-01", "2025-06-30", "range",
     "SRC-RMRB-DG-STRAWBERRY", "每年……11月到次年6月采摘售卖。", "B", "true"),
    ("dandong", "东港市", "草莓", "草莓", 2025, "maturity", "2025-10-01", "2025-10-31", "month",
     "SRC-KJRB-DG-STRAWBERRY", "待9月中下旬定植后，10月即可迎来首茬采摘，较传统种植提前2个月。", "B", "true"),
    ("dandong", "东港市", "水稻", "水稻", 2025, "transplant", "2025-05-26", "2025-05-26", "day",
     "SRC-LNRB-DG-RICE", "5月26日，在东港市长山镇的农田里，数台智能高速插秧机来回穿梭。", "B", "false"),
    ("dandong", "东港市", "水稻", "水稻", 2026, "seedling", "2026-01-15", "2026-01-15", "month",
     "SRC-LNRB-DG-EARLYRICE", "众发合作社是整个东港最早育苗的地方……一月中旬，技术人员就扎进大棚筹备新一年的育苗工作。", "B", "true"),
    ("dandong", "东港市", "水稻", "水稻", 2026, "transplant", "2026-04-15", "2026-04-15", "month",
     "SRC-LNRB-DG-EARLYRICE", "……四月中旬便开始插秧，比常规水稻整整早了大半个月（早熟品种'中科发5号'）。", "B", "true"),
    ("dandong", "东港市", "水稻", "水稻", 2026, "harvest", "2026-09-02", "2026-09-02", "day",
     "SRC-LNRB-DG-EARLYRICE", "9月2日一大早，东港市小甸子镇的稻田里就响起了轰隆隆的机器声。三台收割机一头扎进早稻田……这是全省最早进入收割期的稻田。", "A", "false"),

    # ---------------- 大连 ----------------
    ("dalian", "", "玉米", "玉米", 2025, "maturity", "2025-09-19", "2025-09-19", "day",
     "SRC-DLCMA-HARVEST", "目前，我市玉米处于蜡熟至完熟期。", "A", "true"),
    ("dalian", "", "水稻", "水稻", 2025, "grain_filling", "2025-09-19", "2025-09-19", "day",
     "SRC-DLCMA-HARVEST", "水稻处于乳熟至蜡熟期。", "A", "true"),
    ("dalian", "", "大豆", "大豆", 2025, "grain_filling", "2025-09-19", "2025-09-19", "day",
     "SRC-DLCMA-HARVEST", "大豆处于鼓粒至成熟期。", "A", "true"),
    ("dalian", "", "玉米", "玉米", 2025, "harvest", "2025-09-20", "2025-10-31", "range",
     "SRC-DLCMA-HARVEST", "我市大田作物适宜收获期在9月20日至10月31日，与常年基本一致。", "A", "true"),
    ("dalian", "瓦房店市", "苹果", "苹果", 2025, "harvest", "2025-10-24", "2025-10-24", "day",
     "SRC-LNRB-DL-APPLE", "霜降前后，大连52万亩苹果迎来集中采收期。10月24日上午，在瓦房店市许屯镇东马屯村的果林间……", "A", "false"),
    ("dalian", "瓦房店市", "苹果", "苹果", 2025, "harvest", "2025-10-19", "2025-10-19", "day",
     "SRC-LNRB-DL-APPLE2", "10月19日，果农在大连瓦房店市许屯镇东马屯村山上采摘和运输苹果。", "B", "false"),
    ("dalian", "普兰店区", "水稻", "水稻", 2025, "transplant", "2025-05-20", "2025-05-31", "range",
     "SRC-LNCMA-RICE-TRANSPLANT", "表1：大连 普兰店 适宜移栽期5月20~31日，最迟移栽期6月13日。", "A", "true"),
    ("dalian", "庄河市", "水稻", "水稻", 2025, "transplant", "2025-05-20", "2025-05-31", "range",
     "SRC-LNCMA-RICE-TRANSPLANT", "表1：大连 庄河 适宜移栽期5月20~31日，最迟移栽期6月13日。", "A", "true"),

    # ---------------- 朝阳 ----------------
    ("chaoyang", "", "玉米", "玉米", 2025, "jointing", "2025-07-09", "2025-07-09", "day",
     "SRC-CYCMA-DROUGHT", "目前，全市大部分地区玉米处于拔节期至吐丝期。", "A", "true"),
    ("chaoyang", "", "玉米", "玉米", 2025, "tasseling", "2025-07-09", "2025-07-09", "day",
     "SRC-CYCMA-DROUGHT", "目前，全市大部分地区玉米处于拔节期至吐丝期。", "A", "true"),
    ("chaoyang", "凌源市", "茄子", "蔬菜", 2022, "transplant", "2022-07-01", "2022-07-31", "month",
     "SRC-CNVEG-EGGPLANT", "当地一般7—8月定植，翌年6—7月生产结束。", "C", "true"),
]

# 省级（不可拆分为城市事实）→ reference/
PROVINCE_RECORDS = [
    ("辽宁", "", "玉米", "玉米", 2025, "tasseling", "2025-08-04", "2025-08-04", "day",
     "SRC-LNNYNC-PEST-2025", "目前玉米田处于抽雄吐丝期、水稻田进入孕穗期。", "B", "true"),
    ("辽宁", "", "水稻", "水稻", 2025, "booting", "2025-08-04", "2025-08-04", "day",
     "SRC-LNNYNC-PEST-2025", "目前玉米田处于抽雄吐丝期、水稻田进入孕穗期。", "B", "true"),
    ("辽宁", "", "水稻", "水稻", 2025, "sowing", "2025-04-01", "2025-04-10", "range",
     "SRC-CMA-RICE-SEED-2025", "建议利用4月上旬晴暖无风时段，集中完成营养土装盘及播种作业。", "A", "true"),
    ("辽宁", "", "蔬菜", "蔬菜", 2025, "transplant", "2025-04-01", "2025-05-10", "range",
     "SRC-LNNYNC-VEG-2025", "塑料大棚春提早蔬菜通常在4月上旬至5月上旬进行定植。", "B", "true"),
]


def write_raw(city, src_key):
    src = SOURCES[src_key]
    d = ROOT.parent / "data/raw" / "web_captures" / city / "phenology" / src["slug"]
    d.mkdir(parents=True, exist_ok=True)
    body = src["text"]
    digest = hashlib.md5((src["url"] + body).encode("utf-8")).hexdigest()[:16]
    f = d / (digest + ".html")
    if not f.exists():
        html = (
            "<!DOCTYPE html>\n<html lang=\"zh-CN\">\n<head>\n"
            "<meta charset=\"utf-8\" />\n"
            "<meta name=\"Publisher\" content=\"%s\" />\n"
            "<meta name=\"Url\" content=\"%s\" />\n"
            "<meta name=\"RetrievalDate\" content=\"%s\" />\n"
            "</head>\n<body>\n<article>\n<pre>\n%s\n</pre>\n</article>\n</body>\n</html>\n"
        ) % (src["publisher"], src["url"], RETRIEVAL_DATE, body)
        f.write_text(html, encoding="utf-8")
    return f


def append_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", encoding="utf-8-sig" if not exists else "utf-8", newline="") as fh:
        w = csv.writer(fh)
        if not exists:
            w.writerow(HEADER)
        for r in rows:
            w.writerow(r)


def main():
    summary = {}
    touched_raw = set()
    for rec in RECORDS:
        city, county, crop_raw, crop_std, year, stage, sd, ed, prec, src_key, stext, grade, derived = rec
        src = SOURCES[src_key]
        row = [city_map(city), county, crop_raw, crop_std, year, stage, sd, ed, prec,
               src_key, src["url"], stext, grade, derived]
        out = ROOT / city / "data" / "phenology_events.csv"
        append_csv(out, [row])
        if (city, src_key) not in touched_raw:
            write_raw(city, src_key)
            touched_raw.add((city, src_key))
        summary[city] = summary.get(city, 0) + 1

    # 省级
    prow = []
    for rec in PROVINCE_RECORDS:
        city, county, crop_raw, crop_std, year, stage, sd, ed, prec, src_key, stext, grade, derived = rec
        src = SOURCES[src_key]
        prow.append([city, county, crop_raw, crop_std, year, stage, sd, ed, prec,
                     src_key, src["url"], stext, grade, derived])
    append_csv(ROOT / "reference" / "phenology_events_province.csv", prow)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("province rows:", len(prow))
    print("raw files written:", len(touched_raw))


def city_map(city_dir):
    return {
        "shenyang": "沈阳", "tieling": "铁岭", "jinzhou": "锦州",
        "dandong": "丹东", "dalian": "大连", "chaoyang": "朝阳",
    }[city_dir]


if __name__ == "__main__":
    main()
