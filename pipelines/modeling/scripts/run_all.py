# -*- coding: utf-8 -*-
"""
一键重建全流程。

  python3 decision_engine/scripts/run_all.py                # 核心流水线
  python3 decision_engine/scripts/run_all.py --with-tuning  # 含 Optuna 调参（较慢）
  python3 decision_engine/scripts/run_all.py --with-oss     # 含全部开源 benchmark（较慢）

顺序：
  snapshot → dataset → leakage tests → weather → train → intervals → risk →
  regional → replay → explain → engine demo → figures → reports → full tests
"""
from __future__ import annotations
import argparse
import subprocess
import sys
import time
from pathlib import Path

DE = Path(__file__).resolve().parents[1]
PY = sys.executable


def run(script: str, check: bool = True):
    p = DE / "scripts" / script
    if not p.exists():
        print(f"[run_all] skip (missing): {script}")
        return
    t0 = time.time()
    print(f"\n[run_all] >>> {script}", flush=True)
    r = subprocess.run([PY, str(p)], cwd=str(DE.parent))
    print(f"[run_all] <<< {script} exit={r.returncode} ({time.time()-t0:.0f}s)", flush=True)
    if check and r.returncode != 0:
        raise SystemExit(f"step failed: {script}")


def run_pytest(args: str):
    print(f"\n[run_all] >>> pytest {args}", flush=True)
    r = subprocess.run([PY, "-m", "pytest", str(DE / "tests")] + args.split(), cwd=str(DE.parent))
    return r.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-tuning", action="store_true")
    ap.add_argument("--with-oss", action="store_true")
    ap.add_argument("--with-v2", action="store_true", help="包含 Decision Engine v2（推荐/优化层）流水线")
    ap.add_argument("--skip-tests", action="store_true")
    args = ap.parse_args()

    t_all = time.time()
    run("snapshot_inputs.py")
    run("build_dataset.py")
    if not args.skip_tests:
        run_pytest("-q --no-header -x -k 'units or leakage'")
    run("build_weather_features.py")
    run("train_models.py")
    if args.with_tuning:
        run("tune_models.py")
        run("train_models.py")      # 用 tuned 参数重跑并更新对比/选择
    run("build_intervals.py")
    run("build_risk_models.py")
    run("build_regional.py")
    run("run_replay.py")
    run("explain_models.py")
    run("engine_demo.py")
    if args.with_oss:
        run("oss_statsforecast.py", check=False)
        run("oss_prophet_flaml.py", check=False)
        run("oss_sktime_darts.py", check=False)
        run("oss_tsfresh.py", check=False)
        run("oss_chronos.py", check=False)
        run("oss_autogluon.py", check=False)
        run("oss_evidently.py", check=False)
        run("oss_report.py", check=False)
    run("make_figures.py", check=False)
    run("make_reports.py")
    if args.with_oss:
        run("oss_report.py", check=False)
    if args.with_v2:
        v2 = DE / "scripts" / "run_all_v2.py"
        print("\n[run_all] >>> Decision Engine v2 流水线", flush=True)
        subprocess.run([PY, str(v2)] + (["--skip-tests"] if args.skip_tests else []),
                       cwd=str(DE.parent))
    if not args.skip_tests:
        run_pytest("-q --no-header")
    print(f"\n[run_all] 全流程完成 {time.time()-t_all:.0f}s")


if __name__ == "__main__":
    main()