# -*- coding: utf-8 -*-
"""影子合并审计：对比 city_data/ 与影子目录，验证合并只做「加法」且无重复（AgriScope）

检查项：
  A. 行数变化——是否与预期一致（只增；大连 disaster/volume 为已知减项）
  B. 列结构——新列是否只在末尾追加，原有列顺序与名称是否零改动
  C. 原行内容——原有行是否被意外改写（逐单元格 diff）
  D. 重复——影子表内是否出现「同一观测两行」（按业务键）
  E. 可追溯——新增行的 raw_file 是否都能在 data/raw/ 下解析

用法：
  python3 tools/validators/audit_shadow_merge.py <shadow_dir>
"""
from __future__ import annotations
from pathlib import Path

import csv
import os
import sys
from collections import Counter, defaultdict

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
CITY_DIR = os.path.join(ROOT, "data/raw/retained_source/city_data")
CITIES = {"shenyang": "沈阳", "dalian": "大连", "tieling": "铁岭",
          "chaoyang": "朝阳", "jinzhou": "锦州", "dandong": "丹东"}
TABLES = ["phenology_events", "disaster_events_observed", "policy_events",
          "volume_observations", "price_observation"]

# 预期的已知减项（修复动作造成）
EXPECTED_DROP = {("dalian", "disaster_events_observed"): 11,
                 ("dalian", "volume_observations"): 1}
# 预期有单元格改写的表：(city, table) -> {允许改动的列: 说明}
# 每一项都必须对应 ROUND3_REPAIR_ACTIONS_V3.csv 里的一条显式修复动作
EXPECTED_EDITS = {
    ("dalian", "phenology_events"): {"city": "round3 合并时 city 误写目录名，纠正为中文名"},
    ("shenyang", "volume_observations"): {"note": "抽回 note 中『frequency=X | 』前缀至独立列"},
    ("dalian", "volume_observations"): {
        "note": "前缀抽取 + 重建行 note 重写",
        "volume": "REBUILD：源行错位，按原始留存件重建（40）",
        "volume_unit": "REBUILD：按原始留存件重建（万吨）",
        "volume_type": "REBUILD：按原始留存件重建（annual_throughput）",
        "crop": "REBUILD：按原始留存件重建（果菜）",
        "geo_level": "REBUILD：按原始留存件重建（market）",
        "source_name": "REBUILD：按原始留存件重建",
        "source_url": "REBUILD：按原始留存件重建",
        "raw_file": "REBUILD：按原始留存件重建",
        "quality_grade": "REBUILD：按原始留存件重建（D）",
        "market_name": "REBUILD：按原始留存件重建",
        "date": "REBUILD：年度口径，观测日置空",
        "county": "REBUILD：按原始留存件重建",
        "source_id": "REBUILD：按原始留存件重建",
    },
    ("jinzhou", "volume_observations"): {
        "note": "前缀抽取 + 区间值降入 note",
        "volume": "FIX_CELL_BY_SOURCE_ID：『3000余』→下限3000、『2-3』→下限2",
    },
    ("chaoyang", "volume_observations"): {"note": "同上前缀抽取"},
    ("dandong", "volume_observations"): {"note": "同上前缀抽取"},
    ("tieling", "volume_observations"): {"note": "同上前缀抽取"},
}

# 行标签：用于跨「删除行」的对齐。优先用唯一 source_id，否则用业务键元组。
LABEL_COLS = {
    "phenology_events": ["source_id"],
    "disaster_events_observed": ["source_id"],
    "policy_events": ["source_id"],
    "volume_observations": ["source_id"],
    "price_observation": ["source_id"],
}


def row_label(table, hdr, row):
    cols = LABEL_COLS.get(table, [])
    vals = []
    for c in cols:
        if c in hdr:
            j = hdr.index(c)
            vals.append(row[j].strip() if j < len(row) else "")
    if any(vals):
        return ("sid",) + tuple(vals)
    # 无可用标签 → 退回位置（返回 None，由调用方按索引处理）
    return None

BIZ_KEY = {
    "phenology_events": ["city", "county", "crop_standard", "stage", "start_date", "end_date"],
    "disaster_events_observed": ["city", "county", "event_type", "start_date", "end_date"],
    "policy_events": ["city", "county", "policy_date", "title"],
    "volume_observations": ["date", "city", "county", "market_name", "crop",
                            "volume", "volume_unit"],
    "price_observation": ["city", "county", "market_name", "crop_standard",
                          "observation_date", "price_original", "unit_original"],
}


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        return [], []
    return [h.lstrip("\ufeff") for h in rows[0]], rows[1:]


def main():
    if len(sys.argv) < 2:
        print("用法: audit_shadow_merge.py <shadow_dir>")
        return 1
    shadow = sys.argv[1]

    problems, warns, summary = [], [], []

    for city_dir, city_cn in CITIES.items():
        for table in TABLES:
            old_p = os.path.join(CITY_DIR, city_dir, "data", f"{table}.csv")
            new_p = os.path.join(shadow, city_dir, "data", f"{table}.csv")
            if not os.path.exists(old_p) or not os.path.exists(new_p):
                continue
            oh, orows = read_csv(old_p)
            nh, nrows = read_csv(new_p)

            # B. 列结构
            if nh[:len(oh)] != oh:
                problems.append(f"{city_cn}/{table} 原有列被改动！old={oh} new={nh[:len(oh)]}")
            added = nh[len(oh):]
            dup_cols = [c for c in added if c in oh]
            if dup_cols:
                problems.append(f"{city_cn}/{table} 追加列与原有列重名: {dup_cols}")

            # A. 行数
            d = len(nrows) - len(orows)
            exp = -EXPECTED_DROP.get((city_dir, table), 0)
            if d < exp:
                problems.append(f"{city_cn}/{table} 行数异常减少 {d}（预期 ≥{exp}）")

            # C. 原行内容 diff（前 len(orows) 行应与原表一致或被显式修复）
            allowed_cols = EXPECTED_EDITS.get((city_dir, table), {})
            edited = defaultdict(int)
            ncell = 0

            # 为原行建标签索引（标签唯一时才用于对齐），其余按位置配对
            o_by_label = defaultdict(list)
            for i, r in enumerate(orows):
                lb = row_label(table, oh, r)
                if lb:
                    o_by_label[lb].append(i)
            aligned = set()
            pairs = []          # (原行idx, 新行idx)
            for k, r in enumerate(nrows):
                lb = row_label(table, nh, r)
                if lb and len(o_by_label.get(lb, [])) == 1:
                    i = o_by_label[lb][0]
                    if i not in aligned:
                        pairs.append((i, k))
                        aligned.add(i)
            # 未对齐的按顺序补齐（保持原有相对次序）
            rest_i = [i for i in range(len(orows)) if i not in aligned]
            rest_k = [k for k in range(len(nrows))
                      if row_label(table, nh, nrows[k]) not in o_by_label
                      or len(o_by_label.get(row_label(table, nh, nrows[k]), [])) != 1]
            for i, k in zip(rest_i, rest_k):
                pairs.append((i, k))

            for i, k in pairs:
                a = list(orows[i]) + [""] * (len(nh) - len(orows[i]))
                b = list(nrows[k]) + [""] * (len(nh) - len(nrows[k]))
                for j in range(len(oh)):
                    if a[j] != b[j]:
                        edited[oh[j]] += 1
                        if oh[j] in allowed_cols:
                            continue
                        ncell += 1
                        if ncell <= 6:
                            problems.append(
                                f"{city_cn}/{table} 原行(L{i+2}→新L{k+2}) 列『{oh[j]}』被改: "
                                f"{a[j]!r} → {b[j]!r}")
            ncell_total = sum(edited.values())

            # D. 重复
            bk = [c for c in BIZ_KEY[table] if c in nh]
            si = [nh.index(c) for c in bk]
            cnt = Counter(tuple(r[i].strip() for i in si)
                          for r in nrows if len(r) == len(nh))
            dups = {k: v for k, v in cnt.items() if v > 1}
            if dups:
                warns.append(f"{city_cn}/{table} 业务键重复 {len(dups)} 组 "
                             f"(例: {list(dups.items())[:2]})")

            # E. raw_file 可解析
            rfcol = "raw_file" if "raw_file" in nh else ("raw_file_new" if "raw_file_new" in nh else None)
            unres = 0
            if rfcol:
                ji = nh.index(rfcol)
                for r in nrows:
                    if len(r) <= ji:
                        continue
                    v = r[ji].strip()
                    if not v:
                        continue
                    p = os.path.join(ROOT, v)
                    if not os.path.exists(p):
                        unres += 1
            if unres:
                warns.append(f"{city_cn}/{table} raw_file 无法解析 {unres} 行")

            summary.append(dict(city=city_cn, table=table, before=len(orows), after=len(nrows),
                                delta=d, added_cols=len(added),
                                oldcell_edits=ncell_total, bad_edits=ncell,
                                dup_keys=len(dups) if dups else 0,
                                rawfile_unresolved=unres))

    print("=" * 100)
    print(f"{'city':6s} {'table':26s} {'before':>7s} {'after':>7s} {'delta':>6s} "
          f"{'+col':>5s} {'预期改':>7s} {'!!越界':>7s} {'重复键':>7s} {'raw缺':>6s}")
    for s in summary:
        flag = "  <<<" if s['bad_edits'] else ""
        print(f"{s['city']:6s} {s['table']:26s} {s['before']:>7d} {s['after']:>7d} "
              f"{s['delta']:>+6d} {s['added_cols']:>5d} {s['oldcell_edits']:>7d} "
              f"{s['bad_edits']:>7d} {s['dup_keys']:>7d} {s['rawfile_unresolved']:>6d}{flag}")

    print()
    if problems:
        print(f"### 阻断级问题 {len(problems)}")
        for x in problems[:30]:
            print("  ✗", x)
    else:
        print("### 阻断级问题 0 ✓")

    print()
    if warns:
        print(f"### 需复核 {len(warns)}")
        for x in warns[:30]:
            print("  !", x)
    else:
        print("### 需复核 0 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
