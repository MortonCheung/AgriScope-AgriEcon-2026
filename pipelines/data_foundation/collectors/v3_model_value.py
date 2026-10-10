#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成数据集级模型价值分类表 model_value_classification.csv。"""
import csv, glob
from pathlib import Path
from collections import Counter

REF = Path(next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())) / "city_data/reference/decision_engine_supplement_v3"

# 文件级默认分类（对无逐行 model_value 的文件）
FILE_LEVEL = {
    "price_lnnync_veg_weekly_historical.csv": ("MODEL_FEATURE", "辽宁10蔬菜周度批发价历史延长(2019-2022)，直接进入价格模型与历史分位"),
    "remote_sensing_ndvi_city_monthly.csv": ("MODEL_FEATURE", "城市×月 NDVI，气候暴露/植被状态特征"),
    "remote_sensing_ndvi_derived.csv": ("RISK_FEATURE", "NDVI 同月基线异常度(z)，气候风险解释"),
    "remote_sensing_ndvi_growing_season.csv": ("RISK_FEATURE", "生长季 NDVI 汇总"),
    "remote_sensing_evi_city_monthly.csv": ("MODEL_FEATURE", "城市×月 EVI（同传感器补算）"),
    "agri_insurance_claims_v3.csv": ("RISK_FEATURE", "分城市/作物农险承保与赔付，风险基线"),
    "irrigation_yearly_extended.csv": ("RISK_FEATURE", "高标准农田/灌溉韧性 2020-2025"),
    "market_registry_v3.csv": ("REFERENCE", "市场节点登记(含坐标)"),
    "market_accessibility.csv": ("RISK_FEATURE", "市场道路可达性(OSRM派生)"),
    "source_registry.csv": ("REFERENCE", "来源登记"),
    "qc_summary_v3.json": ("REFERENCE", "QC 结果"),
    "model_value_classification.csv": ("REFERENCE", "本表"),
}


def main():
    out = []
    for f in sorted(REF.iterdir()):
        if f.suffix.lower() not in (".csv", ".json", ".md"):
            continue
        if f.name in ("source_registry.csv",):
            continue
        if f.suffix == ".csv":
            with f.open(encoding="utf-8-sig") as fh:
                rows = list(csv.DictReader(fh))
            nrow = len(rows)
            c = Counter((r.get("model_value") or "").strip() for r in rows if (r.get("model_value") or "").strip())
        else:
            nrow = ""
            c = {}
        if c:
            for mv, cnt in c.most_common():
                note = FILE_LEVEL.get(f.name, ("", ""))[1]
                out.append({"file": f.name, "rows": nrow, "model_value": mv, "row_count": cnt, "note": note})
        else:
            mv, note = FILE_LEVEL.get(f.name, ("REFERENCE", ""))
            out.append({"file": f.name, "rows": nrow, "model_value": mv, "row_count": nrow, "note": note})
    with (REF / "model_value_classification.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["file", "rows", "model_value", "row_count", "note"])
        w.writeheader(); w.writerows(out)
    print(f"[OK] model_value_classification.csv {len(out)} 行")


if __name__ == "__main__":
    main()
