# -*- coding: utf-8 -*-
"""Phase 3: P10/P50/P90 价格区间（calibration 对比）。

四种候选（全部严格 point-in-time）：
  1. seasonal_quantile      —— 历史同期（严格更早年份）P10/P50/P90（情景分布，非 prediction interval）
  2. residual_calibration   —— 训练期 80/20 时序内分裂的 OOS 残差分位（q10/q90）
  3. quantile_regression    —— LightGBM quantile (alpha=0.1/0.5/0.9)
  4. mapie_enbpi            —— MAPIE TimeSeriesRegressor(method='enbpi')，时间序列非交换性适配

评价：empirical coverage / mean & median width / coverage by crop / by fold(year) / undercoverage rate
只有覆盖率接近 nominal 0.8 的方法才允许称为 calibrated prediction interval。
"""
from __future__ import annotations
from typing import Dict, List

import numpy as np
import pandas as pd

from decision_engine.models.backtest import FOLDS, fold_mask
from decision_engine.models.train_price import FEATURE_COLS, MIN_TRAIN_ROWS

NOMINAL = 0.80


def cov_width(actual: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> Dict[str, float]:
    m = np.isfinite(actual) & np.isfinite(lo) & np.isfinite(hi)
    a, l, h = actual[m], lo[m], hi[m]
    if len(a) == 0:
        return {"n": 0, "coverage": np.nan, "mean_width": np.nan, "median_width": np.nan}
    inside = (a >= l) & (a <= h)
    return {"n": int(len(a)), "coverage": float(inside.mean()),
            "mean_width": float((h - l).mean()), "median_width": float(np.median(h - l))}


# ---------------------------------------------------------------- 1. seasonal quantile
def seasonal_quantile_intervals(ds: pd.DataFrame) -> pd.DataFrame:
    d = ds.copy()
    rows = []
    for fold in FOLDS:
        _, te_all = fold_mask(d, fold)
        te = d[te_all & d["target_mean_price_next_30d"].notna()]
        for _, r in te.iterrows():
            rows.append({"method": "seasonal_quantile", "fold": fold["name"], "crop": r["crop"],
                         "date": r["date"], "actual": r["target_mean_price_next_30d"],
                         "mid": r["seasonal_p50"], "lo": r["seasonal_p10"], "hi": r["seasonal_p90"]})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 2. residual calibration
def residual_calibration_intervals(ds: pd.DataFrame, make_model, inner_frac: float = 0.8) -> pd.DataFrame:
    d = ds.copy()
    rows = []
    for fold in FOLDS:
        tr_all, te_all = fold_mask(d, fold)
        for crop, sub in d.groupby("crop"):
            tr = sub[tr_all.loc[sub.index] & sub["target_mean_price_next_30d"].notna()].sort_values("date")
            te = sub[te_all.loc[sub.index] & sub["target_mean_price_next_30d"].notna()]
            if len(tr) < MIN_TRAIN_ROWS or not len(te):
                continue
            cut = int(len(tr) * inner_frac)
            itr, ical = tr.iloc[:cut], tr.iloc[cut:]
            m = make_model()
            m.fit(itr[FEATURE_COLS], itr["target_mean_price_next_30d"])
            res = ical["target_mean_price_next_30d"].values - m.predict(ical[FEATURE_COLS])
            q_lo, q_hi = np.quantile(res, [0.10, 0.90])
            m2 = make_model()
            m2.fit(tr[FEATURE_COLS], tr["target_mean_price_next_30d"])
            mid = m2.predict(te[FEATURE_COLS])
            for dt, act, md in zip(te["date"], te["target_mean_price_next_30d"], mid):
                rows.append({"method": "residual_calibration", "fold": fold["name"], "crop": crop,
                             "date": dt, "actual": act, "mid": md, "lo": md + q_lo, "hi": md + q_hi})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 3. quantile regression (LightGBM)
def quantile_regression_intervals(ds: pd.DataFrame, seed: int = 42) -> pd.DataFrame:
    from lightgbm import LGBMRegressor
    from sklearn.pipeline import Pipeline
    from sklearn.impute import SimpleImputer

    d = ds.copy()
    rows = []
    for fold in FOLDS:
        tr_all, te_all = fold_mask(d, fold)
        for crop, sub in d.groupby("crop"):
            tr = sub[tr_all.loc[sub.index] & sub["target_mean_price_next_30d"].notna()]
            te = sub[te_all.loc[sub.index] & sub["target_mean_price_next_30d"].notna()]
            if len(tr) < MIN_TRAIN_ROWS or not len(te):
                continue
            preds = {}
            for q in [0.1, 0.5, 0.9]:
                m = Pipeline([("imp", SimpleImputer(strategy="median")),
                              ("m", LGBMRegressor(objective="quantile", alpha=q, n_estimators=400,
                                                  learning_rate=0.05, num_leaves=31,
                                                  random_state=seed, n_jobs=-1, verbose=-1))])
                m.fit(tr[FEATURE_COLS], tr["target_mean_price_next_30d"])
                preds[q] = m.predict(te[FEATURE_COLS])
            lo = np.minimum(preds[0.1], preds[0.9])
            hi = np.maximum(preds[0.1], preds[0.9])
            for dt, act, md, a, b in zip(te["date"], te["target_mean_price_next_30d"],
                                         preds[0.5], lo, hi):
                rows.append({"method": "quantile_regression", "fold": fold["name"], "crop": crop,
                             "date": dt, "actual": act, "mid": md, "lo": a, "hi": b})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 4. MAPIE EnbPI
def mapie_enbpi_intervals(ds: pd.DataFrame, seed: int = 42, n_estimators: int = 200) -> pd.DataFrame:
    from sklearn.ensemble import RandomForestRegressor
    from mapie.regression import TimeSeriesRegressor
    from sklearn.impute import SimpleImputer

    d = ds.copy()
    rows = []
    for fold in FOLDS:
        tr_all, te_all = fold_mask(d, fold)
        for crop, sub in d.groupby("crop"):
            tr = sub[tr_all.loc[sub.index] & sub["target_mean_price_next_30d"].notna()]
            te = sub[te_all.loc[sub.index] & sub["target_mean_price_next_30d"].notna()]
            if len(tr) < MIN_TRAIN_ROWS or not len(te):
                continue
            imp = SimpleImputer(strategy="median")
            Xtr = imp.fit_transform(tr[FEATURE_COLS])
            Xte = imp.transform(te[FEATURE_COLS])
            ts = TimeSeriesRegressor(
                estimator=RandomForestRegressor(n_estimators=n_estimators, random_state=seed, n_jobs=-1),
                method="enbpi", cv=None, agg_function="mean")
            ts.fit(Xtr, tr["target_mean_price_next_30d"].values)
            try:
                yp, pi = ts.predict(Xte, confidence_level=NOMINAL)
                pi = np.asarray(pi)[:, :, 0]
                lo, hi = pi[:, 0], pi[:, 1]
                for dt, act, md, a, b in zip(te["date"], te["target_mean_price_next_30d"],
                                             np.asarray(yp), lo, hi):
                    rows.append({"method": "mapie_enbpi", "fold": fold["name"], "crop": crop,
                                 "date": dt, "actual": act, "mid": md, "lo": a, "hi": b})
            except Exception as e:
                print(f"[mapie] {crop} {fold['name']} FAILED {type(e).__name__}: {str(e)[:100]}")
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 5. 同统计量季节分位（窗口均值）
def seasonal_window_quantile_intervals(ds: pd.DataFrame, horizon: int = 30) -> pd.DataFrame:
    """历史同月的「未来 30 天窗口均值」分布（严格 past-only：窗口必须完全结束于 <= t）。

    这是与 target_mean_price_next_30d 同统计量的历史分布，比日频 P10/P90 更贴近目标口径。
    """
    tgt = f"target_mean_price_next_{horizon}d"
    d = ds.sort_values(["crop", "date"]).reset_index(drop=True).copy()
    rows = []
    for crop, sub in d.groupby("crop", sort=False):
        sub = sub.reset_index(drop=True)
        dt = pd.to_datetime(sub["date"])
        tv = sub[tgt].values
        mo = sub["month"].values
        yr = sub["year"].values
        for i in range(len(sub)):
            t = dt.iloc[i]
            # 历史候选：同月、更早年份、且窗口已完全结束（tau + horizon <= t）
            mask = (mo == mo[i]) & (yr < yr[i]) & (dt.values + np.timedelta64(horizon, "D") <= t.to_datetime64())
            vals = tv[mask]
            vals = vals[np.isfinite(vals)]
            if len(vals) < 20:
                continue
            p10, p50, p90 = np.percentile(vals, [10, 50, 90])
            # 只在 fold 测试期输出（与其他方法可比）
            fold = None
            for f in FOLDS:
                if pd.Timestamp(f["test_start"]) <= t <= pd.Timestamp(f["test_end"]):
                    fold = f["name"]
                    break
            if fold is None:
                continue
            rows.append({"method": "seasonal_window_quantile", "fold": fold, "crop": crop,
                         "date": t, "actual": sub[tgt].iloc[i], "mid": p50, "lo": p10, "hi": p90})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 6. 递推 OOS 残差校正
def residual_calibration_expanding_intervals(ds: pd.DataFrame, make_model,
                                             inner_frac: float = 0.8) -> pd.DataFrame:
    """递推 OOS 残差：fold1 用训练期 80/20 内分裂残差；fold2 追加 fold1 测试期残差；
    fold3 追加 fold1+2 残差（全部严格早于当前 fold 的测试期）。"""
    d = ds.sort_values(["crop", "date"]).reset_index(drop=True).copy()
    rows = []
    residuals = {}   # crop -> list of oos residuals（按时间追加）
    for fold in FOLDS:
        tr_all, te_all = fold_mask(d, fold)
        for crop, sub in d.groupby("crop", sort=False):
            tr = sub[tr_all.loc[sub.index] & sub["target_mean_price_next_30d"].notna()].sort_values("date")
            te = sub[te_all.loc[sub.index] & sub["target_mean_price_next_30d"].notna()]
            if len(tr) < MIN_TRAIN_ROWS or not len(te):
                continue
            if crop not in residuals:
                cut = int(len(tr) * inner_frac)
                itr, ical = tr.iloc[:cut], tr.iloc[cut:]
                m = make_model()
                m.fit(itr[FEATURE_COLS], itr["target_mean_price_next_30d"])
                res = ical["target_mean_price_next_30d"].values - m.predict(ical[FEATURE_COLS])
                residuals[crop] = list(res)
            res = np.asarray(residuals[crop], dtype=float)
            res = res[np.isfinite(res)]
            if len(res) < 40:
                continue
            q_lo, q_hi = np.quantile(res, [0.10, 0.90])
            m2 = make_model()
            m2.fit(tr[FEATURE_COLS], tr["target_mean_price_next_30d"])
            mid = m2.predict(te[FEATURE_COLS])
            for dt, act, md in zip(te["date"], te["target_mean_price_next_30d"], mid):
                rows.append({"method": "residual_calibration_expanding", "fold": fold["name"],
                             "crop": crop, "date": dt, "actual": act, "mid": md,
                             "lo": md + q_lo, "hi": md + q_hi})
            # 本 fold 测试期结束后，把该 fold 的 OOS 残差追加（供后续 fold 使用）
            res_now = te["target_mean_price_next_30d"].values - mid
            residuals[crop].extend(list(res_now[np.isfinite(res_now)]))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 7. MAPIE ACI（自适应 conformal，适配分布漂移）
def mapie_aci_intervals(ds: pd.DataFrame, seed: int = 42, n_estimators: int = 200,
                        gamma: float = 0.02) -> pd.DataFrame:
    """Adaptive Conformal Inference：按时间顺序在线更新 alpha，覆盖不足则自动加宽。

    严格 past-only：每个测试原点只用当前及之前的信息更新 alpha，不触碰未来。
    """
    from sklearn.ensemble import RandomForestRegressor
    from mapie.regression import TimeSeriesRegressor
    from sklearn.impute import SimpleImputer

    d = ds.sort_values(["crop", "date"]).reset_index(drop=True).copy()
    rows = []
    for crop, sub in d.groupby("crop", sort=False):
        sub = sub.reset_index(drop=True)
        ts = TimeSeriesRegressor(
            estimator=RandomForestRegressor(n_estimators=n_estimators, random_state=seed, n_jobs=-1),
            method="aci", cv=None, agg_function="mean")
        fitted = False
        for fold in FOLDS:
            tr = sub[(sub["date"] <= pd.Timestamp(fold["train_end"])) &
                     sub["target_mean_price_next_30d"].notna()]
            te = sub[(sub["date"] >= pd.Timestamp(fold["test_start"])) &
                     (sub["date"] <= pd.Timestamp(fold["test_end"])) &
                     sub["target_mean_price_next_30d"].notna()].sort_values("date")
            if len(tr) < MIN_TRAIN_ROWS or not len(te):
                continue
            imp = SimpleImputer(strategy="median")
            Xtr = imp.fit_transform(tr[FEATURE_COLS])
            Xte = imp.transform(te[FEATURE_COLS])
            if not fitted:
                ts.fit(Xtr, tr["target_mean_price_next_30d"].values)
                fitted = True
            try:
                for i in range(0, len(te), 50):
                    Xi = Xte[i:i + 50]
                    yi = te["target_mean_price_next_30d"].values[i:i + 50]
                    yp, pi = ts.predict(Xi, confidence_level=NOMINAL)
                    pi = np.asarray(pi)[:, :, 0]
                    for j in range(len(Xi)):
                        rows.append({"method": "mapie_aci", "fold": fold["name"], "crop": crop,
                                     "date": te["date"].iloc[i + j], "actual": yi[j],
                                     "mid": float(np.asarray(yp).ravel()[j]),
                                     "lo": float(pi[j, 0]), "hi": float(pi[j, 1])})
                    # 批量在线更新（仅使用刚观测到的结果）
                    ts.adapt_conformal_inference(Xi, yi, gamma=gamma, confidence_level=NOMINAL)
            except Exception as e:
                print(f"[mapie_aci] {crop} {fold['name']} FAILED {type(e).__name__}: {str(e)[:120]}")
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 7b. MAPIE EnbPI + 显式 OOS 校准
def mapie_enbpi_calibrated_intervals(ds: pd.DataFrame, seed: int = 42, n_estimators: int = 200,
                                     cal_frac: float = 0.2) -> pd.DataFrame:
    """EnbPI + conformalize(留出校准集)：校准残差来自训练期尾部 OOS 段（严格 past-only）。"""
    from sklearn.ensemble import RandomForestRegressor
    from mapie.regression import TimeSeriesRegressor
    from sklearn.impute import SimpleImputer

    d = ds.sort_values(["crop", "date"]).reset_index(drop=True).copy()
    rows = []
    for crop, sub in d.groupby("crop", sort=False):
        sub = sub.reset_index(drop=True)
        for fold in FOLDS:
            tr = sub[(sub["date"] <= pd.Timestamp(fold["train_end"])) &
                     sub["target_mean_price_next_30d"].notna()].sort_values("date")
            te = sub[(sub["date"] >= pd.Timestamp(fold["test_start"])) &
                     (sub["date"] <= pd.Timestamp(fold["test_end"])) &
                     sub["target_mean_price_next_30d"].notna()]
            if len(tr) < MIN_TRAIN_ROWS or not len(te):
                continue
            cut = int(len(tr) * (1 - cal_frac))
            itr, ical = tr.iloc[:cut], tr.iloc[cut:]
            imp = SimpleImputer(strategy="median")
            Xtr = imp.fit_transform(itr[FEATURE_COLS])
            Xcal = imp.transform(ical[FEATURE_COLS])
            Xte = imp.transform(te[FEATURE_COLS])
            ts = TimeSeriesRegressor(
                estimator=RandomForestRegressor(n_estimators=n_estimators, random_state=seed, n_jobs=-1),
                method="enbpi", cv=None, agg_function="mean")
            try:
                ts.fit(Xtr, itr["target_mean_price_next_30d"].values)
                ts.conformalize(Xcal, ical["target_mean_price_next_30d"].values)
                yp, pi = ts.predict(Xte, confidence_level=NOMINAL)
                pi = np.asarray(pi)[:, :, 0]
                for j in range(len(te)):
                    rows.append({"method": "mapie_enbpi_calibrated", "fold": fold["name"],
                                 "crop": crop, "date": te["date"].iloc[j],
                                 "actual": te["target_mean_price_next_30d"].iloc[j],
                                 "mid": float(np.asarray(yp).ravel()[j]),
                                 "lo": float(pi[j, 0]), "hi": float(pi[j, 1])})
            except Exception as e:
                print(f"[mapie_cal] {crop} {fold['name']} FAILED {type(e).__name__}: {str(e)[:120]}")
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 8. 近期滚动残差校正
def residual_calibration_recent_intervals(ds: pd.DataFrame, make_model,
                                          recent_n: int = 300) -> pd.DataFrame:
    """残差分位只取「最近 recent_n 个 OOS 残差」（更快适应误差水平漂移）。"""
    d = ds.sort_values(["crop", "date"]).reset_index(drop=True).copy()
    rows = []
    residuals = {}
    for fold in FOLDS:
        tr_all, te_all = fold_mask(d, fold)
        for crop, sub in d.groupby("crop", sort=False):
            tr = sub[tr_all.loc[sub.index] & sub["target_mean_price_next_30d"].notna()].sort_values("date")
            te = sub[te_all.loc[sub.index] & sub["target_mean_price_next_30d"].notna()]
            if len(tr) < MIN_TRAIN_ROWS or not len(te):
                continue
            if crop not in residuals:
                cut = int(len(tr) * 0.8)
                itr, ical = tr.iloc[:cut], tr.iloc[cut:]
                m = make_model()
                m.fit(itr[FEATURE_COLS], itr["target_mean_price_next_30d"])
                residuals[crop] = list(ical["target_mean_price_next_30d"].values - m.predict(ical[FEATURE_COLS]))
            res = np.asarray(residuals[crop][-recent_n:], dtype=float)
            res = res[np.isfinite(res)]
            if len(res) < 40:
                continue
            q_lo, q_hi = np.quantile(res, [0.10, 0.90])
            m2 = make_model()
            m2.fit(tr[FEATURE_COLS], tr["target_mean_price_next_30d"])
            mid = m2.predict(te[FEATURE_COLS])
            for dt, act, md in zip(te["date"], te["target_mean_price_next_30d"], mid):
                rows.append({"method": "residual_calibration_recent", "fold": fold["name"],
                             "crop": crop, "date": dt, "actual": act, "mid": md,
                             "lo": md + q_lo, "hi": md + q_hi})
            res_now = te["target_mean_price_next_30d"].values - mid
            residuals[crop].extend(list(res_now[np.isfinite(res_now)]))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 9. 覆盖反馈自适应缩放（轻量 online calibration）
def residual_adaptive_scaled_intervals(ds: pd.DataFrame, make_model,
                                       init_scale: float = 1.3, damping: float = 0.5) -> pd.DataFrame:
    """残差区间 + 基于历史 fold 覆盖率的乘性缩放（只使用更早 fold 的已观测覆盖）。

    s_{k} = s_{k-1} × (目标覆盖 / 上折覆盖)^damping；fold1 使用 init_scale。
    这是 Adversarial/Adaptive calibration 的轻量实现，专门应对误差水平随时间漂移。
    """
    d = ds.sort_values(["crop", "date"]).reset_index(drop=True).copy()
    rows = []
    residuals = {}
    scales = {}
    last_cov = {}
    for fold in FOLDS:
        tr_all, te_all = fold_mask(d, fold)
        for crop, sub in d.groupby("crop", sort=False):
            tr = sub[tr_all.loc[sub.index] & sub["target_mean_price_next_30d"].notna()].sort_values("date")
            te = sub[te_all.loc[sub.index] & sub["target_mean_price_next_30d"].notna()]
            if len(tr) < MIN_TRAIN_ROWS or not len(te):
                continue
            if crop not in residuals:
                cut = int(len(tr) * 0.8)
                itr, ical = tr.iloc[:cut], tr.iloc[cut:]
                m = make_model()
                m.fit(itr[FEATURE_COLS], itr["target_mean_price_next_30d"])
                residuals[crop] = list(ical["target_mean_price_next_30d"].values - m.predict(ical[FEATURE_COLS]))
                scales[crop] = init_scale
            # 在进入本 fold 前，用上一 fold 的覆盖反馈更新缩放
            if crop in last_cov and np.isfinite(last_cov[crop]) and last_cov[crop] > 0:
                scales[crop] = float(np.clip(scales[crop] * (NOMINAL / last_cov[crop]) ** damping, 0.6, 4.0))
            res = np.asarray(residuals[crop], dtype=float)
            res = res[np.isfinite(res)]
            if len(res) < 40:
                continue
            q_lo, q_hi = np.quantile(res, [0.10, 0.90])
            m2 = make_model()
            m2.fit(tr[FEATURE_COLS], tr["target_mean_price_next_30d"])
            mid = m2.predict(te[FEATURE_COLS])
            lo, hi = mid + q_lo * scales[crop], mid + q_hi * scales[crop]
            cov = float(((te["target_mean_price_next_30d"].values >= lo) &
                         (te["target_mean_price_next_30d"].values <= hi)).mean())
            last_cov[crop] = cov
            for dt, act, md, a, b, sc in zip(te["date"], te["target_mean_price_next_30d"], mid, lo, hi,
                                             [scales[crop]] * len(te)):
                rows.append({"method": "residual_adaptive_scaled", "fold": fold["name"],
                             "crop": crop, "date": dt, "actual": act, "mid": md, "lo": a, "hi": b,
                             "scale": sc})
            res_now = te["target_mean_price_next_30d"].values - mid
            residuals[crop].extend(list(res_now[np.isfinite(res_now)]))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 汇总评价
def evaluate_intervals(iv: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (method, crop, fold), g in iv.groupby(["method", "crop", "fold"]):
        m = cov_width(g["actual"].values, g["lo"].values, g["hi"].values)
        m.update({"method": method, "crop": crop, "fold": fold})
        rows.append(m)
    per = pd.DataFrame(rows)
    agg = (per.groupby("method")
           .agg(coverage=("coverage", "mean"), mean_width=("mean_width", "mean"),
                median_width=("median_width", "mean"), n_groups=("coverage", "count"),
                undercoverage_rate=("coverage", lambda s: float((s < 0.70).mean())),
                coverage_std=("coverage", "std")).reset_index())
    agg["coverage_gap"] = (agg["coverage"] - NOMINAL).abs()
    agg = agg.sort_values(["coverage_gap", "mean_width"])
    return per, agg