#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""experiments/analysis/model_selection_bias.py — 模型选择偏差审计（Task 2）。

问题：现行 `select_per_horizon` 用测试折指标选择最终模型，又在同一折评价 → 选择偏差。

本脚本实施**严格前向**的模型选择：
  评价 fold_k 时，只用**严格早于 k 的折**选择模型（含基线），再在 fold_k 上评价。
  由于 fold1 无历史折可选，前向评价覆盖 fold2(2025) 与 fold3(2026)。

同时给出：
  (a) 现行做法（同折选择+同折评价）作为对照；
  (b) 排除 `*_tuned`（超参数调优窗口不可验证）后的敏感性。

输出 -> experiments/results/selection_bias/*.csv
"""
from __future__ import annotations
import os
from pathlib import Path

EXP = Path(__file__).resolve().parent.parent
os.environ.setdefault("PROJECT_ROOT", str(EXP / "root"))
RUN = EXP / "results" / os.environ.get("FIXED_RUN", "B02_pit_fixed") / "exports"
OUT = EXP / "results" / "selection_bias"
OUT.mkdir(parents=True, exist_ok=True)

import numpy as np
import pandas as pd

TARGET = "target_mean_price_next_30d"
CITY = "沈阳"
FOLD_ORDER = ["fold1_test2024", "fold2_test2025", "fold3_test2026"]


def load():
    m = pd.read_csv(RUN / "tables" / "price_model_metrics_by_fold.csv")
    m = m[(m.city == CITY) & (m.target == TARGET)].copy()
    p = pd.read_parquet(RUN / "eval" / "price_predictions.parquet")
    p = p[(p.city == CITY) & (p.target == TARGET)].copy()
    return m, p


def score_table(m, folds, exclude_tuned=False):
    """在给定折集合上计算 (route, model, crop) 的 mean_WAPE + 0.5*std_WAPE。"""
    s = m[m.fold.isin(folds)].copy()
    if exclude_tuned:
        s = s[~s.model.str.endswith("_tuned")]
    g = (s.groupby(["route", "model", "crop"])
         .agg(mean_WAPE=("WAPE", "mean"), std_WAPE=("WAPE", "std"), n_folds=("WAPE", "count"))
         .reset_index())
    g["std_WAPE"] = g["std_WAPE"].fillna(0)
    g["score"] = g["mean_WAPE"] + 0.5 * g["std_WAPE"]
    return g


def pick(g):
    """每个作物：整体最优 + 最优基线（同池竞争）。"""
    best = g.sort_values("score").groupby("crop", as_index=False).first()[
        ["crop", "route", "model", "score"]].rename(
        columns={"route": "sel_route", "model": "sel_model", "score": "sel_score"})
    base = (g[g.route == "baseline"].sort_values("score").groupby("crop", as_index=False).first()[
        ["crop", "model", "score"]].rename(
        columns={"model": "base_model", "score": "base_score"}))
    return best.merge(base, on="crop", how="left")


def eval_on(m, fold, picks):
    """在 fold 上取所选 (model, route) 与该折最优基线的 WAPE。"""
    f = m[m.fold == fold]
    rows = []
    for _, r in picks.iterrows():
        a = f[(f.crop == r["crop"]) & (f.route == r["sel_route"]) & (f.model == r["sel_model"])]
        b = f[(f.crop == r["crop"]) & (f.route == "baseline")]
        if not len(a):
            continue
        rows.append({"fold": fold, "crop": r["crop"],
                     "sel_route": r["sel_route"], "sel_model": r["sel_model"],
                     "WAPE_sel": float(a["WAPE"].iloc[0]),
                     "WAPE_base": float(b["WAPE"].min()) if len(b) else np.nan})
    d = pd.DataFrame(rows)
    d["beats_baseline"] = d["WAPE_sel"] < d["WAPE_base"]
    d["improve_pct"] = (d["WAPE_base"] - d["WAPE_sel"]) / d["WAPE_base"] * 100
    return d


def run(exclude_tuned=False, tag=""):
    m, _ = load()
    out_rows, summ = [], []
    # ---- (a) 现行做法：同折选择 + 同折评价（对照） ----
    for k, fold in enumerate(FOLD_ORDER):
        g = score_table(m, [fold], exclude_tuned)
        picks = pick(g)
        d = eval_on(m, fold, picks)
        d["mode"] = "in_sample_selection"
        out_rows.append(d)
    # ---- (b) 严格前向：只用先前折选择 ----
    for k, fold in enumerate(FOLD_ORDER):
        if k == 0:
            continue
        prior = FOLD_ORDER[:k]
        g = score_table(m, prior, exclude_tuned)
        picks = pick(g)
        d = eval_on(m, fold, picks)
        d["mode"] = "forward_selection"
        d["selection_folds"] = "+".join(prior)
        out_rows.append(d)
    rec = pd.concat(out_rows, ignore_index=True)
    rec["candidate_pool"] = "无_tuned" if exclude_tuned else "全池"
    rec.to_csv(OUT / f"selection_records{tag}.csv", index=False, encoding="utf-8-sig")

    for (mode, fold), g in rec.groupby(["mode", "fold"]):
        summ.append({"candidate_pool": rec.candidate_pool.iloc[0], "mode": mode, "fold": fold,
                     "crops": int(len(g)), "beats": int(g.beats_baseline.sum()),
                     "mean_WAPE_sel": float(g.WAPE_sel.mean()),
                     "mean_WAPE_base": float(g.WAPE_base.mean()),
                     "mean_improve_pct": float(g.improve_pct.mean())})
    s = pd.DataFrame(summ)
    s.to_csv(OUT / f"selection_summary{tag}.csv", index=False, encoding="utf-8-sig")
    return rec, s


if __name__ == "__main__":
    print("=" * 70)
    print("候选池：全部模型（含 *_tuned）")
    r1, s1 = run(False, "")
    print(s1.round(4).to_string(index=False))

    print("\n" + "=" * 70)
    print("敏感性：排除 *_tuned（超参数调优窗口不可验证）")
    r2, s2 = run(True, "_notuned")
    print(s2.round(4).to_string(index=False))

    # 前向 vs 同折 差异
    print("\n=== 折 2025 / 2026：前向选择 vs 同折选择 ===")
    a = s1[s1["fold"].isin(["fold2_test2025", "fold3_test2026"])]
    piv = a.pivot_table(index="fold", columns="mode", values=["beats", "mean_improve_pct"])
    print(piv.round(3).to_string())
    print("\nwritten ->", OUT)
