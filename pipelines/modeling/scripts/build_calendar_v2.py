# -*- coding: utf-8 -*-
"""
Phase 1 入口：构建 v2 农事约束层。

  python3 decision_engine/scripts/build_calendar_v2.py

输出：
  decision_engine/data/features/crop_calendar_v2.parquet
  decision_engine/evaluation/recommendation/calendar_coverage.csv
  decision_engine/evaluation/recommendation/calendar_window_examples.csv
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from decision_engine.common import de_path, ensure_dir  # noqa: E402
from decision_engine.recommendation import calendar as cal  # noqa: E402

SHENYANG_CROPS = ["土豆", "西红柿", "黄瓜", "韭菜", "青椒", "尖椒", "茄子", "芹菜", "芸豆", "甘蓝"]


def _regional_crops(city: str) -> list:
    p = de_path("data", "features", f"regional_{city}.parquet")
    if not p.exists():
        return []
    d = pd.read_parquet(p, columns=["crop"])
    return sorted(d["crop"].dropna().unique().tolist())


def main():
    out_dir = ensure_dir(de_path("evaluation", "recommendation"))
    fdir = ensure_dir(de_path("data", "features"))

    scopes = {"沈阳": SHENYANG_CROPS,
              "朝阳": _regional_crops("朝阳")[:30],
              "锦州": _regional_crops("锦州")[:30]}
    frames = []
    for city, crops in scopes.items():
        if not crops:
            print(f"[calendar] {city}: 无可用作物（跳过）")
            continue
        t = cal.build_crop_calendar(city, crops)
        t["n_crops_in_city"] = len(crops)
        frames.append(t)
        print(f"[calendar] {city}: crops={len(crops)} level={t['calendar_level'].value_counts().to_dict()}")

    tbl = pd.concat(frames, ignore_index=True)
    tbl.to_parquet(fdir / "crop_calendar_v2.parquet", index=False)

    cov = (tbl.groupby(["city", "calendar_level", "constraint_strength"])
           .agg(crops=("crop", "count")).reset_index())
    cov.to_csv(out_dir / "calendar_coverage.csv", index=False, encoding="utf-8-sig")
    print("\n[calendar coverage]\n", cov.to_string(index=False))

    # 窗口示例（沈阳 10 作物：春季/秋季各取一次）
    rows = []
    for city in ["沈阳", "朝阳"]:
        crops = scopes[city][:10]
        for crop in crops:
            for label, (a, b) in {"spring": ("2027-03-01", "2027-07-31"),
                                  "autumn": ("2027-07-01", "2027-10-31")}.items():
                ws = cal.feasible_harvest_windows(city, crop, pd.Timestamp(a), pd.Timestamp(b))
                if not ws:
                    continue
                ok = sum(1 for w in ws if w["feasible"])
                rows.append({"city": city, "crop": crop, "period": label,
                             "n_windows": len(ws), "n_feasible": ok,
                             "planting_date_source": ws[0]["planting_date_source"],
                             "constraint_strength": ws[0]["constraint_strength"],
                             "example_window": f"{ws[0]['window_start'].date()}~{ws[0]['window_end'].date()}"})
    ex = pd.DataFrame(rows)
    ex.to_csv(out_dir / "calendar_window_examples.csv", index=False, encoding="utf-8-sig")
    print(f"\n[calendar] window examples: {len(ex)} 行")
    print(f"[calendar] done -> crop_calendar_v2.parquet ({len(tbl)} 行)")


if __name__ == "__main__":
    main()