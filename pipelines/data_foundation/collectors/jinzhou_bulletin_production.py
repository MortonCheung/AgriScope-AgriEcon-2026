"""从已落盘的锦州统计公报 HTML 提取农业指标 → city_data/reference/staging/jinzhou_production_2025.csv。

来源（均已落盘 data/raw/production/锦州_bulletin/）：
  2025公报 https://www.jz.gov.cn/info/1069/126762.htm
  2024公报 https://www.jz.gov.cn/info/1069/122603.htm

只做确定性提取：原文明确写出的数字才入库；公报未单列的作物（大豆/花生）不推算。
"""
from __future__ import annotations

import csv
import re
import html
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "production" / "锦州_bulletin"
OUT = ROOT / "city_data/reference/staging" / "jinzhou_production_2025.csv"

BULLETINS = [
    ("2025", "2025_公报_6d34fd37445e.html", "https://www.jz.gov.cn/info/1069/126762.htm"),
    ("2024", "2024_公报_c4df9e54aaba.html", "https://www.jz.gov.cn/info/1069/122603.htm"),
]


def text_of(path: Path) -> str:
    h = path.read_text(encoding="utf-8", errors="ignore")
    h = re.sub(r"<script.*?</script>", "", h, flags=re.S | re.I)
    h = re.sub(r"<style.*?</style>", "", h, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", "", h)
    t = html.unescape(t)
    return re.sub(r"\s+", "", t)  # 去掉空白便于匹配


# 面积：XX播种面积NNN.N千公顷（粮食作物/水稻/玉米/其他谷物/经济作物/油料作物/蔬菜及食用菌）
AREA_PAT = re.compile(
    r"((?:粮食作物|水稻|玉米|其他谷物|经济作物|油料作物|蔬菜及食用菌))播种面积([\d.]+)千公顷")
# 果园面积
ORCHARD_PAT = re.compile(r"果园面积([\d.]+)千公顷")
# 产量：全年XX产量NNN.N万吨（粮食/水稻/玉米/其他谷物/油料/蔬菜及食用菌/水果）
PROD_PAT = re.compile(
    r"((?:粮食|水稻|玉米|其他谷物|油料|蔬菜及食用菌|水果))产量([\d.]+)万吨")
# 油料产量表述为「全年油料产量25.1万吨」
OIL_PROD_PAT = re.compile(r"油料产量([\d.]+)万吨")

rows = []
for year, fn, url in BULLETINS:
    txt = text_of(RAW / fn)
    for crop, val in AREA_PAT.findall(txt):
        rows.append([year, "锦州", crop, float(val), "", "千公顷", "锦州市国民经济和社会发展统计公报", url,
                     f"regex: {crop}播种面积([\\d.]+)千公顷", "A"])
    m = ORCHARD_PAT.search(txt)
    if m:
        rows.append([year, "锦州", "果园", float(m.group(1)), "", "千公顷",
                     "锦州市国民经济和社会发展统计公报", url,
                     "regex: 果园面积([\\d.]+)千公顷", "A"])
    for crop, val in PROD_PAT.findall(txt):
        rows.append([year, "锦州", crop, "", float(val), "万吨",
                     "锦州市国民经济和社会发展统计公报", url,
                     f"regex: 全年{crop}产量([\\d.]+)万吨", "A"])

with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["year", "city", "crop", "planting_area(千公顷)", "production(万吨)",
                "unit", "source", "source_url", "extraction_method", "quality_grade"])
    for r in rows:
        w.writerow(r)
print(f"[OK] {OUT} 共 {len(rows)} 行")
for r in rows:
    print(" ", " | ".join(str(x) for x in r))
