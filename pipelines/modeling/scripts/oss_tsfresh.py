# -*- coding: utf-8 -*-
"""
开源 P1 评估：tsfresh —— 受控特征发现实验（严格 past-only）。

方法：
  - 对每个观察 t（stride=3），仅用过去 30 / 90 个观测的价格序列提取 tsfresh 特征
    （窗口只含 <= t 的数据，禁止整条序列一次性提取）；
  - 与手工特征合并后，用同一时间回测（HistGB）比较 WAPE；
  - 若稳定提升 → 只保留少量真正有用特征写入 feature_dictionary；
  - 若无提升 → 删除附加特征，不增加复杂度。
输出：
  decision_engine/evaluation/open_source/tsfresh_features.parquet
  decision_engine/evaluation/open_source/tsfresh_experiment.csv
"""
from __future__ import annotations
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from decision_engine.common import de_path, ensure_dir  # noqa: E402
from decision_engine.models.backtest import FOLDS, fold_mask, metrics_table  # noqa: E402
from decision_engine.models.oss_common import upsert_benchmark, pkg_version  # noqa: E402
from decision_engine.models.train_price import (FEATURE_COLS, MIN_TRAIN_ROWS,  # noqa: E402
                                                PRIMARY_TARGET)

STRIDE = 3
WINDOWS = [30, 90]


def extract_tsfresh(ds: pd.DataFrame) -> pd.DataFrame:
    from tsfresh import extract_features
    from tsfresh.feature_extraction import MinimalFCParameters
    rows = []
    t0 = time.time()
    for crop, sub in ds.groupby("crop"):
        sub = sub.sort_values("date")          # 保留原始索引（用于最后对齐 ds）
        price = sub["price_per_kg"].values.astype(float)
        for w in WINDOWS:
            ids, times, vals = [], [], []
            for i in range(w, len(sub), STRIDE):
                seg = price[i - w + 1:i + 1]        # 只含 <= t（含 t）
                ids.extend([f"{i}"] * w)
                times.extend(range(w))
                vals.extend(seg)
            long = pd.DataFrame({"id": ids, "time": times, "value": vals})
            feat = extract_features(long, column_id="id", column_sort="time",
                                    default_fc_parameters=MinimalFCParameters(),
                                    disable_progressbar=True, n_jobs=4)
            feat = feat.loc[:, ~feat.columns.duplicated()]
            feat.columns = [f"tsf_{crop}_{w}_{c}" for c in feat.columns]
            idx = [int(s) for s in feat.index]
            feat.index = sub.index.values[idx]      # 映射回 ds 的原始行索引
            rows.append(feat)
            print(f"[tsfresh] {crop} w={w}: {feat.shape} ({time.time()-t0:.0f}s)", flush=True)
    out = pd.concat(rows, axis=1)
    return out


def main():
    ds = pd.read_parquet(de_path("data", "processed", "decision_dataset_v1.parquet"))
    ds["date"] = pd.to_datetime(ds["date"])
    out_dir = ensure_dir(de_path("evaluation", "open_source"))

    t0 = time.time()
    tsf = extract_tsfresh(ds)
    tsf = tsf[~tsf.index.duplicated(keep="first")]
    df = ds.join(tsf, how="inner")
    tsf_cols = [c for c in tsf.columns if c.startswith("tsf_")]
    print(f"[tsfresh] merged {df.shape}, tsf cols={len(tsf_cols)}, {time.time()-t0:.0f}s", flush=True)
    df[["date", "crop"] + tsf_cols].to_parquet(out_dir / "tsfresh_features.parquet", index=False)

    from sklearn.pipeline import Pipeline
    from sklearn.impute import SimpleImputer
    from sklearn.ensemble import HistGradientBoostingRegressor

    def make():
        return Pipeline([("imp", SimpleImputer(strategy="median")),
                         ("m", HistGradientBoostingRegressor(max_iter=300, learning_rate=0.06,
                                                             random_state=42))])

    def run(feats, label):
        preds, mets = [], []
        for crop, sub in df.groupby("crop"):
            sub = sub[sub[PRIMARY_TARGET].notna()]
            feats_c = [f for f in feats if f in sub.columns]
            for fold in FOLDS:
                tr_all, te_all = fold_mask(sub, fold)
                tr, te = sub[tr_all], sub[te_all]
                if len(tr) < MIN_TRAIN_ROWS or not len(te):
                    continue
                m = make()
                m.fit(tr[feats_c], tr[PRIMARY_TARGET])
                p = m.predict(te[feats_c])
                mm = metrics_table(te[PRIMARY_TARGET].values, p)
                mm.update({"model": label, "crop": crop, "fold": fold["name"]})
                mets.append(mm)
        return pd.DataFrame(mets)

    base_m = run(FEATURE_COLS, "manual_only")
    tsf_m = run(FEATURE_COLS + tsf_cols, "manual_plus_tsfresh")
    allm = pd.concat([base_m, tsf_m], ignore_index=True)
    cmp = (allm.groupby(["model", "crop"]).agg(WAPE=("WAPE", "mean"), MAE=("MAE", "mean"))
           .reset_index().pivot(index="crop", columns="model", values="WAPE").reset_index())
    cmp["delta_WAPE"] = cmp["manual_plus_tsfresh"] - cmp["manual_only"]
    cmp["delta_pct"] = cmp["delta_WAPE"] / cmp["manual_only"] * 100
    cmp.to_csv(out_dir / "tsfresh_experiment.csv", index=False, encoding="utf-8-sig")
    print("[tsfresh experiment]\n", cmp.to_string(index=False), flush=True)

    mean_delta = float(cmp["delta_pct"].mean())
    n_better = int((cmp["delta_WAPE"] < 0).sum())
    if mean_delta < -1.0 and n_better >= 6:
        status, reason = "BENCHMARK_ONLY", f"平均改善 {mean_delta:.2f}%（{n_better}/10 作物）但复杂度增加；未纳入正式 pipeline"
    else:
        status, reason = "REJECTED", f"无稳定提升（平均 {mean_delta:+.2f}%，{n_better}/10 作物变好）→ 不保留附加特征"
    upsert_benchmark([{"library": "tsfresh", "model": "manual_plus_tsfresh", "version": pkg_version("tsfresh"),
                       "city": "沈阳", "crop": "ALL(10)", "target": PRIMARY_TARGET,
                       "route": "per_crop", "MAE": round(float(tsf_m["MAE"].mean()), 4),
                       "RMSE": round(float(tsf_m["RMSE"].mean()), 4),
                       "sMAPE": round(float(tsf_m["sMAPE"].mean()), 4),
                       "WAPE": round(float(tsf_m["WAPE"].mean()), 4),
                       "status": status, "reason": reason}])
    print(f"[tsfresh] status={status}", flush=True)


if __name__ == "__main__":
    main()