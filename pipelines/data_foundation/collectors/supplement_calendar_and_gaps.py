#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
1) crop_calendar.csv：把六城既有 phenology_events.csv 归一为「城市×作物×阶段」农事历。
2) DATA_GAP_*.md：对无法获取的类别明确登记 NOT_FOUND / NOT_PUBLIC / PROXY。
仅整合既有 canonical 物候数据，不新增/不编造。
"""
import csv, re
from pathlib import Path
from datetime import datetime

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
CD = ROOT / "data/raw/retained_source/city_data"
OUT = CD / "reference" / "decision_engine_supplement"
AD = datetime.now().strftime("%Y-%m-%d")
CITIES = {"shenyang":"沈阳","dalian":"大连","tieling":"铁岭","chaoyang":"朝阳","jinzhou":"锦州","dandong":"丹东"}

STAGE_GROUP = {
 "播种":"planting","sowing":"planting","seedling":"nursery","育苗":"nursery","育秧":"nursery",
 "出苗":"nursery","emergence":"nursery","land_prep":"land_prep","春耕":"land_prep",
 "transplant":"transplant","插秧":"transplant","移栽":"transplant","定植":"transplant",
 "开花":"flowering","flowering":"flowering","抽雄":"flowering","tasseling":"flowering",
 "拔节":"growth","jointing":"growth","现蕾":"flowering","坐果":"growth","grain_filling":"grain_filling",
 "harvest":"harvest","收获":"harvest","采收":"harvest","成熟":"maturity","maturity":"maturity","秋收":"harvest",
}

rows = []
for cd, cn in CITIES.items():
    p = CD / cd / "data" / "phenology_events.csv"
    if not p.exists():
        continue
    with p.open(encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            st = (r.get("stage") or "").strip()
            grp = STAGE_GROUP.get(st, "")
            if not grp:
                continue
            rows.append({
                "city": cn, "crop_raw": r.get("crop_raw",""), "crop_standard": r.get("crop_standard",""),
                "year": r.get("year",""), "stage_raw": st, "stage_group": grp,
                "start_date": r.get("start_date",""), "end_date": r.get("end_date",""),
                "date_precision": r.get("date_precision",""),
                "facility_or_open_field": ("unspecified"),
                "source_id": r.get("source_id",""), "source_url": r.get("source_url",""),
                "source_text": (r.get("source_text","") or "")[:200],
                "quality_grade": r.get("quality_grade",""), "access_date": AD,
            })

cols = ["city","crop_raw","crop_standard","year","stage_raw","stage_group","start_date","end_date",
        "date_precision","facility_or_open_field","source_id","source_url","source_text",
        "quality_grade","access_date"]
with (OUT/"crop_calendar.csv").open("w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader()
    for r in rows: w.writerow(r)
print(f"[OK] crop_calendar.csv {len(rows)} 行")
by = {}
for r in rows:
    by.setdefault(r["city"], set()).add(r["crop_standard"])
for c, s in by.items():
    print(f"   {c}: {len(s)} 作物")

# ---------------- 缺口说明 ----------------
GAPS = {
"market_volume": ("六城市场成交量/上市量", "NOT_PUBLIC（沈阳除外）",
 "沈阳：canonical volume_observations.csv 已有 14,124 行日频批发成交量（单位未知）。"
 "其余五城（朝阳/锦州/大连/铁岭/丹东）无官方公开的日/周频市场成交或上市量序列——"
 "各市商务局/农业农村局未发布连续供应量数据。辽宁省农业农村厅周度价格简讯**只含价格，不含成交量**。",
 ["检索：各市统计局/农业农村局/商务局 网站，「成交量/上市量/进场量/交易量」",
  "检索：辽宁省农业农村厅 价格简讯（已确认无成交量字段）",
  "检索：沈阳菜篮子平台（仅沈阳有）"],
 "本轮新增 0 条；维持既有沈阳 14,124 行，其余 NOT_PUBLIC"),
"crop_cost": ("分城市亩均种植成本", "PROXY / 部分",
 "官方成本调查仅覆盖：沈阳（玉米 2024/2025、水稻 2024/2025）、辽阳（邻市，玉米/大豆 2022–2024，作 regional_proxy）、"
 "昌图县/开原市（2020，单点）。朝阳仅公布净利润（玉米 700、大豆 300、蔬菜 5500 元/亩，2022），非成本。"
 "锦州/大连/丹东未检索到公开发布的分作物亩均成本。可用『种植业保险保额』作直接物化成本的 PROXY。",
 ["检索：各市发改委 成本调查/成本收益 栏目",
  "检索：全国农产品成本收益资料汇编（辽宁分作物公开值未获得）",
  "检索：种植业保险保额（已获得 2023/2025 方案）"],
 "新增 12 行成本 + 11 行保险代理；锦州/大连/丹东分作物成本 NOT_FOUND"),
"price_other_cities": ("六城同口径连续价格", "部分（省级周度已补）",
 "本轮新增辽宁省农业农村厅**省级周度批发价**（10 品种，2022-12~2026-09，1,052 条，含最高/最低地区）。"
 "但六城各自『同作物+同价格层级+足够重叠』的连续序列仍然不足："
 "沈阳=批发日频；朝阳=监测点平均日频；锦州=准周频；大连/铁岭/丹东=稀疏（详见既有审计）。",
 ["检索：辽宁省农业农村厅蔬菜价格简讯（已抓取 193 篇原文）",
  "检索：六城发改委/农业农村局价格栏目"],
 "新增省级周度 1,052 条；六城同口径仍不足，跨城联动仍不可行"),
"phenology": ("物候/农事历", "部分（结构已有）",
 "六城既有 phenology_events.csv 共 240 行，含播种/插秧/定植/开花/收获等阶段，"
 "已归一为 crop_calendar.csv。缺口：多数记录为『关键节点』而非连续观测，"
 "且**较少区分露地/温室/春茬/秋茬**（facility_or_open_field 普遍缺失），2021–2023 城市级样本薄。",
 ["检索：DB21 地方标准、农业技术规程（未获得可结构化条目）",
  "复用：六城既有 phenology_events.csv"],
 "归一 240 行为 crop_calendar.csv；设施/茬口区分仍缺失（NOT_FOUND）"),
"logistics": ("流通/物流/库存", "NOT_FOUND",
 "既有审计已确认 logistics/hydrology/pests 结构化数据缺失；本轮检索未发现六城公开的"
 "农产品物流指数、运输成本、批发市场进场量或粮食库存连续数据。",
 ["检索：各市商务局/交通局 物流指数",
  "检索：粮食库存/冷库库存（官方不公开）"],
 "NOT_FOUND（0 条）"),
"remote_sensing": ("遥感植被/长势", "NOT_FOUND（本轮未采集）",
 "项目 data/raw/remote_sensing 仅有 README。本轮未开展 MODIS/Sentinel 下载（超出单轮可行范围），"
 "如需可另立专项接入。",
 ["（未执行下载）"],
 "NOT_FOUND（0 条）"),
}
for key, (name, status, desc, tries, result) in GAPS.items():
    (OUT/f"DATA_GAP_{key}.md").write_text(
        f"# 数据缺口：{name}\n\n- 状态：**{status}**\n- 生成日期：{AD}\n\n"
        f"## 说明\n{desc}\n\n## 已尝试的检索\n" +
        "".join(f"- {t}\n" for t in tries) +
        f"\n## 本轮结果\n{result}\n", encoding="utf-8")
    print(f"[OK] DATA_GAP_{key}.md  ({status})")
print("\n完成。")
