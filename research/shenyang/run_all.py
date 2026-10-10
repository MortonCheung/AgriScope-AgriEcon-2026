"""run_all.py — 顺序运行 shenyang 全部分析步骤（STEP 00~27）。

用法：
  .venv/bin/python run_all.py                # 运行全部
  .venv/bin/python run_all.py --steps 01,07  # 只运行指定步骤（编号 00~17）
  .venv/bin/python run_all.py --skip 14      # 跳过指定步骤

说明：
  - 各步骤独立可重跑，输出追加/覆盖（results_registry 按 result_id 覆盖）；
  - 步骤失败不中断后续，最后打印汇总；
  - 原始数据仓库只读；全部产物写入本目录。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENV_PY = HERE / ".venv" / "bin" / "python"

# 顺序即研究流程（STEP 号 = 模块序号）
MODULES = [
    "00_inventory",        # STEP 01-03 数据清单/快照/字典
    "01_build_panel",      # STEP 04   日度核心 Panel
    "02_data_qa",          # STEP 05-06 QA 报告
    "03_descriptive",      # STEP 07-09 描述统计 / 季节 / 异常
    "04_deseasonalize",    # STEP 07-09 去季节化（hist + stl）
    "05_lag_analysis",     # STEP 10   天气—量价滞后
    "06_threshold",        # STEP 11   非线性与临界点
    "07_event_study",      # STEP 12   全历史 Event Study
    "08_case_2026",        # STEP 13   2026-07 暴雨案例
    "09_milestone1",       # STEP 14   Milestone 1 报告
    "10_transmission",     # STEP 15-17 传导机制
    "11_crop_heterogeneity",  # STEP 18-20 异质性/指纹/韧性
    "12_phenology",        # STEP 21   物候解释
    "13_yearly_production",   # STEP 22   年度生产
    "14_prediction",       # STEP 23   预测模型
    "15_model_explain",    # STEP 24   模型解释
    "16_counterfactual",   # STEP 25-26 反事实平行世界
    "17_robustness",       # STEP 27   稳健性
]


def main() -> int:
    ap = argparse.ArgumentParser(description="shenyang 分析全流程")
    ap.add_argument("--steps", help="逗号分隔的步骤号，如 01,07,14")
    ap.add_argument("--skip", help="逗号分隔的要跳过的步骤号")
    args = ap.parse_args()

    want = {f"{i:02d}" for i in range(len(MODULES))}
    if args.steps:
        want = set(args.steps.split(","))
    if args.skip:
        want -= set(args.skip.split(","))

    py = str(VENV_PY) if VENV_PY.exists() else sys.executable
    status, t0 = {}, time.time()
    for i, mod in enumerate(MODULES):
        num = f"{i:02d}"
        if num not in want:
            print(f"[skip] {num} {mod}")
            continue
        print(f"\n=== {num} {mod} ===")
        t = time.time()
        r = subprocess.run([py, str(HERE / "src" / f"{mod}.py")], cwd=HERE)
        status[mod] = "OK" if r.returncode == 0 else f"FAIL({r.returncode})"
        print(f"--- {mod}: {status[mod]} ({time.time() - t:.1f}s)")

    print("\n" + "=" * 60)
    print("汇总（FAIL 不影响后续步骤，但对应阶段结论无效）:")
    for m, s in status.items():
        print(f"  {m:26s} {s}")
    print(f"总耗时 {time.time() - t0:.1f}s")
    return 0 if all(v == "OK" for v in status.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
