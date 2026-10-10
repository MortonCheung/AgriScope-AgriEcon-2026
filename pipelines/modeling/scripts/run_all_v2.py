# -*- coding: utf-8 -*-
"""
Decision Engine v2 一键重建 / 验证。

  python3 decision_engine/scripts/run_all_v2.py              # 核心 v2 流水线
  python3 decision_engine/scripts/run_all_v2.py --full       # 含历史推荐回测（较慢）
  python3 decision_engine/scripts/run_all_v2.py --skip-tests

顺序：
  v2/v3 快照 → 农事日历 → 完整示例与 10 案例 → 优化产物（Pareto/压力/组合回测/每日信号）
  → [--full: 历史推荐回测] → 图表 → 报告 → 验收自检 → 测试
"""
from __future__ import annotations
import argparse
import subprocess
import sys
import time
from pathlib import Path

DE = Path(__file__).resolve().parents[1]
PY = sys.executable


def run(script: str, extra: str = ""):
    p = DE / "scripts" / script
    if not p.exists():
        print(f"[v2] skip (missing): {script}")
        return
    t0 = time.time()
    print(f"\n[v2] >>> {script} {extra}", flush=True)
    cmd = [PY, str(p)] + (extra.split() if extra else [])
    r = subprocess.run(cmd, cwd=str(DE.parent))
    print(f"[v2] <<< {script} exit={r.returncode} ({time.time()-t0:.0f}s)", flush=True)
    if r.returncode != 0:
        print(f"[v2] !! {script} 失败（继续后续步骤）")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="包含历史推荐回测")
    ap.add_argument("--skip-tests", action="store_true")
    a = ap.parse_args()
    t0 = time.time()

    run("snapshot_inputs.py", "--version v2 --globs-key snapshot_globs_v2 --manifest input_manifest_v2.csv")
    run("build_calendar_v2.py")
    run("run_v2_examples.py")
    run("build_optimization_v2.py", "--city 沈阳")
    if a.full:
        run("run_recommender_backtest.py", "--cities 沈阳,朝阳 --step-days 30")
    run("make_figures_v2.py")
    run("make_reports_v2.py")
    run("check_acceptance_v2.py")
    if not a.skip_tests:
        print("\n[v2] >>> pytest", flush=True)
        subprocess.run([PY, "-m", "pytest", str(DE / "tests"), "-q", "--no-header"], cwd=str(DE.parent))
    print(f"\n[v2] 完成 {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()