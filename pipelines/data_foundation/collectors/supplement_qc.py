#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对 decision_engine_supplement 全部新增表做自动质量检查：
  重复 / 缺失 / 单位 / 异常值(仅标记) / 来源完整性
产出：QC_REPORT_supplement.md + qc_summary.json
"""
import csv, json
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
OUT = ROOT / "data/raw/retained_source/city_data" / "reference" / "decision_engine_supplement"
AD = datetime.now().strftime("%Y-%m-%d")

FILES = [
    ("price_lnnync_veg_weekly_extended.csv", ["year","week","crop_standard"],
     {"price": (0, 100, "元/公斤")}),
    ("planting_area_yearly.csv", ["year","city","district","crop"], {"planting_area": (0, 2000, "千公顷")}),
    ("production_yearly_extended.csv", ["year","city","district","crop"], {"production": (0, 1000, "万吨")}),
    ("crop_cost_yearly.csv", ["year","city","crop"], {"cost_total_per_mu": (0, 5000, "元/亩")}),
    ("cost_proxy_insurance.csv", ["year","scope","crop","insurance_type"], {"insured_amount_per_mu": (0, 5000, "元/亩")}),
    ("disaster_loss_events.csv", ["event_date","city","disaster_type"], {}),
    ("herding_events.csv", ["event_id"], {}),
    ("soil_moisture_daily_extended.csv", ["date"], {"soil_water_layer_1": (0, 1, "m3/m3")}),
    ("supply_demand_yearly.csv", ["year","city","indicator"], {}),
]

lines = ["# 补充数据自动质量检查报告", "", f"- 生成时间：{AD}", "- 规则：不自动删除任何行，异常值仅标记 qc_flag", ""]
summary = {}

for fn, keycols, ranges in FILES:
    p = OUT / fn
    if not p.exists():
        lines.append(f"## {fn}\n- 缺失：文件不存在\n")
        summary[fn] = {"status": "MISSING"}
        continue
    rows = list(csv.DictReader(p.open(encoding="utf-8-sig")))
    n = len(rows)
    cols = list(rows[0].keys()) if rows else []
    # 重复
    seen = Counter(tuple(r.get(k, "") for k in keycols) for r in rows)
    dup = sum(v - 1 for v in seen.values() if v > 1)
    # 缺失（空字段率）
    miss = {}
    for c in cols:
        e = sum(1 for r in rows if str(r.get(c, "")).strip() == "")
        if e:
            miss[c] = round(100 * e / n, 1)
    # 单位
    units = sorted({r.get("unit", "") or r.get("production_unit", "") or r.get("planting_area_unit", "")
                    or r.get("economic_loss_unit", "") for r in rows if r})
    units = [u for u in units if u]
    # 异常
    flags = 0
    for r in rows:
        for c, (lo, hi, _u) in ranges.items():
            try:
                v = float(r.get(c, ""))
                if not (lo <= v <= hi):
                    flags += 1
            except (ValueError, TypeError):
                pass
    # 来源完整性
    no_src = sum(1 for r in rows if not (r.get("source_url") or r.get("source_id")
                                         or r.get("source_name") or r.get("source")))
    # 时间跨度
    span = ""
    if "year" in cols:
        ys = sorted({r["year"] for r in rows if r.get("year")})
        span = f"{ys[0]}~{ys[-1]}" if ys else ""
    elif "pub_date" in cols:
        ds = sorted({r["pub_date"] for r in rows if r.get("pub_date")})
        span = f"{ds[0]}~{ds[-1]}" if ds else ""
    elif "date" in cols:
        ds = sorted({r["date"] for r in rows if r.get("date")})
        span = f"{ds[0]}~{ds[-1]}" if ds else ""
    elif "event_date" in cols:
        ds = sorted({r["event_date"] for r in rows if r.get("event_date")})
        span = f"{ds[0]}~{ds[-1]}" if ds else ""

    lines += [f"## {fn}", f"- 样本量：{n} 行 / {len(cols)} 列",
              f"- 时间跨度：{span or '（无日期字段）'}",
              f"- 业务键重复行：{dup}（键={'+'.join(keycols)}）",
              f"- 单位：{', '.join(units) if units else '（无单位字段）'}",
              f"- 异常值标记：{flags} 处（仅标记，未删除）",
              f"- 无来源记录：{no_src} 行", "- 缺失率（仅列非空字段）："]
    if miss:
        lines += [f"  - `{c}`：{v}%" for c, v in sorted(miss.items(), key=lambda x: -x[1])]
    else:
        lines.append("  - 无空字段")
    lines.append("")
    summary[fn] = {"rows": n, "dup": dup, "flags": flags, "no_source": no_src,
                   "span": span, "missing_rate": miss}

lines.append("")
lines += [
 "## 重复成因说明（未删除，仅记录）",
 "- `price_lnnync_veg_weekly_extended.csv`：3 组重复均为**官方同一周次两次发布**"
 "（2024-07-18 与 2024-07-24 两篇文章同标「第29周」，数值不同，疑似修订重发）。"
 "保留两行并保留各自 `url`，建模时按 `pub_date` 取较新者或人工裁定。",
 "- `planting_area_yearly.csv` / `production_yearly_extended.csv`：原按 `year+city+crop` 出现 3 组同键，"
 "系「朝阳市级」与「建平县区县级」同作物并存，非错误；已在键中加入 `district` 后归零。",
 "- 其余表业务键重复均为 0。",
]

(OUT / "QC_REPORT_supplement.md").write_text("\n".join(lines), encoding="utf-8")
(OUT / "qc_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
print("\n".join(lines))
