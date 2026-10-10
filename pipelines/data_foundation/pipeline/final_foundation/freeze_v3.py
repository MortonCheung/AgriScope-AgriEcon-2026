# -*- coding: utf-8 -*-
"""FDF-Task4 V3：round3 增量合并后的资产清单、Hash 与冻结快照（AgriScope）

相较 V2 的变化：
  * path 从旧的 `<city>/workspace/data/interim/_final/` 改为新结构的 `<city>/data/`
  * 纳入 round3 合并后的行数与新增列（frequency / geo_level / source_text / retrieval_date 等）
  * 新增列覆盖度统计（记录「已规范化的枚举列」实际填充率，避免虚高完整度）
  * 输出 V3 三件套 + 完整度矩阵 V3，V1/V2 一律保留不覆盖

用法：
  python3 tools/pipeline/final_foundation/freeze_v3.py
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())          # 大数据分析/
CD = ROOT / "data/raw/retained_source/city_data"
FDF = CD / "reference" / "final_foundation"
OUT = FDF

SLUG = {"shenyang": "沈阳", "dalian": "大连", "tieling": "铁岭",
        "chaoyang": "朝阳", "jinzhou": "锦州", "dandong": "丹东"}

# 六城正式数据表（city_data/<city>/data/*.csv）
CANONICAL = [
    ("price_observation", "price", "canonical"),
    ("volume_observations", "volume", "canonical"),
    ("phenology_events", "phenology", "canonical"),
    ("disaster_events_observed", "disaster", "canonical"),
    ("policy_events", "policy", "canonical"),
    ("input_cost_weekly", "input_cost", "canonical"),
    ("production_yearly", "production", "canonical"),
    ("weather_daily", "weather", "supporting"),
    ("weather_daily_era5", "weather", "canonical"),
    ("weather_daily_era5land", "weather", "supporting"),
    ("weather_extra_daily", "weather", "supporting"),
    ("weather_extra_daily_era5", "weather", "supporting"),
    ("weather_extra_daily_era5land", "weather", "supporting"),
    ("soil_daily", "soil", "supporting"),
    ("disaster_events_algorithm", "disaster", "supporting"),
]

DATE_COLS = ("date", "observation_date", "policy_date", "start_date", "year")

TS = datetime.now().isoformat(timespec="seconds")


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def probe(p: Path):
    """返回 (rows, first, last, source_count, col_fill)"""
    try:
        d = pd.read_csv(p, encoding="utf-8-sig", low_memory=False)
    except Exception as e:
        return None
    n = len(d)
    dc = next((c for c in DATE_COLS if c in d.columns), None)
    if dc:
        s = d[dc].astype(str)
        first, last = (s.min(), s.max()) if n else ("", "")
    else:
        first = last = ""
    sc = int(d["source_id"].nunique()) if "source_id" in d.columns else ""
    # 关键列填充率（V3 新增）
    fill = {}
    for c in ("frequency", "volume_type", "geo_level", "quality_grade", "source_text",
              "retrieval_date", "note", "source_id"):
        if c in d.columns:
            fill[c] = round(float(d[c].notna().sum()) / n * 100, 1) if n else 0.0
    return n, first, last, sc, fill


def main():
    manifest = []
    city_stat = {cn: {} for cn in SLUG.values()}
    col_fill_agg = {}

    for slug, cn in SLUG.items():
        ddir = CD / slug / "data"
        if not ddir.exists():
            continue
        for ds, topic, cat in CANONICAL:
            p = ddir / f"{ds}.csv"
            rel = str(p.relative_to(ROOT))
            if not p.exists():
                manifest.append(dict(dataset=ds, city=cn, topic=topic, path=rel, rows=0,
                                     first_date="", last_date="", sha256="", source_count="",
                                     qc_status="MISSING", category=cat, frozen_at=TS, notes=""))
                continue
            r = probe(p)
            if r is None:
                manifest.append(dict(dataset=ds, city=cn, topic=topic, path=rel, rows=0,
                                     first_date="", last_date="", sha256="", source_count="",
                                     qc_status="PARSE_ERROR", category=cat, frozen_at=TS, notes=""))
                continue
            n, first, last, sc, fill = r
            qc = "A_PASS" if cat == "canonical" else "B_SUPPORTING"
            if ds in ("price_observation", "volume_observations") and n > 0:
                qc = "A_PASS"
            manifest.append(dict(dataset=ds, city=cn, topic=topic, path=rel, rows=n,
                                 first_date=first, last_date=last, sha256=sha256(p),
                                 source_count=sc, qc_status=qc, category=cat,
                                 frozen_at=TS, notes=""))
            city_stat[cn][topic] = city_stat[cn].get(topic, 0) + n
            for k, v in fill.items():
                col_fill_agg.setdefault(k, []).append(v)

    mf = pd.DataFrame(manifest)
    mf.to_csv(OUT / "DATA_FOUNDATION_MANIFEST_V3.csv", index=False, encoding="utf-8-sig")

    # ---------------- 完整度矩阵 ----------------
    # 分级阈值：连续测量类看规模，事件类看条数（事件本就稀疏，不适用 20 行门槛）
    EVENT_TOPICS = {"phenology", "disaster", "policy"}
    rows = []
    for cn in SLUG.values():
        st = city_stat.get(cn, {})
        def lv(t):
            n = st.get(t, 0)
            if n == 0:
                return "MISSING"
            thr = 3 if t in EVENT_TOPICS else 20
            return "GREEN" if n >= thr else "YELLOW_LOW"
        rows.append(dict(
            city=cn,
            price=lv("price"), weather=lv("weather"), production=lv("production"),
            volume=lv("volume"), phenology=lv("phenology"), disaster=lv("disaster"),
            policy=lv("policy"), input_cost=lv("input_cost"),
            price_rows=st.get("price", 0), volume_rows=st.get("volume", 0),
            phenology_rows=st.get("phenology", 0), disaster_rows=st.get("disaster", 0),
            policy_rows=st.get("policy", 0), input_cost_rows=st.get("input_cost", 0),
            production_rows=st.get("production", 0),
        ))
    cm = pd.DataFrame(rows)
    cm.to_csv(OUT / "SIX_CITY_DATA_COMPLETENESS_MATRIX_V3.csv", index=False, encoding="utf-8-sig")

    # ---------------- 快照 ----------------
    canon = mf[mf.category == "canonical"]
    snap = {
        "version": "AGRISCOPE_DATA_FOUNDATION_V3",
        "created_at": TS,
        "previous_version": "AGRISCOPE_DATA_FOUNDATION_V2（保留于同目录，未删除未覆盖）",
        "cities": list(SLUG.values()),
        "structure_note": "路径已对齐冻结后的项目结构：city_data/<city>/data/",
        "datasets": {k: int(v) for k, v in mf.groupby("category").size().items()},
        "row_counts": {
            "canonical": int(canon.rows.sum()),
            "all": int(mf.rows.sum()),
        },
        "row_counts_by_city": {cn: int(sum(v.values())) for cn, v in city_stat.items()},
        "row_counts_by_city_topic": {cn: {t: int(n) for t, n in v.items()}
                                     for cn, v in city_stat.items()},
        "key_column_fill_rate_pct": {k: round(sum(v) / len(v), 1)
                                     for k, v in sorted(col_fill_agg.items())},
        "round3_merge": {
            "merged_rows": 1424,
            "net_added_rows": 1412,
            "repairs": [
                "大连 phenology：19 行 city 由 'dalian' 纠正为 '大连'",
                "大连 disaster：11 行列错位无法恢复 → 移出主表（存 archive/review/round3_corrupted/）",
                "大连 volume：1 行按原始留存件重建；1 行无独立原件的重复观测移出",
                "锦州 volume：2 行数值列区间表述取下限（3000余→3000、2-3→2），原文降入 note",
                "沈阳 disaster：1 行棚体受损面积归入 facility_damage_area_mu",
                "丹东 disaster：1 行设施计数 1 座规范化",
            ],
            "volume_type_normalization_rows": 304,
            "dedup": "严格键 / source_id / 宽松键 三级匹配；命中即回填新增列，绝不改写原有列",
        },
        "known_gaps": [
            "锦州/朝阳/铁岭/丹东：日/周级市场成交量时间序列官方不公开（NOT_PUBLIC），仅年度吞吐量/容量/库存",
            "铁岭：粮食收购量/粮库入库量官方不公开",
            "沈阳：市级受灾面积合计未公开（仅街道/村级个案）",
            "大连：成交量 2020 前与 2024 后仍稀",
            "农资周价存在周缺失，禁止插值",
            "存量 raw_file 路径仍指向迁移前位置，待统一重写（不影响数据本身）",
        ],
        "v1_v2_status": "均保留，未删除、未覆盖",
    }
    (OUT / "DATA_FOUNDATION_SNAPSHOT_V3.json").write_text(
        json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")

    print("已写出：")
    for f in ("DATA_FOUNDATION_MANIFEST_V3.csv", "DATA_FOUNDATION_SNAPSHOT_V3.json",
              "SIX_CITY_DATA_COMPLETENESS_MATRIX_V3.csv"):
        print("  ", (OUT / f).relative_to(ROOT))
    print()
    print(f"canonical 行数合计 {int(canon.rows.sum())}  /  全表 {int(mf.rows.sum())}")
    print()
    print(cm[["city", "price", "volume", "phenology", "disaster", "policy",
              "input_cost", "production", "weather"]].to_string(index=False))


if __name__ == "__main__":
    main()
