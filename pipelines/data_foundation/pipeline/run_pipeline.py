#!/usr/bin/env python3
"""辽宁农业气象风险数据底座 —— 统一流水线入口（手册第 64 节）。

用法：
    python run_pipeline.py all            # 全流程（默认，支持断点续跑）
    python run_pipeline.py discover       # 地理/市场主数据
    python run_pipeline.py prices         # 价格层（第一阶段数据再定位）
    python run_pipeline.py weather        # 气象层（核心 + 扩展 + 土壤）
    python run_pipeline.py production     # 生产层（年鉴 + 生产条件）
    python run_pipeline.py disaster       # 灾害层（气象阈值 + 官方文本）
    python run_pipeline.py pests          # 病虫害
    python run_pipeline.py macro          # 宏观（成品油等）
    python run_pipeline.py dimensions     # 日历/作物元数据
    python run_pipeline.py panels         # 面板与特征工程
    python run_pipeline.py validate       # 质量检查与覆盖/清单
    python run_pipeline.py report         # 汇总交付物与审阅包

断点续跑：所有采集器写入前检查目标文件，已成功保存的原始数据不会重复请求。
单步失败不阻塞整体（手册第 37 节）。
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
PY = sys.executable

STEPS: dict[str, list[tuple[str, str]]] = {
    "discover": [("市场与地理主数据", "AgriScope/pipelines/data_foundation/collectors/build_metadata.py")],
    "prices": [("价格层再定位（省级基准 + 农资成本）", "AgriScope/pipelines/data_foundation/transformers/liaoning_agri_transform.py")],
    "weather": [
        ("气象核心变量采集", "AgriScope/pipelines/data_foundation/collectors/weather.py"),
        ("气象扩展变量与土壤分层采集", "AgriScope/pipelines/data_foundation/collectors/weather_extend.py"),
        ("气象转换（日/周/气候异常）", "AgriScope/pipelines/data_foundation/transformers/weather_transform.py"),
        ("土壤与扩展变量转换", "AgriScope/pipelines/data_foundation/transformers/weather_soil_transform.py"),
    ],
    "production": [
        ("统计年鉴下载", "AgriScope/pipelines/data_foundation/collectors/statistical_yearbook.py"),
        ("年鉴解析（播种面积/产量/单产）", "AgriScope/pipelines/data_foundation/parsers/extract_production.py"),
        ("年鉴解析（农业生产条件）", "AgriScope/pipelines/data_foundation/parsers/extract_agri_conditions.py"),
    ],
    "disaster": [
        ("灾害相关公开信息采集", "AgriScope/pipelines/data_foundation/collectors/disaster.py"),
        ("极端事件识别与事件研究面板", "AgriScope/pipelines/data_foundation/transformers/build_events.py"),
    ],
    "pests": [
        ("病虫害情报采集", "AgriScope/pipelines/data_foundation/collectors/pests.py"),
        ("病虫害结构化", "AgriScope/pipelines/data_foundation/parsers/pest_parser.py"),
    ],
    "macro": [
        ("成品油调价公告采集", "AgriScope/pipelines/data_foundation/collectors/fuel_price.py"),
        ("成品油价格解析", "AgriScope/pipelines/data_foundation/parsers/fuel_price_parser.py"),
    ],
    "dimensions": [("日历与作物元数据", "AgriScope/pipelines/data_foundation/transformers/build_dimensions.py")],
    "panels": [
        ("作物元数据", "AgriScope/pipelines/data_foundation/transformers/build_crops.py"),
        ("建模面板与滞后特征", "AgriScope/pipelines/data_foundation/transformers/build_panels.py"),
        ("作物选择矩阵", "AgriScope/pipelines/data_foundation/transformers/build_selection.py"),
    ],
    "validate": [
        ("数据质量检查", "AgriScope/pipelines/data_foundation/validators/quality_check.py"),
        ("数据源登记与占位表", "AgriScope/pipelines/data_foundation/transformers/build_registry.py"),
        ("覆盖矩阵/清单/评级/候选", "AgriScope/pipelines/data_foundation/transformers/build_coverage.py"),
    ],
    "report": [
        ("汇总最终交付物", "AgriScope/pipelines/data_foundation/transformers/final_deliverables.py"),
        ("轻量审阅包", "AgriScope/pipelines/data_foundation/transformers/build_review_bundle.py"),
    ],
}

ORDER = ["discover", "prices", "weather", "production", "disaster", "pests",
         "macro", "dimensions", "panels", "validate", "report"]


def run_step(title: str, script: str) -> bool:
    path = ROOT / script
    if not path.exists():
        print(f"  [SKIP] {script} 不存在")
        return False
    print(f"\n{'=' * 70}\n>> {title}\n   {script}\n{'=' * 70}", flush=True)
    t0 = time.time()
    r = subprocess.run([PY, str(path)], cwd=str(ROOT))
    print(f"<< {title} -> {'OK' if r.returncode == 0 else 'FAILED'} ({(time.time()-t0):.1f}s)", flush=True)
    return r.returncode == 0


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    targets = ORDER if cmd == "all" else ([cmd] if cmd in STEPS else None)
    if targets is None:
        print(__doc__)
        return

    print(f"流水线：{cmd} -> {targets}")
    summary = {}
    for t in targets:
        ok = True
        for title, script in STEPS[t]:
            ok = run_step(title, script) and ok
        summary[t] = "OK" if ok else "PARTIAL/FAILED"

    print(f"\n{'=' * 70}\n流水线执行结果\n{'=' * 70}")
    for k, v in summary.items():
        print(f"  {k:12s} {v}")
    print("\n交付物 : city_data/reference/reports/deliverables/")
    print("审阅包 : city_data/reference/reports/review_bundle.zip")
    print("报告   : city_data/reference/reports/FINAL_REPORT.md")


if __name__ == "__main__":
    main()
