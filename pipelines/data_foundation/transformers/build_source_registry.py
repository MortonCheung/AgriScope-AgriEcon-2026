"""数据源登记表（手册第 49 节要求的字段结构）。

字段：source_id, category, organization, dataset_name, official_flag,
      spatial_resolution, temporal_resolution, date_range, access_method, status, notes

status: success / partial / blocked_by_auth / blocked_by_captcha /
        network_failed / not_publicly_available / source_discontinued
"""
from __future__ import annotations

import pandas as pd

from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
META = ROOT / "data/raw/metadata"
REPORTS = ROOT / "city_data/reference/reports"

COLS = ["source_id", "category", "organization", "dataset_name", "official_flag",
        "spatial_resolution", "temporal_resolution", "date_range",
        "access_method", "status", "notes"]

ROWS = [
    ("SRC-LN-NYNC-PRICE", "price", "辽宁省农业农村厅", "农产品信息·价格简讯", "官方",
     "省/市/区县(极值)", "周", "2021-03-11~2026-09-17", "HTML列表分页(JS tagname)+正文解析",
     "success", "1125篇文章、26216条记录；含省级均价与最高/最低价地区"),
    ("SRC-MOA-PFSC-MARKET", "price", "农业农村部", "全国农产品批发市场价格信息系统·市场目录", "官方",
     "市场", "静态", "-", "公开JSON API(/price_portal/region/selectList、getMarketByProvinceCode)",
     "partial", "取辽宁12个市场(含经纬度)；丹东、铁岭无纳入市场"),
    ("SRC-MOA-PFSC-PRICE", "price", "农业农村部", "全国农产品批发市场价格信息系统·价格查询", "官方",
     "市场×品种", "日", "-", "XHR(/api/priceQuotationController/pageList)",
     "blocked_by_auth", "接口需Bearer token，匿名返回404；未绕过鉴权"),
    ("SRC-MOFCOM", "price", "商务部", "全国农产品产销智能分析平台", "官方",
     "市场", "日", "-", "网站", "network_failed", "域名解析失败；zdscxx.mofcom.gov.cn 502"),
    ("SRC-LN-FGW-PRICE", "price", "辽宁省发展和改革委员会", "价格监测(每日价格/涉农产品/农副产品)", "官方",
     "省", "日/周", "-", "栏目页", "not_publicly_available", "三个栏目均无列表内容(空栏目)"),
    ("SRC-WEATHER-CMA", "weather", "中国气象局", "中国气象数据网", "官方",
     "站点", "日", "-", "网站/API", "blocked_by_auth", "需登录+实名认证；未绕过"),
    ("SRC-WEATHER-OM", "weather", "Copernicus/ECMWF 经 Open-Meteo", "ERA5 / ERA5-Land 再分析", "非官方",
     "0.25°网格(城市点)", "日/小时", "2021-01-01~2026-09-14；基线1991-2020",
     "公开REST API", "success", "核心11变量+扩展8变量+日照时数+土壤3层；data_type=reanalysis"),
    ("SRC-WEATHER-NASA", "weather", "NASA", "POWER Daily API (MERRA2)", "非官方",
     "0.5°网格", "日", "2021-01-01~2026-09-14", "公开REST API", "success", "交叉验证用"),
    ("SRC-LN-TJJ-YEARBOOK", "production", "辽宁省统计局", "辽宁统计年鉴(Excel)", "官方",
     "省/市", "年", "2017~2019(3卷)", "官网ZIP下载→Excel解析", "partial",
     "仅公开2018/2019/2020三卷；含播种面积/产量/单产/农业生产条件/人口/CPI/收入/GDP/官方城市气象"),
    ("SRC-LN-TJJ-BULLETIN", "production", "辽宁省统计局", "年度统计公报", "官方",
     "省", "年", "-", "网页文本", "partial", "文字叙述，未结构化为城市面板"),
    ("SRC-LN-SLT-DISASTER", "disaster", "辽宁省水利厅", "汛情快报/监测预警/防汛动态", "官方",
     "省/市", "事件", "2026", "网页文本", "partial",
     "列表为异步加载，静态页无条目；仅少量文本"),
    ("SRC-LN-NYNC-DISASTER", "disaster", "辽宁省农业农村厅", "农业要闻(防灾减灾)", "官方",
     "省", "事件", "2026", "网页文本+关键词过滤", "partial", "命中少且多为外省转载"),
    ("SRC-DERIVED-WEATHER-EVENTS", "disaster", "本项目派生", "极端天气事件(气象阈值识别)", "派生",
     "城市", "事件", "2021~2026", "日值固定阈值算法", "success",
     "140起(暴雨63/强降水54/高温19/干旱4)；与官方通报严格分开"),
    ("SRC-LN-PESTS", "pests", "辽宁省农业农村厅及省农业发展服务中心", "植保/病虫害相关公开栏目", "官方",
     "省/区域(原文)", "事件", "2026", "网页文本+关键词过滤", "partial",
     "32篇文章；未结构化到城市级；region_raw保留原文如「辽西北」"),
    ("SRC-LN-FGW-FUEL", "input_cost", "辽宁省发展和改革委员会", "成品油价格调整公告", "官方",
     "省", "调价期", "2026-07~2026-09(6期)", "PDF下载+pypdf解析", "partial",
     "仅近期公告公开；含92#/95#/0#柴油批发零售价"),
    ("SRC-LN-SOIL-OFFICIAL", "soil", "辽宁省农业农村厅", "土壤墒情/旱情监测", "官方",
     "-", "-", "-", "栏目检索", "not_publicly_available", "未发现公开的结构化墒情历史序列"),
    ("SRC-ERA5LAND-SOIL", "soil", "Copernicus 经 Open-Meteo", "ERA5-Land 土壤分层含水量", "非官方",
     "0.1°网格", "小时→日", "2021~2026-09-14", "公开REST API", "success",
     "0-7/7-28/28-100cm 土壤水 + 0-7cm 土温；data_type=reanalysis"),
    ("SRC-MARKET-SUPPLY", "market_supply", "-", "批发市场上市量/成交量/库存", "-",
     "-", "-", "-", "-", "not_publicly_available", "官方系统不公开结构化供应量数据"),
    ("SRC-LOGISTICS", "logistics", "交通运输部门", "物流中断/道路封闭事件", "官方",
     "-", "事件", "-", "网站检索", "not_publicly_available", "多为实时公告，无结构化历史留存"),
    ("SRC-HYDRO-MWR", "hydro", "水利部", "大江大河/大型水库水情", "官方",
     "站点", "实时", "-", "网站", "network_failed", "xxfb.mwr.cn 返回502"),
    ("SRC-HYDRO-LNSLT", "hydro", "辽宁省水利厅", "水文动态/实时水情", "官方",
     "站点", "实时", "-", "栏目页", "partial", "列表异步加载，静态页面无条目"),
    ("SRC-DCE", "macro", "大连商品交易所", "玉米/大豆/豆油期货行情", "官方",
     "-", "日", "-", "网站", "blocked_by_auth", "HTTP 412 反爬，需特定Cookie；未绕过"),
    ("SRC-STATS-CN", "macro", "国家统计局", "数据查询接口(CPI/人口等)", "官方",
     "省/市", "月/年", "-", "API data.stats.gov.cn", "blocked_by_auth",
     "HTTP 403 IP限制；**CPI已改从辽宁统计年鉴 Excel 取得**"),
    ("SRC-LN-TJJ-WIDE", "macro", "辽宁省统计局", "辽宁统计年鉴·各地区宽表", "官方",
     "市", "年/月", "2014~2019", "Excel解析", "success",
     "官方城市气象汇总(气温/湿度/降水/日照时数)、人口、CPI、城乡居民收入、GDP"),
    ("SRC-CALENDAR", "macro", "国务院办公厅", "法定节假日安排", "官方",
     "-", "日", "2021~2026", "chinese_calendar库", "success", "2191天"),
    ("SRC-REMOTE-SENSING", "remote_sensing", "NASA/ESA", "MODIS/Sentinel-2 植被指数", "非官方",
     "像元→城市", "8~16天", "-", "未采集", "not_publicly_available",
     "P3增强层，本轮按手册第30节不阻塞主流程，未采集"),
]


def main() -> None:
    df = pd.DataFrame(ROWS, columns=COLS)
    df["checked_at"] = "2026-09-21"
    df.to_csv(META / "source_registry.csv", index=False, encoding="utf-8-sig")
    df.to_csv(REPORTS / "source_registry.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] source_registry.csv {len(df)} 源（含手册§49要求的全部字段）")
    print(df["status"].value_counts().to_string())


if __name__ == "__main__":
    main()
