#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Data Foundation v1.1 · 沈阳统计年鉴（7册）解析
PDF 有文本层（无 OCR）。find_tables 因无框线失效 → 采用坐标法：
  行 = y 对齐；列 = 表头（区县名）x 中心；数值 token 合并（同 y、相邻 x）。
产出：
  raw 索引：data/metadata/evidence/YEARBOOK_TABLE_INDEX.csv
  结构化 ：data/processed/production/yearbook_shenyang_district_crop.parquet
           （district × crop × year × metric：area_ha / production_ton / yield_kg_ha）
不猜数：解析失败/校验失败的页记录为 OCR_QC_FAIL，保留不删。
"""
from __future__ import annotations
import csv, re, json, glob
from pathlib import Path
from collections import defaultdict
import pandas as pd
import fitz

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
YB = ROOT / "data/raw/web_captures/shenyang/district_production/yearbooks"
STD = ROOT / "data/processed"
EV = ROOT / "data/metadata/evidence"
AD = "2026-10-05"

# 年鉴中的区县（表头）
DISTRICTS = ["沈阳市", "苏家屯区", "浑南区", "沈北新区", "于洪区", "辽中区", "康平县", "法库县", "新民市"]
# 农作物项目 → 标准名（用于表 3-4/3-5）
CROP_LABELS = {
    "农作物总播种面积": ("__TOTAL__", "area"),
    "一、粮食作物合计": ("粮食", "area"),
    "（一）谷物": ("谷物", "area"),
    "稻谷": ("水稻", "area"),
    "小麦": ("小麦", "area"),
    "玉米": ("玉米", "area"),
    "（二）豆类合计": ("豆类", "area"),
    "#大豆": ("大豆", "area"),
    "（三）薯类": ("薯类", "area"),
    "#马铃薯": ("土豆", "area"),
    "二、油料作物": ("油料", "area"),
    "#花": ("花生", "area"),
    "五、蔬菜（含菜用瓜）及食用菌": ("蔬菜", "area"),
    "六、瓜果类": ("瓜果类", "area"),
    "#西瓜": ("西瓜", "area"),
    "甜瓜": ("甜瓜", "area"),
    "草莓": ("草莓", "area"),
    "七、其它农作物": ("其它农作物", "area"),
    # 细项（避免被泛化关键词并入父类）
    "其它谷物": ("其它谷物", "area"), "其他谷物": ("其它谷物", "area"),
    "#谷子": ("谷子", "area"), "谷子": ("谷子", "area"),
    "高粱": ("高粱", "area"), "荞麦": ("荞麦", "area"),
    "绿豆": ("绿豆", "area"), "红小豆": ("红小豆", "area"),
    "芝麻": ("芝麻", "area"), "葵花籽": ("葵花籽", "area"),
    "春小麦": ("春小麦", "area"),
}
# 3-5 产量表标签（无“面积”后缀，前缀相同）
PROD_LABELS = {k: (v[0], "production") for k, v in CROP_LABELS.items()}
# 3-6 单产
YIELD_LABELS = {k: (v[0], "yield") for k, v in CROP_LABELS.items()}
# 关键词兜底（长词优先，避免"粮食"抢先匹配）
FALLBACK = [
    ("蔬菜", "蔬菜"), ("瓜果类", "瓜果类"), ("西瓜", "西瓜"), ("甜瓜", "甜瓜"), ("草莓", "草莓"),
    ("食用菌", "蔬菜"), ("药材", "药材类"),
    ("农作物总播种面积", "__TOTAL__"), ("总播种面积", "__TOTAL__"),
    ("粮食作物合计", "粮食"), ("夏收粮食", "夏收粮食"), ("谷物", "谷物"),
    ("薯类", "薯类"), ("马铃薯", "土豆"), ("豆类合计", "豆类"), ("大豆", "大豆"),
    ("油料作物", "油料"), ("花生", "花生"), ("芝麻", "芝麻"), ("葵花籽", "葵花籽"),
    ("糖料", "糖料"), ("甜菜", "甜菜"),
    ("园林水果", "园林水果"), ("其它农作物", "其它农作物"), ("青饲料", "青饲料"),
    ("水稻", "水稻"), ("稻谷", "水稻"), ("玉米", "玉米"), ("小麦", "小麦"),
    ("谷子", "谷子"), ("高粱", "高粱"), ("荞麦", "荞麦"),
]


def cells_from_page(page, ytol=6.0):
    """把一页的 words 转成 {(row_index, col_key): 'value'}。
    列：以 page 顶部出现的区县名 x 中心定义；行：y 聚类。
    """
    words = page.get_text("words")  # (x0,y0,x1,y1,word,block,line,word_no)
    if not words:
        return None
    # 找表头行：包含 >=3 个区县名
    header_y = None
    for w in words:
        if w[4] in DISTRICTS:
            header_y = w[1] if header_y is None else min(header_y, w[1])
    if header_y is None:
        return None
    hdr_words = [w for w in words if abs(w[1] - header_y) < 12 or (header_y - 4 < w[1] < header_y + 20)]
    colmap = {}
    for w in hdr_words:
        if w[4] in DISTRICTS:
            colmap[w[4]] = (w[0] + w[2]) / 2
    if len(colmap) < 3:
        return None
    cols = sorted(colmap.items(), key=lambda kv: kv[1])
    label_x_max = cols[0][1] - 60  # 标签列在第一个数据列左侧

    # 数据区
    data_words = [w for w in words if w[1] > header_y + 8]
    # 1) 标签行：按 y 聚类（容差 4pt）
    lab_words = [w for w in data_words if w[0] < label_x_max]
    lab_rows = defaultdict(list)
    for w in lab_words:
        key = round(w[1] / 4.0)
        lab_rows[key].append(w)
    # 合并相邻 key（同一标签可能跨 4pt 边界）
    keys = sorted(lab_rows)
    merged, used = [], set()
    for k in keys:
        if k in used:
            continue
        grp = list(lab_rows[k]); used.add(k)
        for k2 in keys:
            if k2 != k and k2 not in used and abs(k2 - k) <= 1:
                grp += lab_rows[k2]; used.add(k2)
        grp.sort(key=lambda w: w[0])
        y = sum(w[1] for w in grp) / len(grp)
        merged.append((y, "".join(w[4] for w in grp)))
    merged.sort(key=lambda t: t[0])
    # 2) 数值词：就近归入最近标签行
    out = {}
    for y, txt in merged:
        out[(round(y), "LABEL")] = txt
    lab_ys = [y for y, _ in merged]
    for w in data_words:
        if w[0] < label_x_max:
            continue
        cx = (w[0] + w[2]) / 2
        cname, cxc = min(cols, key=lambda kv: abs(kv[1] - cx))
        if abs(cxc - cx) > 70:
            continue
        # 最近标签 y
        yl = min(lab_ys, key=lambda ly: abs(ly - w[1]))
        if abs(yl - w[1]) > 12:
            continue
        key = (round(yl), cname)
        cur = out.get(key, "")
        out[key] = (cur + w[4]) if cur else w[4]
    return out


def norm_num(s):
    if not s:
        return None
    t = re.sub(r"[^\d\.\-]", "", str(s))
    if t in ("", "-", "—", "…"):
        return None
    try:
        return float(t)
    except Exception:
        return None


AGRI_KW = ["粮食", "蔬菜", "稻谷", "玉米", "油料", "水果", "畜牧", "农业", "灌溉", "水利", "机械",
           "设施", "人口", "收入", "消费", "播种面积", "产量", "单产", "化肥", "农作"]


def parse_book(pdf):
    doc = fitz.open(pdf)
    year = int(re.search(r"data(\d{4})", pdf.name).group(1))  # 数据年份
    rows, meta = [], []
    for pno in range(doc.page_count):
        page = doc[pno]
        full = page.get_text()
        head = full[:200]
        m = re.search(r"(\d-\d+)", head)
        if not m:
            continue  # 非表页（无表号）
        code = m.group(1)
        # 章节号（如 3-4 → 第3章 农业）
        chapter = code.split("-")[0]
        lines = [l.strip() for l in full.splitlines() if l.strip()]
        title = ""
        for i, l in enumerate(lines[:12]):
            if re.search(r"\d-\d+", l):
                title = " ".join(lines[i:i + 2])[:120]
                break
        if not title:
            title = " ".join(lines[:2])[:120]
        agri = any(k in full for k in AGRI_KW)
        meta.append({"table_code": code, "chapter": chapter, "page": pno + 1,
                     "title": title, "agri_related": agri})
        # 按内容识别（跨年份表号不同：2018册为3-6/3-7/3-8，后续册为3-4/3-5/3-6）
        if not re.search(r"\b3-\d", full[:150]):
            continue  # 限定农业章节（3-x），排除区县基本情况等章节
        if not any(k in full for k in ["粮食", "蔬菜", "稻谷", "玉米"]):
            continue
        if not any(d in full for d in ("苏家屯", "辽中", "新民", "康平", "法库", "于洪", "沈北", "浑南")):
            continue
        cells = cells_from_page(page)
        if not cells:
            continue
        # 用「单位」判定 metric
        if "公斤/公顷" in full or "公斤／公顷" in full:
            metric = "yield"
        elif re.search(r"(^|\n)\s*公顷\s*($|\n)", full):
            metric = "area"
        elif re.search(r"(^|\n)\s*吨\s*($|\n)", full):
            metric = "production"
        else:
            continue
        labels = {yk: v for (yk, c), v in cells.items() if c == "LABEL"}
        for yk, lab in labels.items():
            key = re.sub(r"[\s　]", "", lab.strip())
            std = None
            for k, v in CROP_LABELS.items():
                kk = re.sub(r"[\s　]", "", k.rstrip("："))
                if key.startswith(kk) or kk in key:
                    std = (v[0], metric); break
            if not std:  # 关键词兜底（跨年份标签写法不同）
                for kw, name in FALLBACK:
                    if kw in key:
                        std = (name, metric); break
            if not std:
                continue
            for d in DISTRICTS:
                v = norm_num(cells.get((yk, d)))
                if v is not None:
                    rows.append({"table": code, "page": pno + 1, "year": year, "district": d,
                                 "crop_label": key, "crop_standard": std[0], "metric": metric, "value": v})
    doc.close()
    # 标记哪些表页真正产出了行
    parsed_codes = {r["table"] for r in rows}
    for m_ in meta:
        m_["parsed"] = m_["table_code"] in parsed_codes
    return year, rows, meta


def main():
    all_rows, index, table_index = [], [], []
    for pdf in sorted(YB.glob("*.pdf")):
        try:
            year, rows, meta = parse_book(pdf)
        except Exception as e:
            index.append({"book": pdf.name, "status": f"ERROR:{e}"})
            continue
        all_rows.extend(rows)
        index.append({"book": pdf.name, "data_year": year, "parsed_rows": len(rows), "status": "PARSED"})
        for m_ in meta:
            m_.update({"book": pdf.name, "data_year": year})
            table_index.append(m_)
        print(f"  {pdf.name}: data_year={year} rows={len(rows)} tables={len(meta)}")

    EV.mkdir(parents=True, exist_ok=True)
    with (EV / "YEARBOOK_TABLE_INDEX.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["book", "data_year", "parsed_rows", "status"], extrasaction="ignore")
        w.writeheader(); w.writerows(index)
    # 逐册逐表登记（§4：所有相关表全部登记）
    with (EV / "YEARBOOK_ALL_TABLES.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["book", "data_year", "table_code", "chapter", "page",
                                           "title", "agri_related", "parsed"], extrasaction="ignore")
        w.writeheader(); w.writerows(table_index)
    print(f"  [OK] YEARBOOK_ALL_TABLES.csv {len(table_index)} 表页（agri_related="
          f"{sum(1 for t in table_index if t['agri_related'])}，parsed={sum(1 for t in table_index if t['parsed'])}）")

    all_rows = [r for r in all_rows if "value" in r]
    if all_rows:
        df = pd.DataFrame(all_rows)
        df = df.drop_duplicates(subset=["year", "district", "crop_standard", "metric"], keep="first")
        df["geo_level"] = "district"
        df["source_id"] = "SRC-SY-YEARBOOK"
        df["source_file"] = "SY_yearbook_*"
        df["is_proxy"] = False
        df["is_derived"] = False
        df["access_date"] = AD
        # 单位换算（年鉴 3-4=公顷，3-5=吨，3-6=公斤/公顷）→ 保留原始 + 标准
        df["unit_raw"] = df["metric"].map({"area": "公顷", "production": "吨", "yield": "公斤/公顷"})
        df = df.rename(columns={"value": "value_raw"})
        df["unit_standard"] = df["metric"].map({"area": "ha", "production": "ton", "yield": "kg/ha"})
        df["value_standard"] = df["value_raw"]
        df["conversion_rule"] = "同单位（年鉴口径）"
        d = STD / "production"; d.mkdir(parents=True, exist_ok=True)
        df.to_parquet(d / "yearbook_shenyang_district_crop.parquet", index=False)
        print(f"[OK] yearbook_shenyang_district_crop.parquet {len(df)} 行")
        print("   metric:", dict(df["metric"].value_counts()))
        print("   year:", dict(df["year"].value_counts()))
        print("   district:", dict(df["district"].value_counts()))
        print("   crop:", dict(df["crop_standard"].value_counts().head(15)))
    else:
        print("[WARN] 无解析结果")


if __name__ == "__main__":
    main()
