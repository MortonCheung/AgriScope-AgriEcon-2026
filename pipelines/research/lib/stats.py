"""stats.py — 共享统计工具（与沈阳 v2 方法一致）。

包含：HAC/Newey-West OLS、BH-FDR、聚类 OLS、wild cluster bootstrap、
移动块 bootstrap、STL 稳健分解（季节/趋势强度）。
所有研究模块不得自行另立口径。
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd


def hac_ols(y, X, maxlags: int = 14, names: Optional[List[str]] = None) -> Dict:
    """OLS + Newey-West/HAC。返回 coef/se/t/p/r2/n/n_eff/ar1。"""
    import statsmodels.api as sm
    y = np.asarray(y, dtype=float)
    X = np.asarray(X, dtype=float)
    if X.ndim == 1:
        X = X[:, None]
    m = sm.OLS(y, sm.add_constant(X, has_constant="add"), missing="drop").fit(
        cov_type="HAC", cov_kwds={"maxlags": maxlags})
    out = {"coef": np.asarray(m.params)[1:], "se": np.asarray(m.bse)[1:],
           "t": np.asarray(m.tvalues)[1:], "p": np.asarray(m.pvalues)[1:],
           "r2": float(m.rsquared), "n": int(m.nobs)}
    yy = y[np.isfinite(y)]
    if len(yy) > 3:
        r = float(np.corrcoef(yy[:-1], yy[1:])[0, 1])
        out["ar1"] = r
        out["n_eff"] = float(len(yy) * (1 - r) / (1 + r)) if abs(r) < 0.999 else float(len(yy))
    else:
        out["ar1"], out["n_eff"] = np.nan, np.nan
    return out


def bh_fdr(p: Sequence[float]) -> np.ndarray:
    """Benjamini-Hochberg FDR；返回 q 值（与原顺序一致）。"""
    p = np.asarray(p, dtype=float)
    out = np.full_like(p, np.nan)
    mask = ~np.isnan(p)
    pv = p[mask]
    n = pv.size
    if n == 0:
        return out
    order = np.argsort(pv)
    q = pv[order] * n / (np.arange(1, n + 1))
    q = np.minimum.accumulate(q[::-1])[::-1]
    q = np.clip(q, 0, 1)
    res = np.empty(n)
    res[order] = q
    out[mask] = res
    return out


def cluster_ols(y, X, groups) -> Dict:
    import statsmodels.api as sm
    y = np.asarray(y, dtype=float)
    X = np.asarray(X, dtype=float)
    if X.ndim == 1:
        X = X[:, None]
    m = sm.OLS(y, sm.add_constant(X, has_constant="add"), missing="drop").fit(
        cov_type="cluster", cov_kwds={"groups": np.asarray(groups), "use_correction": True})
    return {"coef": np.asarray(m.params)[1:], "se": np.asarray(m.bse)[1:],
            "t": np.asarray(m.tvalues)[1:], "p": np.asarray(m.pvalues)[1:],
            "r2": float(m.rsquared), "n": int(m.nobs),
            "n_clusters": int(pd.Series(groups).nunique())}


def wild_cluster_bootstrap(y, X, groups, j: int = 0, n_boot: int = 999, seed: int = 42) -> Dict:
    """Rademacher wild cluster bootstrap-t（H0: beta_j=0）。"""
    import statsmodels.api as sm
    y = np.asarray(y, float)
    X = np.asarray(X, float)
    if X.ndim == 1:
        X = X[:, None]
    groups = np.asarray(groups)
    ok = ~(np.isnan(y) | np.isnan(X).any(axis=1))
    y, X, groups = y[ok], X[ok], groups[ok]
    if len(y) < 5:
        return {"t_stat": np.nan, "p_boot": np.nan, "n_clusters": int(pd.Series(groups).nunique())}
    Xc = sm.add_constant(X, has_constant="add")
    m = sm.OLS(y, Xc).fit(cov_type="cluster", cov_kwds={"groups": groups, "use_correction": True})
    jj = j + 1
    t_obs = float(m.tvalues[jj])
    keep = [c for c in range(Xc.shape[1]) if c != jj]
    mr = sm.OLS(y, Xc[:, keep]).fit()
    res_r = np.asarray(mr.resid)
    rng = np.random.default_rng(seed)
    uniq = pd.unique(groups)
    pos = {g_: i for i, g_ in enumerate(uniq)}
    gi = np.array([pos[g_] for g_ in groups])
    tb = np.empty(n_boot)
    for b in range(n_boot):
        w = rng.choice([-1.0, 1.0], size=len(uniq))
        yb = np.asarray(mr.fittedvalues) + res_r * w[gi]
        try:
            mb = sm.OLS(yb, Xc).fit(cov_type="cluster",
                                    cov_kwds={"groups": groups, "use_correction": True})
            tb[b] = mb.tvalues[jj]
        except Exception:  # noqa: BLE001
            tb[b] = 0.0
    return {"t_stat": t_obs, "p_boot": float(np.mean(np.abs(tb) >= abs(t_obs))),
            "n_clusters": int(pd.Series(groups).nunique())}


def stl_strength(x: pd.Series, period: int = 52, robust: bool = True) -> Dict[str, float]:
    """STL 季节强度 / 趋势强度（描述性对照，含目标年，非无未来信息口径）。"""
    from statsmodels.tsa.seasonal import STL
    s = pd.Series(x).astype(float).interpolate(limit_direction="both").dropna()
    if len(s) < 2 * period:
        return {"seasonal_strength": np.nan, "trend_strength": np.nan, "n": int(len(s))}
    res = STL(s, period=period, robust=robust).fit()
    var_r = max(np.var(res.resid), 1e-12)
    fs = max(1 - var_r / max(np.var(res.seasonal + res.resid), 1e-12), 0)
    ft = max(1 - var_r / max(np.var(res.trend + res.resid), 1e-12), 0)
    return {"seasonal_strength": float(fs), "trend_strength": float(ft), "n": int(len(s))}


def seasonal_index(dates: pd.Series, values: pd.Series, freq: str = "month") -> pd.DataFrame:
    """季节指数 = 各期均值 / 全期均值。freq in {month, week}。"""
    df = pd.DataFrame({"d": pd.to_datetime(dates), "v": pd.to_numeric(values, errors="coerce")}).dropna()
    if df.empty:
        return pd.DataFrame(columns=["period", "index", "mean"])
    key = df["d"].dt.month if freq == "month" else df["d"].dt.isocalendar().week.astype(int)
    overall = df["v"].mean()
    df["period"] = key
    g = df.groupby("period")["v"].agg(["mean", "count"]).reset_index()
    g["index"] = g["mean"] / overall if overall else np.nan
    return g


def fmt(v, nd: int = 4) -> str:
    try:
        f = float(v)
        return "NA" if not np.isfinite(f) else f"{f:.{nd}f}"
    except Exception:  # noqa: BLE001
        return "NA"