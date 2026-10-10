"""_v2.py — 沈阳研究 v2 共享模块（路径 / 配置 / 统计工具 / 绘图 / 证据登记）。

纪律：本模块不包含研究逻辑；只提供可复用的基础设施。
所有方法实现均对应 plan/analysis_plan.yaml 的预注册设定。
"""
from __future__ import annotations

import csv
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import yaml

# -----------------------------------------------------------------------------
# 路径
# -----------------------------------------------------------------------------
V2 = Path(__file__).resolve().parent.parent          # research/（原 workspace/research_v2）
SHENYANG = V2.parent                                  # city_data/shenyang
WS = SHENYANG                                         # 分析工程根（原 workspace）
SOURCES = V2 / "sources"
PLAN = V2 / "plan"
DATA = SHENYANG / "data" / "v2"
RESULTS = V2 / "results"
TABLES = RESULTS / "tables"
FIGURES = RESULTS / "figures"
METRICS = RESULTS / "metrics"
EVIDENCE = V2 / "evidence"
REVIEWS = V2 / "reviews"
EXPORTS = V2 / "exports" / "frontend"
REPORTS_V2 = V2 / "publication"
for _d in (DATA, TABLES, FIGURES, METRICS, EVIDENCE, EXPORTS / "articles"):
    _d.mkdir(parents=True, exist_ok=True)

PLAN_YAML = yaml.safe_load((PLAN / "analysis_plan.yaml").read_text(encoding="utf-8"))
SEED = int(PLAN_YAML["global"]["random_seed"])
ALPHA = float(PLAN_YAML["global"]["alpha"])
np.random.seed(SEED)

CROPS: List[str] = ["土豆", "尖椒", "甘蓝", "芸豆", "芹菜", "茄子", "西红柿", "青椒", "韭菜", "黄瓜"]
DISTRICTS: List[str] = list(PLAN_YAML["data"]["production"]["districts"])
GS_MONTHS: List[int] = list(PLAN_YAML["data"]["weather"]["growing_season_months"])

FIGSIZE = (7.6, 4.6)
C_MAIN, C_ALT, C_NEG, C_POS = "#2f6f9f", "#c0622b", "#7a5aa8", "#3f8f5f"


def get_logger(name: str) -> logging.Logger:
    lg = logging.getLogger(name)
    if lg.handlers:
        return lg
    lg.setLevel(logging.INFO)
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
                                     datefmt="%H:%M:%S"))
    lg.addHandler(h)
    return lg


def setup_plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    for f in ["Hiragino Sans GB", "PingFang SC", "Heiti SC", "STHeiti", "Arial Unicode MS"]:
        try:
            matplotlib.font_manager.findfont(f, fallback_to_default=False)
            plt.rcParams["font.family"] = f
            break
        except Exception:  # noqa: BLE001
            continue
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.dpi"] = 130
    return plt


def save_fig(fig, name: str) -> Path:
    p = FIGURES / name
    fig.tight_layout()
    fig.savefig(p, bbox_inches="tight")
    import matplotlib.pyplot as plt
    plt.close(fig)
    return p


def save_table(df: pd.DataFrame, name: str) -> Path:
    p = TABLES / name
    df.to_csv(p, index=False, encoding="utf-8-sig")
    return p


# -----------------------------------------------------------------------------
# 统计工具
# -----------------------------------------------------------------------------
def hac_ols(y: np.ndarray, X: np.ndarray, maxlags: int = 14, names: Optional[List[str]] = None):
    """OLS + Newey-West/HAC。返回 dict(coef, se, t, p, r2, n, n_eff, ar1)。"""
    import statsmodels.api as sm
    y = np.asarray(y, dtype=float)
    X = np.asarray(X, dtype=float)
    m = sm.OLS(y, sm.add_constant(X, has_constant="add"), missing="drop").fit(
        cov_type="HAC", cov_kwds={"maxlags": maxlags})
    k = X.shape[1] if X.ndim > 1 else 1
    out = {"coef": np.asarray(m.params)[1:], "se": np.asarray(m.bse)[1:],
           "t": np.asarray(m.tvalues)[1:], "p": np.asarray(m.pvalues)[1:],
           "r2": float(m.rsquared), "n": int(m.nobs)}
    # AR(1) 与有效样本量（用于功效说明，§A02 要求报告 AR(1)）
    yy = y[np.isfinite(y)]
    if len(yy) > 3:
        r = float(np.corrcoef(yy[:-1], yy[1:])[0, 1])
        out["ar1"] = r
        out["n_eff"] = float(len(yy) * (1 - r) / (1 + r)) if r < 0.999 else float(len(yy))
    else:
        out["ar1"], out["n_eff"] = np.nan, np.nan
    return out


def bh_fdr(p: Sequence[float]) -> np.ndarray:
    p = np.asarray(p, dtype=float)
    out = np.full_like(p, np.nan)
    m = ~np.isnan(p)
    pv = p[m]
    n = pv.size
    if n == 0:
        return out
    order = np.argsort(pv)
    q = pv[order] * n / (np.arange(1, n + 1))
    q = np.minimum.accumulate(q[::-1])[::-1]
    q = np.clip(q, 0, 1)
    res = np.empty(n)
    res[order] = q
    out[m] = res
    return out


def cluster_ols(y: np.ndarray, X: np.ndarray, groups: np.ndarray):
    """聚类稳健 OLS（clusters = 例如 district）。返回系数明细 + 聚类数。"""
    import statsmodels.api as sm
    y = np.asarray(y, dtype=float)
    X = np.asarray(X, dtype=float)
    m = sm.OLS(y, sm.add_constant(X, has_constant="add"), missing="drop").fit(
        cov_type="cluster", cov_kwds={"groups": np.asarray(groups), "use_correction": True})
    return {"coef": np.asarray(m.params)[1:], "se": np.asarray(m.bse)[1:],
            "t": np.asarray(m.tvalues)[1:], "p": np.asarray(m.pvalues)[1:],
            "r2": float(m.rsquared), "n": int(m.nobs), "n_clusters": int(pd.Series(groups).nunique())}


def wild_cluster_bootstrap(y: np.ndarray, X: np.ndarray, groups: np.ndarray,
                           j: int = 0, n_boot: int = 999, seed: int = SEED) -> Dict[str, float]:
    """Rademacher wild cluster bootstrap-t（Cameron-Gelbach-Miller 2008；Roodman 2019）。

    对第 j 个回归元做 H0: beta_j = 0 的受限模型 bootstrap-t。
    返回 {"t_stat", "p_boot", "n_clusters"}。
    """
    import statsmodels.api as sm
    y = np.asarray(y, float)
    X = np.asarray(X, float)
    groups = np.asarray(groups)
    ok = ~(np.isnan(y) | np.isnan(X).any(axis=1))
    y, X, groups = y[ok], X[ok], groups[ok]
    if len(y) < 5:
        return {"t_stat": np.nan, "p_boot": np.nan, "n_clusters": int(pd.Series(groups).nunique())}
    Xc = sm.add_constant(X, has_constant="add")
    m = sm.OLS(y, Xc).fit(cov_type="cluster", cov_kwds={"groups": groups, "use_correction": True})
    jj = j + 1
    t_obs = float(m.tvalues[jj])
    # 受限模型：去掉第 j 列
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


def moving_block_bootstrap_idx(n: int, block: int, n_boot: int, rng) -> np.ndarray:
    """移动块 Bootstrap 的索引矩阵（保留序列相关结构）。"""
    nb = int(np.ceil(n / block))
    starts = rng.integers(0, n - block + 1, size=(n_boot, nb))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(n_boot, -1)[:, :n]
    return idx


def ljung_box_p(x: np.ndarray, lags: int = 14) -> float:
    from statsmodels.stats.diagnostic import acorr_ljungbox
    s = pd.Series(np.asarray(x, float)).dropna()
    if len(s) < lags + 5:
        return np.nan
    return float(acorr_ljungbox(s, lags=[lags], return_df=True)["lb_pvalue"].iloc[0])


# -----------------------------------------------------------------------------
# 数据载入（v2 只读复用「已采集数据」，所有派生与结果在 v2 内重算）
# -----------------------------------------------------------------------------
def load_market_panel() -> pd.DataFrame:
    """市场日度面板（10 品种 × 交易日）。来源： marts 经 v1 面板落库。"""
    p = WS / "data" / "processed" / "shenyang_panel_final.parquet"
    d = pd.read_parquet(p)
    d["date"] = pd.to_datetime(d["date"])
    return d


def load_weather_daily() -> pd.DataFrame:
    w = pd.read_parquet(WS / "data" / "interim" / "shenyang_weather_daily.parquet")
    w["date"] = pd.to_datetime(w["date"])
    return w


def load_district_panel() -> pd.DataFrame:
    return pd.read_parquet(WS / "data" / "processed" / "district_yearly_agri_weather_panel.parquet")


def load_district_weather_yearly() -> pd.DataFrame:
    return pd.read_csv(WS / "data" / "processed" / "district_weather_yearly.csv")


# -----------------------------------------------------------------------------
# 证据登记
# -----------------------------------------------------------------------------
def append_claims(rows: List[Dict[str, Any]]) -> None:
    """追加写入 evidence/claim_evidence.csv（按 claim_id 覆盖）。"""
    p = EVIDENCE / "claim_evidence.csv"
    cols = ["claim_id", "study_id", "claim_text", "claim_type", "evidence_id", "source_ids",
            "table_id", "figure_id", "estimate", "ci_low", "ci_high", "p_raw", "p_adjusted",
            "sample_size", "method_id", "status"]
    old = []
    if p.exists():
        with p.open(encoding="utf-8-sig") as fh:
            old = [r for r in csv.DictReader(fh) if r.get("claim_id")]
    new_ids = {r["claim_id"] for r in rows}
    old = [r for r in old if r["claim_id"] not in new_ids]
    allr = old + [{k: r.get(k, "") for k in cols} for r in rows]
    with p.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in allr:
            w.writerow({k: r.get(k, "") for k in cols})


def metrics_dump(name: str, obj: Dict[str, Any]) -> Path:
    p = METRICS / name
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return p


def fmt(v, nd=4):
    try:
        f = float(v)
        return "NA" if not np.isfinite(f) else f"{f:.{nd}f}"
    except Exception:  # noqa: BLE001
        return "NA"
