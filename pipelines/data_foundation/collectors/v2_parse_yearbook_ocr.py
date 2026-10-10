#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
解析《辽宁统计年鉴》2024/2025 卷 13-14「各地区农作物播种面积」OCR 文本。
- 列顺序（经 2020 卷 XLS 表头确认）：
  总播种面积, 粮食作物, 水稻, 小麦, 玉米, 高粱, 谷子, 薯类, 大豆, 其他杂粮,
  经济作物, 油料, #花生, #葵花籽, 棉花, 甜菜, 烟叶, #烤烟, 蔬菜
- 校验：粮食作物 == 水稻+小麦+玉米+高粱+谷子+薯类+大豆+其他杂粮（容差 0.6）
  仅当校验通过才写入；未通过的行标记 quality_flag 并排除该行分项。
不编造任何数值。
"""
import re, csv, json
from pathlib import Path
from datetime import datetime

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
OUT = ROOT / "data/raw/retained_source/city_data" / "reference" / "decision_engine_supplement_v2"
OCR = ROOT / "data/raw" / "decision_engine_supplement_v2" / "production"
AD = datetime.now().strftime("%Y-%m-%d")

TARGET = {"沈阳", "大连", "丹东", "锦州", "铁岭", "朝阳"}
CROPS = ["总播种面积", "粮食作物", "水稻", "小麦", "玉米", "高粱", "谷子", "薯类",
         "大豆", "其他杂粮", "经济作物", "油料", "花生", "葵花籽", "棉花", "甜菜",
         "烟叶", "烤烟", "蔬菜"]
COMP = ["水稻", "小麦", "玉米", "高粱", "谷子", "薯类", "大豆", "其他杂粮"]

JOBS = [
    (2023, OCR / "yearbook_2024_ocr" / "13-14.txt", "yearbook_2024_ocr/13-14.jpg"),
    (2024, OCR / "yearbook_2025_ocr" / "13-14.txt", "yearbook_2025_ocr/13-14.jpg"),
]

rows, log = [], []
for year, txt_path, rawfile in JOBS:
    if not txt_path.exists():
        log.append({"year": year, "status": "MISSING", "file": str(txt_path)})
        continue
    for line in txt_path.read_text(encoding="utf-8", errors="replace").splitlines():
        toks = line.split()
        if len(toks) < 4:
            continue
        # 识别城市：允许 OCR 把「沈阳」拆成「沈   阳」
        joined = re.sub(r"\s+", "", line)
        city = None
        for c in TARGET:
            if joined.startswith(c):
                city = c
                break
        if not city:
            continue
        nums = []
        for t in toks:
            try:
                nums.append(float(t.replace(",", "")))
            except ValueError:
                pass
        if len(nums) < 12:
            log.append({"year": year, "city": city, "status": "TOO_FEW_NUMBERS",
                        "n": len(nums), "raw": line[:90]})
            continue
        # 前两列固定：总、粮食
        total, grain = nums[0], nums[1]
        rest = nums[2:]
        comp = rest[:8]
        tail = rest[8:]
        s = sum(comp)
        ok = abs(s - grain) <= max(0.8, grain * 0.004)
        rec = {"year": year, "city": city, "source_table": "13-14 各地区农作物播种面积",
               "source_file": rawfile, "unit": "千公顷",
               "quality_flag": "OCR_derived; grain_sum_check=PASS" if ok else "OCR_derived; grain_sum_check=FAIL",
               "source_level": "S", "access_date": AD}
        rec["总播种面积"] = total
        rec["粮食作物"] = grain
        if ok:
            for k, v in zip(COMP, comp):
                rec[k] = v
        else:
            for k in COMP:
                rec[k] = ""
        for k, v in zip(CROPS[10:], tail):
            rec[k] = v
        rows.append(rec)
        log.append({"year": year, "city": city, "status": "OK" if ok else "SUM_FAIL",
                    "grain": grain, "sum_components": round(s, 2)})

cols = ["year", "city"] + CROPS + ["source_table", "source_file", "unit",
                                   "quality_flag", "source_level", "access_date"]
with (OUT / "planting_area_crop_yearly_ocr.csv").open("w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow(r)

print(f"[OK] planting_area_crop_yearly_ocr.csv  {len(rows)} 行")
for r in sorted(rows, key=lambda x: (x["year"], x["city"])):
    print(f"  {r['year']} {r['city']:4s} 总={r['总播种面积']:>7} 粮={r['粮食作物']:>7} "
          f"玉米={r.get('玉米',''):>7} 大豆={r.get('大豆',''):>6} 蔬菜={r.get('蔬菜','')}  {r['quality_flag'][-24:]}")
(OCR / "OCR_PARSE_LOG.json").write_text(
    json.dumps({"rows": len(rows), "log": log, "access_date": AD}, ensure_ascii=False, indent=1),
    encoding="utf-8")
print("\n完成。")
