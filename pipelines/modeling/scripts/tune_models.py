# -*- coding: utf-8 -*-
"""
P0 开源评估 4/…: Optuna 调优入口。

  python3 decision_engine/scripts/tune_models.py [--quick]

输出：decision_engine/models/registry/tuned_params.json
说明：目标函数为跨 fold WAPE 的 mean + 0.5*std（时间序列验证，禁止随机 CV）。
"""
from __future__ import annotations
import argparse
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from decision_engine.common import de_path, write_json  # noqa: E402
from decision_engine.models import train_price as tp  # noqa: E402
from decision_engine.models import tune  # noqa: E402

PLAN = [
    # (family, route, trials_full, trials_quick)
    ("hist_gradient_boosting", "per_crop", 40, 8),
    ("extra_trees", "per_crop", 25, 6),
    ("random_forest", "per_crop", 20, 5),
    ("ridge", "per_crop", 25, 6),
    ("elasticnet", "per_crop", 20, 5),
    ("lightgbm", "per_crop", 30, 8),
    ("ebm", "per_crop", 25, 6),
    ("hist_gradient_boosting", "pooled", 30, 8),
    ("extra_trees", "pooled", 20, 5),
]


def main(quick: bool = False):
    ds = pd.read_parquet(de_path("data", "processed", "decision_dataset_v1.parquet"))
    ds["date"] = pd.to_datetime(ds["date"])
    available = set(tp.make_model_factories(42).keys())
    results = []
    t0 = time.time()
    for family, route, n_full, n_quick in PLAN:
        if family not in available:
            print(f"[tune] skip {family} (not installed)")
            continue
        n_trials = n_quick if quick else n_full
        print(f"[tune] {family} route={route} trials={n_trials} ...")
        try:
            r = tune.tune(family, ds, tp.FEATURE_COLS, tp.PRIMARY_TARGET,
                          route=route, n_trials=n_trials)
            r["runtime_sec"] = round(time.time() - t0, 1)
            results.append(r)
            print(f"[tune]   best={r['best_value']:.3f} params={r['best_params']}")
        except Exception as e:
            print(f"[tune]   FAILED {type(e).__name__}: {e}")
            results.append({"family": family, "route": route, "error": str(e)[:200]})
        write_json({"results": results, "quick": quick}, de_path("models", "registry", "tuned_params.json"))
    print(f"[tune] done in {time.time()-t0:.0f}s -> models/registry/tuned_params.json")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()
    main(args.quick)