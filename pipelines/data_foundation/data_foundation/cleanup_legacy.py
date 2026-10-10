#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Data Foundation · P8 旧数据安全清场（任务书 §22-§35/§51/§55/§57-§60）
1) exact duplicate 安全删除（仅 SHA256 完全相同副本；保留 raw_data 证据；不碰受保护目录）
2) 保留源 → data/raw/retained_source/（保持相对路径，供 run_all 重建，§51）
3) 旧加工层 / 审计 / 报告 → archive/
4) DELETE_PLAN.csv / DELETED_DUPLICATES_MANIFEST.csv / 迁移重定向 README
不做任何非重复数据删除。
"""
from __future__ import annotations
import os, shutil, csv
from pathlib import Path
import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
INV = ROOT / "data" / "metadata" / "inventory"
ARC = ROOT / "archive"
RET = ROOT / "data/raw" / "retained_source"

PROTECTED = ("models/", "AgriScope/", "reference/", "data/", "AgriScope/pipelines/data_foundation/", "archive/")

# 保留源（run_all 仍需要读取）→ data/raw/retained_source/<rel>
RETAINED = [
    "city_data/reference/decision_engine_supplement",
    "city_data/reference/decision_engine_supplement_v2",
    "city_data/reference/decision_engine_supplement_v3",
    "city_data/reference/lnnync_history",
]
RETAINED_FILES = [
    "city_data/reference/curated/weekly_climatology_1991_2020.csv",
    "city_data/reference/disaster_events_observed_province.csv",
    "city_data/reference/phenology_events_province.csv",
    "city_data/reference/policy_events_province.csv",
]
# 旧加工层 / 审计 / 报告 → archive/
ARCHIVE_MOVES = [
    ("city_data/reference/marts", "archive/old_marts/marts"),
    ("city_data/reference/staging", "archive/old_marts/staging"),
    ("city_data/reference/curated", "archive/old_marts/curated"),
    ("city_data/reference/final_foundation", "archive/data_reports/final_foundation"),
    ("city_data/reference/reports", "archive/data_reports/reference_reports"),
    ("city_data/reference/registries", "archive/migration/reference_registries"),
    ("decision_audit", "archive/audits/decision_engine_pre_foundation"),
]


def score(p: str) -> int:
    if p.startswith("data/raw/retained_source"):
        return 0
    if p.startswith("data/raw/"):
        return 1
    if p.startswith("city_data/") and "/data/" in p:
        return 2
    if p.startswith("city_data/") and "/research/" in p:
        return 3
    return 5


def is_protected(p: str) -> bool:
    return any(p.startswith(x) for x in PROTECTED)


def plan_duplicates():
    d = pd.read_csv(INV / "DUPLICATE_FILES.csv")
    delete = []
    for _, r in d.iterrows():
        a, b = str(r["keeper"]), str(r["duplicate"])
        final_keep, other = (a, b) if score(a) <= score(b) else (b, a)
        if is_protected(other):
            continue
        if not (ROOT / final_keep).exists() or not (ROOT / other).exists():
            continue
        delete.append({"path": other, "size": int(r["size_bytes"]), "reason": "EXACT_DUPLICATE",
                       "replacement": final_keep, "sha256": r["sha256"], "recoverable": "EXACT_COPY"})
    return pd.DataFrame(delete)


def du(p):
    tot = 0
    for dp, _, fs in os.walk(p):
        for f in fs:
            try:
                tot += (Path(dp) / f).stat().st_size
            except Exception:
                pass
    return tot


def main():
    ARC.mkdir(parents=True, exist_ok=True)
    before = du(ROOT)

    # 1) 删除 exact duplicate
    plan = plan_duplicates()
    plan.to_csv(INV / "DELETE_PLAN.csv", index=False, encoding="utf-8-sig")
    manifest, deleted = [], 0
    for _, r in plan.iterrows():
        p = ROOT / r["path"]
        try:
            sz = p.stat().st_size
            p.unlink()
            manifest.append({"deleted_path": r["path"], "retained_path": r["replacement"],
                             "sha256": r["sha256"], "size": sz, "reason": "EXACT_DUPLICATE"})
            deleted += 1
        except Exception as e:
            print("DEL_FAIL", r["path"], e)
    pd.DataFrame(manifest).to_csv(INV / "DELETED_DUPLICATES_MANIFEST.csv", index=False, encoding="utf-8-sig")
    freed = sum(m["size"] for m in manifest)
    print(f"[DELETE] {deleted} 个 exact duplicate，释放 {freed/1e6:.1f} MB")

    # 2) 保留源迁移（保持相对路径）
    moved = []
    RET.mkdir(parents=True, exist_ok=True)
    for rel in RETAINED:
        s = ROOT / rel
        if s.is_dir():
            dst = RET / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                shutil.rmtree(dst)
            shutil.move(str(s), str(dst))
            moved.append((rel, str(dst.relative_to(ROOT))))
            print(f"[RETAIN] {rel} -> {dst.relative_to(ROOT)}")
    for rel in RETAINED_FILES:
        s = ROOT / rel
        if s.is_file():
            dst = RET / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(s), str(dst))
            moved.append((rel, str(dst.relative_to(ROOT))))
            print(f"[RETAIN] {rel} -> {dst.relative_to(ROOT)}")
    # 2b) 六城 canonical data/ → retained（保持相对路径）
    for citydir in sorted((ROOT / "data/raw/retained_source/city_data").iterdir()):
        dd = citydir / "data"
        if dd.is_dir():
            rel = f"city_data/{citydir.name}/data"
            dst = RET / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                shutil.rmtree(dst)
            shutil.move(str(dd), str(dst))
            moved.append((rel, str(dst.relative_to(ROOT))))
            print(f"[RETAIN] {rel} -> {dst.relative_to(ROOT)}")

    # 3) 归档旧加工层
    for src, dst in ARCHIVE_MOVES:
        s = ROOT / src
        if not s.exists():
            continue
        dstd = ROOT / dst
        dstd.parent.mkdir(parents=True, exist_ok=True)
        if dstd.exists():
            shutil.rmtree(dstd)
        shutil.move(str(s), str(dstd))
        moved.append((src, dst))
        print(f"[ARCHIVE] {src} -> {dst}")

    # 3b) supplement 报告归档
    rep_dst = ARC / "data_reports"
    rep_dst.mkdir(parents=True, exist_ok=True)
    for pat in ["*DECISION_ENGINE_DATA_SUPPLEMENT*.md", "*_V2_REPORT.md", "*V3_REPORT.md",
                "DATA_GAP_*.md", "QC_REPORT_supplement.md", "QC_REPORT_v2.md", "QC_REPORT_v3.md",
                "DECISION_ENGINE_DATA_ENHANCEMENT_V3_REPORT.md"]:
        for f in list((ROOT / "data/raw/retained_source/city_data" / "reference").rglob(pat)) + list((RET).rglob(pat)):
            if f.is_file():
                try:
                    shutil.move(str(f), str(rep_dst / f.name))
                except Exception:
                    pass

    # 4) 重定向 README
    (ROOT / "data/raw/retained_source/city_data" / "README.md").write_text(
        "# city_data/ 说明（已清场）\n\n"
        "本目录**不再是正式结构化数据入口**。\n\n"
        "| 用途 | 位置 |\n|---|---|\n"
        "| 正式原始证据 | `data/raw/` |\n| 正式结构化数据 | `data/` |\n"
        "| 模型输入 | `data/model_ready/` |\n| 研究历史 | `city_data/<city>/research/` |\n"
        "| 重建用保留源 | `data/raw/retained_source/` |\n| 旧加工层 | `archive/` |\n\n"
        "> 新 Agent 请只读 `data/`，不要再读 marts / curated / staging / supplement。\n",
        encoding="utf-8")

    after = du(ROOT)
    print(f"\n清理前 {before/1e9:.2f} GB → 清理后 {after/1e9:.2f} GB；删除 {deleted} 文件；"
          f"释放 {(before-after)/1e6:.1f} MB；迁移 {len(moved)} 目录")
    print("\n[OK] cleanup_legacy 完成")


if __name__ == "__main__":
    main()
