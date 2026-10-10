#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P2-12 小样本统计诊断（EXPLORATORY，不得作为最终结论）。
输出：05_analysis/08_model_readiness/diagnostics_*.csv
"""
import os

import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARTS = os.path.join(BASE, "04_marts")
OUT = os.path.join(BASE, "05_analysis", "08_model_readiness")
os.makedirs(OUT, exist_ok=True)


def ols(X, y):
    X = np.column_stack([np.ones(len(X)), X])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return beta


def ridge(X, y, lam=1.0):
    Xc = X - X.mean(0, keepdims=True)
    Xs = Xc / (Xc.std(0, keepdims=True) + 1e-9)
    n, p = Xs.shape
    A = Xs.T @ Xs + lam * np.eye(p)
    b = Xs.T @ (y - y.mean())
    w = np.linalg.solve(A, b)
    return w, Xc.mean(0), Xc.std(0) + 1e-9, y.mean()


def ridge_pred(model, X):
    w, mu, sd, ym = model
    return ((X - mu) / sd) @ w + ym


def metrics(y, yhat):
    e = y - yhat
    mae = float(np.mean(np.abs(e)))
    rmse = float(np.sqrt(np.mean(e ** 2)))
    ss = float(np.sum((y - y.mean()) ** 2))
    r2 = float(1 - np.sum(e ** 2) / ss) if ss > 0 else float("nan")
    return mae, rmse, r2


def main():
    d = pd.read_csv(os.path.join(MARTS, "corn_model_dataset_annual.csv"))
    core = pd.read_csv(os.path.join(MARTS, "corn_model_dataset_annual_CORE.csv"))
    y = d["corn_yield_kg_ha"].values

    # 1) 样本规模
    feat_cols = [c for c in core.columns if c not in
                 ("year", "corn_yield_kg_ha", "phenology_quality", "weather_quality",
                  "yield_quality", "comparability")]
    rec = {
        "n_years": len(d), "year_min": int(d.year.min()), "year_max": int(d.year.max()),
        "n_features_full": len(d.columns), "n_features_core": len(feat_cols),
        "missing_rate_core": round(float(core[feat_cols].isna().mean().mean()), 4),
        "df_predictor_only_naive": len(d) - len(feat_cols) - 1,
    }
    pd.Series(rec).to_frame("value").to_csv(os.path.join(OUT, "DIAG_sample_size.csv"), encoding="utf-8-sig")
    print("[P2-12] sample:", rec)

    # 2) 时间趋势 yield ~ time_index
    t = d["time_index"].values.astype(float)
    bt = ols(t.reshape(-1, 1), y)
    resid = y - (bt[0] + bt[1] * t)
    trend = pd.DataFrame({"year": d.year, "yield": y, "trend_fit": bt[0] + bt[1] * t,
                          "resid": resid, "resid_z": (resid - resid.mean()) / resid.std(ddof=1)})
    trend.to_csv(os.path.join(OUT, "DIAG_yield_trend.csv"), index=False, encoding="utf-8-sig")
    print(f"[P2-12] trend slope={bt[1]:.1f} kg/ha/yr, R2={1-np.sum(resid**2)/np.sum((y-y.mean())**2):.3f}")
    print("[P2-12] outliers(|z|>1.5):", trend.loc[trend.resid_z.abs() > 1.5, "year"].tolist())

    # 3) 相关矩阵（核心特征）
    corr = core[feat_cols].corr()
    corr.to_csv(os.path.join(OUT, "DIAG_correlation_core.csv"), encoding="utf-8-sig")
    high = [(a, b, round(corr.loc[a, b], 2)) for i, a in enumerate(feat_cols) for b in feat_cols[i + 1:]
            if abs(corr.loc[a, b]) > 0.8]
    pd.DataFrame(high, columns=["v1", "v2", "r"]).to_csv(
        os.path.join(OUT, "DIAG_high_correlation.csv"), index=False, encoding="utf-8-sig")
    print("[P2-12] |r|>0.8 pairs:", high[:12], "...n=", len(high))

    # 4) VIF（核心特征）——当 p >= n 时相关矩阵近奇异，VIF 无意义
    Xs = core[feat_cols].dropna().values
    Xs = (Xs - Xs.mean(0)) / (Xs.std(0) + 1e-9)
    n_obs, p_feat = Xs.shape
    if p_feat >= n_obs:
        vif_df = pd.DataFrame({"feature": feat_cols, "VIF": ["NOT_COMPUTABLE_p_ge_n"] * p_feat})
    else:
        try:
            vif = np.diag(np.linalg.inv(np.corrcoef(Xs, rowvar=False)))
            vif_df = pd.DataFrame({"feature": feat_cols, "VIF": np.round(vif, 1)}).sort_values("VIF", ascending=False)
        except Exception:
            vif_df = pd.DataFrame({"feature": feat_cols, "VIF": ["SINGULAR"] * p_feat})
    vif_df.to_csv(os.path.join(OUT, "DIAG_vif_core.csv"), index=False, encoding="utf-8-sig")
    print(f"[P2-12] p={p_feat} n={n_obs} -> VIF {'不可计算(p>=n)' if p_feat >= n_obs else 'ok'}")

    # 5) Leave-One-Year-Out（外推型验证，EXPLORATORY）
    Xc = core[feat_cols].values.astype(float)
    models = {
        "historical_mean": None,
        "linear_trend": t,
        "ridge_lambda1": Xc,
        "ols_core": Xc,
    }
    res = []
    for name in models:
        preds = np.full(len(y), np.nan)
        for i in range(len(y)):
            m = np.ones(len(y), bool); m[i] = False
            if name == "historical_mean":
                preds[i] = y[m].mean()
            elif name == "linear_trend":
                b = ols(t[m].reshape(-1, 1), y[m]); preds[i] = b[0] + b[1] * t[i]
            elif name == "ridge_lambda1":
                mo = ridge(Xc[m], y[m], lam=1.0); preds[i] = ridge_pred(mo, Xc[i:i + 1])[0]
            elif name == "ols_core":
                b = ols(Xc[m], y[m]); preds[i] = np.r_[1.0, Xc[i]] @ b
        mae, rmse, r2 = metrics(y, preds)
        res.append(dict(model=name, LOYO_MAE_kg_ha=round(mae, 1), LOYO_RMSE_kg_ha=round(rmse, 1),
                        LOYO_R2=round(r2, 3), n_train=len(y) - 1, n_features=len(feat_cols) if name in ("ridge_lambda1", "ols_core") else 1))
    r = pd.DataFrame(res)
    r.to_csv(os.path.join(OUT, "DIAG_loyo_models_EXPLORATORY.csv"), index=False, encoding="utf-8-sig")
    print("[P2-12] LOYO:\n", r.to_string())


if __name__ == "__main__":
    main()
