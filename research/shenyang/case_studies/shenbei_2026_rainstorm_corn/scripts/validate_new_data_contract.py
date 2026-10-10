#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R17：新数据合同 Schema 校验器（PASS / WARNING / FAIL / NOT_FOUND）。
用法：
  python3 scripts/validate_new_data_contract.py                 # 校验默认清单（当前多数为 NOT_FOUND）
  python3 scripts/validate_new_data_contract.py --root <dir>    # 在指定根目录下查找
纪律：只读；不修改 Data Agent 目录；缺数据返回 NOT_FOUND 而非报错。

【2026-09-23 候选选择修复】原实现对每个 dataset 的多个 pattern 做全库 glob 后
直接取 `hits[0]`（字母序第一个），而 patterns 写得较宽（如 `*drainage*`、`*corn*`、
`*sar*`），于是 `02_raw/` 与 `01_sources/` 下的**原始 HTML/PDF/JSON** 会排在
`03_clean/`、`04_marts/` 的正式数据文件之前，被当成候选去校验 → 必然 FAIL，
真实交付状态被误报。修复两点（不改变契约语义，只改候选挑选）：
  1. **按 kind 过滤扩展名**：csv→.csv；vector→.gpkg/.shp/.geojson/.json(GeoJSON)；
     raster→.tif/.tiff/.vrt；
  2. **按数据层级排序**：03_clean > 04_marts > 02_raw > 06_models > 01_sources > 其他，
     同级内再按路径字母序，取第一个作为候选。
"""
import glob
import argparse
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# dataset -> 规则
CONTRACT = {
    "M2_drainage_network": dict(required=True, kind="vector",
                                patterns=["*drainage*", "* waterways*", "*gouqu*", "*沟渠*"],
                                crs_ok=["EPSG:4326", "EPSG:32651"], fields=["geometry", "type"]),
    "M2_pump_stations": dict(required=True, kind="vector",
                             patterns=["*pump*", "*泵站*"], crs_ok=["EPSG:4326", "EPSG:32651"],
                             fields=["geometry", "capacity", "control_area"]),
    "M2_DEM_bare": dict(required=False, kind="raster", patterns=["*dem*", "*DEM*"],
                        crs_ok=["EPSG:32651", "EPSG:4326"], fields=[]),
    "M2_corn_mask": dict(required=False, kind="raster", patterns=["*corn*", "*maize*"],
                         crs_ok=["EPSG:32651"], fields=[]),
    "M2_soil": dict(required=False, kind="raster",
                    patterns=["*soil*clay*", "*soilgrid*", "*soil_texture*"], crs_ok=[], fields=[]),
    "M2_multitemporal_SAR": dict(required=True, kind="raster",
                                 patterns=["*sar*", "*s1*", "*S1*"], crs_ok=[], fields=[]),
    "M2_ground_evidence": dict(required=False, kind="csv",
                               patterns=["*ground_evidence*", "*受灾*", "*灾损*"],
                               fields=["location", "date"]),
    "M3_literature": dict(required=False, kind="csv",
                          patterns=["*literature*", "*waterlog*experiment*", "*渍涝*"],
                          fields=["paper_id", "growth_stage", "waterlogging_duration"]),
    "M4_pump_params": dict(required=True, kind="csv",
                           patterns=["*pump*param*", "*排涝*台账*", "*drainage*capacity*"],
                           fields=["pump_capacity", "pump_count", "start", "end"]),
    "CropState_timeseries": dict(required=False, kind="csv",
                                 patterns=["*ndvi*", "*evi*", "*crop_state*"],
                                 fields=["date", "spatial_unit"]),
    "Market_timeseries": dict(required=False, kind="csv",
                              patterns=["*price*", "*market*", "*corn*price*"],
                              fields=["date", "price", "price_type"]),
}


KIND_EXT = {
    "csv": (".csv", ".tsv"),
    "vector": (".gpkg", ".shp", ".geojson", ".json"),
    "raster": (".tif", ".tiff", ".vrt"),
}
# 数据层级优先级（越小越优先）：正式清洗层 > 派生表 > 原始层 > 模型层 > 来源层
LAYER_RANK = (("03_clean", 0), ("04_marts", 1), ("02_raw", 2),
              ("06_models", 3), ("01_sources", 4), ("05_analysis", 5))


def _rank(path):
    rel = os.path.relpath(path, BASE)
    for key, r in LAYER_RANK:
        if rel.startswith(key + os.sep):
            return r
    return 9


def find(root, patterns, kind=None):
    """返回候选文件，已按 kind 扩展名过滤 + 按数据层级排序（最正式者在前）。"""
    hits = []
    for p in patterns:
        hits += glob.glob(os.path.join(root, "**", p), recursive=True)
    hits = [h for h in hits if "prebuild" not in h and os.path.isfile(h)]
    if kind and kind in KIND_EXT:
        exts = KIND_EXT[kind]
        hits = [h for h in hits if h.lower().endswith(exts)]
    # 去重后按 (层级, 路径) 排序
    return sorted(set(hits), key=lambda h: (_rank(h), h))


def check_csv(path, fields):
    import pandas as pd
    try:
        d = pd.read_csv(path, nrows=200)
    except Exception as e:
        return "FAIL", f"不可读: {e}"
    miss = [f for f in fields if f not in d.columns]
    if miss:
        return "WARNING", f"缺字段 {miss}"
    return "PASS", f"rows(≤200)={len(d)}, cols={len(d.columns)}"


def check_vector(path, fields, crs_ok):
    try:
        import geopandas as gpd
        g = gpd.read_file(path, rows=50)
    except Exception as e:
        return "FAIL", f"不可读: {e}"
    msgs = []
    status = "PASS"
    if crs_ok and (g.crs is None or str(g.crs).upper() not in [c.upper() for c in crs_ok]):
        status = "WARNING"; msgs.append(f"CRS={g.crs} 不在 {crs_ok}")
    miss = [f for f in fields if f not in g.columns and f != "geometry"]
    if miss:
        status = "WARNING"; msgs.append(f"缺字段 {miss}")
    if not g.geometry.is_valid.all():
        status = "WARNING"; msgs.append("存在非法几何")
    return status, "; ".join(msgs) or f"n(≤50)={len(g)}, crs={g.crs}"


def check_raster(path):
    try:
        import rasterio
        with rasterio.open(path) as s:
            return "PASS", f"{s.width}x{s.height}, crs={s.crs}, dtype={s.dtypes[0]}"
    except Exception as e:
        return "FAIL", f"不可读: {e}"


def check_any(path, rule):
    if rule["kind"] == "csv":
        return check_csv(path, rule["fields"])
    if rule["kind"] == "vector":
        return check_vector(path, rule["fields"], rule["crs_ok"])
    return check_raster(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=BASE, help="查找根目录")
    ap.add_argument("--max-candidates", type=int, default=8,
                    help="每个 dataset 最多评估的候选数（按层级排序后取前 N）")
    args = ap.parse_args()
    order = {"PASS": 0, "WARNING": 1, "FAIL": 2, "NOT_FOUND": 3}
    rows = []
    for name, rule in CONTRACT.items():
        hits = find(args.root, rule["patterns"], kind=rule["kind"])
        if not hits:
            rows.append(dict(dataset=name, required=rule["required"],
                             status=("FAIL" if rule["required"] else "NOT_FOUND"),
                             file="", detail=f"未找到（patterns={rule['patterns']}）"))
            continue
        # ★ 候选择优：在层级排序后的前 N 个候选里，选校验状态最好的那个。
        #   原实现直接取 hits[0]，一旦同 pattern 命中多个不同性质的产物
        #   （例如 market 目录下既有 by_type 汇总又有 weekly 明细），
        #   就可能挑到字段不全的那个而误报 WARNING。
        best = None
        for path in hits[:max(args.max_candidates, 1)]:
            st, det = check_any(path, rule)
            cand = (order.get(st, 9), path, st, det)
            if best is None or cand[0] < best[0]:
                best = cand
            if st == "PASS":
                break
        rows.append(dict(dataset=name, required=rule["required"], status=best[2],
                         file=os.path.relpath(best[1], args.root), detail=best[3],
                         n_candidates=len(hits)))
    import pandas as pd
    df = pd.DataFrame(rows)
    df.loc[(df.required) & (df.status == "NOT_FOUND"), "status"] = "FAIL"
    out = os.path.join(BASE, "logs", "PHASE_4R", "DATA_CONTRACT_CHECK.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    df.to_csv(out, index=False, encoding="utf-8-sig")
    cols = [c for c in ["dataset", "required", "status", "n_candidates", "file", "detail"] if c in df.columns]
    print(df[cols].to_string(index=False))
    print("\n汇总:", df.status.value_counts().to_dict())
    return 0


if __name__ == "__main__":
    sys.exit(main())
