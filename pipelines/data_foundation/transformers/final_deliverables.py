"""汇总最终交付物（手册第 41 节的 18 项），统一输出到 city_data/reference/reports/deliverables/。"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
MARTS = ROOT / "city_data/reference/marts"
CURATED = ROOT / "city_data/reference/curated"
META = ROOT / "data/raw/metadata"
REPORTS = ROOT / "city_data/reference/reports"
OUT = REPORTS / "deliverables"
OUT.mkdir(parents=True, exist_ok=True)


def cp_parquet(src: Path, dst_name: str) -> None:
    if src.exists():
        shutil.copy2(src, OUT / dst_name)
        print(f"[OK] {dst_name}")
    else:
        print(f"[MISS] {src}")


def cp_any(src: Path, dst_name: str) -> None:
    if src.exists():
        shutil.copy2(src, OUT / dst_name)
        print(f"[OK] {dst_name}")
    else:
        print(f"[MISS] {src}")


def main() -> None:
    # 01/02 建模主表
    cp_any(MARTS / "city_crop_week_panel.csv", "01_city_crop_week_panel.csv")
    cp_parquet(MARTS / "city_crop_week_panel.parquet", "02_city_crop_week_panel.parquet")
    # 03/04 年度与事件研究
    cp_parquet(MARTS / "city_crop_year_panel.parquet", "03_city_crop_year_panel.parquet")
    cp_parquet(MARTS / "event_study_panel.parquet", "04_event_study_panel.parquet")
    # 05/06 选择与覆盖
    cp_any(REPORTS / "crop_selection_matrix.csv", "05_crop_selection_matrix.csv")
    cp_any(REPORTS / "coverage_matrix.csv", "06_coverage_matrix.csv")
    # 07 fact_price_daily（不可得 → 显式状态占位）
    pd.DataFrame([{
        "status": "not_publicly_available",
        "reason": "城市级农产品日价格需农业农村部 priceQuotation 接口鉴权；商务部源不可达；"
                  "辽宁省发改委价格监测栏目为空。未绕过任何鉴权机制。",
        "alternative": "province_crop_week_panel.parquet（省级真实周序列）；"
                       "fact_input_cost_weekly.parquet（六城市农资周价）",
    }]).to_parquet(OUT / "07_fact_price_daily.parquet", index=False)
    print("[OK] 07_fact_price_daily.parquet（状态占位：not_publicly_available）")
    # 08..13
    cp_parquet(MARTS / "fact_price_weekly.parquet", "08_fact_price_weekly.parquet")
    cp_parquet(MARTS / "fact_weather_daily.parquet", "09_fact_weather_daily.parquet")
    cp_parquet(MARTS / "fact_weather_weekly.parquet", "10_fact_weather_weekly.parquet")
    cp_parquet(MARTS / "fact_production_yearly.parquet", "11_fact_production_yearly.parquet")
    cp_parquet(MARTS / "fact_disaster_events.parquet", "12_fact_disaster_events.parquet")
    cp_parquet(MARTS / "fact_input_cost_weekly.parquet", "13_fact_input_cost_weekly.parquet")
    # 14..16
    cp_any(META / "source_registry.csv", "14_source_registry.csv")
    cp_any(REPORTS / "quality_report.json", "15_quality_report.json")
    cp_any(REPORTS / "missing_data_report.csv", "16_missing_data_report.csv")

    # 附带的补充表（非手册编号项，但有用）
    for n in ["province_crop_week_panel.parquet", "fact_disaster_reports.parquet",
              "weekly_disaster_exposure.parquet"]:
        cp_parquet(MARTS / n, "x_" + n)

    files = sorted(p.name for p in OUT.iterdir())
    print(f"\n交付目录 {OUT}")
    for f in files:
        print("  ", f)


if __name__ == "__main__":
    main()
