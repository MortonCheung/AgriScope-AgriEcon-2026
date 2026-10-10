# -*- coding: utf-8 -*-
"""C10: Final 模型产物持久化（生产推理唯一加载源）。

对每个 (city, crop, horizon∈{7,14,30}) 用 **Final selected model** 在全量 Final 数据上重拟合，
pickle 到 models/models/final/。baseline 类选择不产出 artifact（规则式，实时计算）。
"""
from __future__ import annotations
import pickle
from typing import Dict

import pandas as pd

from decision_engine.final.fcommon import (SNAPSHOT_DIR, FINAL_MODELS_DIR, REPORTS_DIR,
                                           ensure_dir, write_json, now_stamp, sha256_file,
                                           MODEL_VERSION, DATA_VERSION)
from decision_engine.final.models import FINAL_FEATURE_COLS, _factories

CITIES = ["沈阳", "朝阳"]
MODEL_H = [7, 14, 30]


def _sel() -> pd.DataFrame:
    return pd.read_csv(REPORTS_DIR / "tables" / "price_model_selection.csv")


def build_artifacts() -> Dict[str, object]:
    ensure_dir(FINAL_MODELS_DIR)
    sel = _sel()
    facs = _factories()
    rows = []
    for city in CITIES:
        ds = pd.read_parquet(SNAPSHOT_DIR / "datasets" / f"decision_dataset_{city}.parquet")
        for h in MODEL_H:
            sub = sel[(sel["city"] == city) & (sel["horizon"] == h)]
            for _, r in sub.iterrows():
                crop, model = r["crop"], r["model"]
                if model not in facs:
                    rows.append({"city": city, "crop": crop, "horizon": h, "algorithm": model,
                                 "artifact": None, "kind": "rule_baseline"})
                    continue
                tgt = f"target_mean_price_next_{h}d"
                tr = ds[ds["crop"] == crop]
                tr = tr[tr[tgt].notna()]
                if len(tr) < 200:
                    rows.append({"city": city, "crop": crop, "horizon": h, "algorithm": model,
                                 "artifact": None, "kind": "insufficient_train_rows"})
                    continue
                est = facs[model]()
                est.fit(tr[FINAL_FEATURE_COLS], tr[tgt])
                name = f"{city}_{crop}_h{h}_{model}.pkl"
                path = FINAL_MODELS_DIR / name
                with open(path, "wb") as f:
                    pickle.dump({"estimator": est, "features": FINAL_FEATURE_COLS,
                                 "city": city, "crop": crop, "horizon": h,
                                 "algorithm": model, "target": tgt,
                                 "model_version": MODEL_VERSION, "data_version": DATA_VERSION,
                                 "n_train": int(len(tr)),
                                 "train_end": str(pd.to_datetime(tr["date"]).max().date())}, f)
                from decision_engine.common import ROOT
                rows.append({"city": city, "crop": crop, "horizon": h, "algorithm": model,
                             "artifact": str(path.relative_to(ROOT)),
                             "kind": "ml", "n_train": int(len(tr)),
                             "sha256": sha256_file(path),
                             "trained_at": now_stamp()})
    man = pd.DataFrame(rows)
    man.to_csv(REPORTS_DIR / "tables" / "final_model_artifacts.csv", index=False, encoding="utf-8-sig")
    out = {"n_ml": int((man["kind"] == "ml").sum()),
           "n_rule_baseline": int((man["kind"] == "rule_baseline").sum()),
           "dir": str(FINAL_MODELS_DIR)}
    write_json(out, REPORTS_DIR / "tables" / "final_artifacts_summary.json")
    return out


_CACHE: Dict[str, object] = {}


def load_artifact(city: str, crop: str, horizon: int):
    key = f"{city}_{crop}_h{horizon}"
    if key in _CACHE:
        return _CACHE[key]
    sel = _sel()
    row = sel[(sel["city"] == city) & (sel["crop"] == crop) & (sel["horizon"] == horizon)]
    if not len(row):
        return None
    model = row.iloc[0]["model"]
    p = FINAL_MODELS_DIR / f"{city}_{crop}_h{horizon}_{model}.pkl"
    if not p.exists():
        return None
    with open(p, "rb") as f:
        obj = pickle.load(f)
    _CACHE[key] = obj
    return obj


def predict(city: str, crop: str, horizon: int, features_row: pd.Series):
    obj = load_artifact(city, crop, horizon)
    if obj is None:
        return None
    X = pd.DataFrame([features_row[obj["features"]].to_dict()])
    return float(obj["estimator"].predict(X)[0])


if __name__ == "__main__":
    print(build_artifacts())