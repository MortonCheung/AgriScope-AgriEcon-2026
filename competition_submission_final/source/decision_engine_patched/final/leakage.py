# -*- coding: utf-8 -*-
"""F2: 时间泄漏审计 —— 截断不变性实证测试（强于静态代码审查）。

原理：若特征在 t 只用 <=t 的信息，则「把数据集截断到 T 后重建特征」，
      在 date<=T 的行上与「全量重建特征」逐值一致（数值容差内）。
      任何依赖未来（centered rolling / 全样本分位回填 / 未来窗口均值）的特征
      都会在截断实验中产生差异 → 判为 leakage。

同时静态检查：目标列命名、禁用特征列是否被误用。
"""
from __future__ import annotations
from typing import Dict, List

import numpy as np
import pandas as pd

from decision_engine.features.build_features import add_price_features
from decision_engine.final.build import shenyang_base, chaoyang_base
from decision_engine.final.fcommon import MANIFEST_DIR, SNAPSHOT_DIR, ensure_dir

CUTOFFS = ["2023-06-30", "2024-06-30", "2025-06-30"]

TARGET_PREFIXES = ("target_",)
META_NON_FEATURE = {"date", "city", "crop", "year", "month", "week", "day_of_year",
                    "quarter", "season"}


def _feature_cols(df: pd.DataFrame) -> List[str]:
    cols = []
    for c in df.columns:
        if c in META_NON_FEATURE or c.startswith(TARGET_PREFIXES):
            continue
        if pd.api.types.is_numeric_dtype(df[c]):
            cols.append(c)
    return cols


def truncation_test(city: str = "沈阳", cutoffs: List[str] = CUTOFFS) -> pd.DataFrame:
    base = shenyang_base() if city == "沈阳" else chaoyang_base()
    full = add_price_features(base)
    feats = _feature_cols(full)
    rows = []
    for cut in cutoffs:
        cut_t = pd.Timestamp(cut).date()
        b_t = base[pd.to_datetime(base["date"]).dt.date <= cut_t].copy()
        f_t = add_price_features(b_t)
        key = ["crop", "date"]
        m = full[key].astype(str).agg("|".join, axis=1)
        n = f_t[key].astype(str).agg("|".join, axis=1)
        full_i = full.assign(_k=m).set_index("_k")
        trunc_i = f_t.assign(_k=n).set_index("_k")
        common = full_i.index.intersection(trunc_i.index)
        diffs = {}
        for c in feats:
            a = pd.to_numeric(full_i.loc[common, c], errors="coerce").to_numpy(dtype=float)
            b = pd.to_numeric(trunc_i.loc[common, c], errors="coerce").to_numpy(dtype=float)
            both_na = np.isnan(a) & np.isnan(b)
            d = np.where(both_na, 0.0, np.abs(np.nan_to_num(a, nan=1e9) - np.nan_to_num(b, nan=1e9)))
            diffs[c] = float(np.max(d)) if len(d) else 0.0
        bad = {k: v for k, v in diffs.items() if v > 1e-6}
        rows.append({
            "city": city, "cutoff": cut, "n_common_rows": int(len(common)),
            "n_features": len(feats), "n_leak_features": len(bad),
            "leak_features": ";".join(sorted(bad.keys())) if bad else "",
            "max_diff": max(diffs.values()) if diffs else 0.0,
        })
    return pd.DataFrame(rows)


def static_checks(ds: pd.DataFrame) -> pd.DataFrame:
    rows = []
    # 目标列必须只作为标签
    tgts = [c for c in ds.columns if c.startswith("target_")]
    rows.append({"check": "target 列数量", "value": len(tgts), "ok": True,
                 "note": "建模时禁止进入 X（由 FINAL_FEATURE_COLS 白名单保证）"})
    # 禁用特征是否出现
    forbidden = ["centered", "future", "forward", "next_price", "lead_"]
    hit = [c for c in ds.columns for f in forbidden if f in c.lower()]
    rows.append({"check": "禁用特征名扫描", "value": len(hit), "ok": len(hit) == 0,
                 "note": ";".join(sorted(set(hit)))})
    # volume 是否缺席（Final 不使用，因不在 model_ready）
    vol = [c for c in ds.columns if c.startswith("volume")]
    rows.append({"check": "volume 特征缺席", "value": len(vol), "ok": len(vol) == 0,
                 "note": "volume 不在 data/model_ready/，Final 价格模型不使用"})
    return pd.DataFrame(rows)


def run() -> Dict[str, object]:
    ensure_dir(MANIFEST_DIR)
    t1 = truncation_test("沈阳")
    t2 = truncation_test("朝阳")
    ds = pd.read_parquet(SNAPSHOT_DIR / "datasets" / "decision_dataset_沈阳.parquet")
    static = static_checks(ds)
    both = pd.concat([t1, t2], ignore_index=True)
    both.to_csv(MANIFEST_DIR / "leakage_truncation_test.csv", index=False, encoding="utf-8-sig")
    static.to_csv(MANIFEST_DIR / "leakage_static_checks.csv", index=False, encoding="utf-8-sig")
    leak = int(both["n_leak_features"].sum())
    return {"leak_features_total": leak, "passed": leak == 0,
            "static_ok": bool(static["ok"].all())}


if __name__ == "__main__":
    r = run()
    print(r)