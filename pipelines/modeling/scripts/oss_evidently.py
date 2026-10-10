# -*- coding: utf-8 -*-
"""
开源 P1 评估：Evidently —— 数据漂移与回归质量报告（QC 工具，不改变预测）。

  python3 decision_engine/scripts/oss_evidently.py

输出：
  decision_engine/evaluation/open_source/evidently_drift_{period}.html
  decision_engine/evaluation/open_source/evidently_drift_summary.csv
  decision_engine/evaluation/open_source/evidently_regression_{fold}.html
说明：漂移结论已通过自研 KS 检验接入 Confidence Engine（confidence/drift.py）；
      Evidently 用于生成可展示的 QC 报告（降低人工 QC 工作量）。
"""
from __future__ import annotations
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from decision_engine.common import de_path, ensure_dir  # noqa: E402
from decision_engine.models.oss_common import upsert_benchmark, pkg_version  # noqa: E402

DRIFT_FEATURES = ["price_per_kg", "price_ma7", "price_ma30", "volatility_30",
                  "price_return_30", "price_momentum_30", "volume_ma30", "month"]


def get_report_cls():
    try:
        from evidently import Report  # >=0.7 新 API
        from evidently.presets import DataDriftPreset
        return Report, DataDriftPreset, "new"
    except Exception:
        from evidently.report import Report
        from evidently.metric_preset import DataDriftPreset
        return Report, DataDriftPreset, "legacy"


def main():
    ds = pd.read_parquet(de_path("data", "processed", "decision_dataset_v1.parquet"))
    ds["date"] = pd.to_datetime(ds["date"])
    out = ensure_dir(de_path("evaluation", "open_source"))
    cols = [c for c in DRIFT_FEATURES if c in ds.columns]

    try:
        Report, DataDriftPreset, api = get_report_cls()
        print(f"[evidently] API={api}", flush=True)
    except Exception as e:
        print(f"[evidently] 不可用: {e}", flush=True)
        upsert_benchmark([{"library": "evidently", "model": "DataDriftPreset", "version": pkg_version("evidently"),
                           "city": "沈阳", "crop": "ALL", "target": "-", "route": "-",
                           "status": "FAILED", "reason": f"导入失败: {type(e).__name__}"}])
        return

    ref = ds[ds["date"] <= "2023-12-31"][cols]
    summary = []
    for label, start, end in [("2024", "2024-01-01", "2024-12-31"),
                              ("2025", "2025-01-01", "2025-12-31"),
                              ("2026", "2026-01-01", "2026-09-14")]:
        cur = ds[(ds["date"] >= start) & (ds["date"] <= end)][cols]
        rep = Report(metrics=[DataDriftPreset()])
        try:
            rep.run(reference_data=ref, current_data=cur)
            rep.save_html(str(out / f"evidently_drift_{label}.html"))
            d = rep.as_dict()
            n_drift = None
            for m in d.get("metrics", []):
                r = m.get("result", {})
                if isinstance(r, dict) and "number_of_drifted_columns" in r:
                    n_drift = r["number_of_drifted_columns"]
                    share = r.get("share_of_drifted_columns")
                    summary.append({"period": label, "n_features": len(cols),
                                    "drifted_columns": n_drift, "drift_share": share})
                    break
            print(f"[evidently] {label}: drifted={n_drift}/{len(cols)}", flush=True)
        except Exception as e:
            print(f"[evidently] {label} failed: {type(e).__name__} {str(e)[:120]}", flush=True)
            summary.append({"period": label, "n_features": len(cols), "drifted_columns": None,
                            "error": f"{type(e).__name__}: {str(e)[:100]}"})
    pd.DataFrame(summary).to_csv(out / "evidently_drift_summary.csv", index=False, encoding="utf-8-sig")

    # 回归质量报告（按 fold 汇总所有作物的 chosen model 预测）
    preds_path = de_path("evaluation", "backtests", "predictions.parquet")
    if preds_path.exists():
        preds = pd.read_parquet(preds_path)
        preds = preds[preds["target"] == "target_mean_price_next_30d"]
        preds["date"] = pd.to_datetime(preds["date"])
        try:
            df = preds.rename(columns={"actual": "target", "prediction": "prediction"})
            for fold, g in df.groupby("fold"):
                rep = Report(metrics=[])
                from evidently.metrics import RegressionQualityMetric  # legacy 兼容
                rep = Report(metrics=[RegressionQualityMetric()])
                rep.run(reference_data=g[["target", "prediction"]],
                        current_data=g[["target", "prediction"]])
                rep.save_html(str(out / f"evidently_regression_{fold}.html"))
            print("[evidently] regression reports saved", flush=True)
        except Exception as e:
            print(f"[evidently] regression 报告失败（不影响主流程）: {type(e).__name__} {str(e)[:100]}")

    upsert_benchmark([{"library": "evidently", "model": "DataDriftPreset", "version": pkg_version("evidently"),
                       "city": "沈阳", "crop": "ALL", "target": "-", "route": "qc",
                       "status": "ADOPTED",
                       "reason": "QC/漂移报告工具：降低人工 QC 工作量；漂移结论已由自研 KS 检验接入 confidence"}])


if __name__ == "__main__":
    main()