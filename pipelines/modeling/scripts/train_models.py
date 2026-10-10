# -*- coding: utf-8 -*-
"""
Phase 2 入口：价格模型时间回测 + 最终模型选择 + 注册。

  python3 decision_engine/scripts/train_models.py

输出：
  decision_engine/evaluation/backtests/predictions.parquet
  decision_engine/evaluation/metrics/model_comparison.csv
  decision_engine/evaluation/metrics/model_selection.csv
  decision_engine/evaluation/metrics/weather_ablation.csv
  decision_engine/models/price/*.joblib
  decision_engine/models/registry/model_registry.json
"""
from __future__ import annotations
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from decision_engine.common import de_path, ensure_dir, write_json  # noqa: E402
from decision_engine.models import train_price as tp  # noqa: E402
from decision_engine.models.backtest import FOLDS  # noqa: E402

SEED = 42
SECONDARY_TARGETS = ["target_price_t7", "target_price_t14", "target_price_t30",
                     "target_mean_price_next_7d", "target_mean_price_next_14d",
                     "target_median_price_next_30d", "target_min_price_next_30d",
                     "target_max_price_next_30d"]


def load_dataset() -> pd.DataFrame:
    ds = pd.read_parquet(de_path("data", "processed", "decision_dataset_v1.parquet"))
    ds["date"] = pd.to_datetime(ds["date"])
    return ds


def run_primary(ds: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    facs = tp.make_model_factories(SEED)
    tuned = tp.make_tuned_factories(SEED)
    if tuned:
        facs.update(tuned)
        print(f"[models] tuned variants: {list(tuned.keys())}", flush=True)
    print("[models]", list(facs.keys()), flush=True)
    preds_a, mets_a, rt_a = tp.run_ml_backtest(ds, tp.FEATURE_COLS, tp.PRIMARY_TARGET, facs, route="per_crop")
    print(f"[routeA] preds={len(preds_a)}")
    preds_b, mets_b, rt_b = tp.run_ml_backtest(ds, tp.FEATURE_COLS, tp.PRIMARY_TARGET, facs, route="pooled")
    print(f"[routeB] preds={len(preds_b)}")
    bp = tp.baseline_predictions(ds, tp.PRIMARY_TARGET)
    bm = tp.baseline_metrics(bp)
    preds = pd.concat([preds_a, preds_b, bp], ignore_index=True)
    mets = pd.concat([mets_a, mets_b, bm], ignore_index=True)
    rts = pd.concat([rt_a, rt_b], ignore_index=True)
    return preds, mets, rts


def run_secondary(ds: pd.DataFrame, chosen_families: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    facs_all = tp.make_model_factories(SEED)
    facs = {k: v for k, v in facs_all.items() if k in chosen_families}
    preds_list, mets_list = [], []
    for tgt in SECONDARY_TARGETS:
        p, m, _ = tp.run_ml_backtest(ds, tp.FEATURE_COLS, tgt, facs, route="per_crop")
        preds_list.append(p)
        mets_list.append(m)
        print(f"[secondary] {tgt}: preds={len(p)}", flush=True)
    bp_list = [tp.baseline_predictions(ds, t) for t in SECONDARY_TARGETS]
    bm_list = [tp.baseline_metrics(b) for b in bp_list]
    return pd.concat(preds_list + bp_list, ignore_index=True), pd.concat(mets_list + bm_list, ignore_index=True)


def weather_ablation(ds: pd.DataFrame) -> pd.DataFrame:
    """受控 ablation：market-only vs market+weather（HistGB + ExtraTrees，Route A）。"""
    w = pd.read_parquet(de_path("data", "features", "weather_features_shenyang.parquet"))
    w["date"] = pd.to_datetime(w["date"])
    d = ds.merge(w[["date"] + tp.WEATHER_COLS], on="date", how="left", validate="many_to_one")
    facs = tp.make_model_factories(SEED)
    sub = {k: facs[k] for k in ["hist_gradient_boosting", "extra_trees"] if k in facs}
    rows = []
    for label, cols in [("market_only", tp.FEATURE_COLS),
                        ("market_plus_weather", tp.FEATURE_COLS + tp.WEATHER_COLS)]:
        p, m, _ = tp.run_ml_backtest(d, cols, tp.PRIMARY_TARGET, sub, route="per_crop")
        m["feature_set"] = label
        rows.append(m)
        print(f"[ablation] {label}: rows={len(m)}", flush=True)
    out = pd.concat(rows, ignore_index=True)
    # 逐作物对比
    cmp = (out.groupby(["feature_set", "model", "crop"])
           .agg(mean_WAPE=("WAPE", "mean"), mean_MAE=("MAE", "mean")).reset_index())
    piv = cmp.pivot_table(index=["model", "crop"], columns="feature_set", values="mean_WAPE").reset_index()
    piv["delta_WAPE"] = piv["market_plus_weather"] - piv["market_only"]
    piv["delta_WAPE_pct"] = piv["delta_WAPE"] / piv["market_only"] * 100
    return piv, out


def retrain_and_register(ds: pd.DataFrame, selection: pd.DataFrame,
                         metrics_summary: pd.DataFrame) -> list[dict]:
    facs = tp.make_model_factories(SEED)
    facs.update(tp.make_tuned_factories(SEED))
    registry = []
    created = datetime.now().isoformat(timespec="seconds")
    for _, row in selection.iterrows():
        crop, model, route = row["crop"], row["model"], row["route"]
        tgt = tp.PRIMARY_TARGET
        tr = ds[ds[tgt].notna()].copy()
        entry = {
            "model_id": f"price_{crop}_{model}",
            "city": "沈阳", "crop": crop, "target": tgt,
            "algorithm": model, "route": route,
            "train_start": str(ds["date"].min().date()),
            "train_end": str(tr["date"].max().date()),
            "validation_period": "expanding folds: train<=2023->test2024; <=2024->test2025; <=2025->test2026(1-9月)",
            "features": tp.FEATURE_COLS if route != "baseline" else [],
            "metrics": {
                "mean_WAPE": float(row["mean_WAPE"]), "mean_MAE": float(row["mean_MAE"]),
                "mean_RMSE": float(row["mean_RMSE"]), "mean_sMAPE": float(row["mean_sMAPE"]),
            },
            "baseline_metrics": {
                "best_baseline": row["best_baseline"],
                "mean_WAPE": float(row["baseline_mean_WAPE"]),
                "mean_MAE": float(row["baseline_mean_MAE"]),
            },
            "beats_baseline": bool(row["beats_baseline"]),
            "artifact_path": None,
            "created_at": created,
            "data_snapshot": "models/data/snapshots/v1",
            "n_train_rows": int(len(tr[tr["crop"] == crop])) if route == "per_crop" else int(len(tr)),
        }
        if route != "baseline" and model in facs:
            m = facs[model]()
            feat_cols_saved = list(tp.FEATURE_COLS)
            if route == "per_crop":
                trc = tr[tr["crop"] == crop]
                m.fit(trc[tp.FEATURE_COLS], trc[tgt])
            else:
                trf = tr[tp.FEATURE_COLS].copy()
                trf["crop_cat"] = tr["crop"].astype("category").cat.codes
                feat_cols_saved = feat_cols_saved + ["crop_cat"]
                m.fit(trf, tr[tgt])
            p = ensure_dir(de_path("models", "price")) / f"{crop}_{model}_{route}.joblib"
            joblib.dump({"model": m, "crop": crop, "algorithm": model, "route": route,
                         "feature_cols": feat_cols_saved, "target": tgt,
                         "train_end": entry["train_end"]}, p)
            entry["artifact_path"] = str(p.relative_to(de_path(".")))
            entry["artifact_size_mb"] = round(p.stat().st_size / 1e6, 4)
        registry.append(entry)
    return registry


def main():
    t0 = time.time()
    ds = load_dataset()
    print(f"[dataset] {ds.shape} {ds['date'].min().date()} ~ {ds['date'].max().date()}")

    preds, mets, rts = run_primary(ds)
    summary = tp.summarize_metrics(mets)
    sel = tp.select_final_models(summary)
    print("\n[selection]\n", sel[["crop", "route", "model", "mean_WAPE", "baseline_mean_WAPE",
                                  "improvement_vs_baseline_pct", "beats_baseline"]].to_string(index=False))

    # 次要目标：固定 2 个轻量家族（快速、稳定）+ 基线（重家族仅跑主目标，避免数小时级重复训练）
    chosen = [f for f in ["hist_gradient_boosting", "ridge", "extra_trees"]
              if f in tp.make_model_factories(SEED)][:2]
    print(f"[secondary] chosen families: {chosen}", flush=True)
    preds2, mets2 = run_secondary(ds, chosen)

    all_preds = pd.concat([preds, preds2], ignore_index=True)
    all_mets = pd.concat([mets, mets2], ignore_index=True)

    eval_dir = ensure_dir(de_path("evaluation", "metrics"))
    bt_dir = ensure_dir(de_path("evaluation", "backtests"))
    all_preds.to_parquet(bt_dir / "predictions.parquet", index=False)
    all_mets.to_csv(eval_dir / "model_metrics_by_fold.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(eval_dir / "model_comparison.csv", index=False, encoding="utf-8-sig")
    rts.to_csv(eval_dir / "model_runtime.csv", index=False, encoding="utf-8-sig")
    sel.to_csv(eval_dir / "model_selection.csv", index=False, encoding="utf-8-sig")
    print(f"[save] predictions={len(all_preds)}")

    # 天气 ablation
    abl, abl_raw = weather_ablation(ds)
    abl.to_csv(eval_dir / "weather_ablation.csv", index=False, encoding="utf-8-sig")
    abl_raw.to_csv(eval_dir / "weather_ablation_by_fold.csv", index=False, encoding="utf-8-sig")
    print("\n[ablation]\n", abl.to_string(index=False))

    # 最终模型注册
    registry = retrain_and_register(ds, sel, summary)
    rp = ensure_dir(de_path("models", "registry")) / "model_registry.json"
    existing = {}
    if rp.exists():
        try:
            existing = json.loads(rp.read_text())
        except Exception:
            existing = {}
    existing["price_models"] = registry
    existing["updated_at"] = datetime.now().isoformat(timespec="seconds")
    write_json(existing, rp)

    print(f"\n[done] total runtime {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()