"""通用：从城市统计公报（HTML 文字版）解析农业生产数据。

输入目录：data/raw/production/{city}_bulletin/*.html
输出：city_data/reference/staging/{city}_production_bulletin.csv（year, city, crop, planting_area, production, unit...）

只提取原文明确给出的数字，绝不推算。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
STAGING = ROOT / "city_data/reference/staging"
STAGING.mkdir(parents=True, exist_ok=True)


def extract_text(html: str) -> str:
    html = re.sub(r"<script.*?</script>", "", html, flags=re.S | re.I)
    html = re.sub(r"<style.*?</style>", "", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", html)
    text = text.replace("&nbsp;", " ").replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text


def parse_production(text: str, city: str, year: str) -> list[dict]:
    """解析 农业 段落中的面积/产量数字。"""
    rows = []

    def add(crop, area, area_unit, prod, prod_unit, note=""):
        rows.append({"year": year, "city": city, "crop": crop,
                     "planting_area": area, "unit_area": area_unit,
                     "production": prod, "unit_production": prod_unit,
                     "note": note})

    # 总播种面积
    m = re.search(r"粮食(?:作物)?播种面积\s*([\d.]+)\s*(千公顷|万亩|公顷)", text)
    if m:
        add("grain_total", m.group(1), m.group(2), None, None)
    # 分作物播种面积：水稻播种面积X千公顷；玉米播种面积X千公顷
    for crop in ["水稻", "玉米", "大豆", "花生", "小麦", "马铃薯", "高粱", "谷子"]:
        m = re.search(rf"{crop}播种面积\s*([\d.]+)\s*(千公顷|万亩|公顷)", text)
        if m:
            add(f"{crop}_area_only", m.group(1), m.group(2), None, None)
    # 粮食总产量
    m = re.search(r"粮食总产量\s*([\d.]+)\s*(万吨|亿斤|吨)", text)
    if m:
        add("grain_total", None, None, m.group(1), m.group(2))
    # 分作物产量：水稻产量X万吨；玉米产量X万吨
    for crop in ["水稻", "玉米", "大豆", "花生", "小麦", "马铃薯", "高粱"]:
        m = re.search(rf"{crop}产量\s*([\d.]+)\s*(万吨|亿斤|吨)", text)
        if m:
            add(crop, None, None, m.group(1), m.group(2))
    # 经济作物/蔬菜/油料
    m = re.search(r"蔬菜(?:及食用菌)?播种面积\s*([\d.]+)\s*(千公顷|万亩|公顷)", text)
    if m:
        add("vegetable", m.group(1), m.group(2), None, None)
    m = re.search(r"蔬菜(?:及食用菌)?产量\s*([\d.]+)\s*(万吨|亿斤|吨)", text)
    if m:
        add("vegetable", None, None, m.group(1), m.group(2))
    m = re.search(r"油料作物播种面积\s*([\d.]+)\s*(千公顷|万亩|公顷)", text)
    if m:
        add("oilseed_total", m.group(1), m.group(2), None, None)
    m = re.search(r"油料产量\s*([\d.]+)\s*(万吨|亿斤|吨)", text)
    if m:
        add("oilseed_total", None, None, m.group(1), m.group(2))
    return rows


def main(city: str) -> None:
    d = ROOT / "data/raw" / "production" / f"{city}_bulletin"
    if not d.exists():
        print(f"[ERR] 目录不存在: {d}")
        sys.exit(1)
    all_rows = []
    for f in sorted(d.glob("*.html")):
        m = re.match(r"(20\d{2})", f.name)
        if not m:
            continue
        year = m.group(1)
        text = extract_text(f.read_text(encoding="utf-8", errors="ignore"))
        rows = parse_production(text, city, year)
        all_rows.extend(rows)
        print(f"  {f.name}: {len(rows)} 行")
    if all_rows:
        df = pd.DataFrame(all_rows)
        out = STAGING / f"{city}_production_bulletin.csv"
        df.to_csv(out, index=False, encoding="utf-8-sig")
        print(f"[OK] {len(all_rows)} 行 → {out}")
        print(df.to_string(index=False))


if __name__ == "__main__":
    main(sys.argv[1])
