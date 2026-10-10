"""建立 source_lead_registry.csv（线索注册表）与 market_registry.csv（市场注册表）。

source_lead_registry：把"文章里提到的监测行为"落成可追踪的线索，
  每条线索记录：城市 / 线索原文 / 疑似来源 / 当前状态 / 已试路径 / 下一步
  —— 用于落实用户规则："据XX监测……"这类话说明底层数据一定曾经存在。

market_registry：六城市主要农产品批发市场清单，用于路径 H（市场本身）
  与路径 F（农业农村部批发市场系统按市场定位到城市）。
"""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
META = ROOT / "data/raw/metadata"
META.mkdir(parents=True, exist_ok=True)

LEADS = [
    # city, clue(原文/现象), suspected_source, status, tried_paths, next_action
    ("朝阳", "栏目列出《朝阳市主要菜篮子产品每日价情》20条/页，共75页",
     "fgw.chaoyang.gov.cn 价格信息栏目(CMS 栏目ID 162063350188546)",
     "FOUND_COLLECTING",
     "站内栏目;前端JS分页函数getDynamicPageUrl;CMS分页接口page.xhtml",
     "已定位 cms.chaoyang.gov.cn/html/page.xhtml?s=CYFGW&o=N，采集中"),
    ("朝阳", "早期页面含《朝阳市农资市场销售价格调查分析》《居民消费价格指数》",
     "同一栏目历史文章", "FOUND_COLLECTING", "同栏目回溯至 2017-03", "随栏目一并采集"),
    ("锦州", "省发改委文件：'设立市级菜篮子信息发布平台，发布每日价情信息'",
     "锦州市政府 菜篮子信息发布平台", "FOUND_COLLECTING",
     "搜索引擎 site 反查;市政府专题专栏",
     "已定位 jz.gov.cn/ztzl/clzxxfbpt.htm，倒序96页，采集中"),
    ("锦州", "已有 jinzhou_price_basket_weekly.csv(1885行/291周)",
     "锦州菜篮子周报", "PARTIAL", "已解析入库 staging", "待与日度原文交叉验证并入库"),
    ("大连", "民生商品价格监测系统(含每日蔬菜批发价表)",
     "jgjc.pc.dl.gov.cn:8090", "NETWORK_FAILED",
     "沙箱代理;直连;本机代理7892;80/8080/8090 三端口",
     "换网络环境重试；主站 pc.dl.gov.cn 通，仅该系统端口不通"),
    ("大连", "中国价格信息网 36个大中城市月度价格",
     "www.chinaprice.cn", "FOUND", "已采集260行月度入库", "继续回溯 2025/2024/2023 及更早"),
    ("大连", "市发展改革研究中心周度农副产品监测文章",
     "www.dl.gov.cn col1437", "FOUND", "已采集399行周度入库", "继续回溯历史页"),
    ("铁岭", "铁岭县价格监测(530行)",
     "铁岭县", "FOUND", "已入库并标注 geo_level=county", "严禁冒充市级；继续找铁岭市级"),
    ("铁岭", "市统计公报 2020-2024 含分作物播种面积与产量",
     "tieling.gov.cn 统计公报栏目", "FOUND", "已入库", "补 2025"),
    ("丹东", "省发改委材料显示丹东发改委曾对16种蔬菜高频监测",
     "丹东市发改委价格监测系统", "SEARCHING",
     "市政府主站栏目;发改委;搜索引擎", "下一步：site:dandong.gov.cn 价格监测/16种蔬菜"),
    ("丹东", "丹东统计年鉴含主要农作物产量/播种面积/单产",
     "丹东市统计年鉴", "FOUND", "已入库35行(2025)", "继续回溯 2020-2024 作物细粒度"),
    ("全省", "省农业农村厅周报'最高价地区A/最低价地区B'",
     "辽宁农业农村厅周报", "ISOLATED",
     "已隔离为 fact_price_city_extremum_weekly", "保持隔离，禁止当连续城市价"),
]

MARKETS = [
    # city, market_name, county, market_type, official_site, moa_market, data_available, source
    ("沈阳", "沈阳盛发蔬菜批发市场", "沈阳市", "蔬菜批发", "", "否", "待查", "公开资料"),
    ("沈阳", "沈阳粮食批发市场", "沈阳市", "粮食批发", "", "否", "待查", "公开资料"),
    ("大连", "大连双兴商品城", "大连市", "综合农批", "", "是", "待查", "pfsc市场目录"),
    ("大连", "大连金三角粮食批发市场", "大连市", "粮食批发", "", "否", "待查", "市发改委粮油报告"),
    ("铁岭", "铁岭县农产品批发市场", "铁岭县", "综合农批", "", "否", "部分(县级530行)", "铁岭县监测"),
    ("朝阳", "朝阳市主要超市及农贸市场(监测点)", "朝阳市", "零售监测点", "", "否",
     "有(每日价情)", "fgw.chaoyang.gov.cn"),
    ("锦州", "锦州市农贸市场/生鲜超市(监测点)", "锦州市", "零售监测点", "", "否",
     "有(每日价情)", "jz.gov.cn 菜篮子平台"),
    ("丹东", "丹东市农贸市场(待确认)", "丹东市", "零售监测点", "", "否", "待查", "待侦查"),
]


def main() -> None:
    p1 = META / "source_lead_registry.csv"
    with p1.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["city", "clue", "suspected_source", "status",
                    "tried_paths", "next_action"])
        w.writerows(LEADS)
    print(f"[OK] source_lead_registry.csv {len(LEADS)} 条")

    p2 = META / "market_registry.csv"
    with p2.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["city", "market_name", "county", "market_type", "official_site",
                    "public_account", "historical_name", "aliases", "moa_market",
                    "data_available", "source"])
        for row in MARKETS:
            w.writerow([row[0], row[1], row[2], row[3], row[4], "", "", "",
                        row[5], row[6], row[7]])
    print(f"[OK] market_registry.csv {len(MARKETS)} 条")


if __name__ == "__main__":
    main()
