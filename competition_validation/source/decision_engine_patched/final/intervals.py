# -*- coding: utf-8 -*-
"""F5: 价格区间重校准（P10/P50/P90）。

方法（全部严格 point-in-time，使用 FINAL_FEATURE_COLS）：
  1. seasonal_window_quantile —— 历史同月「未来 h 天窗口均价」分布（与目标同统计量）
  2. quantile_regression      —— LightGBM 分位回归
  3. residual_recent          —— 最终模型残差（最近 N 个 OOS 残差）的 P10/P90
  4. residual_expanding       —— 递推累积 OOS 残差

评价：nominal=0.80 的 actual coverage / width / sharpness / by crop / by season。
判定：若最优方法 |coverage-0.80| <= 0.05 且分作物最低覆盖 >= 0.60 → calibrated prediction interval；
      否则一律称 scenario range（绝不谎称 80% prediction interval）。
"""
from __future__ import annotations
from typing import Callable, Dict, List

import numpy as np
import pandas as pd

from decision_engine.models.backtest import FOLDS, fold_mask
from decision_engine.models.train_price import FEATURE_COLS
from decision_engine.final.fcommon import (FINAL_EVAL_DIR, REPORTS_DIR, SNAPSHOT_DIR,
                                           ensure_dir, write_json, now_stamp)
from decision_engine.final.models import FINAL_FEATURE_COLS, _factories, PRIMARY_H

NOMINAL = 0.80
H = PRIMARY_H


def _season(dt) -> str:
    m = pd.Timestamp(dt).month
    return {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
            6: "summer", 7: "summer", 8: "summer", 9: "autumn", 10: "autumn",
            11: "autumn"}[m]


def _per_crop_factory(sel: pd.DataFrame, h: int = H) -> Dict[str, Callable]:
    facs = _factories()
    out = {}
    for _, r in sel[(sel["horizon"] == h) & (sel["city"] == "沈阳")].iterrows():
        if r["model"] in facs:
            out[r["crop"]] = (facs[r["model"]], r["model"])
    return out


# ---------------------------------------------------------------- 1. seasonal window quantile
def seasonal_window_quantile(ds: pd.DataFrame, h: int = H) -> pd.DataFrame:
    tgt = f"target_mean_price_next_{h}d"
    d = ds.sort_values(["crop", "date"]).reset_index(drop=True).copy()
    rows = []
    for crop, sub in d.groupby("crop", sort=False):
        sub = sub.reset_index(drop=True)
        dt = pd.to_datetime(sub["date"]); tv = sub[tgt].values
        mo = sub["month"].values; yr = sub["year"].values
        for i in range(len(sub)):
            t = dt.iloc[i]
            mask = (mo == mo[i]) & (yr < yr[i]) & (dt.values + np.timedelta64(h, "D") <= t.to_datetime64())
            vals = tv[mask]; vals = vals[np.isfinite(vals)]
            fold = None
            for f in FOLDS:
                if pd.Timestamp(f["test_start"]) <= t <= pd.Timestamp(f["test_end"]):
                    fold = f["name"]; break
            if fold is None or len(vals) < 20:
                continue
            p10, p50, p90 = np.percentile(vals, [10, 50, 90])
            rows.append({"method": "seasonal_window_quantile", "fold": fold, "crop": crop,
                         "date": t, "actual": sub[tgt].iloc[i], "mid": p50, "lo": p10, "hi": p90})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 2. quantile regression
def quantile_regression(ds: pd.DataFrame, h: int = H, seed: int = 42) -> pd.DataFrame:
    from lightgbm import LGBMRegressor
    from sklearn.pipeline import Pipeline
    from sklearn.impute import SimpleImputer
    tgt = f"target_mean_price_next_{h}d"
    d = ds.copy()
    if tgt not in d.columns:
        return pd.DataFrame()
    rows = []
    for fold in FOLDS:
        tr_all, te_all = fold_mask(d, fold)
        for crop, sub in d.groupby("crop"):
            tr = sub[tr_all.loc[sub.index] & sub[tgt].notna()]
            te = sub[te_all.loc[sub.index] & sub[tgt].notna()]
            if len(tr) < 200 or not len(te):
                continue
            preds = {}
            for q in [0.1, 0.5, 0.9]:
                m = Pipeline([("imp", SimpleImputer(strategy="median")),
                              ("m", LGBMRegressor(objective="quantile", alpha=q, n_estimators=300,
                                                  learning_rate=0.05, num_leaves=31,
                                                  random_state=seed, n_jobs=-1, verbose=-1))])
                m.fit(tr[FINAL_FEATURE_COLS], tr[tgt]); preds[q] = m.predict(te[FINAL_FEATURE_COLS])
            lo = np.minimum(preds[0.1], preds[0.9]); hi = np.maximum(preds[0.1], preds[0.9])
            for dt, act, md, a, b in zip(te["date"], te[tgt], preds[0.5], lo, hi):
                rows.append({"method": "quantile_regression", "fold": fold["name"], "crop": crop,
                             "date": dt, "actual": act, "mid": md, "lo": a, "hi": b})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 3/4. residual (recent / expanding)
def residual_intervals(ds: pd.DataFrame, crop_fac: Dict[str, Callable], h: int = H,
                       recent_n: int = 400, mode: str = "recent") -> pd.DataFrame:
    tgt = f"target_mean_price_next_{h}d"
    d = ds.sort_values(["crop", "date"]).reset_index(drop=True).copy()
    rows = []
    residuals: Dict[str, List[float]] = {}
    for fold in FOLDS:
        tr_all, te_all = fold_mask(d, fold)
        for crop, sub in d.groupby("crop", sort=False):
            fac = crop_fac.get(crop)
            if fac is None:
                continue
            fac_k, name = fac
            tr = sub[tr_all.loc[sub.index] & sub[tgt].notna()].sort_values("date")
            te = sub[te_all.loc[sub.index] & sub[tgt].notna()]
            if len(tr) < 200 or not len(te):
                continue
            if crop not in residuals:
                cut = int(len(tr) * 0.8)
                itr, ical = tr.iloc[:cut], tr.iloc[cut:]
                m = fac_k(); m.fit(itr[FINAL_FEATURE_COLS], itr[tgt])
                residuals[crop] = list(ical[tgt].values - m.predict(ical[FINAL_FEATURE_COLS]))
            res = np.asarray(residuals[crop][-recent_n:] if mode == "recent" else residuals[crop], dtype=float)
            res = res[np.isfinite(res)]
            if len(res) < 40:
                continue
            q_lo, q_hi = np.quantile(res, [0.10, 0.90])
            m2 = fac_k(); m2.fit(tr[FINAL_FEATURE_COLS], tr[tgt])
            mid = m2.predict(te[FINAL_FEATURE_COLS])
            for dt, act, md in zip(te["date"], te[tgt], mid):
                rows.append({"method": f"residual_{mode}", "fold": fold["name"], "crop": crop,
                             "date": dt, "actual": act, "mid": md, "lo": md + q_lo, "hi": md + q_hi})
            residuals[crop].extend(list((te[tgt].values - mid)[np.isfinite(te[tgt].values - mid)]))
    return pd.DataFrame(rows)


def evaluate(iv: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    per = []
    for (method, crop, fold), g in iv.groupby(["method", "crop", "fold"]):
        a, l, hi = g["actual"].values, g["lo"].values, g["hi"].values
        m = np.isfinite(a) & np.isfinite(l) & np.isfinite(hi)
        if m.sum() == 0:
            continue
        ins = (a[m] >= l[m]) & (a[m] <= hi[m])
        per.append({"method": method, "crop": crop, "fold": fold, "n": int(m.sum()),
                    "coverage": float(ins.mean()), "mean_width": float((hi[m] - l[m]).mean()),
                    "median_width": float(np.median(hi[m] - l[m]))})
    per = pd.DataFrame(per)
    iv2 = iv.copy()
    iv2["season"] = iv2["date"].apply(_season)
    seas = []
    for (method, season), g in iv2.groupby(["method", "season"]):
        a, l, hi = g["actual"].values, g["lo"].values, g["hi"].values
        m = np.isfinite(a) & np.isfinite(l) & np.isfinite(hi)
        if m.sum() == 0:
            continue
        ins = (a[m] >= l[m]) & (a[m] <= hi[m])
        seas.append({"method": method, "season": season, "n": int(m.sum()), "coverage": float(ins.mean())})
    seas = pd.DataFrame(seas)
    agg = (per.groupby("method").agg(coverage=("coverage", "mean"), coverage_std=("coverage", "std"),
                                      mean_width=("mean_width", "mean"),
                                      median_width=("median_width", "mean"),
                                      min_crop_coverage=("coverage", "min"),
                                      n_crop_fold=("coverage", "count")).reset_index())
    agg["coverage_gap"] = (agg["coverage"] - NOMINAL).abs()
    agg = agg.sort_values(["coverage_gap", "mean_width"])
    return per, agg, seas


def run() -> Dict[str, object]:
    ensure_dir(FINAL_EVAL_DIR)
    ds = pd.read_parquet(SNAPSHOT_DIR / "datasets" / "decision_dataset_沈阳.parquet")
    sel = pd.read_csv(REPORTS_DIR / "tables" / "price_model_selection.csv")
    crop_fac = _per_crop_factory(sel, H)
    parts = [seasonal_window_quantile(ds, H),
             quantile_regression(ds, H),
             residual_intervals(ds, crop_fac, H, mode="recent"),
             residual_intervals(ds, crop_fac, H, mode="expanding")]
    iv = pd.concat([p for p in parts if len(p)], ignore_index=True)
    per, agg, seas = evaluate(iv)
    per.to_csv(REPORTS_DIR / "tables" / "interval_calibration_by_crop_fold.csv", index=False, encoding="utf-8-sig")
    agg.to_csv(REPORTS_DIR / "tables" / "interval_calibration_summary.csv", index=False, encoding="utf-8-sig")
    seas.to_csv(REPORTS_DIR / "tables" / "interval_coverage_by_season.csv", index=False, encoding="utf-8-sig")
    best = agg.iloc[0]
    calibrated = bool(best["coverage_gap"] <= 0.05 and best["min_crop_coverage"] >= 0.60)
    label = "prediction_interval" if calibrated else "scenario_range"
    # 最终区间：取最优 method 的 P10/P50/P90
    iv_best = iv[iv["method"] == best["method"]].copy()
    iv_best = iv_best.rename(columns={"lo": "p10", "mid": "p50", "hi": "p90"})[
        ["date", "crop", "fold", "actual", "p10", "p50", "p90", "method"]]
    iv_best.to_parquet(FINAL_EVAL_DIR / "predictions_with_intervals.parquet", index=False)
    out = {"method": best["method"], "coverage": float(best["coverage"]),
           "mean_width": float(best["mean_width"]), "label": label,
           "nominal": NOMINAL, "calibrated": calibrated,
           "min_crop_coverage": float(best["min_crop_coverage"]), "ts": now_stamp()}
    write_json(out, REPORTS_DIR / "tables" / "interval_decision.json")
    return out


if __name__ == "__main__":
    print(run())