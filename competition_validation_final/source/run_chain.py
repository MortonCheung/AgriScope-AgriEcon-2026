#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""experiments/run_chain.py — 独立验证环境运行入口。

用法：
    python3 run_chain.py <输出目录> [阶段列表]

阶段：leakage, models, intervals, risk, hri, backtest, hri_prefix_test

环境：
    PROJECT_ROOT = <experiments>/root （隔离，绝不指向原工程）
    代码         = <experiments>/code/src （原 AgriScope 的副本，修复在此进行）
    快照         = <experiments>/root/models/data/snapshots/final_v1 （冻结的 final_v1）
"""
from __future__ import annotations
import json
import os
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE / "root"
os.environ["PROJECT_ROOT"] = str(ROOT)
sys.path.insert(0, str(HERE / "code" / "src"))

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else (HERE / "results" / "run")
STAGES = (sys.argv[2].split(",") if len(sys.argv) > 2 else
          ["leakage", "models", "intervals", "risk", "hri", "backtest"])
OUT.mkdir(parents=True, exist_ok=True)

LOG = open(OUT / "run.log", "w", encoding="utf-8")


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    LOG.write(s + "\n")
    LOG.flush()


def stage(name, fn):
    t0 = time.time()
    log(f"\n=== [{name}] start ===")
    try:
        r = fn()
        log(f"=== [{name}] ok ({time.time()-t0:.0f}s): {json.dumps(r, ensure_ascii=False, default=str)[:600]}")
    except Exception as e:
        import traceback
        log(f"=== [{name}] FAILED: {type(e).__name__}: {e}")
        log(traceback.format_exc())
        raise
    return r


def main():
    from decision_engine.common import ROOT as DEROOT, DE
    from decision_engine.final import fcommon
    log("PROJECT_ROOT =", str(DEROOT))
    log("DE           =", str(DE))
    log("SNAPSHOT_DIR =", str(fcommon.SNAPSHOT_DIR), "exists:", fcommon.SNAPSHOT_DIR.exists())
    log("REPORTS_DIR  =", str(fcommon.REPORTS_DIR))
    log("FINAL_EVAL   =", str(fcommon.FINAL_EVAL_DIR))
    log("stages:", STAGES)

    if "leakage" in STAGES:
        from decision_engine.final import leakage
        stage("leakage", leakage.run)
    if "models" in STAGES:
        from decision_engine.final import models
        stage("price_models", lambda: models.run(cities=("沈阳", "朝阳")))
    if "intervals" in STAGES:
        from decision_engine.final import intervals
        stage("intervals", intervals.run)
    if "risk" in STAGES:
        from decision_engine.final import risk
        stage("risk(HRI/market)", risk.run)
    if "hri" in STAGES:
        from decision_engine.final import hri_stats
        stage("hri_timeseries", lambda: (hri_stats.run("沈阳"), hri_stats.run("朝阳"))[0])
    if "backtest" in STAGES:
        from decision_engine.final import backtest
        def _bt():
            p = backtest.build_panel()
            d = backtest.diagnosis(p)
            r7 = backtest.run_backtest(7, "step7")
            r30 = backtest.run_backtest(30, "step30")
            return {"panel_rows": int(len(p)), "diagnosis": d,
                    "step7_cutoffs": r7.get("n_cutoffs"), "step30_cutoffs": r30.get("n_cutoffs")}
        stage("backtest", _bt)

    # ---- 收集产物快照 ----
    exp = OUT / "exports"
    if exp.exists():
        shutil.rmtree(exp)
    exp.mkdir(parents=True)
    for src, dst in [
        (fcommon.REPORTS_DIR / "tables", exp / "tables"),
        (fcommon.MANIFEST_DIR, exp / "manifests"),
        (fcommon.FINAL_EVAL_DIR, exp / "eval"),
    ]:
        if src.exists():
            shutil.copytree(src, dst)
    log("\ncollected ->", str(exp))


if __name__ == "__main__":
    main()
