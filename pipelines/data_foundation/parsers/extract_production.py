"""从辽宁统计年鉴「各地区」农业表抽取六城市生产数据（数据源 C）。

目标表（年鉴第 13 章「农业」）：
  13-16 各地区农作物播种面积
  13-18 各地区主要农产品产量
  13-20 各地区主要农产品单位面积产量

年鉴年份 → 数据年份：年鉴 N 年卷 = N-1 年数据（如 2020 年卷 = 2019 年数据）。
单位取自表头原文，不做任何换算或补全；缺失留空。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
import xlrd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "statistical_yearbooks"
CURATED = ROOT / "city_data/reference/curated"
MARTS = ROOT / "city_data/reference/marts"
for d in (CURATED, MARTS):
    d.mkdir(parents=True, exist_ok=True)

TARGET_CITIES = ["沈阳", "铁岭", "朝阳", "锦州", "丹东", "大连"]

# 年鉴卷 → 数据年份
YEARBOOK_YEAR = {"yearbook_2018": 2017, "yearbook_2019": 2018, "yearbook_2020": 2019,
                 "yearbook_2021": 2020, "yearbook_2022": 2021, "yearbook_2023": 2022,
                 "yearbook_2024": 2023, "yearbook_2025": 2024, "yearbook_2026": 2025}

# 表类型 → (文件名模式, 指标名, 单位)
TABLES = {
    "planting_area": ("13-16", "千公顷"),
    "production": ("13-18", "万吨"),
    "yield_per_area": ("13-20", "公斤/公顷"),
}


def norm(s: str) -> str:
    return re.sub(r"\s+", "", str(s or "")).replace("　", "")


def read_sheet(path: Path) -> list[list[str]]:
    book = xlrd.open_workbook(str(path))
    sh = book.sheet_by_index(0)
    return [[str(sh.cell_value(r, c)).strip() for c in range(sh.ncols)] for r in range(sh.nrows)]


def parse_table(path: Path) -> tuple[list[str], dict[str, dict[str, float]]]:
    """返回 (列作物名列表, {城市: {作物: 数值}})。"""
    rows = read_sheet(path)
    if len(rows) < 8:
        return [], {}

    # 表头：合并单元格，取 row2 与 row3 组合（row2 为大类，row3 为具体作物）
    hdr_main = [norm(x) for x in rows[2]]
    hdr_sub = [norm(x) for x in rows[3]] if len(rows) > 3 else [""] * len(hdr_main)

    crops: list[str] = []
    for i in range(len(hdr_main)):
        sub = hdr_sub[i] if i < len(hdr_sub) else ""
        main = hdr_main[i]
        name = sub if sub else main
        if i == 0:
            crops.append("__region__")
        else:
            crops.append(name)

    data: dict[str, dict[str, float]] = {}
    # 不同年份卷的表头行数不同（数据起始行可能是 6、7 或其它），
    # 因此不固定起始行，而是扫描全表找地区行。
    for r in rows:
        if not rows or r[0] is None:
            continue
        region = norm(r[0])
        if not region or region in ("地", "地区"):
            continue
        city = region.replace("　", "")
        city = re.sub(r"[市省]$", "", city) if city != "全省" else "全省"
        if city not in TARGET_CITIES and city != "全省":
            continue
        vals: dict[str, float] = {}
        for i in range(1, min(len(crops), len(r))):
            name = crops[i]
            if not name or name == "__region__":
                continue
            raw = norm(r[i])
            try:
                v = float(raw)
            except (TypeError, ValueError):
                continue
            vals[name] = v
        if vals:
            data[city] = vals
    return crops, data


TITLE_PAT = {
    "planting_area": re.compile(r"各地区.*播种面积"),
    "production": re.compile(r"各地区.*产量(?!.*单位面积)"),
    "yield_per_area": re.compile(r"各地区.*单位面积产量"),
}


def pick_by_title(yb_dir: Path, kind: str, cands: list[Path]) -> Path:
    """在候选文件中按表标题关键词挑选真正的「各地区」表。"""
    pat = TITLE_PAT[kind]
    for p in sorted(yb_dir.glob("13-*.xls")) + sorted(yb_dir.glob("13-*.xlsx")):
        try:
            rows = read_sheet(p)
        except Exception:
            continue
        if not rows:
            continue
        head = " ".join(norm(x) for x in rows[0][:1] + (rows[2][:1] if len(rows) > 2 else []))
        if pat.search(head):
            return p
    return cands[0]


def main() -> None:
    out_rows = []
    for yb_dir in sorted(RAW.glob("yearbook_*")):
        if not yb_dir.is_dir():
            continue
        year = YEARBOOK_YEAR.get(yb_dir.name)
        if year is None:
            print(f"[SKIP] 未知年份 {yb_dir.name}")
            continue
        for kind, (prefix, unit) in TABLES.items():
            # 年鉴编号在各卷之间会漂移（如「各地区单产」在 2020 卷是 13-20，在 2019 卷是 13-21），
            # 因此按「表标题关键词」匹配，而不是死记编号；编号只作为首选候选。
            pats = [prefix + "*.xls", prefix + "*.xlsx"]
            cands = []
            for p in pats:
                cands += sorted(yb_dir.glob(p))
            if not cands:
                continue
            path = pick_by_title(yb_dir, kind, cands)
            try:
                crops, data = parse_table(path)
            except Exception as exc:
                print(f"[FAIL] {path.name}: {exc}")
                continue
            for city, vals in data.items():
                if city == "全省":
                    continue
                for crop, v in vals.items():
                    out_rows.append({
                        "year": year, "city": city, "crop": crop,
                        "metric": kind, "value": v, "unit": unit,
                        "source_file": str(path.relative_to(ROOT)),
                        "source": "辽宁省统计局 辽宁统计年鉴",
                    })
            print(f"[OK] {yb_dir.name} {prefix} ({kind}) -> {len(data)} 地区, {len(crops)} 列")

    df = pd.DataFrame(out_rows)
    if df.empty:
        print("[WARN] 未抽取到任何生产数据")
        return

    # 透视：每个 (year, city, crop) 一行，三种指标各一列
    piv = df.pivot_table(index=["year", "city", "crop"], columns="metric",
                         values="value", aggfunc="first").reset_index()
    piv.columns.name = None
    for c in ("planting_area", "production", "yield_per_area"):
        if c not in piv.columns:
            piv[c] = None
    piv["unit_planting_area"] = "千公顷"
    piv["unit_production"] = "万吨"
    piv["unit_yield"] = "公斤/公顷"
    piv["source"] = "辽宁省统计局 辽宁统计年鉴"
    piv = piv[["year", "city", "crop", "planting_area", "production", "yield_per_area",
               "unit_planting_area", "unit_production", "unit_yield", "source"]]
    piv.to_parquet(MARTS / "fact_production_yearly.parquet", index=False)
    piv.to_csv(MARTS / "fact_production_yearly.csv", index=False, encoding="utf-8-sig")
    df.to_csv(CURATED / "production_long_raw.csv", index=False, encoding="utf-8-sig")
    print(f"\n[OK] fact_production_yearly {len(piv)} 行")
    print("   年份:", sorted(piv["year"].unique().tolist()))
    print("   城市:", sorted(piv["city"].unique().tolist()))
    print("   作物样本:", sorted(piv["crop"].dropna().unique().tolist())[:20])


if __name__ == "__main__":
    main()
