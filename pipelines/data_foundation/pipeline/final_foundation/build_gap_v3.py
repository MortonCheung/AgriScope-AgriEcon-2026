# -*- coding: utf-8 -*-
"""生成六城 GAP 表 V3（AgriScope）

与 V2 的 *_GAP_FINAL.csv 的区别：
  * status_after 不再沿用增量预期，而是按【合并后实际行数】重算
  * 明确区分「新增」与「因真实性原则移出」的量（后者必须如实反映为减项）
  * 六城合并为单一文件，附 city 列，便于跨城比对

用法：
  python3 tools/pipeline/final_foundation/build_gap_v3.py
"""
from __future__ import annotations
from pathlib import Path

import csv
import json
import os

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
CD = os.path.join(ROOT, "data/raw/retained_source/city_data")
FF = os.path.join(CD, "reference", "final_foundation")
BASE = os.path.join(ROOT, "archive", "migration", "PRE_ROUND3_MERGE_BASELINE_20260923.json")

CITIES = [("shenyang", "沈阳"), ("dalian", "大连"), ("tieling", "铁岭"),
          ("chaoyang", "朝阳"), ("jinzhou", "锦州"), ("dandong", "丹东")]

# 研究分支归属
BRANCH = {
    "price_observation": "生产→供应→价格",
    "volume_observations": "生产→供应→价格（供应层）",
    "phenology_events": "作物物候窗口",
    "disaster_events_observed": "灾害冲击",
    "policy_events": "政策与市场干预",
}

# 事件类阈值 3，测量类阈值 20
EVENT_TOPICS = {"phenology_events", "disaster_events_observed", "policy_events"}

# 合并后的已知剩余缺口（人工核定，逐城）
REMAINING = {
    ("dalian", "disaster_events_observed"):
        "11 行列错位无法可靠恢复已移出（见 archive/review/round3_corrupted/）；台风农业损失量化仍不足",
    ("dalian", "volume_observations"):
        "2020 前与 2024 后仍稀；年度吞吐量仅 1 条可溯源",
    ("shenyang", "disaster_events_observed"):
        "市级受灾面积合计未公开（仅街道/村级个案）",
    ("shenyang", "phenology_events"):
        "2017-2020 无直接物候记录",
    ("jinzhou", "volume_observations"):
        "日/周级成交序列官方不公开（NOT_PUBLIC），仅年度吞吐量+容量，不能做日频传导",
    ("chaoyang", "volume_observations"):
        "同上；且 disaster start_date 实为报告日，待校正为事件日",
    ("tieling", "volume_observations"):
        "粮库入库量/收购量官方不公开；成交量以市场级年度吞吐为主",
    ("dandong", "price_observation"):
        "草莓产地价仅 E 级来源，2020-2022 仍缺",
}


def nrows(p):
    if not os.path.exists(p):
        return 0
    with open(p, encoding="utf-8-sig") as fh:
        return max(0, sum(1 for _ in fh) - 1)


def grade(table, n):
    if n == 0:
        return "MISSING"
    thr = 3 if table in EVENT_TOPICS else 20
    return "GREEN" if n >= thr else "YELLOW_LOW"


def main():
    base = json.load(open(BASE, encoding="utf-8"))
    out = []
    for slug, cn in CITIES:
        for table, branch in BRANCH.items():
            key = f"{slug}/{table}"
            before = base.get(key, {}).get("rows", 0)
            after = nrows(os.path.join(CD, slug, "data", f"{table}.csv"))
            delta = after - before
            out.append(dict(
                city=cn, research_branch=branch, dataset=table,
                rows_before=before, rows_added_this_round=max(delta, 0),
                rows_removed_this_round=max(-delta, 0), rows_after=after,
                status_before=grade(table, before), status_after=grade(table, after),
                remaining_gap=REMAINING.get((slug, table), ""),
                note="净减为真实性修复（列错位不可恢复 → 移出），非数据丢失" if delta < 0 else "",
            ))
    p = os.path.join(FF, "SIX_CITY_GAP_FINAL_V3.csv")
    with open(p, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)
    print("已写出:", os.path.relpath(p, ROOT))
    print()
    print(f"{'city':6s} {'dataset':26s} {'前':>7s} {'增':>6s} {'减':>4s} {'后':>7s} "
          f"{'前级':>11s} {'后级':>11s}")
    for r in out:
        mark = "  <<<" if r["rows_removed_this_round"] else ""
        print(f"{r['city']:6s} {r['dataset']:26s} {r['rows_before']:>7d} "
              f"{r['rows_added_this_round']:>6d} {r['rows_removed_this_round']:>4d} "
              f"{r['rows_after']:>7d} {r['status_before']:>11s} {r['status_after']:>11s}{mark}")
    tot_a = sum(r["rows_added_this_round"] for r in out)
    tot_r = sum(r["rows_removed_this_round"] for r in out)
    print()
    print(f"合计 新增 {tot_a} / 移出 {tot_r} / 净 {tot_a - tot_r}")


if __name__ == "__main__":
    main()
