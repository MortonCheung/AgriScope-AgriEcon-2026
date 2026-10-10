#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从项目内既有《辽宁统计年鉴》XLS（data/raw/production/yearbook_2018/2019/2020）提取
分市 × 分作物 的播种面积 / 产量 / 单产，以及分市水利与灾损信息。
数据年为 yearbook_2018→2017, yearbook_2019→2018, yearbook_2020→2019。
只读既有原始文件，不新增下载，不覆盖任何数据。
"""
import csv, re, json
from pathlib import Path
from datetime import datetime
import warnings
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
YB = ROOT / "data/raw" / "production"
OUT = ROOT / "data/raw/retained_source/city_data" / "reference" / "decision_engine_supplement_v2"
RAWOUT = ROOT / "data/raw" / "decision_engine_supplement_v2"
OUT.mkdir(parents=True, exist_ok=True)
AD = datetime.now().strftime("%Y-%m-%d")

CITY_ALIAS = {
    "沈阳": "沈阳", "大连": "大连", "鞍山": "鞍山", "抚顺": "抚顺", "本溪": "本溪",
    "丹东": "丹东", "锦州": "锦州", "营口": "营口", "阜新": "阜新", "辽阳": "辽阳",
    "盘锦": "盘锦", "铁岭": "铁岭", "朝阳": "朝阳", "葫芦岛": "葫芦岛",
    "全 省": "全省", "辽宁": "全省",
}
TARGET = {"沈阳", "大连", "丹东", "锦州", "铁岭", "朝阳"}


def norm_city(s):
    t = re.sub(r"[\s\u3000]+", "", str(s))
    for k, v in CITY_ALIAS.items():
        if t.startswith(k):
            return v
    return ""


def read_xls(p):
    try:
        return pd.read_excel(p, header=None, engine="xlrd")
    except Exception:
        return None


def find_tables(yb_dir):
    """扫描该年鉴目录，返回 {表标题关键词: 文件路径} 以及标题文本。"""
    res = []
    for f in sorted(Path(yb_dir).glob("13-*.xls")):
        d = read_xls(f)
        if d is None or d.empty:
            continue
        head = " ".join(str(x) for x in d.iloc[0].tolist() if str(x) != "nan")
        head2 = " ".join(str(x) for x in d.iloc[:3].values.flatten().tolist()
                         if str(x) != "nan")[:120]
        res.append({"file": f, "title": head.strip(), "head": head2, "df": d})
    return res


def extract_area(df):
    """各地区农作物播种面积：表头两行，行=地区。"""
    # 找到首列为 '地区' 的表头行
    hdr_i = None
    for i in range(min(8, len(df))):
        c0 = re.sub(r"[\s\u3000]+", "", str(df.iloc[i, 0]))
        if c0 in ("地区", "地区名称"):
            hdr_i = i
            break
    if hdr_i is None:
        return []
    r1 = df.iloc[hdr_i].tolist()
    r2 = df.iloc[hdr_i + 1].tolist() if hdr_i + 1 < len(df) else []
    # 组装列名（父+子）
    cols = []
    parent = ""
    for j in range(len(r1)):
        p = str(r1[j]).strip() if j < len(r1) else ""
        c = str(r2[j]).strip() if j < len(r2) else ""
        if p and p != "nan":
            parent = p
        name = c if c and c != "nan" else p
        if parent and c and c != "nan" and parent != c:
            name = f"{parent}-{c}"
        cols.append(re.sub(r"[\s\u3000]+", "", name))
    rows = []
    for i in range(hdr_i + 1, len(df)):
        city = norm_city(df.iloc[i, 0])
        if not city:
            continue
        for j in range(1, len(df.columns)):
            v = df.iloc[i, j]
            if pd.isna(v):
                continue
            try:
                val = float(v)
            except (ValueError, TypeError):
                continue
            col = cols[j] if j < len(cols) else f"col{j}"
            if not col:
                continue
            rows.append({"city": city, "column": col, "value": val,
                         "unit": "千公顷", "table": "各地区农作物播种面积"})
    return rows


def extract_by_city_table(df, table_name, unit, value_cols=range(1, 25)):
    """通用：地区为行、指标为列的分市表。"""
    hdr_i = None
    for i in range(min(8, len(df))):
        row = "".join(str(x) for x in df.iloc[i].tolist())
        if "地" in row and "区" in row:
            hdr_i = i
            break
    if hdr_i is None:
        return []
    r1 = df.iloc[hdr_i].tolist()
    r2 = df.iloc[hdr_i + 1].tolist() if hdr_i + 1 < len(df) else []
    cols, parent = [], ""
    for j in range(len(r1)):
        p = str(r1[j]).strip() if j < len(r1) else ""
        c = str(r2[j]).strip() if j < len(r2) else ""
        if p and p != "nan":
            parent = p
        name = c if c and c != "nan" and c != p else p
        cols.append(re.sub(r"[\s\u3000]+", "", name))
    rows = []
    for i in range(hdr_i + 1, len(df)):
        city = norm_city(df.iloc[i, 0])
        if not city:
            continue
        for j in value_cols:
            if j >= len(df.columns):
                continue
            v = df.iloc[i, j]
            if pd.isna(v):
                continue
            try:
                val = float(v)
            except (ValueError, TypeError):
                continue
            col = cols[j] if j < len(cols) else f"col{j}"
            if not col:
                continue
            rows.append({"city": city, "column": col, "value": val,
                         "unit": unit, "table": table_name})
    return rows


def main():
    yd = {"2017": "yearbook_2018", "2018": "yearbook_2019", "2019": "yearbook_2020"}
    all_area, all_prod, all_yield, all_water = [], [], [], []

    for data_year, yb in yd.items():
        tabs = find_tables(YB / yb)
        print(f"== {yb} (数据年 {data_year}) 找到 {len(tabs)} 张 13-* 表")
        for t in tabs:
            title = t["title"]
            if "各地区农作物播种面积" in title:
                for r in extract_area(t["df"]):
                    r["year"] = data_year
                    r["source_file"] = t["file"].name
                    all_area.append(r)
                print("   面积表:", t["file"].name, title[:40])
            elif "各地区主要农产品产量" in title:
                for r in extract_by_city_table(t["df"], "各地区主要农产品产量", "吨"):
                    r["year"] = data_year
                    r["source_file"] = t["file"].name
                    all_prod.append(r)
                print("   产量表:", t["file"].name, title[:40])
            elif "各地区主要农产品单位面积产量" in title:
                for r in extract_by_city_table(t["df"], "各地区主要农产品单位面积产量", "公斤/公顷"):
                    r["year"] = data_year
                    r["source_file"] = t["file"].name
                    all_yield.append(r)
                print("   单产表:", t["file"].name, title[:40])
            elif "各地区水利设施" in title or "各地区农田水利" in title:
                for r in extract_by_city_table(t["df"], title[:30], "混合"):
                    r["year"] = data_year
                    r["source_file"] = t["file"].name
                    all_water.append(r)
                print("   水利表:", t["file"].name, title[:40])

    def write(fn, rows, extra=None):
        if not rows:
            print(f"[空] {fn} 无数据")
            return
        cols = ["year", "city", "column", "value", "unit", "table", "source_file"]
        with (OUT / fn).open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow(r)
        # 只保留六城
        six = [r for r in rows if r["city"] in TARGET]
        print(f"[OK] {fn}  全部 {len(rows)} 行 / 六城 {len(six)} 行")

    write("planting_area_crop_yearly.csv", all_area)
    write("production_crop_yearly.csv", all_prod)
    write("crop_yield_by_city.csv", all_yield)
    write("irrigation_yearly.csv", all_water)

    # 原始提取结果留档
    (RAWOUT / "production" / "YEARBOOK_EXTRACT_INDEX.json").write_text(
        json.dumps({"area_rows": len(all_area), "prod_rows": len(all_prod),
                    "yield_rows": len(all_yield), "water_rows": len(all_water),
                    "yearbooks": yd, "access_date": AD}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print("\n完成。")


if __name__ == "__main__":
    main()
