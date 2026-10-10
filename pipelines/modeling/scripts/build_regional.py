# -*- coding: utf-8 -*-
"""
Phase 12 入口：朝阳 / 锦州 简化价格模块 + HRI-lite + 市场风险。

  python3 decision_engine/scripts/build_regional.py

输出：
  decision_engine/data/features/regional_朝阳.parquet / regional_锦州.parquet
  decision_engine/data/features/regional_risk_朝阳.parquet / regional_risk_锦州.parquet
  decision_engine/evaluation/metrics/regional_model_comparison.csv
  decision_engine/evaluation/metrics/regional_model_selection.csv
  decision_engine/evaluation/backtests/regional_predictions.parquet
"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from decision_engine.common import de_path, ensure_dir, write_json  # noqa: E402
from decision_engine.models import regional as rg  # noqa: E402
from decision_engine.risk import hri as hri_mod  # noqa: E402
from decision_engine.risk import market_risk as mr_mod  # noqa: E402

CITY_LOADERS = {"朝阳": rg.load_chaoyang_base, "锦州": rg.load_jinzhou_base}


def build_city(city: str) -> dict:
    base = CITY_LOADERS[city]()
    ds = rg.build_regional_dataset(base)
    print(f"[regional] {city}: crops={ds['crop'].nunique()} rows={len(ds)}", flush=True)

    fdir = ensure_dir(de_path("data", "features"))
    ds.to_parquet(fdir / f"regional_{city}.parquet", index=False)

    preds, mets = rg.run_regional_backtest(ds, city)
    summary = rg.regional_summary(mets)
    sel = rg.regional_selection(summary)
    print(f"\n[regional {city} selection]\n",
          sel[["crop", "model", "mean_WAPE", "baseline_mean_WAPE", "beats_baseline"]].head(30).to_string(index=False),
          flush=True)

    # HRI-lite + market risk（无成交量；面积仅当 production_context 有精确匹配）
    h = hri_mod.build_hri(ds)
    mr = mr_mod.build_market_risk(h, interval_preds=None, use_pyod=True)
    risk = mr.copy()
    # market_risk 输出已包含 hri 列（同一 frame），统一保存
    keep = (["date", "city", "crop", "price_per_kg"] +
            [c for c in risk.columns if c.startswith("c_") or c.startswith("hri_")
             or c.startswith("mr_") or c.startswith("market_risk")])
    risk[keep].to_parquet(fdir / f"regional_risk_{city}.parquet", index=False)
    return {"city": city, "crops": int(ds["crop"].nunique()), "rows": len(ds),
            "preds": preds, "mets": mets, "summary": summary, "selection": sel}


def main():
    t0 = time.time()
    out = {c: build_city(c) for c in ["朝阳", "锦州"]}
    mdir = ensure_dir(de_path("evaluation", "metrics"))
    bdir = ensure_dir(de_path("evaluation", "backtests"))

    all_preds = pd.concat([out[c]["preds"] for c in out], ignore_index=True)
    all_mets = pd.concat([out[c]["mets"] for c in out], ignore_index=True)
    all_sum = pd.concat([out[c]["summary"] for c in out], ignore_index=True)
    all_sel = pd.concat([out[c]["selection"] for c in out], ignore_index=True)
    all_preds.to_parquet(bdir / "regional_predictions.parquet", index=False)
    all_mets.to_csv(mdir / "regional_model_metrics_by_fold.csv", index=False, encoding="utf-8-sig")
    all_sum.to_csv(mdir / "regional_model_comparison.csv", index=False, encoding="utf-8-sig")
    all_sel.to_csv(mdir / "regional_model_selection.csv", index=False, encoding="utf-8-sig")

    # 注册表追加
    rp = de_path("models", "registry", "model_registry.json")
    reg = json.loads(rp.read_text()) if rp.exists() else {}
    reg["regional_models"] = [
        {"model_id": f"price_{r['crop']}_{r['model']}", "city": r.get("city", ""),
         "crop": r["crop"], "target": "target_mean_price_next_30d", "algorithm": r["model"],
         "route": r["route"], "metrics": {"mean_WAPE": float(r["mean_WAPE"]),
                                          "mean_MAE": float(r["mean_MAE"])},
         "baseline_metrics": {"best_baseline": r["best_baseline"],
                              "mean_WAPE": float(r["baseline_mean_WAPE"])},
         "beats_baseline": bool(r["beats_baseline"]),
         "data_snapshot": "models/data/snapshots/v1",
         "note": "简化模块：market_average（朝阳）/单一价格层级（锦州），无成交量"}
        for _, r in all_sel.iterrows()]
    write_json(reg, rp)
    print(f"[regional] done {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()