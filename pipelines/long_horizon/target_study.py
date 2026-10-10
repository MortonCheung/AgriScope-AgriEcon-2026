# -*- coding: utf-8 -*-
"""Phase 7：Long-Horizon Target 研究。

问题：长期目标应该是「第 N 天单点价」还是「N 附近未来 w 日均价」（或全程均价）？

做法（只读 + 回测，不改 Final）：
  1. 对 N ∈ {30,60,90,120} 构造 5 种候选 target；
  2. 用**同一组 baseline**（LastValue / SeasonalNaive / SameSeasonMedian）在**同一批折**上比
     MAE / WAPE / sMAPE / 跨折稳定性；
  3. 程序化判定：score = mean_WAPE + 0.5·std_WAPE（越低越好）；在最优 2% 容差内的候选按
     「更平滑、与现有 Final 口径更可比」优先（win30 > win14 > win7 > full > end）。

产出：artifacts/long_horizon_target_study.csv + reports/LONG_HORIZON_TARGET_STUDY.md
"""
from __future__ import annotations
from typing import Dict, List

import numpy as np
import pandas as pd

from .baselines import rowwise_baselines
from .backtest import evaluate_horizon
from .common import (load_frozen_dataset, write_csv_artifact, write_report,
                     dataset_fingerprint, now_iso)
from .targets import add_long_horizon_targets, target_col_name, target_availability

STUDY_HORIZONS = [30, 60, 90, 120]
COMPARE_BASELINES = ["b_last_value", "b_seasonal_naive_365", "b_same_season_median"]
CANDIDATES = [("end", None), ("win", 7), ("win", 14), ("win", 30), ("full", None)]
# 平滑度 / 可比性优先序（用于容差内 tie-break）
TIEBREAK_ORDER = ["win30", "win14", "win7", "full", "end"]


def _cand_label(kind: str, w) -> str:
    return kind if w is None else f"win{w}"


def run_study() -> Dict:
    df = add_long_horizon_targets(load_frozen_dataset(), horizons=STUDY_HORIZONS)
    rows: List[Dict] = []
    for h in STUDY_HORIZONS:
        rb = rowwise_baselines(df, h)                 # 每 horizon 只算一次，跨候选复用
        for kind, w in CANDIDATES:
            col = target_col_name(kind, h, w)
            r = evaluate_horizon(df, col, h, with_trained=False, rb_full=rb)
            mets = r["mets"]
            if not len(mets):
                continue
            mets = mets[mets["method"].isin(COMPARE_BASELINES)]
            if not len(mets):
                continue
            per_crop = mets.groupby("crop").agg(
                mean_WAPE=("WAPE", "mean"), std_WAPE=("WAPE", "std"),
                mean_sMAPE=("sMAPE", "mean"), mean_MAE=("MAE", "mean"),
                n=("n", "sum")).reset_index()
            rows.append({
                "horizon": h, "candidate": _cand_label(kind, w),
                "mean_WAPE": float(per_crop["mean_WAPE"].mean()),
                "mean_std_WAPE": float(per_crop["std_WAPE"].fillna(0).mean()),
                "mean_sMAPE": float(per_crop["mean_sMAPE"].mean()),
                "mean_MAE": float(per_crop["mean_MAE"].mean()),
                "n_total": int(per_crop["n"].sum()),
                "n_crops": int(len(per_crop)),
            })
    res = pd.DataFrame(rows)
    res["score"] = res["mean_WAPE"] + 0.5 * res["mean_std_WAPE"]

    # 跨 horizon 汇总（Phase 7 判定主口径）
    agg = (res.groupby("candidate")
           .agg(overall_mean_WAPE=("mean_WAPE", "mean"),
                overall_std_WAPE=("mean_std_WAPE", "mean"),
                overall_sMAPE=("mean_sMAPE", "mean")).reset_index())
    agg["decision_score"] = agg["overall_mean_WAPE"] + 0.5 * agg["overall_std_WAPE"]
    best = float(agg["decision_score"].min())
    tol = best * 1.02
    tied = agg[agg["decision_score"] <= tol].copy()
    tied["pref"] = tied["candidate"].map({c: i for i, c in enumerate(TIEBREAK_ORDER)})
    winner = tied.sort_values(["pref", "decision_score"]).iloc[0]["candidate"]
    agg = agg.sort_values("decision_score").reset_index(drop=True)
    agg["decision"] = np.where(agg["candidate"] == winner, "SELECTED", "")

    write_csv_artifact(res, "long_horizon_target_study_by_horizon.csv")
    write_csv_artifact(agg, "long_horizon_target_study.csv")
    av = target_availability(df, horizons=STUDY_HORIZONS)
    write_csv_artifact(av, "long_horizon_target_availability_study.csv")

    md = _render_md(res, agg, av, winner)
    write_report(md, "LONG_HORIZON_TARGET_STUDY.md")
    return {"winner": winner, "table": agg, "by_horizon": res, "availability": av}


def _render_md(res: pd.DataFrame, agg: pd.DataFrame, av: pd.DataFrame, winner: str) -> str:
    def tbl(d: pd.DataFrame) -> str:
        d = d.copy()
        cols = list(d.columns)
        head = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"
        body = ""
        for _, r in d.iterrows():
            body += "| " + " | ".join(
                (f"{v:.3f}" if isinstance(v, float) else str(v)) for v in r[cols]) + " |\n"
        return head + body

    avail = (av.groupby("horizon")
             .agg(作物数=("crop", "nunique"), 非重叠样本均值=("n_nonoverlap", "mean"),
                  全程窗口观测数均值=("mean_obs_full", "mean")).reset_index().round(2))
    return f"""# Long-Horizon Target 研究（Phase 7）

> 只读回测，未修改 Final。数据指纹 `{dataset_fingerprint()}`；生成时间 `{now_iso()}`。
> 候选 target 定义见 `models/long_horizon/targets.py`。
> 对照 baseline：{", ".join(COMPARE_BASELINES)}（同折同口径，逐 crop 平均后再跨 horizon 平均）。

## 1. 判定主表（跨 horizon 平均；score = mean_WAPE + 0.5·std_WAPE，越低越好）

{tbl(agg)}

**程序化结论：正式 Long-Horizon Target = `{winner}`**。
判定规则：取 decision_score 最低；若存在多个候选落在最优值 2% 容差内，按平滑度/可比性优先序
`{' > '.join(TIEBREAK_ORDER)}` 选择（避免单点端点噪声与 {round(1-0.677,3)*100:.0f}% 日历日缺失叠加）。

## 2. 逐 horizon × 候选对照

{tbl(res)}

## 3. 样本量（诚实读数）

{tbl(avail)}

> 注：非重叠样本随 h 迅速下降；150/180 属探索级（见 `LONG_HORIZON_FEASIBILITY_AUDIT.md`）。
> 本研究的 5 种候选口径下，端点（end）受单次观测噪声影响最大，尾窗（win）与全程（full）更平滑。
"""


if __name__ == "__main__":
    out = run_study()
    print("winner:", out["winner"])
    print(out["table"].to_string(index=False))