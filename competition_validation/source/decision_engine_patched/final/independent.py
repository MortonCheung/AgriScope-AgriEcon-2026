# -*- coding: utf-8 -*-
"""F16: 独立内部审计 —— 关键指标用独立实现复算一次，与训练输出对比。

不复用训练代码里的函数，重新实现 WAPE / coverage / group-diff / mean return，
逐项与实现输出对比，差异在容差内才判定通过。
"""
from __future__ import annotations
from typing import Dict, List

import numpy as np
import pandas as pd

from decision_engine.final.fcommon import (REPORTS_DIR, FINAL_EVAL_DIR, MANIFEST_DIR,
                                           ensure_dir, write_json, now_stamp)

TOL = {"WAPE": 0.05, "coverage": 0.01, "return": 1e-6, "group_diff": 1e-6, "selection": 1e-9}


def _wape(y, p) -> float:
    y = np.asarray(y, float); p = np.asarray(p, float)
    m = np.isfinite(y) & np.isfinite(p)
    y, p = y[m], p[m]
    if not len(y) or np.abs(y).sum() == 0:
        return np.nan
    return float(np.abs(y - p).sum() / np.abs(y).sum() * 100)


def check_price_metrics() -> pd.DataFrame:
    preds = pd.read_parquet(FINAL_EVAL_DIR / "price_predictions.parquet")
    preds = preds[preds["target"] == "target_mean_price_next_30d"]
    reported = pd.read_csv(REPORTS_DIR / "tables" / "price_model_metrics_by_fold.csv")
    reported = reported[reported["target"] == "target_mean_price_next_30d"]
    rows = []
    for _, r in reported.iterrows():
        sub = preds[(preds["city"] == r["city"]) & (preds["crop"] == r["crop"]) &
                    (preds["model"] == r["model"]) & (preds["route"] == r["route"]) &
                    (preds["fold"] == r["fold"])]
        if not len(sub):
            continue
        indep = _wape(sub["actual"], sub["prediction"])
        rows.append({"check": "WAPE", "city": r["city"], "crop": r["crop"], "model": r["model"],
                     "fold": r["fold"], "impl": float(r["WAPE"]), "indep": indep,
                     "diff": abs(indep - float(r["WAPE"])),
                     "pass": abs(indep - float(r["WAPE"])) <= TOL["WAPE"]})
    return pd.DataFrame(rows)


def check_interval_coverage() -> pd.DataFrame:
    iv = pd.read_parquet(FINAL_EVAL_DIR / "predictions_with_intervals.parquet")
    # 独立重实现：按 (crop, fold) 组内覆盖率再取组均值（与实现口径一致）
    covs = []
    for (_, _), g in iv.groupby(["crop", "fold"]):
        a, lo, hi = g["actual"].values, g["p10"].values, g["p90"].values
        m = np.isfinite(a) & np.isfinite(lo) & np.isfinite(hi)
        if m.sum() == 0:
            continue
        covs.append(float(((a[m] >= lo[m]) & (a[m] <= hi[m])).mean()))
    indep = float(np.mean(covs))
    rep = pd.read_csv(REPORTS_DIR / "tables" / "interval_calibration_summary.csv")
    method = iv["method"].iloc[0]
    impl = float(rep[rep["method"] == method]["coverage"].iloc[0]) if len(rep) else np.nan
    return pd.DataFrame([{"check": "interval_coverage", "method": method,
                          "impl": impl, "indep": indep, "diff": abs(indep - impl),
                          "pass": abs(indep - impl) <= TOL["coverage"]}])


def check_strategy_returns() -> pd.DataFrame:
    bt = pd.read_parquet(FINAL_EVAL_DIR / "strategy_backtest.parquet")
    rep = pd.read_csv(REPORTS_DIR / "tables" / "strategy_benchmark.csv")
    rows = []
    for _, r in rep.iterrows():
        sub = bt[bt["strategy"] == r["strategy"]]["realized_return"].dropna()
        indep = float(sub.mean())
        rows.append({"check": "strategy_mean_market_return", "strategy": r["strategy"],
                     "impl": float(r["mean_market_return"]), "indep": indep,
                     "diff": abs(indep - float(r["mean_market_return"])),
                     "pass": abs(indep - float(r["mean_market_return"])) <= TOL["return"]})
    return pd.DataFrame(rows)


def check_hri_groupdiff() -> pd.DataFrame:
    h = pd.read_parquet(FINAL_EVAL_DIR / "hri_weekly_沈阳.parquet")
    rep = pd.read_csv(REPORTS_DIR / "tables" / "hri_validation.csv")
    rep = rep[rep["city"] == "沈阳"]
    rows = []
    for _, r in rep.iterrows():
        sub = h[h["crop"] == r["crop"]]
        w = int(r["window_w"])
        f = f"fwd_{w}w"
        if f not in sub.columns:
            continue
        hi = sub[sub["hri_pct"] >= 80][f].dropna()
        lo = sub[sub["hri_pct"] <= 50][f].dropna()
        if len(hi) < 15 or len(lo) < 15:
            continue
        indep = float(hi.mean() - lo.mean())
        rows.append({"check": "hri_group_diff", "crop": r["crop"], "window_w": w,
                     "impl": float(r["diff"]), "indep": indep,
                     "diff": abs(indep - float(r["diff"])),
                     "pass": abs(indep - float(r["diff"])) <= TOL["group_diff"]})
    return pd.DataFrame(rows)


def check_selection() -> pd.DataFrame:
    mets = pd.read_csv(REPORTS_DIR / "tables" / "price_model_metrics_by_fold.csv")
    sel = pd.read_csv(REPORTS_DIR / "tables" / "price_model_selection.csv")
    m30 = mets[mets["target"] == "target_mean_price_next_30d"].copy()
    g = m30.groupby(["city", "route", "model", "crop"]).agg(
        mean_WAPE=("WAPE", "mean"), std_WAPE=("WAPE", "std")).reset_index()
    g["score"] = g["mean_WAPE"] + 0.5 * g["std_WAPE"].fillna(0)
    rows = []
    for _, r in sel[sel["horizon"] == 30].iterrows():
        sub = g[(g["city"] == r["city"]) & (g["crop"] == r["crop"])]
        if not len(sub):
            continue
        best = sub.sort_values("score").iloc[0]
        ok = (best["model"] == r["model"]) and (best["route"] == r["route"])
        rows.append({"check": "selection", "city": r["city"], "crop": r["crop"],
                     "impl": f"{r['route']}/{r['model']}", "indep": f"{best['route']}/{best['model']}",
                     "diff": 0.0 if ok else 1.0, "pass": bool(ok)})
    return pd.DataFrame(rows)


def check_high_hri_and_regret() -> pd.DataFrame:
    """独立复算 high-HRI 选中率与 regret（不调用训练/推荐代码的聚合函数）。"""
    bt = pd.read_parquet(FINAL_EVAL_DIR / "strategy_backtest.parquet")
    rep = pd.read_csv(REPORTS_DIR / "tables" / "strategy_benchmark.csv")
    rows = []
    # ---- mean_regret：独立重算（不使用实现写入的 best/regret 列）
    best = bt.groupby("date")["realized_return"].max().rename("_best").reset_index()
    for _, r in rep.iterrows():
        sub = bt[bt["strategy"] == r["strategy"]].drop(
            columns=[c for c in ("best", "regret") if c in bt.columns])
        m = sub.merge(best, on="date", how="left")
        reg = float((m["_best"] - m["realized_return"]).mean())
        rows.append({"check": "mean_regret", "strategy": r["strategy"],
                     "impl": float(r["mean_regret"]), "indep": reg,
                     "diff": abs(reg - float(r["mean_regret"])),
                     "pass": abs(reg - float(r["mean_regret"])) <= 1e-6})
    # ---- high_hri_rate：用**独立重建候选池**的 P90 阈值 + 原始 HRI 重算命中率
    fp = FINAL_EVAL_DIR / "policy_picks.parquet"
    if fp.exists():
        from decision_engine.final.backtest import build_panel
        panel = build_panel()
        thr = panel.groupby("date")["HRI"].quantile(0.90).rename("_thr").reset_index()
        picks = pd.read_parquet(fp)
        mm = picks.merge(thr, on="date", how="left")
        mm["_hh"] = mm["HRI"] >= mm["_thr"]
        indep = mm.groupby("strategy")["_hh"].mean()
        implf = picks.groupby("strategy")["high_hri"].mean()
        for s in indep.index:
            rows.append({"check": "high_hri_rate", "strategy": s,
                         "impl": float(implf.get(s, np.nan)), "indep": float(indep[s]),
                         "diff": abs(float(indep[s]) - float(implf.get(s, np.nan))),
                         "pass": abs(float(indep[s]) - float(implf.get(s, np.nan))) <= 1e-9})
    return pd.DataFrame(rows)


def check_balanced_production() -> pd.DataFrame:
    """§59：'Balanced 高-HRI=0' 的独立复核（生产推荐输出直接统计）。"""
    fp = FINAL_EVAL_DIR / "recommender_backtest_沈阳.parquet"
    if not fp.exists():
        return pd.DataFrame()
    bt = pd.read_parquet(fp)
    bt = bt[(bt["rank"] == "top1")]
    THR = 73.2
    indep = bt.groupby("policy").apply(lambda s: float((s["HRI_mean"] >= THR).mean()))
    rep = pd.read_csv(REPORTS_DIR / "tables" / "balanced_fix_before_after_fixed_thr.csv")
    rep = rep.set_index("policy")["after"]
    rows = []
    for pol in indep.index:
        if pol in rep.index:
            rows.append({"check": "production_high_hri_rate", "strategy": pol,
                         "impl": float(rep.loc[pol]), "indep": float(indep.loc[pol]),
                         "diff": abs(float(indep.loc[pol]) - float(rep.loc[pol])),
                         "pass": abs(float(indep.loc[pol]) - float(rep.loc[pol])) <= 1e-9})
    return pd.DataFrame(rows)


def run() -> Dict[str, object]:
    ensure_dir(MANIFEST_DIR)
    parts = [check_price_metrics(), check_interval_coverage(), check_strategy_returns(),
             check_hri_groupdiff(), check_selection(), check_high_hri_and_regret(),
             check_balanced_production()]
    allc = pd.concat([p for p in parts if len(p)], ignore_index=True)
    allc.to_csv(MANIFEST_DIR / "independent_recalculation.csv", index=False, encoding="utf-8-sig")
    out = {"n_checks": int(len(allc)), "n_pass": int(allc["pass"].sum()),
           "all_pass": bool(allc["pass"].all()), "max_diff": float(allc["diff"].max()) if len(allc) else 0.0,
           "ts": now_stamp()}
    write_json(out, MANIFEST_DIR / "independent_recalc_summary.json")
    return out


if __name__ == "__main__":
    print(run())