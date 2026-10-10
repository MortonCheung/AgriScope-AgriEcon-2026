# -*- coding: utf-8 -*-
"""round3 增量：结构修复 + QC + 合并入库（AgriScope）

背景：round3 采集产出的增量暂存于 `archive/review/round3_deltas/<city>/`，需要
在 QC 通过后合并进正式城市数据 `city_data/<city>/data/`。

本脚本做三件事：
  STEP 1  修复 round3 合并已造成的损坏（仅大连 3 处，见 REPAIRS）
  STEP 2  把尚未合并的增量做：结构修复 → 字段映射 → QC 过滤 → 去重 → 追加
  STEP 3  输出 QC 报告（逐文件 + 逐行拒绝原因）

设计原则（不可违背）：
  * 真实性优先：列语义不可靠恢复的行一律 REJECT，绝不猜测填充
  * 只做「加法」扩展：目标表原有列的顺序与含义绝不改动，新列一律追加在末尾
  * 省级行（geo_level=province / city=辽宁省）不得写入城市事实，路由到 reference/
  * 合并前必备份（archive/backups/round3_merge_<ts>/）
  * 幂等：按内容键去重，重复跑不会重复插入

用法：
  python3 tools/pipeline/city_data_ops/merge_round3_deltas.py            # dry-run
  python3 tools/pipeline/city_data_ops/merge_round3_deltas.py --apply    # 实际写入
"""
from __future__ import annotations
from pathlib import Path

import argparse
import csv
import datetime as dt
import json
import os
import re
import shutil
import sys
from collections import Counter, defaultdict

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
CITY_DIR = os.path.join(ROOT, "data/raw/retained_source/city_data")
DELTA_DIR = os.path.join(ROOT, "archive", "review", "round3_deltas")
RAW_DIR = os.path.join(ROOT, "data/raw", "web_captures")
ARCHIVE = os.path.join(ROOT, "archive")
FF = os.path.join(CITY_DIR, "reference", "final_foundation")
TODAY = "2026-09-23"
TS = dt.datetime.now().strftime("%Y%m%d_%H%M%S")

CITIES = {
    "shenyang": "沈阳", "dalian": "大连", "tieling": "铁岭",
    "chaoyang": "朝阳", "jinzhou": "锦州", "dandong": "丹东",
}
CITY_ALIAS = {"shenyang": "沈阳", "dalian": "大连", "tieling": "铁岭",
              "chaoyang": "朝阳", "jinzhou": "锦州", "dandong": "丹东",
              "沈阳": "沈阳", "大连": "大连", "铁岭": "铁岭",
              "朝阳": "朝阳", "锦州": "锦州", "丹东": "丹东", "辽宁省": "辽宁省"}

# ---------------------------------------------------------------- STEP 1 修复

REPAIRS = {
    # 大连 disaster：11 行由列错位文件合入，列语义不可靠恢复 → 移出主表
    ("dalian", "disaster_events_observed"): {
        "kind": "drop_rows_where",
        "predicate": ("city", "dalian"),
        "reason": "源增量 dalian/disaster_new.csv 列错位（ragged 13-18/23，自由文本落入 "
                  "economic_loss 等数值列），语义不可靠恢复，按真实性原则移出主表",
    },
    # 大连 phenology：19 行内容合规，仅 city 标签写成英文 → 就地修正
    ("dalian", "phenology_events"): {
        "kind": "fix_value",
        "column": "city", "from": "dalian", "to": "大连",
        "reason": "round3 合并时 city 写为目录名而非中文城市名",
    },
    # 大连 volume：2 行 annual_throughput 列语义整体左移，从独立原件重建 1 行、移出 1 行
    ("dalian", "volume_observations"): {
        "kind": "repair_shifted_rows",
        "rebuild": {
            # 依据原始留存件逐字重建（data/raw/web_captures/dalian/volume/round3/
            #   news.qq.com_2024-12-12_guocai_40wan.txt 的 VERBATIM 段）
            "https://news.qq.com/rain/a/20241212A08BUL00": {
                "market_name": "大连果菜批发市场",
                "crop": "果菜",
                "volume": "40",
                "volume_unit": "万吨",
                "volume_type": "annual_throughput",
                "geo_level": "market",
                "source_name": "腾讯新闻（引大连果菜批发市场负责人姜敏）",
                "source_url": "https://news.qq.com/rain/a/20241212A08BUL00",
                "raw_file": "data/raw/web_captures/dalian/volume/round3/news.qq.com_2024-12-12_guocai_40wan.txt",
                "quality_grade": "D",
                "note": "腾讯新闻引市场负责人姜敏；年度吞吐量非日度量；原文『果菜等商品年交易量超过40万吨，占全市交易量50%以上』",
            },
        },
        "drop_source_ids": {
            "https://k.sina.cn/article_7879924051_1d5ae195306802aujk.html":
                "无独立留存原件（raw_file 误指向 news.qq.com 抓取件），且与上行为同一事实"
                "（南关岭系大连果菜批发市场所在区域），重复观测予以移出",
        },
        "reason": "源增量 dalian/volume_new.csv 第 44/45 行列语义整体左移（year=40、volume=万吨、"
                  "quality_grade=city），不可按位置恢复；改由原始留存件重建",
    },
    # 锦州 volume：2 行数值列混入区间/约数文字，按 source_id 定点归一化（原文降入 note）
    ("jinzhou", "volume_observations"): {
        "kind": "fix_cell_by_source_id",
        "cells": {
            "SRC-JZ-MOFCOM-HQZ-20060913": {
                "volume": "3000",
                "note_append": "原文『年交易各种反季蔬菜3000余万公斤』，值取下限（≥3000）",
            },
            "SRC-JZ-BJH-SJZ-20251107": {
                "volume": "2",
                "note_append": "原文『一天大概能收2万至3万斤』区间，值取区间下限2万斤",
            },
        },
        "reason": "数值列混入『3000余』『2-3』等非标量表述，破坏列类型一致性",
    },
}

# 旧合并遗留：note 被写成「frequency=X | 原文…」，抽回独立列
FREQ_PREFIX_RE = re.compile(r"^frequency=([^；;|]*)\s*\|\s*")

# 源增量中列语义不可靠、不得按位置解读的行（显式排除，附证据）
SOURCE_EXCLUDE = {
    # dalian/volume_new.csv 第 44、45 行：整行左移（year=40 / value=万吨 / price_level=抓取批次标记
    # / quality_grade=city），已改由原始留存件重建或移出，禁止再被 STEP 2 当作新观测合并
    ("dalian", "volume_new.csv", 44): "列语义整体左移，已由原件重建（news.qq.com 果菜 40 万吨）",
    ("dalian", "volume_new.csv", 45): "列语义整体左移且无独立留存原件，与上一行为同一事实",
}

# ---------------------------------------------------------------- 目标表规范

TABLE_SPEC = {
    "phenology_events": {
        "delta_file": "phenology_new.csv",
        "new_cols": ["raw_file_new", "retrieval_date", "geo_level", "note"],
        "province_file": "phenology_events_province.csv",
    },
    "disaster_events_observed": {
        "delta_file": "disaster_new.csv",
        "new_cols": ["lodging_area_value", "lodging_area_unit", "facility_damage_count",
                     "facility_damage_area_mu", "livestock_death_heads", "yield_loss_ton",
                     "geo_level", "note", "source_id"],
        "province_file": "disaster_events_observed_province.csv",
    },
    "policy_events": {
        "delta_file": "policy_new.csv",
        "new_cols": ["amount_yuan", "target_crop", "linked_disaster_date",
                     "geo_level", "source_id", "retrieval_date", "note"],
        "province_file": "policy_events_province.csv",
    },
    "volume_observations": {
        "delta_files": ["volume_new.csv", "volume_round3b.csv"],
        "new_cols": ["frequency", "period_start", "period_end", "year", "price_level",
                     "retrieval_date", "source_text"],
        "province_file": None,
    },
    "price_observation": {
        "delta_file": "price_new.csv",
        "new_cols": ["source_text", "retrieval_date"],
        "province_file": None,
        "province_target": "price_observation_province.csv",
    },
}

ENUMS = {
    "volume_type": {"daily_transaction", "weekly_transaction", "monthly_transaction",
                    "market_inflow", "market_supply", "purchase_volume", "storage_volume",
                    "annual_throughput", "market_capacity", "inventory", "livestock_heads",
                    "procurement"},
    "frequency": {"daily", "weekly", "monthly", "annual", "event_point", "capacity"},
    "policy_type": {"emergency_response", "market_supply", "price_stabilization",
                    "agricultural_subsidy", "disaster_relief", "insurance", "transport",
                    "grain_purchase", "industry_support", "other"},
    "disaster_source_type": {"observed_event"},
    "date_precision": {"day", "tenday", "month", "year", "period", "week"},
    "price_level": {"wholesale", "retail", "supermarket", "farm_gate", "purchase",
                    "auction", "other"},
    "geo_level": {"market", "city", "county", "district", "province", "store", "site", "region"},
}
SOFT_ENUMS = {"quality_grade": set("ABCDEF")}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
NUM_RE = re.compile(r"^-?\d+(\.\d+)?$")

# ---------------------------------------------------------------- 行级归一化
#
# 逐行、显式、可审计。只允许做「把原文口径落进正确列」这一件事，
# 严禁猜测填充。键 = (city_dir, table, delta_basename, src_row)。
NORMALIZE = {
    # 沈阳：棚体受损是【面积】口径，原填入 facility_damage_count（计数列）会污染列语义
    ("shenyang", "disaster_events_observed", "disaster_new.csv", 9): {
        "action": "NORMALIZE_FACILITY_AREA",
        "set": {"facility_damage_count": "", "facility_damage_area_mu": "128.27"},
        "note_append": "棚体受损为面积口径，128.27 归入 facility_damage_area_mu",
        "reason": "原文『农业生产大棚受损128.27亩』为设施受损面积而非损毁座数",
    },
    # 丹东：『一座草莓大棚垮塌』是明确计数 1，描述性文字移入 note
    ("dandong", "disaster_events_observed", "disaster_new.csv", 3): {
        "action": "NORMALIZE_FACILITY_COUNT",
        "set": {"facility_damage_count": "1"},
        "note_append": "原文『一座草莓大棚垮塌』，计数取1",
        "reason": "计数列混入描述文字，原文计数明确为『一座』",
    },
    # 锦州：『3000余万公斤』→ 取下限 3000，note 显式声明
    ("jinzhou", "volume_observations", "volume_new.csv", 8): {
        "action": "NORMALIZE_LOWER_BOUND",
        "set": {"value": "3000"},
        "note_append": "原文『3000余万公斤』，值取区间下限（≥3000）",
        "reason": "『N余』为下限表述，取下限并显式标注，非插值",
    },
    # 锦州：『2万至3万斤』→ 取下限 2
    ("jinzhou", "volume_observations", "volume_new.csv", 9): {
        "action": "NORMALIZE_LOWER_BOUND",
        "set": {"value": "2"},
        "note_append": "原文『2万至3万斤』区间，取区间下限2万斤",
        "reason": "区间表述取明确下限，非取中值",
    },
    # 丹东：『全市当前商业库存』= 库存口径快照（原文即明确说明是库存）
    ("dandong", "volume_observations", "volume_new.csv", 12): {
        "action": "ENUM_COMPLETE_INVENTORY",
        "set": {"volume_type": "inventory", "frequency": "event_point"},
        "note_append": "volume_type/frequency 按原文『商业库存』归入 inventory / event_point",
        "reason": "原文口径为「当前商业库存」，属存量快照，非交易量",
    },
    ("dandong", "volume_observations", "volume_new.csv", 13): {
        "action": "ENUM_COMPLETE_INVENTORY",
        "set": {"volume_type": "inventory", "frequency": "event_point"},
        "note_append": "volume_type/frequency 按原文『商业库存』归入 inventory / event_point",
        "reason": "同上",
    },
    ("dandong", "volume_observations", "volume_new.csv", 14): {
        "action": "ENUM_COMPLETE_INVENTORY",
        "set": {"volume_type": "inventory", "frequency": "event_point"},
        "note_append": "volume_type/frequency 按原文『商业库存』归入 inventory / event_point",
        "reason": "同上",
    },
    ("dandong", "volume_observations", "volume_new.csv", 15): {
        "action": "ENUM_COMPLETE_INVENTORY",
        "set": {"volume_type": "inventory", "frequency": "event_point"},
        "note_append": "volume_type/frequency 按原文『商业库存』归入 inventory / event_point",
        "reason": "同上",
    },
}

# 物候跨年窗口豁免：草莓等越冬作物的上市/退市期为跨年档期（如 9月20日→第二年6月25日），
# 属年度固定窗口，不是「未来事件」。判定条件：start.year < end.year 且窗口 ≤ 366 天。
def _is_crossyear_phenology(rec):
    a, b = rec.get("start_date", ""), rec.get("end_date", "")
    if not (DATE_RE.match(a) and DATE_RE.match(b)):
        return False
    if a[:4] >= b[:4]:
        return False
    try:
        d1 = dt.date(*map(int, a.split("-")))
        d2 = dt.date(*map(int, b.split("-")))
    except ValueError:
        return False
    return 0 < (d2 - d1).days <= 366


# ---------------------------------------------------------------- 工具

def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        return [], []
    hdr = [h.lstrip("\ufeff") for h in rows[0]]
    return hdr, rows[1:]


def resolve_delta(city_dir, fname):
    """增量文件可能位于 <city>/ 或 <city>/_round3/（历史遗留嵌套）。"""
    for sub in ("", "_round3", "round3"):
        p = os.path.join(DELTA_DIR, city_dir, sub, fname) if sub else os.path.join(DELTA_DIR, city_dir, fname)
        if os.path.exists(p):
            return p
    return None


def read_delta(path):
    """读增量 CSV；返回 (header, rows, structural_report)"""
    rep = {"file": os.path.relpath(path, ROOT), "fixed_rows": 0, "unfixable": 0}
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        return [], [], rep
    hdr = [h.lstrip("\ufeff") for h in rows[0]]
    n = len(hdr)
    out = []
    base = os.path.basename(path)
    for rno, r in enumerate(rows[1:], start=2):
        if not r or all(not x.strip() for x in r):
            continue
        if len(r) == n:
            out.append((rno, r))
            continue
        # 已知的两种确定性错位
        if len(r) == n + 1 and r[9] == "" and base == "volume_new.csv":
            # 多一个空列位于 index 9 → 删除
            rr = r[:9] + r[10:]
            if len(rr) == n:
                out.append((rno, rr))
                rep["fixed_rows"] += 1
                continue
        if len(r) == n - 1 and base == "volume_new.csv":
            # 少一个空列（period_end）→ 在 index 8 前补空
            rr = r[:8] + [""] + r[8:]
            if len(rr) == n:
                out.append((rno, rr))
                rep["fixed_rows"] += 1
                continue
        rep["unfixable"] += 1
    return hdr, out, rep


def norm_rawfile(v, city_dir):
    """把旧 raw/... 路径重定向到 data/raw/web_captures/<city>/...，并校验存在性。"""
    v = (v or "").strip()
    if not v:
        return "", "EMPTY"
    base = v.split("/")[-1].split("\\")[-1]
    if not base:
        return v, "UNRESOLVED"
    import glob as _g
    cands = _g.glob(os.path.join(RAW_DIR, city_dir, "**", base), recursive=True)
    if cands:
        rel = os.path.relpath(cands[0], ROOT)
        return rel.replace(os.sep, "/"), "OK"
    return v, "UNRESOLVED"


def derive_year(d):
    d = (d or "").strip()
    if DATE_RE.match(d):
        return d[:4]
    return ""


def loose_key(table, row, hdr):
    """宽松去重键：比 key_of 少一两个「后补列」，用于识别『同一观测、列值不全』。"""
    g = lambda c: (row[hdr.index(c)].strip() if c in hdr and hdr.index(c) < len(row) else "")
    if table == "volume_observations":
        return (g("date"), g("city"), g("county"), g("market_name"), g("crop"),
                g("volume"), g("volume_unit"))
    if table == "disaster_events_observed":
        return (g("city"), g("county"), g("event_type"), g("start_date"), g("end_date"))
    return key_of(table, row, hdr)


def key_of(table, row, hdr):
    """内容去重键：取语义稳定的若干列。"""
    g = lambda c: (row[hdr.index(c)].strip() if c in hdr and hdr.index(c) < len(row) else "")
    if table == "volume_observations":
        return (g("date"), g("city"), g("county"), g("market_name"), g("crop"),
                g("volume"), g("volume_unit"), g("volume_type"))
    if table == "phenology_events":
        return (g("city"), g("county"), g("crop_standard"), g("stage"),
                g("start_date"), g("end_date"))
    if table == "disaster_events_observed":
        return (g("city"), g("county"), g("event_type"), g("start_date"), g("end_date"),
                g("affected_area_value"))
    if table == "policy_events":
        return (g("city"), g("county"), g("policy_date"), g("title"))
    if table == "price_observation":
        return (g("city"), g("county"), g("market_name"), g("crop_standard"),
                g("observation_date"), g("price_original"), g("unit_original"), g("price_level"))
    return tuple(row)


# ---------------------------------------------------------------- 字段映射

NORM_LOG = []


def map_rows(table, d_hdr, d_rows, city_dir, city_cn, seq_start, delta_name=None):
    """把增量行映射为目标表列名 → 值的 dict（仅语义列；新列已含）。"""
    di = {h: i for i, h in enumerate(d_hdr)}

    def g(r, c):
        j = di.get(c)
        if j is None or j >= len(r):
            return ""
        return r[j].strip()

    out = []
    seq = seq_start
    for rno, r in d_rows:
        rec = {}
        rf, rf_status = norm_rawfile(g(r, "raw_file"), city_dir)
        if table == "phenology_events":
            rec = {
                "city": CITY_ALIAS.get(g(r, "city"), city_cn),
                "county": g(r, "county"),
                "crop_raw": g(r, "crop"),
                "crop_standard": g(r, "crop"),
                "year": g(r, "year") or derive_year(g(r, "start_date")),
                "stage": g(r, "stage"),
                "start_date": g(r, "start_date"),
                "end_date": g(r, "end_date"),
                "date_precision": g(r, "date_precision"),
                "source_id": g(r, "source_id"),
                "source_url": g(r, "source_url"),
                "source_text": g(r, "source_text"),
                "quality_grade": g(r, "quality_grade"),
                "derived_from_text": g(r, "derived_from_text").lower(),
                "raw_file_new": rf,
                "retrieval_date": g(r, "retrieval_date"),
                "geo_level": g(r, "geo_level"),
                "note": g(r, "note"),
            }
        elif table == "disaster_events_observed":
            seq += 1
            rec = {
                "event_id": f"R3-{city_cn}-{seq:03d}",
                "event_name": " ".join(x for x in [g(r, "county"), g(r, "event_type")] if x),
                "event_type": g(r, "event_type"),
                "start_date": g(r, "start_date"),
                "end_date": g(r, "end_date"),
                "year": derive_year(g(r, "start_date")),
                "province": "辽宁省",
                "city": CITY_ALIAS.get(g(r, "city"), city_cn),
                "county": g(r, "county"),
                "spatial_level": g(r, "geo_level"),
                "affected_area_value": g(r, "affected_area_mu"),
                "affected_area_unit": "亩" if g(r, "affected_area_mu") else "",
                "damaged_area_value": g(r, "disaster_area_mu"),
                "crop_failure_area_value": g(r, "no_harvest_area_mu"),
                "drainage_area_value": "",
                "drainage_area_unit": "",
                "evacuated_persons": "",
                "deaths": "",
                "economic_loss": g(r, "economic_loss_yuan"),
                "crop": g(r, "affected_crop"),
                "title": g(r, "source_id"),
                "official_description": g(r, "source_text"),
                "source_name": g(r, "source_id"),
                "source_url": g(r, "source_url"),
                "raw_file": rf,
                "quality_grade": g(r, "quality_grade"),
                "data_type": g(r, "disaster_source_type"),
                "fetched_at": g(r, "retrieval_date"),
                "lodging_area_value": g(r, "lodging_area_mu"),
                "lodging_area_unit": "亩" if g(r, "lodging_area_mu") else "",
                "facility_damage_count": g(r, "facility_damage_count"),
                "livestock_death_heads": g(r, "livestock_death_heads"),
                "yield_loss_ton": g(r, "yield_loss_ton"),
                "geo_level": g(r, "geo_level"),
                "note": g(r, "note"),
                "source_id": g(r, "source_id"),
            }
        elif table == "policy_events":
            seq += 1
            rec = {
                "event_id": f"R3-POL-{city_cn}-{seq:03d}",
                "policy_date": g(r, "policy_date"),
                "year": derive_year(g(r, "policy_date")) or g(r, "policy_date"),
                "policy_type": g(r, "policy_type"),
                "level": g(r, "geo_level"),
                "city": CITY_ALIAS.get(g(r, "city"), city_cn),
                "county": g(r, "county"),
                "issuing_org": g(r, "issuing_org"),
                "title": g(r, "policy_title"),
                "summary": g(r, "source_text"),
                "source_name": g(r, "source_id"),
                "source_url": g(r, "source_url"),
                "raw_file": rf,
                "quality_grade": g(r, "quality_grade"),
                "amount_yuan": g(r, "amount_yuan"),
                "target_crop": g(r, "target_crop"),
                "linked_disaster_date": g(r, "linked_disaster_date"),
                "geo_level": g(r, "geo_level"),
                "source_id": g(r, "source_id"),
                "retrieval_date": g(r, "retrieval_date"),
                "note": g(r, "note"),
            }
        elif table == "volume_observations":
            rec = {
                "date": g(r, "observation_date"),
                "city": CITY_ALIAS.get(g(r, "city"), city_cn),
                "county": g(r, "county"),
                "market_name": g(r, "market_name"),
                "crop": g(r, "crop"),
                "volume": g(r, "value"),
                "volume_unit": g(r, "unit"),
                "volume_type": g(r, "volume_type"),
                "geo_level": g(r, "geo_level"),
                "source_id": g(r, "source_id"),
                "source_name": g(r, "source_id"),
                "source_url": g(r, "source_url"),
                "raw_file": rf,
                "quality_grade": g(r, "quality_grade"),
                "note": g(r, "note"),
                "frequency": g(r, "frequency"),
                "period_start": g(r, "period_start"),
                "period_end": g(r, "period_end"),
                "year": g(r, "year"),
                "price_level": g(r, "price_level"),
                "retrieval_date": g(r, "retrieval_date"),
                "source_text": g(r, "source_text"),
            }
        elif table == "price_observation":
            rec = {
                "city": CITY_ALIAS.get(g(r, "city"), city_cn),
                "county": g(r, "county"),
                "market_name": g(r, "market_name"),
                "store_name": "",
                "platform": "",
                "crop_raw": g(r, "crop_raw"),
                "crop_standard": g(r, "crop"),
                "sku_name": "",
                "specification": "",
                "package_size": "",
                "price_original": g(r, "price"),
                "unit_original": g(r, "unit"),
                "price_per_kg": g(r, "price_per_kg"),
                "price_level": g(r, "price_level"),
                "observation_date": g(r, "observation_date"),
                "observation_time": "",
                "frequency": "",
                "source_type": "round3_web",
                "source_name": g(r, "source_id"),
                "source_url": g(r, "source_url"),
                "source_id": g(r, "source_id"),
                "retrieval_time": g(r, "retrieval_date"),
                "promotion_flag": "",
                "member_price_flag": "",
                "derived_flag": "",
                "quality_grade": g(r, "quality_grade"),
                "raw_file": rf,
                "geo_level": g(r, "geo_level"),
                "record_kind": "observation",
                "note": g(r, "note"),
                "source_text": g(r, "source_text"),
                "retrieval_date": g(r, "retrieval_date"),
            }
        rec["_src_row"] = rno
        rec["_rawfile_status"] = rf_status
        rec["_warn"] = ""
        exc = SOURCE_EXCLUDE.get((city_dir, delta_name, rno)) if delta_name else None
        if exc:
            rec["_excluded"] = exc

        nspec = NORMALIZE.get((city_dir, table, delta_name, rno))
        if nspec:
            for k, v in nspec.get("set", {}).items():
                rec[k] = v
            if nspec.get("note_append"):
                rec["note"] = (rec.get("note", "") + "；" + nspec["note_append"]).strip("；")
            NORM_LOG.append(dict(city=city_cn, table=table, action=nspec.get("action", "NORMALIZE"),
                                 n=1, detail=f"src_row={rno} {nspec.get('reason','')}"))
        out.append(rec)
    return out


# ---------------------------------------------------------------- QC

def qc_row(table, rec):
    """返回 [] = 通过；否则返回拒绝原因列表。"""
    bad = []
    # 通用：城市一致性
    if rec.get("city") in ("", None):
        bad.append("CITY_EMPTY")
    # 枚举
    for col, allowed in ENUMS.items():
        if col in rec and rec[col] and rec[col] not in allowed:
            bad.append(f"ENUM:{col}={rec[col]}")
    for col, allowed in SOFT_ENUMS.items():
        if col in rec and rec[col] and rec[col] not in allowed:
            bad.append(f"ENUM:{col}={rec[col]}")
    # 日期
    cy = table == "phenology_events" and _is_crossyear_phenology(rec)
    for col in ("start_date", "end_date", "date", "policy_date", "observation_date"):
        if col in rec and rec[col]:
            v = rec[col]
            if not (DATE_RE.match(v) or re.match(r"^\d{4}$", v) or re.match(r"^\d{4}-\d{2}$", v)):
                bad.append(f"DATE_FORMAT:{col}={v}")
            elif v > TODAY:
                if cy and col in ("start_date", "end_date"):
                    rec["_warn"] = "PHENO_CROSSYEAR_WINDOW"
                else:
                    bad.append(f"DATE_FUTURE:{col}={v}")
    for a, b in (("start_date", "end_date"), ("period_start", "period_end")):
        if rec.get(a) and rec.get(b) and DATE_RE.match(rec[a]) and DATE_RE.match(rec[b]) \
                and rec[a] > rec[b]:
            bad.append(f"DATE_ORDER:{a}>{b}")

    if table == "volume_observations":
        if not rec.get("volume_type"):
            bad.append("VOLUME_TYPE_EMPTY")
        if not rec.get("frequency"):
            bad.append("FREQUENCY_EMPTY")
        if rec.get("volume") and not NUM_RE.match(str(rec["volume"])):
            bad.append(f"VOLUME_NOT_NUMERIC={rec['volume']}")
        # 年度/容量口径不得带观测日
        if rec.get("frequency") in ("annual", "capacity") and rec.get("date"):
            bad.append("ANNUAL_HAS_OBS_DATE")
        if rec.get("volume_unit") in ("%", "万元"):
            bad.append(f"UNIT_NOT_VOLUME={rec['volume_unit']}")
    if table == "disaster_events_observed":
        if rec.get("data_type") != "observed_event":
            bad.append(f"NOT_OBSERVED_EVENT={rec.get('data_type')}")
        for c in ("affected_area_value", "damaged_area_value", "crop_failure_area_value",
                  "lodging_area_value", "facility_damage_count", "livestock_death_heads",
                  "yield_loss_ton"):
            v = rec.get(c)
            if v and not NUM_RE.match(str(v).replace(",", "")):
                bad.append(f"NUM_FREE_TEXT:{c}")
    if table == "phenology_events":
        d = rec.get("derived_from_text")
        if d not in ("true", "false"):
            bad.append(f"DERIVED_NOT_BOOL={d}")
        if not rec.get("stage"):
            bad.append("STAGE_EMPTY")
    if table == "price_observation":
        if not rec.get("price_level"):
            bad.append("PRICE_LEVEL_EMPTY")
        p = rec.get("price_original")
        if p and not NUM_RE.match(str(p).replace(",", "")):
            bad.append(f"PRICE_NOT_NUMERIC={p}")
    if table == "policy_events":
        if not rec.get("policy_date"):
            bad.append("POLICY_DATE_EMPTY")
        if not rec.get("title"):
            bad.append("TITLE_EMPTY")
    return bad


# ---------------------------------------------------------------- 主流程

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="实际写入（默认 dry-run）")
    ap.add_argument("--shadow", metavar="DIR",
                    help="影子写入：结果写到 DIR/<city>/data/ 而不动正式数据，用于审计")
    args = ap.parse_args()
    apply = args.apply or bool(args.shadow)
    shadow = args.shadow

    backup_dir = os.path.join(ARCHIVE, "backups", f"round3_merge_{TS}")
    qc_rows = []          # 逐行 QC
    file_summary = []     # 逐文件
    action_log = []       # 修复动作

    for city_dir, city_cn in CITIES.items():
        ddir = os.path.join(DELTA_DIR, city_dir)
        for table, spec in TABLE_SPEC.items():
            tpath = os.path.join(CITY_DIR, city_dir, "data", f"{table}.csv")
            if not os.path.exists(tpath):
                continue
            t_hdr, t_rows = read_csv(tpath)

            # ---------------- STEP 1 修复 ----------------
            rep = None
            for (rc, rt), rspec in REPAIRS.items():
                if rc == city_dir and rt == table:
                    rep = rspec
            if rep:
                if rep["kind"] == "drop_rows_where":
                    col, val = rep["predicate"]
                    j = t_hdr.index(col)
                    keep, drop = [], []
                    for r in t_rows:
                        (drop if j < len(r) and r[j].strip() == val else keep).append(r)
                    if drop:
                        action_log.append(dict(city=city_cn, table=table, action="DROP_ROWS",
                                               n=len(drop), detail=rep["reason"]))
                        if apply:
                            os.makedirs(os.path.join(ARCHIVE, "review", "round3_corrupted"),
                                        exist_ok=True)
                            outp = os.path.join(ARCHIVE, "review", "round3_corrupted",
                                                f"{city_dir}__{table}__dropped_{TS}.csv")
                            with open(outp, "w", encoding="utf-8-sig", newline="") as fh:
                                w = csv.writer(fh)
                                w.writerow(t_hdr)
                                w.writerows(drop)
                            t_rows = keep
                elif rep["kind"] == "fix_value":
                    j = t_hdr.index(rep["column"])
                    n = 0
                    for r in t_rows:
                        if j < len(r) and r[j].strip() == rep["from"]:
                            r[j] = rep["to"]
                            n += 1
                    if n:
                        action_log.append(dict(city=city_cn, table=table, action="FIX_VALUE",
                                               n=n, detail=f'{rep["column"]}: {rep["from"]}→{rep["to"]}'))
                elif rep["kind"] == "fix_cell_by_source_id":
                    if "source_id" in t_hdr and "note" in t_hdr:
                        js, jn = t_hdr.index("source_id"), t_hdr.index("note")
                        n = 0
                        for r in t_rows:
                            while len(r) < len(t_hdr):
                                r.append("")
                            sid = r[js].strip()
                            cspec = rep["cells"].get(sid)
                            if not cspec:
                                continue
                            for col, val in cspec.items():
                                if col == "note_append":
                                    if val not in r[jn]:
                                        r[jn] = (r[jn].rstrip("；") + "；" + val).strip("；")
                                    continue
                                if col in t_hdr:
                                    r[t_hdr.index(col)] = val
                            n += 1
                        if n:
                            action_log.append(dict(city=city_cn, table=table,
                                                   action="FIX_CELL_BY_SOURCE_ID", n=n,
                                                   detail=rep["reason"]))
                elif rep["kind"] == "repair_shifted_rows":
                    j_sid = t_hdr.index("source_id")
                    # (a) 逐字重建：用原始留存件恢复的字段覆盖
                    n_re = 0
                    for r in t_rows:
                        while len(r) < len(t_hdr):
                            r.append("")
                        spec_r = rep["rebuild"].get(r[j_sid].strip())
                        if not spec_r:
                            continue
                        for c, v in spec_r.items():
                            if c in t_hdr:
                                r[t_hdr.index(c)] = v
                        n_re += 1
                    if n_re:
                        action_log.append(dict(city=city_cn, table=table,
                                               action="REBUILD_FROM_SOURCE_FILE", n=n_re,
                                               detail=rep["reason"]))
                    # (b) 移出无独立原件的重复观测
                    drop = rep.get("drop_source_ids") or {}
                    keep, gone = [], []
                    for r in t_rows:
                        while len(r) < len(t_hdr):
                            r.append("")
                        sid = r[j_sid].strip()
                        (gone if sid in drop else keep).append(r)
                    if gone:
                        if apply:
                            os.makedirs(os.path.join(ARCHIVE, "review", "round3_corrupted"),
                                        exist_ok=True)
                            outp = os.path.join(ARCHIVE, "review", "round3_corrupted",
                                                f"{city_dir}__{table}__dropped_{TS}.csv")
                            with open(outp, "w", encoding="utf-8-sig", newline="") as fh:
                                w = csv.writer(fh)
                                w.writerow(t_hdr)
                                w.writerows(gone)
                        action_log.append(dict(city=city_cn, table=table, action="DROP_ROWS",
                                               n=len(gone),
                                               detail=drop.get(gone[0][j_sid].strip(), rep["reason"])))
                        t_rows = keep

            # ---------------- STEP 2 合并增量 ----------------
            merged = 0
            for dfile in spec.get("delta_files") or [spec["delta_file"]]:
                dp = resolve_delta(city_dir, dfile)
                if not dp:
                    continue
                dh, drows, drep = read_delta(dp)
                if not dh:
                    file_summary.append(dict(city=city_cn, table=table, delta=dfile, rows=0,
                                             merged=0, rejected=0, note="EMPTY_FILE"))
                    continue
                seq = sum(1 for r in t_rows if len(r) > 0 and r[0].startswith("R3-"))
                mapped = map_rows(table, dh, drows, city_dir, city_cn, seq, dfile)

                # 目标列 = 原列 + 新列（raw_file_new 特殊处理）
                new_cols = [c for c in spec["new_cols"]
                            if c not in t_hdr and c not in ("raw_file_new",)]
                eff_cols = t_hdr + [c for c in new_cols if c not in t_hdr]
                if "raw_file_new" in spec["new_cols"] and "raw_file_new" not in eff_cols:
                    eff_cols = eff_cols + ["raw_file_new"]

                # 三级去重索引：严格键 / source_id / 宽松键
                strict_idx, loose_idx, src_idx = {}, {}, defaultdict(list)
                js = eff_cols.index("source_id") if "source_id" in eff_cols else -1
                for r in t_rows:
                    while len(r) < len(eff_cols):
                        r.append("")
                    strict_idx.setdefault(key_of(table, r, eff_cols), r)
                    loose_idx.setdefault(loose_key(table, r, eff_cols), []).append(r)
                    if js >= 0 and r[js].strip():
                        src_idx[r[js].strip()].append(r)

                # 仅允许回填的列 = 本轮新追加的列。
                # 原有列一律不动：命中同一观测时，增量不得改写既有语义（防止把
                # 增量来源标签、派生常量等写进属于其他来源的原行）。
                fillable = set(eff_cols[len(t_hdr):])

                def backfill(target, f):
                    """只对【新增列】填空，绝不覆盖、绝不触及原有列。"""
                    n = 0
                    while len(target) < len(eff_cols):
                        target.append("")
                    for i, c in enumerate(eff_cols):
                        if c not in fillable:
                            continue
                        v = str(f.get(c, "")).strip()
                        if v and not target[i].strip():
                            target[i] = v
                            n += 1
                    return n

                # 批量内唯一性守卫：source_id / 宽松键在【本批】里不唯一时，
                # 不得作为去重依据（同一页面报多行是常态）
                prepared = [(f, [str(f.get(c, "")) for c in eff_cols]) for f in mapped]
                batch_src = Counter(r[js].strip() for _, r in prepared
                                    if js >= 0 and r[js].strip())
                batch_loose = Counter(loose_key(table, r, eff_cols) for _, r in prepared)

                for f, row in prepared:
                    if f.get("_excluded"):
                        qc_rows.append(dict(city=city_cn, table=table, delta=dfile,
                                            src_row=f["_src_row"], verdict="REJECT_UNRELIABLE",
                                            reasons=f["_excluded"]))
                        continue
                    reasons = qc_row(table, f)
                    if f.get("_warn"):
                        qc_rows.append(dict(city=city_cn, table=table, delta=dfile,
                                            src_row=f["_src_row"], verdict="WARN",
                                            reasons=f["_warn"]))
                    # 省级路由
                    is_prov = (f.get("geo_level") == "province" or f.get("city") == "辽宁省")
                    if is_prov and table == "price_observation":
                        reasons = [r for r in reasons if not r.startswith("PRICE_LEVEL")]
                    if reasons:
                        qc_rows.append(dict(city=city_cn, table=table, delta=dfile,
                                            src_row=f["_src_row"], verdict="REJECT",
                                            reasons="|".join(reasons)))
                        continue
                    if is_prov:
                        qc_rows.append(dict(city=city_cn, table=table, delta=dfile,
                                            src_row=f["_src_row"], verdict="ROUTE_PROVINCE",
                                            reasons="geo_level=province"))
                        continue
                    if f.get("_rawfile_status") == "UNRESOLVED":
                        qc_rows.append(dict(city=city_cn, table=table, delta=dfile,
                                            src_row=f["_src_row"], verdict="WARN_RAWFILE",
                                            reasons=f.get("raw_file_new") or f.get("raw_file") or ""))
                    k = key_of(table, row, eff_cols)

                    # —— 三级匹配：命中即视为同一观测，改为「空列回填」而非新增
                    hit, how = None, ""
                    if k in strict_idx:
                        hit, how = strict_idx[k], "SKIP_DUP"
                    else:
                        sid = str(f.get("source_id", "")).strip()
                        lk = loose_key(table, row, eff_cols)
                        if sid and batch_src[sid] == 1 and len(src_idx.get(sid, [])) == 1:
                            hit, how = src_idx[sid][0], "SKIP_DUP_BY_SOURCE_ID"
                        elif batch_loose[lk] == 1 and len(loose_idx.get(lk, [])) == 1:
                            hit, how = loose_idx[lk][0], "SKIP_DUP_BY_LOOSE_KEY"
                    if hit is not None:
                        nb = backfill(hit, f) if apply else 0
                        qc_rows.append(dict(city=city_cn, table=table, delta=dfile,
                                            src_row=f["_src_row"], verdict=how,
                                            reasons=(f"backfilled={nb}" if nb else "")))
                        if nb:
                            action_log.append(dict(city=city_cn, table=table, action="BACKFILL",
                                                   n=nb,
                                                   detail=f"src_row={f['_src_row']} {how}"))
                        continue

                    strict_idx[k] = row
                    loose_idx.setdefault(loose_key(table, row, eff_cols), []).append(row)
                    sid = str(f.get("source_id", "")).strip()
                    if sid:
                        src_idx[sid].append(row)
                    if apply:
                        t_rows.append(row)
                    merged += 1
                if apply:
                    t_hdr = eff_cols
                file_summary.append(dict(city=city_cn, table=table, delta=dfile,
                                         rows=len(mapped), merged=merged,
                                         fixed=drep["fixed_rows"], unfixable=drep["unfixable"],
                                         note=""))

            # ---------------- STEP 1b 旧 note 前缀抽回独立列 ----------------
            # 必须在 STEP 2 之后：frequency 列由本轮合并新增
            if table == "volume_observations" and "note" in t_hdr and "frequency" in t_hdr:
                jn, jf = t_hdr.index("note"), t_hdr.index("frequency")
                n = 0
                for r in t_rows:
                    while len(r) < len(t_hdr):
                        r.append("")
                    m = FREQ_PREFIX_RE.match(r[jn])
                    if m:
                        if m.group(1) and not r[jf].strip():
                            r[jf] = m.group(1)
                        # 抽掉前缀后，清理可能残留在行首的分隔符
                        r[jn] = FREQ_PREFIX_RE.sub("", r[jn]).lstrip("|；; ").strip()
                        n += 1
                if n:
                    action_log.append(dict(city=city_cn, table=table,
                                           action="EXTRACT_FREQ_PREFIX", n=n,
                                           detail="note「frequency=X | 」前缀抽回 frequency 列"))

            # ---------------- 写回 ----------------
            if apply:
                if shadow:
                    outp = os.path.join(shadow, city_dir, "data", f"{table}.csv")
                    os.makedirs(os.path.dirname(outp), exist_ok=True)
                else:
                    os.makedirs(backup_dir, exist_ok=True)
                    shutil.copy2(tpath, os.path.join(backup_dir, f"{city_dir}__{table}.csv"))
                    outp = tpath
                with open(outp, "w", encoding="utf-8-sig", newline="") as fh:
                    w = csv.writer(fh)
                    w.writerow(t_hdr)
                    w.writerows(t_rows)

    action_log.extend(NORM_LOG)

    # ---------------- 报告 ----------------
    os.makedirs(FF, exist_ok=True)
    s1 = os.path.join(FF, "ROUND3_MERGE_QC_FILES_V3.csv")
    with open(s1, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["city", "table", "delta", "rows", "merged",
                                           "fixed", "unfixable", "note"])
        w.writeheader()
        w.writerows(file_summary)
    s2 = os.path.join(FF, "ROUND3_MERGE_QC_ROWS_V3.csv")
    with open(s2, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["city", "table", "delta", "src_row", "verdict", "reasons"])
        w.writeheader()
        w.writerows(qc_rows)
    s3 = os.path.join(FF, "ROUND3_REPAIR_ACTIONS_V3.csv")
    with open(s3, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["city", "table", "action", "n", "detail"])
        w.writeheader()
        w.writerows(action_log)

    print(f"{'[SHADOW]' if shadow else ('[APPLY]' if apply else '[DRY-RUN]')} 报告写入:")
    print("  ", os.path.relpath(s1, ROOT))
    print("  ", os.path.relpath(s2, ROOT))
    print("  ", os.path.relpath(s3, ROOT))
    print()
    print("=== 修复动作 ===")
    for a in action_log:
        print(f"  {a['city']:4s} {a['table']:26s} {a['action']:20s} n={a['n']:<4d} {a['detail'][:70]}")
    print()
    print("=== 合并统计 ===")
    tot_m = tot_r = 0
    for f in file_summary:
        tot_m += f["merged"]; tot_r += f["rows"]
        print(f"  {f['city']:4s} {f['table']:26s} {f['delta']:22s} rows={f['rows']:<5d} "
              f"merged={f['merged']:<5d} fixed={f['fixed']:<3d} unfixable={f['unfixable']}")
    print(f"  ---- 合计 rows={tot_r} merged={tot_m}")
    print()
    vc = Counter(r["verdict"] for r in qc_rows)
    print("=== 逐行判定 ===", dict(vc))
    print()
    rc = Counter()
    for r in qc_rows:
        if r["verdict"] == "REJECT":
            for x in r["reasons"].split("|"):
                rc[x.split("=")[0]] += 1
    for k, v in rc.most_common():
        print(f"  REJECT {k:28s} {v}")


if __name__ == "__main__":
    main()
