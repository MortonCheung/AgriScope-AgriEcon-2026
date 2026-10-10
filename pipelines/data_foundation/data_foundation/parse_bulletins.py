#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Data Foundation v1.1 · 沈阳区县公报解析
来源：data/raw/web_captures/shenyang/district_production/bulletins/
可用类型：PDF(文本层) / docx / xls（HTML 为 JS 空壳，登记不可用）
提取：粮食/蔬菜/设施农业/农林牧渔业总产值/肉类 等关键数字 + 原文片段。
产出：02_standardized/production/bulletin_shenyang_district.parquet
     07_evidence/bulletin_parse_index.csv
"""
from __future__ import annotations
import csv, re, glob, json
from pathlib import Path
import pandas as pd
import fitz

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
BUL = ROOT / "data/raw/web_captures/shenyang/district_production/bulletins"
STD = ROOT / "data/processed"
EV = ROOT / "data/metadata/evidence"
AD = "2026-10-05"

# metric 关键词 → (标准名, 期望单位类)
PATTERNS = [
    ("粮食产量", ["粮食产量", "粮食总产量", "粮食总产"]),
    ("蔬菜产量", ["蔬菜产量", "蔬菜及食用菌产量", "蔬菜总产量"]),
    ("粮食播种面积", ["粮食播种面积", "粮食作物播种面积", "粮食种植面积"]),
    ("蔬菜播种面积", ["蔬菜播种面积", "蔬菜种植面积", "蔬菜及食用菌播种面积"]),
    ("农林牧渔业总产值", ["农林牧渔业总产值", "农林牧渔总产值"]),
    ("设施农业面积", ["设施农业面积", "设施蔬菜面积", "设施农业"]),
    ("肉类总产量", ["肉类总产量", "肉产量"]),
    ("高标准农田", ["高标准农田"]),
    ("有效灌溉面积", ["有效灌溉面积", "耕地灌溉面积"]),
]
NUM = r"(\d[\d,\.]*)"
UNIT = r"(万吨|万头|万只|万亩|亿元|万元|吨|公顷|亩|公斤|元)"


def pdf_text(p):
    d = fitz.open(p); t = "".join(d[i].get_text() for i in range(d.page_count)); d.close()
    return t


def docx_text(p):
    import docx
    d = docx.Document(p)
    return "\n".join(x.text for x in d.paragraphs) + "\n" + "\n".join(
        " ".join(c.text for c in row.cells) for tb in d.tables for row in tb.rows)


def xls_text(p):
    try:
        xl = pd.ExcelFile(p)
        out = []
        for sh in xl.sheet_names:
            df = xl.parse(sh, dtype=str)
            out.append(df.to_csv(index=False))
        return "\n".join(out)
    except Exception:
        return ""


def extract(text, district, year, srcfile):
    rows = []
    t = re.sub(r"[ \u3000]+", "", text)
    for std, kws in PATTERNS:
        for kw in kws:
            for m in re.finditer(re.escape(kw) + r"[^。；\n]{0,40}?" + NUM + UNIT, t):
                val = float(m.group(1).replace(",", ""))
                unit = m.group(2)
                ctx = t[max(0, m.start() - 30):m.end() + 30]
                rows.append({"district": district, "year": year, "metric": std, "value_raw": val,
                             "unit_raw": unit, "source_file": srcfile, "source_text": ctx})
                break  # 每关键词取首个命中
    return rows


def main():
    rows, index = [], []
    for p in sorted(glob.glob(str(BUL / "*" / "*"))):
        p = Path(p)
        district = p.parent.name
        ext = p.suffix.lower()
        ym = re.search(r"(\d{4})", p.name)
        year = int(ym.group(1)) if ym else None
        try:
            if ext == ".pdf":
                text = pdf_text(p)
            elif ext == ".docx":
                text = docx_text(p)
            elif ext in (".xls", ".xlsx"):
                text = xls_text(p)
            elif ext == ".doc":
                try:
                    text = p.read_bytes().decode("utf-8", errors="ignore")
                except Exception:
                    text = ""
            elif ext == ".html":
                index.append({"file": str(p.relative_to(ROOT)), "district": district, "year": year,
                              "type": "html", "status": "JS_RENDERED_UNUSABLE", "rows": 0})
                continue
            else:
                continue
        except Exception as e:
            index.append({"file": str(p.relative_to(ROOT)), "district": district, "year": year,
                          "type": ext, "status": f"ERROR:{type(e).__name__}", "rows": 0})
            continue
        got = extract(text, district, year, p.name)
        rows += got
        index.append({"file": str(p.relative_to(ROOT)), "district": district, "year": year,
                      "type": ext.lstrip("."), "status": "PARSED" if got else "NO_MATCH",
                      "text_len": len(text), "rows": len(got)})

    EV.mkdir(parents=True, exist_ok=True)
    with (EV / "bulletin_parse_index.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["file", "district", "year", "type", "status", "text_len", "rows"], extrasaction="ignore")
        w.writeheader(); w.writerows(index)

    if rows:
        df = pd.DataFrame(rows)
        df["city"] = "沈阳"
        df["geo_level"] = "district"
        df["source_id"] = "SRC-SY-DISTRICT-BULLETIN"
        df["is_proxy"] = False
        df["is_derived"] = False
        df["frequency"] = "yearly"
        df["access_date"] = AD
        # 单位标准化（仅数学可验证）
        fac = {"万吨": ("吨", 10000.0), "吨": ("吨", 1.0), "万亩": ("亩", 10000.0),
               "亿元": ("万元", 10000.0), "万元": ("万元", 1.0), "公顷": ("公顷", 1.0), "亩": ("亩", 1.0)}
        df["unit_standard"] = df["unit_raw"].map(lambda u: fac.get(u, (u, 1.0))[0])
        df["value_standard"] = df.apply(lambda r: r["value_raw"] * fac.get(r["unit_raw"], ("", 1.0))[1], axis=1)
        df["conversion_rule"] = df["unit_raw"].map(lambda u: f"{u}->{fac[u][0]} x{fac[u][1]}" if u in fac else "未换算")
        d = STD / "production"; d.mkdir(parents=True, exist_ok=True)
        df.to_parquet(d / "bulletin_shenyang_district.parquet", index=False)
        print(f"[OK] bulletin_shenyang_district.parquet {len(df)} 行")
        print("   metric:", dict(df["metric"].value_counts()))
        print("   district:", dict(df["district"].value_counts()))
    else:
        print("[WARN] 无提取结果")

    from collections import Counter
    print("=== 文件解析状态 ===")
    for k, v in Counter(x["status"] for x in index).most_common():
        print(f"   {k}: {v}")


if __name__ == "__main__":
    main()
