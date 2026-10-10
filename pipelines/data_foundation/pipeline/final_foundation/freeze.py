"""FDF-Task4：生成研究资产清单、Hash 与冻结快照。

输出：04_final_assets/RESEARCH_READY_ASSETS.md
      04_final_assets/DATA_FOUNDATION_MANIFEST.csv
      04_final_assets/DATA_FOUNDATION_SNAPSHOT.json
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir()) / "data/raw/retained_source/city_data"
FDF = ROOT / "reference" / "final_foundation"
OUT = FDF / "04_final_assets"
OUT.mkdir(parents=True, exist_ok=True)
SLUG = {"shenyang": "沈阳", "tieling": "铁岭", "jinzhou": "锦州",
        "dandong": "丹东", "dalian": "大连", "chaoyang": "朝阳"}
FROZEN_AT = datetime.now().isoformat(timespec="seconds")
VERSION = "AGRISCOPE_DATA_FOUNDATION_V1"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def info(p: Path):
    try:
        d = pd.read_csv(p, encoding="utf-8-sig", low_memory=False)
    except Exception:
        return None, None, None
    dcol = next((c for c in ("date", "observation_date", "year", "policy_date", "start_date")
                 if c in d.columns), None)
    s = d[dcol].astype(str) if dcol else pd.Series(dtype=str)
    sc = d["source_id"].nunique() if "source_id" in d.columns else (
        d["source"].nunique() if "source" in d.columns else "")
    return len(d), (s.min() if len(s) else ""), (s.max() if len(s) else ""), sc


def add(rows, dataset, city, path: Path, category, qc_status, note=""):
    if not path.exists():
        rows.append({"dataset": dataset, "city": city, "path": str(path.relative_to(ROOT.parent)),
                     "rows": 0, "first_date": "", "last_date": "", "sha256": "",
                     "source_count": "", "qc_status": "MISSING", "category": category,
                     "frozen_at": FROZEN_AT, "notes": note})
        return
    r = info(path)
    n, first, last, sc = (r + ("",))[:4] if isinstance(r, tuple) else (0, "", "", "")
    rows.append({"dataset": dataset, "city": city, "path": str(path.relative_to(ROOT.parent)),
                 "rows": n, "first_date": first, "last_date": last, "sha256": sha256(path),
                 "source_count": sc, "qc_status": qc_status, "category": category,
                 "frozen_at": FROZEN_AT, "notes": note})


def main():
    rows = []
    # Canonical weather: ERA5 2010-2026
    for s, cn in SLUG.items():
        p = ROOT / s / "data" / "weather_daily_era5.csv"
        add(rows, "weather_daily_era5land", cn, p, "canonical",
            "A_PASS" if p.exists() else "PENDING_RATE_LIMIT",
            "ERA5(显式models=era5) 2010-2026 8核心变量")
    for s, cn in SLUG.items():
        p = ROOT / s / "data" / "weather_extra_daily_era5.csv"
        add(rows, "weather_extra_daily_era5", cn, p, "canonical",
            "A_PASS" if p.exists() else "PENDING_RATE_LIMIT", "ERA5 扩展变量")
    for s, cn in SLUG.items():
        p = ROOT / s / "data" / "weather_daily_era5land.csv"
        add(rows, "weather_daily_era5land_temp", cn, p, "supporting", "A_PASS",
            "ERA5-Land 高分辨率温度/湿度(仅2变量)")
    # legacy
    for s, cn in SLUG.items():
        p = ROOT / s / "data" / "weather_daily.csv"
        add(rows, "weather_daily_legacy", cn, p, "legacy", "B_LEGACY_VALIDATION",
            "旧 best_match 2021-2026，保留作验证")
    # Production clean
    add(rows, "production_yearly_clean", "六城", FDF / "02_production_qc" / "production_yearly_clean.csv",
        "canonical", "A_QC_PASS", "仅含 VERIFIED/CORRECTED_UNIT/ROUNDING_CONSISTENT")
    add(rows, "PRODUCTION_QC_MASTER", "六城", FDF / "02_production_qc" / "PRODUCTION_QC_MASTER.csv",
        "supporting", "QC_AUDIT", "含全部行与判定")
    # Price
    for s, cn in SLUG.items():
        p = ROOT / s / "data" / "price_observation.csv"
        add(rows, "price_observation", cn, p, "canonical", "A_B_MIXED", "统一价格观测(30列)")
    # Supporting
    for s, cn in SLUG.items():
        for ds, cat in (("disaster_events_observed.csv", "supporting"),
                        ("policy_events.csv", "supporting"),
                        ("phenology_events.csv", "supporting"),
                        ("volume_observations.csv", "supporting")):
            add(rows, ds.replace(".csv", ""), cn, ROOT / s / "data" / ds,
                cat, "SUPPORTING")
    # Reference
    for f in sorted((ROOT / "reference").glob("*.csv")):
        add(rows, f.stem, "辽宁省(省级)", f, "reference", "REFERENCE")
    # research windows
    for f in sorted((FDF / "03_research_windows").glob("*.csv")):
        add(rows, f.stem, "六城", f, "canonical", "DERIVED")

    man = pd.DataFrame(rows)
    man.to_csv(OUT / "DATA_FOUNDATION_MANIFEST.csv", index=False, encoding="utf-8-sig")

    # snapshot
    snap = {
        "version": VERSION, "created_at": FROZEN_AT,
        "cities": list(SLUG.values()),
        "weather_baseline": "ERA5 (Open-Meteo archive, 显式 models=era5), 2010-01-01~2026-09-14, Asia/Shanghai",
        "weather_variant": "ERA5-Land (温度/湿度, 高分辨率)",
        "production_qc_version": "production_yearly_clean v1 (2026-09-22)",
        "core_crop_version": "CORE_CROP_CANDIDATES_FINAL v1",
        "datasets": man.groupby("category")["dataset"].nunique().to_dict(),
        "row_counts": {c: int(man[man["category"] == c]["rows"].fillna(0).sum())
                       for c in man["category"].unique()},
        "weather_status": {
            "era5_complete_cities": [r["city"] for _, r in man.iterrows()
                                     if r["dataset"] == "weather_daily_era5land" and r["qc_status"] == "A_PASS"],
            "era5_pending_cities": [r["city"] for _, r in man.iterrows()
                                    if r["dataset"] == "weather_daily_era5land" and r["qc_status"] != "A_PASS"],
            "note": "Open-Meteo 免费额度每小时请求上限；脚本可断点续跑 build_weather_era5.py",
        },
        "known_gaps": [
            "除大连外四城无日/周频市场成交量（官方不公开）",
            "铁岭/丹东连续官方城市价格稀疏（多以县级/产地价补）",
            "大连2024-2026、锦州/丹东2023-2026 官方量化灾情未公开",
            "物候以关键节点为主，2021-2023样本薄",
            "生产 14 行 UNRESOLVED 已排除出模型",
        ],
    }
    (OUT / "DATA_FOUNDATION_SNAPSHOT.json").write_text(
        json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")

    # assets md
    canon = man[man["category"] == "canonical"]
    L = ["# RESEARCH_READY_ASSETS — 正式研究资产清单", "",
         f"> 版本 {VERSION}　冻结于 {FROZEN_AT}", "",
         "## 1. Canonical（正式研究默认使用）", "",
         "| 数据集 | 城市 | 行数 | 时间范围 | QC | 路径 |", "|---|---|---|---|---|---|"]
    for _, r in canon.iterrows():
        L.append(f"| {r['dataset']} | {r['city']} | {r['rows']} | {r['first_date']}~{r['last_date']} | {r['qc_status']} | {r['path']} |")
    L += ["", "## 2. Supporting（辅助研究）", "",
          "| 数据集 | 城市 | 行数 | 时间范围 |", "|---|---|---|---|"]
    sup = man[man["category"] == "supporting"]
    for ds, g in sup.groupby("dataset"):
        L.append(f"| {ds} | {len(g)}城 | {int(g['rows'].fillna(0).sum())} | {g['first_date'].min()}~{g['last_date'].max()} |")
    L += ["", "## 3. Reference（不可当城市观测）", "",
          "| 数据集 | 行数 | 路径 |", "|---|---|---|"]
    for _, r in man[man["category"] == "reference"].iterrows():
        L.append(f"| {r['dataset']} | {r['rows']} | {r['path']} |")
    L += ["", "## 4. Legacy（保留、不删除）", "",
          "| 数据集 | 城市 | 行数 | 说明 |", "|---|---|---|---|"]
    for _, r in man[man["category"] == "legacy"].iterrows():
        L.append(f"| {r['dataset']} | {r['city']} | {r['rows']} | {r['notes']} |")
    L += ["", "## 5. 已知限制", ""] + [f"- {g}" for g in snap["known_gaps"]]
    (OUT / "RESEARCH_READY_ASSETS.md").write_text("\n".join(L), encoding="utf-8")

    print(f"[OK] DATA_FOUNDATION_MANIFEST.csv {man.shape}")
    print(f"[OK] DATA_FOUNDATION_SNAPSHOT.json")
    print(f"[OK] RESEARCH_READY_ASSETS.md")
    print("\n=== 天气完成情况 ===")
    w = man[man["dataset"] == "weather_daily_era5land"]
    print(w[["city", "rows", "first_date", "last_date", "qc_status"]].to_string(index=False))


if __name__ == "__main__":
    main()
