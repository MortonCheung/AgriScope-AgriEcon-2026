#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V2 构建脚本 D：crop_calendar_detailed + QC + DATA_GAP。"""
import csv, json
from pathlib import Path
from datetime import datetime
from collections import Counter

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
V1 = ROOT / "city_data/reference/decision_engine_supplement"
OUT = ROOT / "city_data/reference/decision_engine_supplement_v2"
AD = datetime.now().strftime("%Y-%m-%d")

# ---------- crop_calendar_detailed：在 V1 农事历上加生产体制与 DB21 依据 ----------
src = list(csv.DictReader((V1/"crop_calendar.csv").open(encoding="utf-8-sig")))
VEG = {"西红柿","黄瓜","番茄","茄子","辣椒","青椒","尖椒","韭菜","芹菜","甘蓝","芸豆","菜豆",
       "大白菜","油菜","菠菜","菜花","土豆","角瓜","西葫芦"}
rows = []
for r in src:
    crop = r.get("crop_standard","")
    ps = "greenhouse/solar_greenhouse" if crop in VEG else "open_field"
    r2 = dict(r)
    r2["production_system"] = ps
    r2["season"] = "unknown"
    r2["standard_ref"] = ("DB21/T 3416.2—2021(番茄)/DB21/T 3416.3—2021(黄瓜)"
                          if crop in ("黄瓜","西红柿","番茄") else "")
    r2["db21_applicable"] = "YES" if crop in ("黄瓜","西红柿","番茄") else "NO"
    r2["quality_flag"] = "stage_normalized"
    rows.append(r2)
write_cols = ["city","crop_raw","crop_standard","year","stage_raw","stage_group","start_date",
              "end_date","date_precision","production_system","season","facility_or_open_field",
              "standard_ref","db21_applicable","source_id","source_url","source_text",
              "quality_grade","quality_flag","access_date"]
with (OUT/"crop_calendar_detailed.csv").open("w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=write_cols, extrasaction="ignore"); w.writeheader()
    for r in rows: w.writerow(r)
print(f"[OK] crop_calendar_detailed.csv  {len(rows)} 行")

# ---------- QC ----------
FILES = {
 "price_series_inventory.csv": ["city","crop","price_level","unit"],
 "price_city_comparable.csv": ["crop","price_level","unit","cities"],
 "planting_area_crop_yearly.csv": ["year","city"],
 "production_crop_yearly.csv": ["year","city","column","table"],
 "crop_yield_by_city.csv": ["year","city","column","table"],
 "irrigation_yearly.csv": ["year","city","column","table"],
 "planting_area_crop_yearly_ocr.csv": ["year","city"],
 "crop_cost_yearly_extended.csv": ["year","city","crop","cost_type"],
 "agri_insurance_claims.csv": ["year","scope","crop","metric"],
 "disaster_loss_crop_events.csv": ["event_date","city","disaster_type"],
 "cold_chain_capacity.csv": ["year","city","district"],
 "demand_yearly.csv": ["year","city","indicator"],
 "market_registry_extended.csv": ["market_name","city"],
 "herding_events_extended.csv": ["event_id"],
 "crop_mapping.csv": ["raw_name"],
}
lines = ["# V2 补充数据质量检查报告","",f"- 生成时间：{AD}","- 规则：不自动删除；异常仅标记",""]
summary = {}
for fn, keys in FILES.items():
    p = OUT/fn
    if not p.exists():
        lines.append(f"## {fn}\n- 文件不存在\n"); summary[fn]={"status":"MISSING"}; continue
    rws = list(csv.DictReader(p.open(encoding="utf-8-sig")))
    n = len(rws); cols = list(rws[0].keys()) if rws else []
    dup = sum(v-1 for v in Counter(tuple(r.get(k,"") for k in keys) for r in rws).values() if v>1)
    miss = {c: round(100*sum(1 for r in rws if str(r.get(c,"")).strip()=="")/max(n,1),1) for c in cols}
    miss = {k:v for k,v in miss.items() if v>0}
    nosrc = sum(1 for r in rws if not (r.get("source_url") or r.get("source_id") or r.get("source_name") or r.get("source")))
    lines += [f"## {fn}", f"- 样本量：{n} 行 / {len(cols)} 列",
              f"- 业务键重复：{dup}（键={'+'.join(keys)}）",
              f"- 无来源记录：{nosrc} 行"]
    if miss:
        lines.append("- 缺失率>0 字段：" + "；".join(f"`{k}` {v}%" for k,v in sorted(miss.items(), key=lambda x:-x[1])[:8]))
    lines.append("")
    summary[fn] = {"rows":n,"dup":dup,"no_source":nosrc}
(OUT/"QC_REPORT_v2.md").write_text("\n".join(lines), encoding="utf-8")
(OUT/"qc_summary_v2.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
print("[OK] QC_REPORT_v2.md / qc_summary_v2.json")

# ---------- DATA_GAP ----------
GAPS = {
 "city_price_comparable": ("六城同口径可比价格","仍不可进行区域同步价格模型",
  "本轮重算了六城全部价格序列（2,275 条 city×crop×level 序列）与跨城重叠。"
  "满足『≥3城 + 重叠≥180天 + 覆盖≥30%』的组合数 = **0**。"
  "最接近的：猪肉(retail_market, 大连|铁岭|锦州, 重叠783天但覆盖仅21.8%)、"
  "肉牛(farm_gate 5城, 重叠395天覆盖15.6%)。沈阳因价格层级为 wholesale，与其余城市不重叠。",
  "NOT_FOUND（跨城同口径）"),
 "market_volume": ("六城市场成交量/上市量","NOT_PUBLIC（沈阳除外）",
  "V2 未新增。沈阳 canonical 已有 14,124 行日频批发成交量（单位未知）。其余五城无公开连续供应量序列。",
  "NOT_PUBLIC"),
 "crop_disaster_loss": ("分作物灾损面积","NOT_PUBLIC",
  "官方灾情通报多为『农作物受灾X公顷』合计，不按作物拆分。V2 新增 8·20 洪涝保险估损（锦州/朝阳/葫芦岛）",
  "NOT_PUBLIC（分作物）"),
 "remote_sensing": ("遥感植被 NDVI/EVI","未获取",
  "本轮未接入 MODIS/Sentinel（需 Earthdata/Copernicus 账号鉴权）。"
  "如需可另立专项，用 NASA Earthdata 或 Copernicus Data Space 的 COG/API 子集。",
  "NOT_FOUND（本轮）"),
 "vegetable_cost_city": ("分城市蔬菜亩均成本","PROXY",
  "仅获得东北地区8市加权平均（日光温室果菜运行成本 23,840 元/667m²·年，沈阳农业大学，110份问卷）。"
  "单城市蔬菜成本官方未公开。",
  "PROXY（regional）"),
 "facility_phenology": ("设施/露地/茬口细分农事历","部分",
  "已按作物类型推断 production_system（设施/露地），并关联 DB21/T 3416.2/.3—2021 番茄/黄瓜规程。"
  "但逐作物的『设施 vs 露地 vs 春茬/秋茬』官方分列时间窗口未获取到结构化条目。",
  "PARTIAL"),
 "logistics": ("物流成本/市场可达性","未获取",
  "未获得六城间道路距离或运输成本官方数据。已登记市场清单（6 条）与冷链库容（4 条）。",
  "NOT_FOUND"),
}
for k,(name,status,desc,st) in GAPS.items():
    (OUT/f"DATA_GAP_{k}.md").write_text(
        f"# 数据缺口：{name}\n\n- 状态：**{status}**\n- 生成日期：{AD}\n\n## 说明\n{desc}\n", encoding="utf-8")
    print(f"[OK] DATA_GAP_{k}.md")
print("\n完成脚本 D。")
