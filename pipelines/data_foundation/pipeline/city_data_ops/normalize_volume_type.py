# -*- coding: utf-8 -*-
"""volume_observations.volume_type 跨城规范化（AgriScope）

问题：六城 volume_type 使用了同义异名 token，导致该列无法跨城聚合，
也无法与前端枚举对齐。实测取值：
    规范值      : daily_transaction / market_inflow / market_supply / inventory /
                  livestock_heads / annual_throughput / storage_volume / purchase_volume / market_capacity
    非规范 token: inflow(255) / transaction(19) / trade(7) / sales(5) / supply(6) / stock(4) / ''(4)

规则（三级，全部可审计）：
  L1  token 直映射          inflow→market_inflow, supply→market_supply, stock→inventory
  L2  transaction 按 note 的「周期=」标记分流   日/集日/丰果期→daily_transaction；年→annual_throughput
  L3  trade / sales 逐行显式裁定（12 行，见 ROW_OVERRIDE，依据见各行 note 原文）

附带：把旧合并遗留的 note 前缀「frequency=X | 」抽出为独立 frequency 值。

用法：
  python3 tools/pipeline/city_data_ops/normalize_volume_type.py            # dry-run，只出账本
  python3 tools/pipeline/city_data_ops/normalize_volume_type.py --apply    # 写入
"""
from __future__ import annotations
from pathlib import Path

import argparse
import csv
import datetime as dt
import os
import re
import shutil

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
CITY_DIR = os.path.join(ROOT, "data/raw/retained_source/city_data")
ARCHIVE = os.path.join(ROOT, "archive")
FF = os.path.join(CITY_DIR, "reference", "final_foundation")
TS = dt.datetime.now().strftime("%Y%m%d_%H%M%S")

CITIES = {"shenyang": "沈阳", "dalian": "大连", "tieling": "铁岭",
          "chaoyang": "朝阳", "jinzhou": "锦州", "dandong": "丹东"}

STD_TYPES = {"daily_transaction", "weekly_transaction", "monthly_transaction",
             "market_inflow", "market_supply", "purchase_volume", "storage_volume",
             "annual_throughput", "market_capacity", "inventory", "livestock_heads",
             "procurement"}

TOKEN_MAP = {
    "inflow": ("market_inflow", "同义 token：inflow ≡ market_inflow"),
    "supply": ("market_supply", "同义 token：supply ≡ market_supply"),
    "stock": ("inventory", "同义 token：stock ≡ inventory（时点库存/储备）"),
}

# L3：trade / sales 逐行显式裁定。键 = (城市, 日期, volume, volume_unit)
ROW_OVERRIDE = {
    # —— 锦州 trade（7 行）：依据 note 原文判定日/年口径
    ("锦州", "2023-09-08", "1000", "吨"): ("daily_transaction", "note『日均流转交易蔬菜1000吨左右』，值对应日均口径"),
    ("锦州", "2025-11-17", "30", "万斤"): ("daily_transaction", "note『日均交易量30至40万斤（区间下限）』"),
    ("锦州", "2018-11-29", "10", "亿公斤"): ("annual_throughput", "note『年成交量10亿公斤』市场集群口径"),
    ("锦州", "2022-12-31", "48", "万吨"): ("annual_throughput", "note『年交易量48万吨』"),
    ("锦州", "2024-12-31", "12", "亿公斤"): ("annual_throughput", "note『蔬菜年成交量12亿公斤』"),
    ("锦州", "2025-07-11", "5", "亿公斤"): ("annual_throughput", "note『年交易量超5亿公斤』"),
    ("锦州", "2023-09-12", "40", "万吨"): ("annual_throughput", "note『年蔬菜交易量达40万吨』县内五大市场合计"),
    # —— 锦州 sales（4 行）
    ("锦州", "2022-07-14", "1000", "吨"): ("daily_transaction", "note『日均销售量可达1000余吨』"),
    ("锦州", "2022-11-02", "300", "吨"): ("daily_transaction", "note『近三天…销售量300多吨（近三天均值）』，日频口径"),
    ("锦州", "2023-09-08", "1500", "吨"): ("daily_transaction", "note『日均销量1500吨左右』"),
    ("锦州", "2024-04-22", "1500", "吨"): ("daily_transaction", "note『日均销量1500吨左右』"),
    # —— 丹东 sales（1 行）
    ("丹东", "2026-09-16", "2", "万斤"): ("daily_transaction", "note『每天能走货2万斤左右』日走货量"),
}

# 空 volume_type 的定点补全：原文口径已在 note 中明示，按 source_id 显式落列
EMPTY_FILL = {
    "DD-VOL-2022-0315-01": ("inventory", "原文『全市当前商业库存米面1800吨』，存量快照口径"),
    "DD-VOL-2022-0315-02": ("inventory", "原文『全市当前商业库存…食用油200吨』，存量快照口径"),
    "DD-VOL-2022-0315-03": ("inventory", "原文『全市当前商业库存…肉类120吨』，存量快照口径"),
    "DD-VOL-2022-0315-04": ("inventory", "原文『全市当前商业库存…蔬菜660吨』，存量快照口径"),
}

PERIOD_RE = re.compile(r"周期=([^；;|]{1,10})")
FREQ_PREFIX_RE = re.compile(r"^frequency=([^；;|]*)\s*\|\s*")


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        return [], []
    return [h.lstrip("\ufeff") for h in rows[0]], rows[1:]


def classify(city_cn, row, hdr):
    """返回 (新值, 依据, 规则级)。已是规范值 → (None, '', '')"""
    d = {h: (row[i].strip() if i < len(row) else "") for i, h in enumerate(hdr)}
    vt = d.get("volume_type", "")
    if vt in STD_TYPES:
        return None, "", ""
    if not vt:
        ef = EMPTY_FILL.get(d.get("source_id", ""))
        if ef:
            return ef[0], ef[1], "L0_EMPTY_FILL"
        return None, "", ""

    key = (city_cn, d.get("date", ""), d.get("volume", ""), d.get("volume_unit", ""))
    if key in ROW_OVERRIDE:
        new, why = ROW_OVERRIDE[key]
        return new, why, "L3_ROW"

    if vt in TOKEN_MAP:
        new, why = TOKEN_MAP[vt]
        return new, why, "L1_TOKEN"

    if vt == "transaction":
        m = PERIOD_RE.search(d.get("note", ""))
        per = m.group(1) if m else ""
        if per.startswith("年"):
            return "annual_throughput", f"note『周期={per}』→ 年度口径", "L2_PERIOD"
        if per.startswith("日"):
            return "daily_transaction", f"note『周期={per}』→ 日频口径", "L2_PERIOD"
        return None, f"UNRESOLVED 周期标记={per!r}", "L2_PERIOD"

    if vt in ("trade", "sales"):
        return "daily_transaction", f"『{vt}』未命中行级裁定，按日频默认（需复核）", "L3_DEFAULT"

    return None, f"UNRESOLVED token={vt!r}", ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    apply = args.apply

    ledger, actions = [], []
    backup_dir = os.path.join(ARCHIVE, "backups", f"volume_type_norm_{TS}")

    for city_dir, city_cn in CITIES.items():
        p = os.path.join(CITY_DIR, city_dir, "data", "volume_observations.csv")
        if not os.path.exists(p):
            continue
        hdr, rows = read_csv(p)
        if "volume_type" not in hdr:
            continue
        jv = hdr.index("volume_type")
        has_freq = "frequency" in hdr
        jf = hdr.index("frequency") if has_freq else -1
        jn = hdr.index("note") if "note" in hdr else -1

        changed = freq_filled = 0
        for i, row in enumerate(rows):
            while len(row) < len(hdr):
                row.append("")
            old = row[jv].strip()
            new, why, lvl = classify(city_cn, row, hdr)
            if new and new != old:
                row[jv] = new
                # 空值补全时同步补 frequency（原文为时点快照）
                if lvl == "L0_EMPTY_FILL" and jf >= 0 and not row[jf].strip():
                    row[jf] = "event_point"
                changed += 1
                ledger.append(dict(city=city_cn, date=row[hdr.index("date")],
                                   market_name=row[hdr.index("market_name")],
                                   crop=row[hdr.index("crop")], volume=row[hdr.index("volume")],
                                   volume_unit=row[hdr.index("volume_unit")],
                                   before=old, after=new, rule=lvl, reason=why))
            # 抽出 note 里的 frequency=X 前缀
            if jn >= 0 and jf >= 0:
                m = FREQ_PREFIX_RE.match(row[jn])
                if m:
                    if m.group(1) and not row[jf].strip():
                        row[jf] = m.group(1)
                        freq_filled += 1
                    row[jn] = FREQ_PREFIX_RE.sub("", row[jn]).lstrip("|；; ").strip()
        if changed or freq_filled:
            actions.append(dict(city=city_cn, file=os.path.relpath(p, ROOT),
                                type_changed=changed, freq_filled=freq_filled))
            if apply:
                os.makedirs(backup_dir, exist_ok=True)
                shutil.copy2(p, os.path.join(backup_dir, f"{city_dir}__volume_observations.csv"))
                with open(p, "w", encoding="utf-8-sig", newline="") as fh:
                    w = csv.writer(fh)
                    w.writerow(hdr)
                    w.writerows(rows)

    os.makedirs(FF, exist_ok=True)
    lp = os.path.join(FF, "VOLUME_TYPE_NORMALIZATION_LEDGER_V3.csv")
    with open(lp, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["city", "date", "market_name", "crop", "volume",
                                           "volume_unit", "before", "after", "rule", "reason"])
        w.writeheader()
        w.writerows(ledger)

    print(f"{'[APPLY]' if apply else '[DRY-RUN]'}  账本: {os.path.relpath(lp, ROOT)}")
    print()
    print(f"{'city':6s} {'改 type':>8s} {'补 freq':>8s}")
    for a in actions:
        print(f"{a['city']:6s} {a['type_changed']:>8d} {a['freq_filled']:>8d}")
    print()
    print(f"合计改写 volume_type {len(ledger)} 行")
    from collections import Counter
    print("规则分布:", dict(Counter(x["rule"] for x in ledger)))
    print("映射分布:", dict(Counter(f"{x['before']}→{x['after']}" for x in ledger)))
    un = [x for x in ledger if not x["after"]]
    if un:
        print("!! 未解析:", len(un))
        for x in un[:20]:
            print("   ", x["city"], x["date"], x["before"], x["reason"])


if __name__ == "__main__":
    main()
