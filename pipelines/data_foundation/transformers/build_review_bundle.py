"""生成轻量审阅包 review_bundle/ 与 review_bundle.zip（手册第 48 节）。

目标 < 20MB：只放报告、清单、覆盖/质量文件，以及每张核心表的分层抽样 200 行。
用户可直接把 zip 上传给 ChatGPT 审阅，无需上传全部原始数据。
"""
from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
MARTS = ROOT / "city_data/reference/marts"
CURATED = ROOT / "city_data/reference/curated"
META = ROOT / "data/raw/metadata"
REPORTS = ROOT / "city_data/reference/reports"
BUNDLE = REPORTS / "review_bundle"
SAMPLES = BUNDLE / "samples"

# 直接复制的说明与清单文件
COPY = [
    REPORTS / "FINAL_REPORT.md",
    REPORTS / "DATA_DICTIONARY.md",
    REPORTS / "NOT_ACQUIRED.md",
    REPORTS / "data_manifest.csv",
    REPORTS / "source_registry.csv" if (REPORTS / "source_registry.csv").exists() else META / "source_registry.csv",
    REPORTS / "coverage_matrix.csv",
    REPORTS / "city_data_coverage.csv",
    REPORTS / "crop_data_coverage.csv",
    REPORTS / "candidate_crops.csv",
    REPORTS / "data_quality_grades.csv",
    REPORTS / "missing_data_report.csv",
    REPORTS / "crop_selection_matrix.csv",
    REPORTS / "quality_report.json",
]

# 需要抽样的事实表
TABLES = [
    MARTS / "fact_weather_daily.parquet",
    MARTS / "fact_weather_extra_daily.parquet",
    MARTS / "fact_weather_weekly.parquet",
    MARTS / "fact_soil_daily.parquet",
    MARTS / "fact_price_weekly.parquet",
    MARTS / "fact_input_cost_weekly.parquet",
    MARTS / "fact_production_yearly.parquet",
    MARTS / "fact_agri_conditions.parquet",
    MARTS / "fact_disaster_events.parquet",
    MARTS / "fact_fuel_price.parquet",
    MARTS / "city_crop_week_panel.parquet",
    MARTS / "province_crop_week_panel.parquet",
    MARTS / "event_study_panel.parquet",
    CURATED / "province_price_weekly.parquet",
]


def stratified_sample(df: pd.DataFrame, n: int = 200) -> pd.DataFrame:
    """按 city / crop（若存在）分层抽样，保证各城市各作物都有代表。"""
    keys = [c for c in ("city", "crop") if c in df.columns]
    if not keys or len(df) <= n:
        return df.head(n)
    try:
        per = max(1, n // max(df.groupby(keys, dropna=False).ngroups, 1))
        out = df.groupby(keys, dropna=False, group_keys=False).apply(
            lambda g: g.head(per), include_groups=False)
        return out.head(n) if len(out) > n else out
    except Exception:
        return df.head(n)


def main() -> None:
    if BUNDLE.exists():
        shutil.rmtree(BUNDLE)
    SAMPLES.mkdir(parents=True, exist_ok=True)

    for p in COPY:
        if p and p.exists():
            shutil.copy2(p, BUNDLE / p.name)
            print(f"[OK] {p.name}")

    for t in TABLES:
        if not t.exists():
            continue
        try:
            df = pd.read_parquet(t)
        except Exception:
            continue
        s = stratified_sample(df, 200)
        out = SAMPLES / (t.stem + "_sample200.csv")
        s.to_csv(out, index=False, encoding="utf-8-sig")
        print(f"[OK] 抽样 {t.stem}: {len(s)}/{len(df)} 行")

    # 打包
    zpath = REPORTS / "review_bundle.zip"
    if zpath.exists():
        zpath.unlink()
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(BUNDLE.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(BUNDLE.parent))
    size = zpath.stat().st_size / 1024 / 1024
    print(f"\n[OK] review_bundle.zip {size:.2f} MB（目标 <20MB）")


if __name__ == "__main__":
    main()
