"""数据源登记表、缺失数据说明、以及不可得数据源的显式占位表。

手册第 22 / 37 / 42 节要求：所有源必须记录真实状态（success / partial /
blocked_by_auth / network_failed / not_publicly_available …），
不可得的数据源不隐藏、不伪造，而是生成显式的占位说明。
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
META = ROOT / "data/raw/metadata"
MARTS = ROOT / "city_data/reference/marts"
REPORTS = ROOT / "city_data/reference/reports"
RAW = ROOT / "data/raw"
for d in (META, MARTS, REPORTS):
    d.mkdir(parents=True, exist_ok=True)

# 全部数据源的实测状态
SOURCES = [
    # id, name, category, url, status, note
    ("SRC-LN-NYNC", "辽宁省农业农村厅 农产品信息栏目", "agricultural_price",
     "https://nync.ln.gov.cn/nync/index/zwgk/zszdgz/ncpxx/", "success",
     "1125 篇历史周报，26216 条价格记录，2021-03-11~2026-09-17；含省级均价与最高/最低价地区"),
    ("SRC-MOA-PFSC-MARKET", "农业农村部 全国农产品批发市场价格信息系统（市场目录）", "market_metadata",
     "https://pfsc.agri.cn/", "partial",
     "公开接口可取辽宁市场 12 个（含经纬度）；丹东、铁岭无纳入市场"),
    ("SRC-MOA-PFSC-PRICE", "农业农村部 全国农产品批发市场价格信息系统（价格查询）", "daily_market_price",
     "https://pfsc.agri.cn/api/priceQuotationController/pageList", "blocked_by_auth",
     "前端拦截器显示该接口需 Authorization Bearer（localStorage），匿名访问返回 404，未绕过鉴权"),
    ("SRC-MOFCOM", "商务部 全国农产品产销智能分析平台", "daily_market_price",
     "https://nc.mofcom.gov.cn/", "network_failed",
     "域名无法解析/连接失败；zdscxx.mofcom.gov.cn 返回 502"),
    ("SRC-LN-FGW-PRICE", "辽宁省发展和改革委员会 价格监测栏目", "market_price",
     "https://fgw.ln.gov.cn/fgw/xxgk/jgjc/mrjg/index.shtml", "not_publicly_available",
     "「每日价格」「涉农产品」「农副产品」栏目无列表内容（空栏目），首页仅见周报标题"),
    ("SRC-WEATHER-CMA", "中国气象数据网（中国气象局）", "weather_observation",
     "https://data.cma.cn/", "blocked_by_auth",
     "数据下载需登录与实名认证，接口匿名返回 404，按手册不绕过，改用再分析源"),
    ("SRC-WEATHER-OM", "Open-Meteo Historical Weather API (ERA5)", "weather_reanalysis",
     "https://archive-api.open-meteo.com/v1/archive", "success",
     "6 城市 + 沈北新区，2021-01-01~2026-09-14 日值 2083 天，另含 1991-2020 基线 10958 天"),
    ("SRC-WEATHER-NASA", "NASA POWER Daily API (MERRA2)", "weather_reanalysis",
     "https://power.larc.nasa.gov/api/temporal/daily/point", "success",
     "7 个点全时段交叉验证数据（增强项）"),
    ("SRC-LN-TJJ-YEARBOOK", "辽宁省统计局 辽宁统计年鉴（Excel 数据下载）", "production",
     "https://tjj.ln.gov.cn/tjj/tjsj/tjnj/njsjxz/index.shtml", "partial",
     "仅公开 2018/2019/2020 三卷（覆盖 2017-2019 年数据）；2021 年及以后年鉴未公开发布"),
    ("SRC-LN-TJJ-BULLETIN", "辽宁省统计局 年度统计公报", "production",
     "https://tjj.ln.gov.cn/tjj/tjsj/tjgb/ndtjgb/index.shtml", "partial",
     "公报为文字叙述，仅含少量全省级农业数字，未结构化为城市级面板"),
    ("SRC-LN-SLT", "辽宁省水利厅 汛情快报 / 监测预警", "disaster",
     "https://slt.ln.gov.cn/slt/xwzx/fxdt/xqkb/index.shtml", "partial",
     "列表为异步加载，静态 HTML 中无条目；已改用水象数据驱动的事件识别补足"),
    ("SRC-LN-NYNC-DISASTER", "辽宁省农业农村厅 农业要闻（防灾减灾）", "disaster",
     "https://nync.ln.gov.cn/nync/index/nyyw/index.shtml", "partial",
     "关键词命中少量报道，且多为外省转载，非辽宁本地灾情"),
    ("SRC-MARKET-SUPPLY", "批发市场上市量/交易量", "market_supply",
     "—", "not_publicly_available",
     "农业农村部与商务部相关系统均不公开结构化上市量/成交量数据"),
]


def main() -> None:
    df = pd.DataFrame(SOURCES, columns=["source_id", "source_name", "category",
                                        "source_url", "status", "note"])
    df["checked_at"] = "2026-09-21"
    df.to_csv(META / "source_registry.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] source_registry.csv {len(df)} 条")
    print(df["status"].value_counts().to_string())

    # ---------- fact_price_daily：城市级日价格不可得，显式占位 ----------
    pd.DataFrame([{
        "table": "fact_price_daily", "status": "not_publicly_available",
        "reason": "城市级农产品日价格需农业农村部 priceQuotation 接口鉴权；"
                  "商务部源不可达；省发改委价格栏目为空。未绕过任何鉴权。",
        "available_alternative": "province_crop_week_panel.parquet（省级周价，真实连续）; "
                                 "fact_input_cost_weekly.parquet（农资城市周价）",
        "rows": 0,
    }]).to_csv(MARTS / "fact_price_daily.STATUS.csv", index=False, encoding="utf-8-sig")

    # ---------- fact_market_supply ----------
    pd.DataFrame([{
        "table": "fact_market_supply_daily/weekly", "status": "not_publicly_available",
        "reason": "官方系统不公开结构化上市量/成交量/库存数据",
        "available_alternative": "无", "rows": 0,
    }]).to_csv(MARTS / "fact_market_supply.STATUS.csv", index=False, encoding="utf-8-sig")

    # ---------- 灾害公开报道（辅助证据）----------
    jl = RAW / "disaster_reports" / "disaster_articles.jsonl"
    if jl.exists():
        rows = [json.loads(l) for l in jl.open(encoding="utf-8") if l.strip()]
        if rows:
            rep = pd.DataFrame(rows)[["article_id", "site", "column", "title",
                                      "list_date", "url", "raw_text"]]
            rep.to_parquet(MARTS / "fact_disaster_reports.parquet", index=False)
            rep.to_csv(MARTS / "fact_disaster_reports.csv", index=False, encoding="utf-8-sig")
            print(f"[OK] fact_disaster_reports {len(rep)} 条")

    print("[OK] 不可得数据源占位表已生成")


if __name__ == "__main__":
    main()
