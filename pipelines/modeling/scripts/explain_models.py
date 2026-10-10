# -*- coding: utf-8 -*-
"""
开源 P0 5-6/…: 最终模型解释（EBM 内在解释 / SHAP / 线性系数 + permutation fallback）。

  python3 decision_engine/scripts/explain_models.py

输出：
  decision_engine/evaluation/metrics/feature_importance_{crop}.csv
  decision_engine/evaluation/metrics/feature_importance_all.csv
  decision_engine/evaluation/cases/local_explanations.json
  （并 upsert OPEN_SOURCE_MODEL_BENCHMARK.csv：interpret / shap）
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from decision_engine.common import de_path, ensure_dir  # noqa: E402
from decision_engine.models import explain as ex  # noqa: E402
from decision_engine.models.oss_common import upsert_benchmark, pkg_version  # noqa: E402


def main():
    ds = pd.read_parquet(de_path("data", "processed", "decision_dataset_v1.parquet"))
    ds["date"] = pd.to_datetime(ds["date"])
    mdir = ensure_dir(de_path("evaluation", "metrics"))
    cdir = ensure_dir(de_path("evaluation", "cases"))
    sel_path = de_path("evaluation", "metrics", "model_selection.csv")
    if not sel_path.exists():
        print("[explain] model_selection.csv 不存在，先运行 train_models.py")
        return
    sel = pd.read_csv(sel_path)

    all_imp = []
    local_out = {}
    bench_rows = []
    for _, row in sel.iterrows():
        crop, model, route = row["crop"], row["model"], row["route"]
        art_path = de_path("models", "price", f"{crop}_{model}_{route}.joblib")
        if not art_path.exists():
            print(f"[explain] {crop}: 无 artifact（{model} 可能为 baseline）")
            all_imp.append({"crop": crop, "model": model, "kind": "baseline_rule",
                            "note": "基线模型：解释=规则本身（如 MA7 跟随；季节中位数=历史同月 P50）"})
            bench_rows.append({"library": "builtin", "model": f"baseline_rule:{model}",
                               "version": "-", "city": "沈阳", "crop": crop,
                               "target": row.get("target", "target_mean_price_next_30d"),
                               "route": "baseline", "status": "ADOPTED",
                               "reason": "基线胜出：无参数模型，天然可解释（规则即解释）"})
            continue
        art = joblib.load(art_path)
        X = ds[ds["crop"] == crop].copy()
        if route == "pooled":
            # pooled 模型的类别编码：与训练时 astype("category").cat.codes 一致（按排序后的类别）
            crop_order = sorted(ds["crop"].unique())
            X["crop_cat"] = crop_order.index(crop)
            X_all = ds.copy()
            X_all["crop_cat"] = X_all["crop"].map({c: i for i, c in enumerate(crop_order)})
        else:
            X_all = X
        X_feat = X_all[X_all[art["target"]].notna()] if art["target"] in X_all.columns else X_all
        # 局部解释：最新 3 行 + 2024-01 前后 2 行（按本作物）
        recent = X.sort_values("date").tail(3)
        hist_sample = X[(X["date"] >= "2024-01-01") & (X["date"] <= "2024-01-15")].head(2)
        locals_df = pd.concat([recent, hist_sample])
        if route == "pooled":
            locals_df = locals_df.copy()
            locals_df["crop_cat"] = crop_order.index(crop)
        res = ex.explain_model(art, X_feat, local_rows=locals_df)
        imp = res.get("global_importance")
        if imp is not None:
            imp = imp.copy()
            imp["crop"] = crop
            imp["model"] = model
            imp["kind"] = res.get("kind")
            all_imp.append(imp)
            imp.to_csv(mdir / f"feature_importance_{crop}.csv", index=False, encoding="utf-8-sig")
            print(f"[explain] {crop} {model}: {res.get('kind')} top3="
                  f"{imp['feature'].head(3).tolist() if 'feature' in imp else '?'}")
        local_out[crop] = {"model": model, "kind": res.get("kind"), "note": res.get("note"),
                           "local": res.get("local"),
                           "local_rows": locals_df[["date", "price_per_kg"]].astype(str).to_dict("records")}
        lib = "interpret" if res.get("kind") == "ebm_global" else (
            "shap" if res.get("kind") == "shap_tree" else "builtin")
        bench_rows.append({"library": lib, "model": f"explain:{model}", "version": pkg_version(lib),
                           "city": "沈阳", "crop": crop, "target": art["target"],
                           "route": route, "status": "ADOPTED",
                           "reason": f"最终模型解释方式={res.get('kind')}（解释模型决策依据，非因果）"})

    if all_imp:
        pd.concat([pd.DataFrame([a]) if not isinstance(a, pd.DataFrame) else a for a in all_imp],
                  ignore_index=True).to_csv(mdir / "feature_importance_all.csv",
                                            index=False, encoding="utf-8-sig")
    with open(cdir / "local_explanations.json", "w", encoding="utf-8") as f:
        json.dump(local_out, f, ensure_ascii=False, indent=2, default=str)
    upsert_benchmark(bench_rows)
    print(f"[explain] done crops={len(sel)}")


if __name__ == "__main__":
    main()