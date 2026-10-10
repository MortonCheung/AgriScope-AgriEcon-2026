# -*- coding: utf-8 -*-
"""F3/F4: Final Price Model —— baseline 重建 + 逐作物/多 horizon 训练与严格 OOT 选择。

规则：
  - 特征白名单 FINAL_FEATURE_COLS（不含 volume：volume 不在 data/model_ready/）；
  - walk-forward expanding（复用 backtest.FOLDS，测试期目标为 NaN 的样本自动剔除）；
  - 基线（last_value / MA7 / MA30 / seasonal_median / previous_year_same_period）与 ML 同池竞争；
  - 选择标准：mean_WAPE + 0.5·std_WAPE（平均 + 稳定性惩罚），打不过 baseline 就用 baseline；
  - 多 horizon：7/14/30/60/90，逐 horizon 独立选择（不假设同一模型全程有效）。
"""
from __future__ import annotations
from typing import Dict, List

import numpy as np
import pandas as pd

from decision_engine.models.backtest import FOLDS, fold_mask, metrics_table, prev_year_window_mean
from decision_engine.models.train_price import (FEATURE_COLS, baseline_predictions,
                                                run_ml_backtest, summarize_metrics)
from decision_engine.final.fcommon import (FINAL_EVAL_DIR, REPORTS_DIR, SNAPSHOT_DIR,
                                           ensure_dir, write_json, now_stamp, MODEL_VERSION,
                                           DATA_VERSION, git_fingerprint)
from decision_engine.models.train_price import make_model_factories, make_tuned_factories

HORIZONS = [7, 14, 30, 60, 90]
PRIMARY_H = 30

# 只剔除 volume（不在 model_ready）；其余沿用已验证无泄漏的特征集
FINAL_FEATURE_COLS: List[str] = [c for c in FEATURE_COLS if not c.startswith("volume")]

CORE_MODELS = ["elasticnet", "extra_trees", "catboost"]


def _factories():
    allf = make_model_factories(include_optional=True)
    tuned = make_tuned_factories()
    out = {}
    for k in CORE_MODELS:
        if k in allf:
            out[k] = allf[k]
    for k in ["elasticnet_tuned", "extra_trees_tuned"]:
        if k in tuned:
            out[k] = tuned[k]
    return out


def run_horizon(ds: pd.DataFrame, h: int, factories: Dict) -> Dict[str, pd.DataFrame]:
    target = f"target_mean_price_next_{h}d"
    d = ds.copy()
    if target not in d.columns:
        return {}
    preds_ml, mets_ml, rt = run_ml_backtest(d, FINAL_FEATURE_COLS, target, factories,
                                            route="per_crop", folds=FOLDS)
    preds_pl, mets_pl, _ = run_ml_backtest(d, FINAL_FEATURE_COLS, target, factories,
                                           route="pooled", folds=FOLDS)
    bpreds = baseline_predictions(d, target, folds=FOLDS)
    # 基线指标
    bmets = []
    for (model, crop, fold_), sub in bpreds.groupby(["model", "crop", "fold"]):
        mm = metrics_table(sub["actual"].values, sub["prediction"].values,
                           anchor=sub["anchor_price"].values)
        mm.update({"model": model, "route": "baseline", "crop": crop, "fold": fold_,
                   "target": target})
        bmets.append(mm)
    bmets = pd.DataFrame(bmets)
    mets = pd.concat([mets_ml, mets_pl, bmets], ignore_index=True)
    preds = pd.concat([preds_ml, preds_pl, bpreds], ignore_index=True)
    return {"preds": preds, "mets": mets, "runtime": rt}


def fold_metadata(ds: pd.DataFrame) -> pd.DataFrame:
    """§15：显式保存每折的 train/validation 区间、样本数、指标聚合（train→past, validate→future）。"""
    rows = []
    d = ds.copy()
    d["_dt"] = pd.to_datetime(d["date"])
    for fold in FOLDS:
        tr_all, te_all = fold_mask(d, fold)
        for crop, sub in d.groupby("crop", sort=False):
            tr = sub[tr_all.loc[sub.index]]
            te = sub[te_all.loc[sub.index] &
                     sub[f"target_mean_price_next_30d"].notna()] if \
                f"target_mean_price_next_30d" in sub.columns else sub[te_all.loc[sub.index]]
            rows.append({
                "fold": fold["name"],
                "train_start": str(tr["_dt"].min().date()) if len(tr) else None,
                "train_end": str(tr["_dt"].max().date()) if len(tr) else None,
                "validation_start": str(te["_dt"].min().date()) if len(te) else None,
                "validation_end": str(te["_dt"].max().date()) if len(te) else None,
                "n_train": int(len(tr)), "n_validation": int(len(te)), "crop": crop,
                "train_end_declared": fold["train_end"],
            })
    return pd.DataFrame(rows)


def select_per_horizon(mets: pd.DataFrame, target: str) -> pd.DataFrame:
    s = mets[mets["target"] == target].copy()
    if not len(s):
        return pd.DataFrame()
    g = s.groupby(["route", "model", "crop"])
    summ = g.agg(mean_WAPE=("WAPE", "mean"), std_WAPE=("WAPE", "std"),
                 worst_WAPE=("WAPE", "max"), mean_MAE=("MAE", "mean"),
                 mean_RMSE=("RMSE", "mean"), mean_sMAPE=("sMAPE", "mean"),
                 mean_bias=("bias", "mean"), folds=("WAPE", "count")).reset_index()
    summ["score"] = summ["mean_WAPE"] + 0.5 * summ["std_WAPE"].fillna(0)
    best = summ.sort_values("score").groupby("crop", as_index=False).first()
    base = (summ[summ["route"] == "baseline"].sort_values("score")
            .groupby("crop", as_index=False).first()
            .rename(columns={"model": "best_baseline", "mean_WAPE": "baseline_WAPE",
                             "score": "baseline_score"})[["crop", "best_baseline", "baseline_WAPE", "baseline_score"]])
    best = best.merge(base, on="crop", how="left")
    best["improvement_vs_baseline_pct"] = (best["baseline_WAPE"] - best["mean_WAPE"]) / best["baseline_WAPE"] * 100
    best["beats_baseline"] = best["mean_WAPE"] < best["baseline_WAPE"]
    best["horizon"] = int(target.split("_")[-1].replace("d", ""))
    return best.sort_values("crop")


def run(cities=("沈阳",)) -> Dict[str, object]:
    ensure_dir(FINAL_EVAL_DIR)
    ensure_dir(REPORTS_DIR / "tables")
    factories = _factories()
    all_sel, all_mets, all_preds, runtimes = [], [], [], []
    for city in cities:
        ds = pd.read_parquet(SNAPSHOT_DIR / "datasets" / f"decision_dataset_{city}.parquet")
        for h in HORIZONS:
            r = run_horizon(ds, h, factories)
            if not r:
                continue
            r["preds"]["city"] = city
            r["mets"]["city"] = city
            all_preds.append(r["preds"]); all_mets.append(r["mets"])
            if len(r["runtime"]):
                rr = r["runtime"].copy(); rr["city"] = city; rr["horizon"] = h
                runtimes.append(rr)
            sel = select_per_horizon(r["mets"], f"target_mean_price_next_{h}d")
            sel["city"] = city
            all_sel.append(sel)
            print(f"[{city} h={h}] selected; baseline_win="
                  f"{int((~sel['beats_baseline']).sum())}/{len(sel)}", flush=True)
    sel = pd.concat(all_sel, ignore_index=True)
    mets = pd.concat(all_mets, ignore_index=True)
    preds = pd.concat(all_preds, ignore_index=True)
    # §15 折元数据（train/validation 区间 + 样本数）
    fm = pd.concat([fold_metadata(pd.read_parquet(
        SNAPSHOT_DIR / "datasets" / f"decision_dataset_{c}.parquet")) for c in cities], ignore_index=True)
    fm.to_csv(REPORTS_DIR / "tables" / "price_model_folds.csv", index=False, encoding="utf-8-sig")
    sel.to_csv(REPORTS_DIR / "tables" / "price_model_selection.csv", index=False, encoding="utf-8-sig")
    mets.to_csv(REPORTS_DIR / "tables" / "price_model_metrics_by_fold.csv", index=False, encoding="utf-8-sig")
    preds.to_parquet(FINAL_EVAL_DIR / "price_predictions.parquet", index=False)
    if runtimes:
        pd.concat(runtimes, ignore_index=True).to_csv(
            REPORTS_DIR / "tables" / "price_model_runtime.csv", index=False, encoding="utf-8-sig")
    # 多 horizon 汇总（沈阳）
    sh = sel[sel["city"] == "沈阳"]
    summ = sh.pivot_table(index="crop", columns="horizon", values="mean_WAPE", aggfunc="first")
    summ.to_csv(REPORTS_DIR / "tables" / "multi_horizon_WAPE.csv", encoding="utf-8-sig")
    meta = {"model_version": MODEL_VERSION, "data_version": DATA_VERSION,
            "features": len(FINAL_FEATURE_COLS), "horizons": HORIZONS,
            "folds": [f["name"] for f in FOLDS], "models": list(factories.keys()),
            "git_fingerprint": git_fingerprint(), "ts": now_stamp()}
    write_json(meta, REPORTS_DIR / "tables" / "price_model_run_meta.json")
    return {"rows_selection": len(sel), "models": list(factories.keys())}


if __name__ == "__main__":
    print(run())