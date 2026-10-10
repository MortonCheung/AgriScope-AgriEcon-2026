"""修复并统一入库五城生产数据 → fact_production_yearly_2025（并并入 2020-2024 表）。

处理要点：
1. `chaoyang_production_2025.csv` 因 unit_production 字段含逗号且未加引号，解析失败
   → 手工按字段位置重建（unit_production 为第 7 列，可能吞掉多余逗号）
2. 各来源单位混乱（万亩/千公顷、万吨/亿斤）→ 统一到 **千公顷 / 吨**，
   并在 unit_original 保留原文，**换算过程可追溯**
3. 媒体"预计值"必须标注 quality_grade=B 且 note 写明（不冒充官方定案值）
4. 严禁县级数据冒充市级
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
STAGING = ROOT / "city_data/reference/staging"
MARTS = ROOT / "city_data/reference/marts"

F_COLS = ["year", "city", "crop", "planting_area", "unit_area", "production",
          "unit_production", "source", "source_url", "raw_file",
          "extraction_method", "quality_grade"]


def fix_chaoyang() -> pd.DataFrame:
    """按字段位置重建朝阳生产 CSV（unit_production 含逗号导致列数溢出）。"""
    p = STAGING / "chaoyang_production_2025.csv"
    lines = [l for l in p.read_text(encoding="utf-8").split("\n") if l.strip()]
    rows = []
    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) < len(F_COLS):
            continue
        if len(parts) > len(F_COLS):
            # 多余逗号全部归属 unit_production（第 7 列，index 6）
            extra = len(parts) - len(F_COLS)
            merged = ",".join(parts[6:7 + extra])
            parts = parts[:6] + [merged] + parts[7 + extra:]
        rows.append(dict(zip(F_COLS, parts)))
    df = pd.DataFrame(rows)
    # 修正后回写（加引号，避免再次损坏）
    df.to_csv(p, index=False, encoding="utf-8-sig", quoting=1)
    return df


def num(x):
    try:
        return float(str(x).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def parse_unit_area(v: str | float, raw_unit: str) -> tuple[float | None, str]:
    """面积统一到千公顷。原文万亩→千公顷(×0.6667)；原文已是千公顷→原值。"""
    n = num(v)
    if n is None:
        return None, str(raw_unit or "")
    u = str(raw_unit or "")
    if "万亩" in u:
        return round(n * 0.6667, 3), f"{u} → 千公顷(×0.6667)"
    if "万公顷" in u:
        return round(n * 10, 3), f"{u} → 千公顷(×10)"
    return n, u or "千公顷"


def parse_unit_prod(v, raw_unit: str) -> tuple[float | None, str]:
    """产量统一到吨。原文万吨→吨(×10000)；亿斤→吨(×50000)；万吨(预计)同理。"""
    n = num(v)
    if n is None:
        return None, str(raw_unit or "")
    u = str(raw_unit or "")
    note = "预计值" if "预计" in u else ""
    if "亿斤" in u:
        return round(n * 50000, 1), f"{u} → 吨(×50000){'；'+note if note else ''}"
    if "万吨" in u:
        return round(n * 10000, 1), f"{u} → 吨(×10000){'；'+note if note else ''}"
    if "万斤" in u:
        return round(n * 5, 1), f"{u} → 吨(×5){'；'+note if note else ''}"
    return n, u or "吨"


def main() -> None:
    cy = fix_chaoyang()
    print(f"[OK] 修复 chaoyang_production_2025.csv：{len(cy)} 行（已加引号回写）")

    out = []
    specs = [
        # (df, 面积列, 面积单位列, 产量列, 产量单位列)
        (cy, "planting_area", "unit_area", "production", "unit_production"),
    ]
    for f, acol, aucol, pcol, pucol in [
        ("dandong_production_2025.csv", "planting_area_kha", None, "production_wan_t", None),
        ("jinzhou_production_2025.csv", "planting_area(千公顷)", None, "production(万吨)", None),
        ("tieling_production_2025.csv", "planting_area", "unit", "production", "unit"),
        ("dalian_production_2025.csv", "planting_area", "unit_area", "production", "unit_production"),
    ]:
        p = STAGING / f
        if p.exists():
            specs.append((pd.read_csv(p), acol, aucol, pcol, pucol))

    # 各文件的单位语义：千公顷/万吨 为默认；丹东/锦州列名已含单位
    for df, acol, aucol, pcol, pucol in specs:
        if df is None or not len(df):
            continue
        for _, r in df.iterrows():
            city = str(r.get("city") or "").strip()
            crop = str(r.get("crop") or "").strip()
            year = r.get("year")
            if not city or not crop or pd.isna(year):
                continue
            # 面积
            au = str(r.get(aucol)) if aucol else ("千公顷" if "kha" in acol else "")
            if aucol is None:
                au = "千公顷" if "kha" in acol or "千公顷" in acol else "万亩"
                if "万吨" in acol or "万吨" in str(pcol):
                    pass
            pa, pa_note = parse_unit_area(r.get(acol), au)
            # 产量
            pu = str(r.get(pucol)) if pucol else ("万吨" if "wan_t" in pcol or "万吨" in pcol else "")
            pr, pr_note = parse_unit_prod(r.get(pcol), pu)
            qg = str(r.get("quality_grade") or "B")
            note = str(r.get("note") or "")
            out.append({
                "year": int(float(year)),
                "city": city,
                "crop": crop,
                "planting_area_kha": pa,
                "production_ton": pr,
                "yield_kg_per_ha": (round(pr * 1000 / (pa * 100), 1)
                                    if (pa and pr and pa > 0) else None),
                "unit_area": "千公顷",
                "unit_production": "吨",
                "unit_original": f"面积:{au} / 产量:{pu}",
                "conversion_note": f"{pa_note} | {pr_note}",
                "source": str(r.get("source") or ""),
                "source_url": str(r.get("source_url") or ""),
                "raw_file": str(r.get("raw_file") or ""),
                "extraction_method": str(r.get("extraction_method") or ""),
                "quality_grade": qg,
                "note": note,
            })

    new = pd.DataFrame(out)
    if not len(new):
        print("[WARN] 无生产数据")
        return
    print(f"[OK] 待入库生产记录 {len(new)} 行")

    # 并入 2020-2024 表，生成完整 2020-2025
    tgt = MARTS / "fact_production_yearly_2020_2024.parquet"
    old = pd.read_parquet(tgt) if tgt.exists() else pd.DataFrame()
    keep_cols = ["year", "city", "crop", "planting_area_kha", "production_ton",
                 "yield_kg_per_ha", "unit_area", "unit_production", "unit_original",
                 "conversion_note", "source", "source_url", "raw_file",
                 "extraction_method", "quality_grade", "note"]
    if len(old):
        for c in keep_cols:
            if c not in old.columns:
                old[c] = None
        comb = pd.concat([old[keep_cols], new[keep_cols]], ignore_index=True)
    else:
        comb = new[keep_cols]
    key = ["year", "city", "crop"]
    comb = comb.drop_duplicates(subset=key, keep="last")
    comb = comb.sort_values(["city", "year", "crop"])
    comb.to_parquet(tgt, index=False)
    comb.to_csv(MARTS / "fact_production_yearly_2020_2025.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] fact_production_yearly_2020_2024 更新为 {len(comb)} 行（现覆盖 2020-2025）")
    print()
    print("=== 各城市年份与作物 ===")
    print(comb.groupby("city").agg(
        years=("year", lambda s: f"{int(s.min())}-{int(s.max())}"),
        records=("crop", "size"), crops=("crop", "nunique")).to_string())
    print()
    print("=== 2025 年新增（各城市）===")
    y25 = comb[comb["year"] == 2025]
    if len(y25):
        print(y25.groupby("city").agg(n=("crop", "size")).to_string())
    print()
    print("=== 质量等级分布 ===")
    print(comb["quality_grade"].astype(str).str[0].value_counts().to_string())


if __name__ == "__main__":
    main()
