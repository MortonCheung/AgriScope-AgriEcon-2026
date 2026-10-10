# -*- coding: utf-8 -*-
"""
Phase 11 入口：历史回放（strict point-in-time）+ 案例选择。

  python3 decision_engine/scripts/run_replay.py

原则：
  - 站在历史时刻 T，引擎只能看到 <= T 的数据（as_of=T）；
  - 对未来真实结果（T 之后）只用于评估，不进入任何输入；
  - 回放假设的亩均成本/亩产为「回放情景假设」（非真实成本），报告中明确标注。

输出：
  decision_engine/evaluation/backtests/replay_results.csv
  decision_engine/evaluation/metrics/replay_interval_coverage.csv
  decision_engine/evaluation/cases/replay_cases.json
"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from decision_engine.common import de_path, ensure_dir  # noqa: E402
from decision_engine.engine.engine import DecisionEngine, SHENYANG_CROPS  # noqa: E402

REPLAY_COST_PER_MU = 5000.0     # 回放情景假设（非真实成本）
REPLAY_YIELD_PER_MU = 4000.0    # 回放情景假设（非真实亩产）
REPLAY_AREA_MU = 80.0
HARVEST_OFFSET_DAYS = 90
WINDOW_HALF = 15


def replay_dates(ds: pd.DataFrame, step_days: int = 15) -> list:
    d0 = pd.Timestamp("2024-01-01")
    last = ds["date"].max() - pd.Timedelta(days=HARVEST_OFFSET_DAYS + WINDOW_HALF)
    out = []
    t = d0
    while t <= last:
        out.append(t)
        t += pd.Timedelta(days=step_days)
    return out


def realized_window_price(ds: pd.DataFrame, crop: str, harvest: pd.Timestamp) -> float | None:
    sub = ds[(ds["crop"] == crop)]
    w = sub[(sub["date"] >= harvest - pd.Timedelta(days=WINDOW_HALF)) &
            (sub["date"] <= harvest + pd.Timedelta(days=WINDOW_HALF))]
    if len(w) < 5:
        return None
    return float(w["price_per_kg"].mean())


def main():
    t0 = time.time()
    ds = pd.read_parquet(de_path("data", "processed", "decision_dataset_v1.parquet"))
    ds["date"] = pd.to_datetime(ds["date"])
    dates = replay_dates(ds)
    print(f"[replay] {len(dates)} 个历史时点 x {len(SHENYANG_CROPS)} 作物", flush=True)

    rows = []
    engines = {}
    for T in dates:
        key = str(T.date())
        if key not in engines:
            engines[key] = DecisionEngine(as_of=key)
        eng = engines[key]
        for crop in SHENYANG_CROPS:
            harvest = T + pd.Timedelta(days=HARVEST_OFFSET_DAYS)
            plan = {"city": "沈阳", "crop": crop,
                    "plant_date": str(T.date()), "harvest_date": str(harvest.date()),
                    "area_mu": REPLAY_AREA_MU, "cost_per_mu": REPLAY_COST_PER_MU,
                    "expected_yield_per_mu": REPLAY_YIELD_PER_MU,
                    "risk_preference": "balanced"}
            r = eng.evaluate_plan(plan)
            if r.get("status") != "ok":
                continue
            realized = realized_window_price(ds, crop, harvest)
            row = {
                "replay_date": T, "crop": crop, "harvest_date": harvest,
                "p10": r["price"]["low"], "p50": r["price"]["mid"], "p90": r["price"]["high"],
                "hri": (r["risk"]["herding"] or {}).get("value"),
                "hri_level": (r["risk"]["herding"] or {}).get("level"),
                "market_risk": (r["risk"]["market"] or {}).get("value"),
                "climate_exposure": r["risk"]["climate"].get("climate_exposure_score"),
                "decision_score": r["decision"]["score"],
                "confidence": r["confidence"]["score"],
                "realized_price": realized,
            }
            if realized is not None:
                row["interval_hit"] = bool(r["price"]["low"] <= realized <= r["price"]["high"])
                row["p50_error"] = realized - r["price"]["mid"]
                row["p50_abs_error"] = abs(realized - r["price"]["mid"])
            rows.append(row)
        if (dates.index(T) + 1) % 10 == 0:
            print(f"[replay] {dates.index(T)+1}/{len(dates)} done {time.time()-t0:.0f}s", flush=True)

    df = pd.DataFrame(rows)
    bdir = ensure_dir(de_path("evaluation", "backtests"))
    mdir = ensure_dir(de_path("evaluation", "metrics"))
    cdir = ensure_dir(de_path("evaluation", "cases"))
    df.to_csv(bdir / "replay_results.csv", index=False, encoding="utf-8-sig")

    withreal = df[df["realized_price"].notna()].copy()
    cov = {
        "overall": {
            "n": int(len(withreal)),
            "coverage": float(withreal["interval_hit"].mean()) if len(withreal) else None,
            "mean_p50_abs_error": float(withreal["p50_abs_error"].mean()) if len(withreal) else None,
            "median_p50_abs_error": float(withreal["p50_abs_error"].median()) if len(withreal) else None,
        }
    }
    by_crop = withreal.groupby("crop").agg(
        n=("interval_hit", "count"), coverage=("interval_hit", "mean"),
        mean_abs_error=("p50_abs_error", "mean")).reset_index()
    by_year = withreal.assign(year=pd.to_datetime(withreal["replay_date"]).dt.year).groupby("year").agg(
        n=("interval_hit", "count"), coverage=("interval_hit", "mean"),
        mean_abs_error=("p50_abs_error", "mean")).reset_index()
    by_crop.to_csv(mdir / "replay_coverage_by_crop.csv", index=False, encoding="utf-8-sig")
    by_year.to_csv(mdir / "replay_coverage_by_year.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame([cov["overall"]]).to_csv(mdir / "replay_interval_coverage.csv", index=False, encoding="utf-8-sig")
    print("[replay] overall coverage:", cov["overall"], flush=True)

    # ---- 案例选择（不是 cherry-picking：全样本回放 + 自动规则）----
    cases = []
    wr = withreal.copy()
    # 3 个高 HRI 案例（HRI 最高的 3 个，且满足"高HRI后价格回落"叙事检查）
    hi = wr.sort_values("hri", ascending=False).head(3)
    for i, (_, r) in enumerate(hi.iterrows(), 1):
        cases.append({"case_type": "high_hri", "case_id": f"HIGH-{i}",
                       "replay_date": str(pd.Timestamp(r["replay_date"]).date()),
                       "crop": r["crop"], "hri": r["hri"], "hri_level": r["hri_level"],
                       "predicted_range": [r["p10"], r["p50"], r["p90"]],
                       "realized": r["realized_price"], "interval_hit": r["interval_hit"],
                       "decision_score": r["decision_score"], "confidence": r["confidence"],
                       "narrative": "高 HRI（高价+强动能）→ 检查随后 90 天价格是否回落/滞涨"})
    # 2 个普通案例（HRI 中位附近，随机不挑选）
    med = wr.iloc[(wr["hri"] - wr["hri"].median()).abs().argsort()[:2]]
    for i, (_, r) in enumerate(med.iterrows(), 1):
        cases.append({"case_type": "normal", "case_id": f"NORMAL-{i}",
                       "replay_date": str(pd.Timestamp(r["replay_date"]).date()),
                       "crop": r["crop"], "hri": r["hri"], "hri_level": r["hri_level"],
                       "predicted_range": [r["p10"], r["p50"], r["p90"]],
                       "realized": r["realized_price"], "interval_hit": r["interval_hit"],
                       "decision_score": r["decision_score"], "confidence": r["confidence"],
                       "narrative": "普通市况下的基准表现"})
    # 1 个失败案例（区间偏差最大的）
    fail = wr.iloc[wr["p50_abs_error"].abs().argsort()[::-1][:1]]
    for _, r in fail.iterrows():
        cases.append({"case_type": "failure", "case_id": "FAIL-1",
                       "replay_date": str(pd.Timestamp(r["replay_date"]).date()),
                       "crop": r["crop"], "hri": r["hri"], "hri_level": r["hri_level"],
                       "predicted_range": [r["p10"], r["p50"], r["p90"]],
                       "realized": r["realized_price"], "interval_hit": r["interval_hit"],
                       "p50_error": r["p50_error"],
                       "decision_score": r["decision_score"], "confidence": r["confidence"],
                       "narrative": "预测偏差最大的失败案例（必须展示，避免 cherry-picking）"})
    with open(cdir / "replay_cases.json", "w", encoding="utf-8") as f:
        json.dump({"cases": cases, "selection_rule": "全样本回放后按自动规则选择：HRI Top3 / HRI 中位 2 例 / P50 绝对误差最大 1 例",
                   "replay_assumption": {"cost_per_mu": REPLAY_COST_PER_MU, "yield_per_mu": REPLAY_YIELD_PER_MU,
                                         "note": "回放情景假设，非真实亩均成本/亩产；收益类指标受此假设影响"}},
                  f, ensure_ascii=False, indent=2)
    print(f"[replay] cases={len(cases)} done {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()