# -*- coding: utf-8 -*-
"""Phase 12: 朝阳 / 锦州 简化价格模块。

关键事实（审计确认）：
  - 朝阳：crop_standard 被错填为规格词；真实作物在 crop_raw；price_level=market_average；
  - 锦州：price_level 混有 supermarket/retail_market/market_average，禁止混层级；
  - 二者均无成交量；不用天气驱动价格。
简化模块内容：特征（复用 build_features）→ 基线 + Ridge + HistGB → 同一 fold 回测
            → 季节分位（P10/P50/P90）+ 简化 HRI-lite 组件。
"""
from __future__ import annotations
from typing import Dict, List

import numpy as np
import pandas as pd

from decision_engine.common import de_path
from decision_engine.data.build_dataset import add_calendar, join_qc  # noqa: F401
from decision_engine.features.build_features import add_price_features, add_targets

FOLDS = [
    {"name": "fold1_test2024", "train_end": "2023-12-31", "test_start": "2024-01-01", "test_end": "2024-12-31"},
    {"name": "fold2_test2025", "train_end": "2024-12-31", "test_start": "2025-01-01", "test_end": "2025-12-31"},
    {"name": "fold3_test2026", "train_end": "2025-12-31", "test_start": "2026-01-01", "test_end": "2026-09-21"},
]

REGIONAL_FEATURES = None  # 延迟构建（去除 volume 列）


def load_chaoyang_base(min_obs: int = 200) -> pd.DataFrame:
    p = pd.read_csv(de_path("data", "snapshots", "v1", "city_data/chaoyang/data/price_observation.csv"),
                    low_memory=False)
    df = p[p["price_level"] == "market_average"].copy()
    df["crop"] = df["crop_raw"].astype(str).str.strip()   # 用 crop_raw（crop_standard 错填规格）
    df["date"] = pd.to_datetime(df["observation_date"]).dt.date
    df = df.rename(columns={"price_per_kg": "price_per_kg_canonical"})
    df["price_per_kg"] = pd.to_numeric(df["price_per_kg_canonical"], errors="coerce")
    df = df[["date", "crop", "price_per_kg"]].dropna()
    df["city"] = "朝阳"
    # 去重：同 (crop, date) 多条记录取均值（并报告）
    dup = int(df.duplicated(["date", "crop"]).sum())
    if dup:
        print(f"[regional] 朝阳: 发现 {dup} 条重复 (date,crop)，按均值聚合（原样记录）")
    df = df.groupby(["date", "crop"], as_index=False).agg(
        price_per_kg=("price_per_kg", "mean"), city=("city", "first"))
    cnt = df.groupby("crop")["date"].count()
    keep = cnt[cnt >= min_obs].index
    return df[df["crop"].isin(keep)].sort_values(["crop", "date"]).reset_index(drop=True)


def load_jinzhou_base(min_obs: int = 200, levels=("supermarket", "retail_market", "market_average")) -> pd.DataFrame:
    p = pd.read_csv(de_path("data", "snapshots", "v1", "city_data/jinzhou/data/price_observation.csv"),
                    low_memory=False)
    df = p[p["price_level"].isin(levels)].copy()
    df["date"] = pd.to_datetime(df["observation_date"]).dt.date
    df["crop"] = df["crop_raw"].astype(str).str.strip()
    df = df.rename(columns={"price_per_kg": "price_per_kg_canonical"})
    df["price_per_kg"] = pd.to_numeric(df["price_per_kg_canonical"], errors="coerce")
    df = df[["date", "crop", "price_level", "price_per_kg"]].dropna()
    # 每个作物只保留观测最多的单一价格层级（禁止混层级）
    best = (df.groupby(["crop", "price_level"])["date"].count().reset_index()
            .sort_values(["crop", "date"], ascending=[True, False])
            .drop_duplicates("crop").rename(columns={"date": "n_obs"}))
    df = df.merge(best[["crop", "price_level"]], on=["crop", "price_level"], how="inner")
    cnt = df.groupby("crop")["date"].count()
    keep = cnt[cnt >= min_obs].index
    df = df[df["crop"].isin(keep)].copy()
    df["city"] = "锦州"
    dup = int(df.duplicated(["date", "crop"]).sum())
    if dup:
        print(f"[regional] 锦州: 发现 {dup} 条重复 (date,crop)，按均值聚合")
    df = df.groupby(["date", "crop"], as_index=False).agg(
        price_per_kg=("price_per_kg", "mean"), price_level=("price_level", "first"),
        city=("city", "first"))
    return df.sort_values(["crop", "date"]).reset_index(drop=True)


def build_regional_dataset(base: pd.DataFrame) -> pd.DataFrame:
    """复用主特征工程（无 volume；含季节分位与目标）。"""
    d = base.copy()
    d["date"] = pd.to_datetime(d["date"]).dt.date
    d = add_calendar(d)
    d = add_price_features(d)
    d = add_targets(d)
    return d


def regional_feature_cols(ds: pd.DataFrame) -> List[str]:
    from decision_engine.models.train_price import FEATURE_COLS
    return [c for c in FEATURE_COLS if c in ds.columns and not c.startswith("volume")]


def run_regional_backtest(ds: pd.DataFrame, city: str, crops: List[str] | None = None) -> tuple:
    """基线 + Ridge + ExtraTrees + HistGB 的简化回测（同一 fold 定义）。"""
    from decision_engine.models.backtest import fold_mask, metrics_table
    from decision_engine.models.train_price import baseline_predictions, baseline_metrics

    colmap = {c: c for c in ds.columns}
    ds = ds.rename(columns=colmap)
    tgt = "target_mean_price_next_30d"
    facs = _regional_models()
    preds = baseline_predictions(ds, tgt, folds=FOLDS)
    mets = [baseline_metrics(preds)]
    for crop, sub in ds.groupby("crop"):
        if crops and crop not in crops:
            continue
        feats = regional_feature_cols(sub)
        for fold in FOLDS:
            tr_all, te_all = fold_mask(sub, fold)
            tr = sub[tr_all & sub[tgt].notna()]
            te = sub[te_all & sub[tgt].notna()]
            if len(tr) < 200 or not len(te):
                continue
            rows = []
            for name, fac in facs.items():
                m = fac()
                m.fit(tr[feats], tr[tgt])
                p = m.predict(te[feats])
                for dt, act, pr, anc in zip(te["date"], te[tgt], p, te["price_per_kg"]):
                    rows.append({"date": dt, "crop": crop, "model": name, "fold": fold["name"],
                                 "route": f"regional_{city}", "target": tgt,
                                 "actual": float(act), "prediction": float(pr),
                                 "anchor_price": float(anc)})
            pr = pd.DataFrame(rows)
            preds = pd.concat([preds, pr], ignore_index=True)
            for name in facs:
                g = pr[pr["model"] == name]
                mm = metrics_table(g["actual"].values, g["prediction"].values,
                                   anchor=g["anchor_price"].values)
                mm.update({"model": name, "route": f"regional_{city}", "crop": crop,
                           "fold": fold["name"], "target": tgt})
                mets.append(pd.DataFrame([mm]))
    return preds, pd.concat(mets, ignore_index=True)


def _regional_models() -> Dict:
    from sklearn.pipeline import Pipeline
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import Ridge
    from sklearn.ensemble import HistGradientBoostingRegressor, ExtraTreesRegressor

    def pipe(est):
        return Pipeline([("imp", SimpleImputer(strategy="median")), ("m", est)])

    return {
        "regional_ridge": lambda: pipe(Ridge(alpha=1.0, random_state=42)),
        "regional_histgb": lambda: pipe(HistGradientBoostingRegressor(
            max_iter=250, learning_rate=0.06, random_state=42)),
        "regional_extra_trees": lambda: pipe(ExtraTreesRegressor(
            n_estimators=300, min_samples_leaf=3, n_jobs=-1, random_state=42)),
    }


def regional_summary(mets: pd.DataFrame) -> pd.DataFrame:
    g = mets.groupby(["route", "model", "crop"])
    out = g.agg(mean_WAPE=("WAPE", "mean"), std_WAPE=("WAPE", "std"),
                mean_MAE=("MAE", "mean"), mean_sMAPE=("sMAPE", "mean"),
                folds=("WAPE", "count")).reset_index()
    out["score"] = out["mean_WAPE"] + 0.5 * out["std_WAPE"].fillna(0)
    return out.sort_values(["crop", "score"])


def regional_selection(summary: pd.DataFrame) -> pd.DataFrame:
    best = summary.sort_values("score").groupby("crop", as_index=False).first()
    base = (summary[summary["model"].str.startswith("baseline_")].sort_values("score")
            .groupby("crop", as_index=False).first()
            .rename(columns={"model": "best_baseline", "mean_WAPE": "baseline_mean_WAPE"})
            [["crop", "best_baseline", "baseline_mean_WAPE"]])
    best = best.merge(base, on="crop", how="left")
    best["beats_baseline"] = best["mean_WAPE"] < best["baseline_mean_WAPE"]
    return best.sort_values("crop")