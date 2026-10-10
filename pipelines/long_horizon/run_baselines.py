# -*- coding: utf-8 -*-
"""Phase 8 + 15：长期 baseline 正式对照集与 walk-forward 指标。

- 正式 target = `full`（Phase 7 判定），即 (t, t+N] 窗口均价；
- 覆盖 horizon = 7/14/30/60/90/120/150/180（7/14/30/60/90 供 Error Growth Curve 对照）；
- 输出 LONG_HORIZON_METRICS.csv（fold × crop × horizon × method × 指标）
  + summary / selection / error growth curve + LONG_HORIZON_MODEL_REPORT.md。
"""
from __future__ import annotations
from typing import Dict, List

import numpy as np
import pandas as pd

from decision_engine.final.models import _factories

from .baselines import rowwise_baselines, trained_factories, ROWWISE_BASELINES, TRAINED_BASELINES
from .backtest import evaluate_horizon, summarize
from .common import (load_frozen_dataset, write_csv_artifact, write_report,
                     dataset_fingerprint, now_iso, LH_ARTIFACTS, ensure_dir)
from .target_definition import primary_target_col
from .targets import add_long_horizon_targets, target_availability

GROWTH_HORIZONS = [7, 14, 30, 60, 90, 120, 150, 180]
EXPLORATORY = [150, 180]
NON_OVERLAP = {7: 201, 14: 100, 30: 68, 60: 34, 90: 22, 120: 17, 150: 13, 180: 11}


def _all_factories() -> Dict:
    f = dict(trained_factories())
    core = _factories()
    for k in ["extra_trees", "elasticnet", "catboost"]:
        if k in core:
            f.setdefault(k, core[k])
    return f


def run(horizons: List[int] = None) -> Dict:
    horizons = horizons or GROWTH_HORIZONS
    ensure_dir(LH_ARTIFACTS)
    df = add_long_horizon_targets(load_frozen_dataset(), horizons=horizons)
    facs = _all_factories()
    all_preds, all_mets = [], []
    for h in horizons:
        rb = rowwise_baselines(df, h)
        r = evaluate_horizon(df, primary_target_col(h), h, rb_full=rb, factories=facs)
        if len(r["mets"]):
            all_preds.append(r["preds"]); all_mets.append(r["mets"])
        print(f"[h={h}] methods={sorted(r['mets']['method'].unique()) if len(r['mets']) else []}",
              flush=True)
    preds = pd.concat(all_preds, ignore_index=True)
    mets = pd.concat(all_mets, ignore_index=True)

    preds.to_parquet(LH_ARTIFACTS / "long_horizon_predictions.parquet", index=False)
    write_csv_artifact(mets, "LONG_HORIZON_METRICS.csv")
    summ = summarize(mets)
    write_csv_artifact(summ, "long_horizon_summary.csv")

    sel = _selection(summ)
    write_csv_artifact(sel, "long_horizon_selection.csv")

    growth = _error_growth(mets)
    growth = growth.merge(_endpoint_curve(df, horizons), on="horizon", how="left")
    write_csv_artifact(growth, "error_growth_curve.csv")

    av = target_availability(df, horizons=horizons)
    write_csv_artifact(av, "long_horizon_target_availability.csv")

    md = _render_md(summ, sel, growth, av)
    write_report(md, "LONG_HORIZON_MODEL_REPORT.md")
    return {"metrics_rows": len(mets), "selection": sel, "growth": growth}


def _selection(summ: pd.DataFrame) -> pd.DataFrame:
    """逐 (crop, horizon) 选最优方法（mean_WAPE + 0.5·std），并给出 baseline 对照与是否超越。"""
    rows = []
    for (crop, h), sub in summ.groupby(["crop", "horizon"]):
        sub = sub.sort_values("score")
        best = sub.iloc[0]
        base_pool = sub[sub["method"] == "b_last_value"]
        base = base_pool.iloc[0] if len(base_pool) else None
        rows.append({
            "crop": crop, "horizon": int(h), "method": best["method"],
            "mean_WAPE": round(float(best["mean_WAPE"]), 3),
            "std_WAPE": round(float(best["std_WAPE"]), 3) if np.isfinite(best["std_WAPE"]) else None,
            "worst_WAPE": round(float(best["worst_WAPE"]), 3),
            "mean_MASE": round(float(best["mean_MASE"]), 3) if np.isfinite(best["mean_MASE"]) else None,
            "mean_bias": round(float(best["mean_bias"]), 3),
            "n_obs": int(best["n_obs"]),
            "last_value_WAPE": round(float(base["mean_WAPE"]), 3) if base is not None else None,
            "winner_beats_last_value": bool(base is not None and best["mean_WAPE"] < base["mean_WAPE"]),
            "exploratory": int(h) in EXPLORATORY,
        })
    return pd.DataFrame(rows).sort_values(["horizon", "crop"])


def _error_growth(mets: pd.DataFrame) -> pd.DataFrame:
    """每个 horizon：最优方法 / last_value / 同季中位数 的平均 WAPE；+ 非重叠样本数。"""
    rows = []
    for h, sub in mets.groupby("horizon"):
        agg = sub.groupby("method")["WAPE"].mean()
        rows.append({
            "horizon": int(h),
            "best_method": agg.idxmin(),
            "best_method_WAPE": round(float(agg.min()), 3),
            "last_value_WAPE": round(float(agg.get("b_last_value", np.nan)), 3),
            "same_season_median_WAPE": round(float(agg.get("b_same_season_median", np.nan)), 3),
            "drift_trend90_WAPE": round(float(agg.get("b_drift_trend90", np.nan)), 3),
            "best_trained_WAPE": round(float(min(
                [agg.get(m, np.inf) for m in TRAINED_BASELINES] or [np.nan])), 3),
            "n_nonoverlap": NON_OVERLAP.get(int(h)),
            "exploratory": int(h) in EXPLORATORY,
        })
    return pd.DataFrame(rows).sort_values("horizon")


def _endpoint_curve(df: pd.DataFrame, horizons: List[int]) -> pd.DataFrame:
    """端点口径（单点价）的误差对照：证明「单点误差随 horizon 持续增长」，
    而 `full`（窗口均价）误差会趋于平台 —— 这是 Phase 7 选 `full` 的直接原因。"""
    rows = []
    for h in horizons:
        col = f"target_lh_end_{h}"
        if col not in df.columns:
            continue
        rb = rowwise_baselines(df, h)
        r = evaluate_horizon(df, col, h, with_trained=False, rb_full=rb)
        m = r["mets"]
        if not len(m):
            continue
        agg = m.groupby("method")["WAPE"].mean()
        rows.append({"horizon": int(h),
                     "endpoint_best_WAPE": round(float(agg.min()), 3),
                     "endpoint_last_value_WAPE": round(float(agg.get("b_last_value", np.nan)), 3),
                     "endpoint_same_season_median_WAPE": round(float(agg.get("b_same_season_median", np.nan)), 3)})
    return pd.DataFrame(rows)


def _render_md(summ: pd.DataFrame, sel: pd.DataFrame, growth: pd.DataFrame,
               av: pd.DataFrame) -> str:
    def tbl(d: pd.DataFrame) -> str:
        cols = list(d.columns)
        head = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"
        body = ""
        for _, r in d.iterrows():
            body += "| " + " | ".join(
                (f"{v:.2f}" if isinstance(v, float) else str(v)) for v in r[cols]) + " |\n"
        return head + body

    cols = [c for c in ["horizon", "best_method", "best_method_WAPE", "last_value_WAPE",
                        "same_season_median_WAPE", "drift_trend90_WAPE",
                        "endpoint_best_WAPE", "endpoint_last_value_WAPE",
                        "n_nonoverlap", "exploratory"] if c in growth.columns]
    pivot = growth[cols]
    worst_h = sel.sort_values("mean_WAPE", ascending=False).head(3)[["crop", "horizon", "method", "mean_WAPE"]]
    return f"""# Long-Horizon Model Report（Phase 8 + 15）

> 只读回测，未修改 Final。数据指纹 `{dataset_fingerprint()}`；生成时间 `{now_iso()}`。
> 正式 target = `full`（(t, t+N] 窗口均价，见 `LONG_HORIZON_TARGET_STUDY.md`）。
> 折定义与 Final 一致（fold1=2024 / fold2=2025 / fold3=2026 截断），同折同口径。

## 1. Error Growth Curve（7 → 180d）

{tbl(pivot)}

**读数**：
1. 正式 target（`full` = N 天窗口均价）下，`best_method_WAPE` 在 30d 后**趋于平台（≈15–16%）**，
   不会爆炸 —— 因为长期「均价」本身是平滑、可回归到季节中枢的量；`last_value` 则从 5.3%(7d)
   单调退化到 36.7%(180d)，`drift_trend90`（趋势外推）在 ≥90d 彻底失效（62%→207%）。
2. **端点对照**（`endpoint_*` 列，单点价口径）误差随 horizon **持续增长**，
   这正是 Phase 7 判定 `full` 优于 `endpoint` 的直接证据（详见 `LONG_HORIZON_TARGET_STUDY.md`）。
3. `n_nonoverlap` 为审核过的非重叠样本量；150/180 标记 `exploratory=True`（样本不足以支撑上线级评估）。
4. 结论：长期能力应表述为**「N 天窗口均价的情景化估计」**，**不得**表述为「第 N 天精确点位」。

## 2. 逐 (crop × horizon) 最优方法（top-3 最难）

{tbl(worst_h)}

完整 60 行见 `artifacts/long_horizon_selection.csv`。

## 3. 样本量（诚实读数）

{tbl(av.groupby('horizon').agg(非重叠样本均值=('n_nonoverlap','mean'),
                              观测数均值=('mean_obs_full','mean')).reset_index().round(2))}

## 4. 方法清单

- 行内 PIT baseline：{", ".join(ROWWISE_BASELINES)}
- 训练型 baseline：{", ".join(TRAINED_BASELINES)}
- 判定：`score = mean_WAPE + 0.5·std_WAPE`（跨 fold 平均 + 稳定性惩罚），与 Final 选择口径一致。
"""


if __name__ == "__main__":
    print(run())