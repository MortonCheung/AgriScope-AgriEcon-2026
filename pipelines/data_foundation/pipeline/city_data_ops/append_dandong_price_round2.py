"""丹东价格第二轮：把合格 staging 追加进 interim/price_observation.csv（30 列 schema）。

原则：只追加真实观测；按「业务主键」去重，避免与既有行重复；不改既有行；不插值、不编造。

用法：
    python3 append_dandong_price_round2.py --dry-run
    python3 append_dandong_price_round2.py
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

BASE = Path(next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())) / "city_data/dandong/data"
INTERIM = BASE / "price_observation.csv"
STAGING = BASE / ".." / "sources" / "staged" / "price"

FIELDS = ["city", "county", "market_name", "store_name", "platform", "crop_raw", "crop_standard",
          "sku_name", "specification", "package_size", "price_original", "unit_original",
          "price_per_kg", "price_level", "observation_date", "observation_time", "frequency",
          "source_type", "source_name", "source_url", "source_id", "retrieval_time",
          "promotion_flag", "member_price_flag", "derived_flag", "quality_grade", "raw_file",
          "geo_level", "record_kind", "note"]

# 每个来源的业务主键（用于与既有行/已加行去重）
KEY_CAP = ("source_id", "county", "observation_date", "crop_raw", "specification",
           "market_name", "price_original", "unit_original", "price_level")
KEY_GRAIN = ("source_id", "county", "observation_date", "crop_raw", "record_kind")

STAGING_FILES = [
    (STAGING / "cnhnb" / "dandong_price_cnhnb_county.csv", KEY_CAP),
    (STAGING / "lnnync_grain" / "dandong_grain_county.csv", KEY_GRAIN),
]


def key_of(row: dict, cols) -> tuple:
    return tuple((row.get(c) or "").strip() for c in cols)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    existing = list(csv.DictReader(INTERIM.open(encoding="utf-8-sig")))
    assert len(existing[0]) == 30, f"既有表列数异常: {len(existing[0])}"
    seen = {key_of(r, KEY_CAP) for r in existing} | {key_of(r, KEY_GRAIN) for r in existing}

    added, report = [], []
    for path, cols in STAGING_FILES:
        if not path.exists():
            print(f"[skip] 未找到 {path}")
            continue
        rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
        n = 0
        for r in rows:
            k = key_of(r, cols)
            if k in seen:
                continue
            seen.add(k)
            added.append({f: r.get(f, "") for f in FIELDS})
            n += 1
        dates = sorted({r["observation_date"] for r in rows if r["observation_date"]})
        report.append((path.name, len(rows), n, dates[0] if dates else "-", dates[-1] if dates else "-"))

    print("=== staging 汇总 ===")
    for name, total, n, d0, d1 in report:
        print(f"  {name:34s} 解析={total:4d}  新增={n:4d}  {d0}..{d1}")
    print(f"既有 {len(existing)} 行 -> 追加 {len(added)} 行 -> 合计 {len(existing) + len(added)} 行")

    if args.dry_run:
        print("[dry-run] 未写盘")
        return
    with INTERIM.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(existing)
        w.writerows(added)
    print(f"[OK] 已写入 {INTERIM}")


if __name__ == "__main__":
    main()
