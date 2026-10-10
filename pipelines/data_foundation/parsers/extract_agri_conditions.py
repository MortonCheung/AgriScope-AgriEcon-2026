"""从辽宁统计年鉴提取「各地区」农业生产条件数据（手册第 11 节）。

覆盖：化肥施用量、农田水利/有效灌溉、除涝治碱、农业机械、造林、牲畜饲养等。
方法：按**表标题**（而非编号，编号各卷漂移）定位所有「各地区」表，
逐表提取 城市 × 指标 → 长表，保留原始单位原文。

只读取官方年鉴原文件，不做换算、不补值。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
import xlrd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "production"
CURATED = ROOT / "city_data/reference/curated"
MARTS = ROOT / "city_data/reference/marts"
for d in (CURATED, MARTS):
    d.mkdir(parents=True, exist_ok=True)

TARGET_CITIES = ["沈阳", "铁岭", "朝阳", "锦州", "丹东", "大连"]
YEARBOOK_YEAR = {"yearbook_2018": 2017, "yearbook_2019": 2018, "yearbook_2020": 2019,
                 "yearbook_2021": 2020, "yearbook_2022": 2021, "yearbook_2023": 2022,
                 "yearbook_2024": 2023, "yearbook_2025": 2024, "yearbook_2026": 2025}

# 与农业生产条件相关的表标题关键词
CONDITION_PAT = re.compile(
    r"各地区.*(化肥|水利|灌溉|除涝|治碱|机械|造林|牲畜|农业生产条件|农村|电力)")


def norm(s) -> str:
    return re.sub(r"\s+", "", str(s or "")).replace("　", "")


def read_sheet(path: Path) -> list[list[str]]:
    sh = xlrd.open_workbook(str(path)).sheet_by_index(0)
    return [[str(sh.cell_value(r, c)).strip() for c in range(sh.ncols)] for r in range(sh.nrows)]


def build_header(rows: list[list[str]]) -> tuple[list[str], str]:
    """把多行合并表头拼成列名；返回 (列名, 单位候选)。"""
    if not rows:
        return [], ""
    # 表头通常在前 5 行
    head_rows = rows[:5]
    ncol = max(len(r) for r in head_rows)
    cols = []
    for c in range(ncol):
        parts = []
        for r in head_rows:
            v = norm(r[c]) if c < len(r) else ""
            if v and v not in parts and not re.fullmatch(r"\d+(\.\d+)?", v):
                parts.append(v)
        cols.append("/".join(parts) if parts else f"col{c}")
    unit = ""
    m = re.search(r"[（(]([^）)]*单位[^）)]*|[^）)]*公顷[^）)]*|[^）)]*吨[^）)]*)[）)]",
                  " ".join(norm(x) for x in rows[0][:3]))
    if m:
        unit = m.group(1)
    return cols, unit


def main() -> None:
    out_rows = []
    table_index = []

    for yb_dir in sorted(RAW.glob("yearbook_*")):
        if not yb_dir.is_dir():
            continue
        year = YEARBOOK_YEAR.get(yb_dir.name)
        if year is None:
            continue
        for path in sorted(list(yb_dir.glob("13-*.xls")) + list(yb_dir.glob("13-*.xlsx"))):
            try:
                rows = read_sheet(path)
            except Exception:
                continue
            if not rows:
                continue
            title = norm(rows[0][0]) if rows[0] else ""
            if not CONDITION_PAT.search(title):
                continue
            cols, unit = build_header(rows)
            table_index.append({"year": year, "file": path.name, "title": title,
                                "unit_raw": unit, "ncols": len(cols)})
            # 数据行：首列是地区名
            for r in rows:
                if not r:
                    continue
                region = norm(r[0])
                city = re.sub(r"[市省]$", "", region)
                if city not in TARGET_CITIES:
                    continue
                for i in range(1, min(len(cols), len(r))):
                    raw = norm(r[i])
                    try:
                        v = float(raw)
                    except (TypeError, ValueError):
                        continue
                    out_rows.append({
                        "year": year, "city": city,
                        "table_title": title, "indicator": cols[i],
                        "value": v, "unit_raw": unit,
                        "source_file": str(path.relative_to(ROOT)),
                        "source": "辽宁省统计局 辽宁统计年鉴",
                    })
            print(f"[OK] {year} {path.name} {title[:40]}")

    (CURATED / "yearbook_condition_tables.json").write_text(
        json.dumps(table_index, ensure_ascii=False, indent=1), encoding="utf-8")

    df = pd.DataFrame(out_rows)
    if df.empty:
        print("[WARN] 未提取到生产条件数据")
        return
    df.to_parquet(MARTS / "fact_agri_conditions.parquet", index=False)
    df.to_csv(MARTS / "fact_agri_conditions.csv", index=False, encoding="utf-8-sig")
    print(f"\n[OK] fact_agri_conditions {len(df)} 行")
    print("   年份:", sorted(df['year'].unique().tolist()))
    print("   指标数:", df["indicator"].nunique())
    print("   表:", df["table_title"].nunique())


if __name__ == "__main__":
    main()
