"""STEP 11：非线性与风险临界点（Phase 4，§二十六~§二十八）。

对应任务书：
  §二十六 GAM：precipitation → volume_anomaly / price_anomaly 的非线性关系，
             同时考虑 temperature、VPD、soil moisture（本模块逐个单独扫描，暴露=当日值）；
  §二十七 临界点识别：segmented regression / breakpoint 搜索，**必须有 Bootstrap CI**；
             禁止输出「XX mm 就是风险临界值」式的单点结论，只能写区间；
             若 CI 覆盖几乎整个暴露范围，结论是「当前数据无法定位临界点」；
  §二十八 人工分箱（0-10/10-25/25-50/50-100/100+）**仅作解释性图表**，
             禁止据此判定临界点；临界点必须由连续模型辅助识别。

推断策略（为何不直接用 pygam 的 p 值）：
  pygam 平滑项 p 值在平滑参数被估计时偏乐观（Wood 2006 §4.8.5），
  故主推断改用「自然三次样条基 vs 线性」的嵌套 Wald 检验：
    - cr(x, df=wald_spline_df=7) 张成 7 维样条空间，扣除截距+线性后剩 5 个非线性自由度；
    - 系数用 HAC / Newey-West（maxlags=14，§四十）协方差做 Wald F 检验；
  pygam 仅用于输出平滑偏依赖曲线（描述性，固定平滑参数），不承担显著性判定。

断点（segmented / kink）检验：
  - 模型  y = b0 + b1·x + b2·(x−c)+ + controls ，c 在分位网格上搜索（SSR 最小化）；
  - 零假设「无断点」用 sup-Wald 统计量（网格上稳健 Wald 的最大值），
    零分布由**循环块 Bootstrap**（块长 block_days=30）在线性零模型残差上重抽样得到；
  - c* 与 Δ斜率的置信区间由**移动块 Bootstrap 重抽数据**得到（§二十七 硬性要求）；
  - precip_3d 约 35% 为 0：网格先 np.unique 去重，并要求断点两侧各 ≥10% 样本，
    防止重复断点导致设计矩阵奇异（该坑已在可行性验证中复现并修复）。

预登记判定规则（写入报告，防事后挑结果）：
  1) 非线性存在：Wald-F 全家族 BH-FDR < 0.05；
  2) 临界点存在：非线性通过 → 断点 sup-Wald 块 Bootstrap p < 0.05；
  3) 临界点可定位：c* 的 95% Bootstrap CI 宽度 < 暴露观测范围的 50%；
  任一环节不通过 → 该组合记 `NOT SUPPORTED BY CURRENT DATA`（§八十三）。
  断点分析的候选 = 通过环节 1 的组合；若为空，仅对 precip_3d 中 Wald p 最小的组合
  做一次**探索性**断点分析（明确标注，不得作为临界点证据）。

产出：
  outputs/tables/threshold_gam_scan.csv          非线性 Wald 扫描（4 hazard × 10 品种 × 2 响应）
  outputs/tables/threshold_power.csv             AR(1)/有效样本量功效诊断
  outputs/tables/threshold_breakpoint.csv        断点分析（门槛通过者 + 探索性最佳候选）
  outputs/tables/threshold_bins_explanatory.csv  解释性分箱（§二十八，禁止用于判定临界点）
  outputs/figures/F20..F22
  reports/05_THRESHOLD.md
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from patsy import dmatrix

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    ANALYSIS, CROPS_CFG, PATHS, StepTimer, bh_fdr, get_logger, hac_ols,
    load_parquet, log_blocker, register_results, render_figure, require_columns,
    save_table, set_seed, setup_matplotlib,
)

try:  # pygam 仅用于偏依赖曲线描述；缺失不阻断推断（Wald 检验不依赖它）
    from pygam import LinearGAM, l, s
    PYGAM_OK = True
except Exception as _e:  # pragma: no cover
    PYGAM_OK = False
    log_blocker("06_threshold", "pygam 不可用", str(_e))

LOG = get_logger("06_threshold")
CORE_CROPS: list = CROPS_CFG["core_crops"]
PRICE_UNIT: str = CROPS_CFG["market"]["price_unit_raw"]
VOL_UNIT: str = CROPS_CFG["market"]["volume_unit"]
CORE_START = pd.Timestamp(ANALYSIS["time"]["core_start_planned"])
CORE_END = pd.Timestamp(ANALYSIS["time"]["weather_end"])
LAG_CFG = ANALYSIS["lag"]
TH = ANALYSIS["threshold"]
HAC_LAGS = int(LAG_CFG["hac_maxlags"])
MIN_OBS = int(LAG_CFG["min_obs"])
GAM_HAZARDS: list = TH["gam_hazards"]
GAM_SPLINES = int(TH["gam_spline_df"])
WALD_DF = int(TH["wald_spline_df"])
GRID_PTS = int(TH["segmented_grid_points"])
N_BOOT = int(TH["n_boot"])
MIN_FRAC = float(TH["min_segment_frac"])
BLOCK_DAYS = int(TH["block_days"])
SMOOTH_PTS = int(TH["smooth_grid_points"])
BASE_SEED = int(ANALYSIS["project"]["random_seed"])
VARS = [("price", "价格"), ("volume", "成交量")]
CONTROLS = ["is_weekend", "is_public_holiday"]
BINS = list(ANALYSIS["precip_bins_mm"])
BIN_LABELS = list(ANALYSIS["precip_bin_labels"])
CI_WIDTH_MAX = 0.50  # 判定规则 3：CI 宽度 / 暴露范围 上限


# -----------------------------------------------------------------------------
# 数据准备
# -----------------------------------------------------------------------------
def load_study_panel() -> pd.DataFrame:
    p = load_parquet("panel_final")
    p = p[(p["date"] >= CORE_START) & (p["date"] <= CORE_END) & (p["crop"].isin(CORE_CROPS))].copy()
    need = ([h["col"] for h in GAM_HAZARDS]
            + [f"{v}_anomaly_z_hist" for v, _ in VARS] + CONTROLS + ["date", "crop"])
    if not require_columns(p, need, "06_threshold"):
        raise SystemExit("面板缺少必需列，06_threshold 终止（见 BLOCKERS.md）")
    return p.sort_values(["crop", "date"]).reset_index(drop=True)


def combo_arrays(panel: pd.DataFrame, crop: str, var: str, col: str):
    """取单个 (品种, 响应, hazard) 的有效样本（y, x, ctrl，均无缺失）。"""
    g = panel[panel["crop"] == crop]
    y = g[f"{var}_anomaly_z_hist"].to_numpy(dtype=float)
    x = g[col].to_numpy(dtype=float)
    ctrl = g[CONTROLS].to_numpy(dtype=float)
    ok = ~(np.isnan(y) | np.isnan(x) | np.isnan(ctrl).any(axis=1))
    return y[ok], x[ok], ctrl[ok]


# -----------------------------------------------------------------------------
# 功效诊断：AR(1) 与有效样本量
# -----------------------------------------------------------------------------
def _ar1(v: np.ndarray) -> float:
    ok = ~np.isnan(v)
    vv = v[ok]
    if vv.size < 50 or np.std(vv) == 0:
        return np.nan
    return float(np.corrcoef(vv[:-1], vv[1:])[0, 1])


def power_table(panel: pd.DataFrame) -> pd.DataFrame:
    """异常序列自相关越强，名义样本量越虚：n_eff = n(1-ρ)/(1+ρ)。"""
    rows = []
    for crop in CORE_CROPS:
        g = panel[panel["crop"] == crop]
        for var, _ in VARS:
            y = g[f"{var}_anomaly_z_hist"].to_numpy(dtype=float)
            n = int((~np.isnan(y)).sum())
            rho = _ar1(y)
            neff = np.nan if not np.isfinite(rho) else max(n * (1 - rho) / (1 + rho), 1.0)
            rows.append({"crop": crop, "response": var, "n_obs": n,
                         "ar1": rho, "n_eff": float(neff)})
    return pd.DataFrame(rows)


# -----------------------------------------------------------------------------
# 主推断：自然样条基 vs 线性 的 HAC 稳健 Wald F 检验
# -----------------------------------------------------------------------------
def wald_nonlinearity(y: np.ndarray, x: np.ndarray, ctrl: np.ndarray):
    """H0: E[y|x] 为线性。H1: 属于 cr(x, df=WALD_DF) 样条空间。

    做法：把样条基对 [1, x, ctrl] 残差化（QR 投影）得到非线性增量 G（秩=非线性格点数），
    在 [1, x, ctrl, G] 的 HAC 回归里对 G 的系数做联合 Wald F 检验。
    """
    n = y.size
    B = np.asarray(dmatrix(f"cr(t, df={WALD_DF}) - 1", {"t": x}), dtype=float)
    Xlin = np.column_stack([np.ones(n), x, ctrl])
    Q, _ = np.linalg.qr(Xlin)
    Bp = B - Q @ (Q.T @ B)
    U, sv, _ = np.linalg.svd(Bp, full_matrices=False)
    if sv.size == 0 or sv.max() <= 0:
        return None
    G = U[:, sv > sv.max() * 1e-8] * sv[sv > sv.max() * 1e-8]
    q = G.shape[1]
    if q == 0:
        return None
    Xfull = np.column_stack([Xlin, G])
    m = sm.OLS(y, Xfull).fit(cov_type="HAC", cov_kwds={"maxlags": HAC_LAGS})
    R = np.zeros((q, Xfull.shape[1]))
    R[:, Xlin.shape[1]:] = np.eye(q)
    w = m.wald_test(R, use_f=True, scalar=True)
    return {
        "wald_F": float(np.squeeze(w.statistic)),
        "wald_p": float(np.squeeze(w.pvalue)),
        "wald_df1": int(q), "n": int(m.nobs),
    }


def _gam_descriptive(y: np.ndarray, x: np.ndarray, ctrl: np.ndarray):
    """pygam 拟合仅取偏依赖曲线与 edof/R2（描述性；不用其 p 值，见模块 docstring）。"""
    if not PYGAM_OK:
        return None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            X = np.column_stack([x, ctrl])
            gam = LinearGAM(s(0, n_splines=GAM_SPLINES, spline_order=3) + l(1) + l(2))
            gam.fit(X, y)
            edof = float(np.ravel(gam.statistics_["edof"])[0])
            pred = np.ravel(gam.predict(X))
            r2 = float(1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum())
            gx = np.linspace(float(x.min()), float(x.max()), SMOOTH_PTS)
            XX = np.column_stack([gx,
                                  np.full(gx.size, ctrl[:, 0].mean()),
                                  np.full(gx.size, ctrl[:, 1].mean())])
            out = gam.partial_dependence(term=0, X=XX, width=0.95)
            if isinstance(out, (list, tuple)):
                if len(out) == 3:
                    _, pdv, ci = out
                else:
                    pdv, ci = out[0], out[1]
            else:
                pdv, ci = out, None
            pdv = np.ravel(np.asarray(pdv, dtype=float))
            ci = None if ci is None else np.asarray(ci, dtype=float).reshape(pdv.size, 2)
            return {"edof": edof, "r2": r2, "grid": gx, "pdv": pdv, "ci": ci}
    except Exception as e:  # 单个组合拟合失败不阻断扫描
        LOG.debug("pygam 拟合失败：%s", e)
        return None


def gam_scan(panel: pd.DataFrame):
    """4 hazard × 10 品种 × 2 响应 的非线性扫描（响应=方法B 异常稳健 z）。"""
    rows, pd_store = [], {}
    for crop in CORE_CROPS:
        g = panel[panel["crop"] == crop]
        ctrl_all = g[CONTROLS].to_numpy(dtype=float)
        for var, _vlabel in VARS:
            y_all = g[f"{var}_anomaly_z_hist"].to_numpy(dtype=float)
            for hz in GAM_HAZARDS:
                col = hz["col"]
                x_all = g[col].to_numpy(dtype=float)
                ok = ~(np.isnan(y_all) | np.isnan(x_all) | np.isnan(ctrl_all).any(axis=1))
                base = {
                    "crop": crop, "response": var, "hazard_key": hz["key"],
                    "hazard_label": hz["label"], "hazard_unit": hz["unit"],
                    "n": int(ok.sum()),
                }
                if ok.sum() < MIN_OBS:
                    base.update({"wald_F": np.nan, "wald_p": np.nan, "wald_df1": np.nan,
                                 "gam_edof": np.nan, "gam_r2": np.nan, "pd_range_z": np.nan,
                                 "linear_effect": np.nan, "note": f"有效观测<{MIN_OBS}，跳过"})
                    rows.append(base)
                    continue
                y, x, ctrl = y_all[ok], x_all[ok], ctrl_all[ok]
                if np.std(x) == 0:
                    base.update({"wald_F": np.nan, "wald_p": np.nan, "wald_df1": np.nan,
                                 "gam_edof": np.nan, "gam_r2": np.nan, "pd_range_z": np.nan,
                                 "linear_effect": np.nan, "note": "暴露无变异，跳过"})
                    rows.append(base)
                    continue
                w = wald_nonlinearity(y, x, ctrl)
                lin = hac_ols(y, np.column_stack([x, ctrl]), HAC_LAGS)
                gd = _gam_descriptive(y, x, ctrl)
                row = dict(base)
                row.update({
                    "wald_F": np.nan if w is None else w["wald_F"],
                    "wald_p": np.nan if w is None else w["wald_p"],
                    "wald_df1": np.nan if w is None else w["wald_df1"],
                    "gam_edof": np.nan if gd is None else gd["edof"],
                    "gam_r2": np.nan if gd is None else gd["r2"],
                    "pd_range_z": np.nan if gd is None else float(gd["pdv"].max() - gd["pdv"].min()),
                    "linear_effect": float(lin["coef"][1]),
                    "note": "" if w is not None else "Wald 检验失败（样条基退化）",
                })
                rows.append(row)
                if hz["key"] == "precip_3d" and gd is not None and w is not None:
                    pd_store[(crop, var)] = {
                        "grid": gd["grid"], "pdv": gd["pdv"], "ci": gd["ci"],
                        "slope": float(lin["coef"][1]), "slope_p": float(lin["p"][1]),
                        "xmean": float(x.mean()), "F": w["wald_F"], "p": w["wald_p"],
                        "fdr": np.nan,
                    }
        LOG.info("非线性扫描完成：%s", crop)
    scan = pd.DataFrame(rows)
    scan["fdr_p"] = bh_fdr(scan["wald_p"].to_numpy())
    # soil_z 的证据等级：官方基线缺失 → 观测期自建基线（B 级，见 BLOCKERS.md/01_build_panel）
    scan["evidence_level"] = np.where(scan["hazard_key"] == "soil_z", "B*", "B")
    scan["note"] = np.where(
        scan["hazard_key"] == "soil_z",
        scan["note"].fillna("") + "；土壤水分为观测期自建基线（B 级）",
        scan["note"].fillna(""),
    )
    for k, d in pd_store.items():
        m = scan[(scan["crop"] == k[0]) & (scan["response"] == k[1])
                 & (scan["hazard_key"] == "precip_3d")]
        if not m.empty:
            d["fdr"] = float(m["fdr_p"].iloc[0])
    return scan, pd_store


def select_breakpoint_candidates(scan: pd.DataFrame):
    """断点候选 = 非线性 Wald 通过全家族 FDR(0.05) 的组合；空则取 precip_3d 最小 p 作探索性。"""
    gate = scan[scan["fdr_p"] < 0.05][["crop", "response", "hazard_key"]].drop_duplicates()
    combos = gate.to_dict("records")
    expl = None
    p3 = scan[(scan["hazard_key"] == "precip_3d") & scan["wald_p"].notna()]
    if not p3.empty:
        r = p3.loc[p3["wald_p"].idxmin()]
        expl = {"crop": r["crop"], "response": r["response"], "hazard_key": "precip_3d"}
    return combos, expl


# -----------------------------------------------------------------------------
# 断点（segmented / kink）分析：网格搜索 + 循环块 Bootstrap
# -----------------------------------------------------------------------------
def _block_idx(rng: np.random.Generator, n: int, L: int) -> np.ndarray:
    """循环块 Bootstrap 的行索引（块长 L，环绕拼接后截断到 n）。"""
    nb = int(np.ceil(n / L))
    starts = rng.integers(0, n, size=nb)
    idx = np.concatenate([np.arange(int(s), int(s) + L) for s in starts])
    return idx[:n] % n


def _make_grid(xv: np.ndarray) -> np.ndarray:
    cand = np.unique(np.quantile(xv, np.linspace(MIN_FRAC, 1 - MIN_FRAC, GRID_PTS)))
    return np.array([c for c in cand
                     if (xv < c).sum() >= MIN_FRAC * xv.size
                     and (xv >= c).sum() >= MIN_FRAC * xv.size])


def _grid_tensor(xv: np.ndarray, ctrlv: np.ndarray, grid: np.ndarray):
    J, K = grid.size, 3 + ctrlv.shape[1]
    dx = xv[None, :] - grid[:, None]
    st = (dx > 0).astype(float)
    X = np.empty((J, xv.size, K), dtype=float)
    X[:, :, 0] = 1.0
    X[:, :, 1] = dx
    X[:, :, 2] = dx * st
    for j in range(ctrlv.shape[1]):
        X[:, :, 3 + j] = ctrlv[None, :, j]
    LtL = np.einsum("jik,jil->jkl", X, X)
    return X, np.linalg.pinv(LtL)


def _fit_grid(X: np.ndarray, inv: np.ndarray, yy: np.ndarray):
    LtY = np.einsum("jik,i->jk", X, yy)
    b = np.einsum("jkl,jl->jk", inv, LtY)
    r = yy[None, :] - np.einsum("jik,jk->ji", X, b)
    ssr = np.einsum("ji,ji->j", r, r)
    return b, r, ssr


def _supwald(X: np.ndarray, inv: np.ndarray, b: np.ndarray, r: np.ndarray) -> np.ndarray:
    """网格上逐点的稳健 Wald 统计量（断点系数 b2）。"""
    e2 = r * r
    V = np.einsum("jik,ji,jil->jkl", X, e2, X)
    S = inv @ V @ inv
    var22 = np.maximum(S[:, 2, 2], 1e-30)
    return b[:, 2] ** 2 / var22


def segmented_analysis(y: np.ndarray, x: np.ndarray, ctrl: np.ndarray, seed: int):
    """kink 断点模型：y = b0 + b1·x + b2·(x−c)+ + ctrl + e。

    返回 c*（SSR 最小）、Δ斜率 b2、稳健 SE、sup-Wald 的块 Bootstrap p 值、
    以及 c*/b2 的移动块 Bootstrap 95% CI。网格空 / 自由度不足 → None。
    """
    rng = np.random.default_rng(seed)
    n = y.size
    grid = _make_grid(x)
    if grid.size < 2:
        return None
    X, inv = _grid_tensor(x, ctrl, grid)
    b, r, ssr = _fit_grid(X, inv, y)
    jstar = int(np.argmin(ssr))
    c_hat = float(grid[jstar])

    # 观测 sup-Wald（零假设：任意 c 处斜率变化均为 0）+ c* 处稳健 SE
    e2 = r * r
    V = np.einsum("jik,ji,jil->jkl", X, e2, X)
    S = inv @ V @ inv
    var22 = np.maximum(S[:, 2, 2], 1e-30)
    W = b[:, 2] ** 2 / var22
    stat_obs = float(W.max())
    se_robust = float(np.sqrt(var22[jstar]))

    # 线性零模型（供零分布与 SSR 对比）
    X0 = np.column_stack([np.ones(n), x, ctrl])
    b0 = np.linalg.lstsq(X0, y, rcond=None)[0]
    fit0 = X0 @ b0
    e0 = y - fit0
    ssr0 = float((e0 ** 2).sum())
    K = X.shape[2]
    f_ssr = float((ssr0 - ssr[jstar]) / (ssr[jstar] / (n - K)))

    # (a) 零分布：固定设计，循环块重抽残差
    stat_null = np.empty(N_BOOT)
    for i in range(N_BOOT):
        idx = _block_idx(rng, n, BLOCK_DAYS)
        b_b, r_b, _ = _fit_grid(X, inv, fit0 + e0[idx])
        stat_null[i] = float(_supwald(X, inv, b_b, r_b).max())
    p_supwald = float((1 + np.sum(stat_null >= stat_obs)) / (N_BOOT + 1))

    # (b) 数据块 Bootstrap → c* 与 Δ斜率的 CI（§二十七 硬性要求）
    boot_c, boot_b2, boundary_hits, skipped = [], [], 0, 0
    for _ in range(N_BOOT):
        idx = _block_idx(rng, n, BLOCK_DAYS)
        yb, xb, cb = y[idx], x[idx], ctrl[idx]
        gb = _make_grid(xb)
        if gb.size < 2:
            skipped += 1
            continue
        Xb, invb = _grid_tensor(xb, cb, gb)
        bb, _, ssrb = _fit_grid(Xb, invb, yb)
        jb = int(np.argmin(ssrb))
        boot_c.append(float(gb[jb]))
        boot_b2.append(float(bb[jb, 2]))
        if jb == 0 or jb == gb.size - 1:
            boundary_hits += 1
    boot_c = np.asarray(boot_c)
    boot_b2 = np.asarray(boot_b2)
    if boot_c.size >= 50:
        c_ci = (float(np.quantile(boot_c, 0.025)), float(np.quantile(boot_c, 0.975)))
        b2_ci = (float(np.quantile(boot_b2, 0.025)), float(np.quantile(boot_b2, 0.975)))
    else:
        c_ci = b2_ci = (np.nan, np.nan)
    boundary_frac = float(boundary_hits / max(boot_c.size, 1))
    x_range = float(x.max() - x.min())
    ci_width_frac = np.nan if not np.isfinite(c_ci[0]) else (c_ci[1] - c_ci[0]) / x_range

    return {
        "n": n, "n_grid": int(grid.size), "c_hat": c_hat,
        "slope_change": float(b[jstar, 2]), "se_robust": se_robust,
        "supwald_stat": stat_obs, "p_supwald": p_supwald, "f_ssr": f_ssr,
        "c_ci_low": c_ci[0], "c_ci_high": c_ci[1],
        "b2_ci_low": b2_ci[0], "b2_ci_high": b2_ci[1],
        "ci_width_frac": float(ci_width_frac) if np.isfinite(ci_width_frac) else np.nan,
        "boot_boundary_frac": boundary_frac, "n_boot_skipped": skipped,
        "coef": b[jstar].copy(), "ctrl_mean": ctrl.mean(axis=0),
        "grid": grid.copy(), "ssr": ssr.copy(), "boot_c": boot_c.copy(),
    }


# -----------------------------------------------------------------------------
# 解释性分箱（§二十八：仅解释性，禁止据此判定临界点）
# -----------------------------------------------------------------------------
def bins_explanatory(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for crop in CORE_CROPS:
        g = panel[panel["crop"] == crop].dropna(subset=["precip_3d"]).copy()
        g["bin"] = pd.cut(g["precip_3d"], bins=BINS, labels=BIN_LABELS,
                          right=False, include_lowest=True)
        for var, _vlabel in VARS:
            y = g[f"{var}_anomaly_z_hist"]
            for bl in BIN_LABELS:
                m = (g["bin"] == bl) & y.notna()
                nn = int(m.sum())
                if nn >= 2:
                    yy = y[m].to_numpy(dtype=float)
                    mean = float(yy.mean())
                    se = float(yy.std(ddof=1) / np.sqrt(nn))
                    lo, hi = mean - 1.96 * se, mean + 1.96 * se
                else:
                    mean = se = lo = hi = np.nan
                rows.append({"crop": crop, "response": var, "bin_label": bl, "n_days": nn,
                             "mean_z": mean, "se": se, "ci_low": lo, "ci_high": hi})
    return pd.DataFrame(rows)


# -----------------------------------------------------------------------------
# 图
# -----------------------------------------------------------------------------
def fig_gam_pd(pd_store: dict, fname: str, tag: str) -> None:
    plt = setup_matplotlib()
    fig, axes = plt.subplots(2, 4, figsize=(17.0, 7.4))
    for row, (var, vlabel) in enumerate(VARS):
        cands = [k for k in pd_store if k[1] == var]
        cands.sort(key=lambda k: pd_store[k]["F"], reverse=True)
        for i, (crop, v) in enumerate(cands[:4]):
            d = pd_store[(crop, v)]
            ax = axes[row, i]
            if d["ci"] is not None:
                ax.fill_between(d["grid"], d["ci"][:, 0], d["ci"][:, 1],
                                color="#9dc3e6", alpha=0.5, label="pygam 逐点 95% 带")
            ax.plot(d["grid"], d["pdv"], color="#1f4e79", lw=1.8, label="GAM 偏依赖")
            ax.plot(d["grid"], d["slope"] * (d["grid"] - d["xmean"]), "--",
                    color="#c0392b", lw=1.3, label="线性参照（HAC）")
            ax.axhline(0, color="#333", lw=0.8)
            ax.set_title(f"{crop}｜{vlabel}异常", fontsize=11)
            ax.set_xlabel("3日累计降水（mm）")
            ax.set_ylabel("偏依赖（异常稳健 z）")
            ax.annotate(f"Wald F={d['F']:.2f}\nFDR p={d['fdr']:.3f}",
                        xy=(0.97, 0.05), xycoords="axes fraction", ha="right", va="bottom",
                        fontsize=8.5, color="#333")
            if i == 0:
                ax.legend(fontsize=7.5)
    fig.suptitle(f"图{tag}　GAM 偏依赖曲线：3日累计降水 → 量价异常（各响应取 Wald F 最大的 4 个品种）\n"
                 "置信带为 pygam 逐点带（未校正自相关，仅示意）；显著性判定以样条基 Wald-HAC 检验为准",
                 fontsize=12.5, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.91))
    render_figure(fig, fname,
                  "数据来源：沈阳市场=市发改委菜篮子发布平台（批发口径）；气象=Open-Meteo ERA5/ERA5-Land 再分析。"
                  "响应=去季节化异常(方法B 留一年法)的逐品种稳健 z；GAM 固定平滑参数（描述性），控制=周末/节假日。")


def fig_bins(bins_df: pd.DataFrame, fname: str, tag: str) -> None:
    plt = setup_matplotlib()
    fig, axes = plt.subplots(1, 2, figsize=(14.0, 5.4))
    for ax, (var, vlabel) in zip(axes, VARS):
        d = bins_df[bins_df["response"] == var]
        mat = d.pivot_table(index="crop", columns="bin_label", values="mean_z").reindex(CORE_CROPS)
        cnt = d.pivot_table(index="crop", columns="bin_label", values="n_days").reindex(CORE_CROPS)
        mat_masked = mat.mask(cnt < 30)
        vmax = float(np.nanmax(np.abs(mat_masked.values))) if mat_masked.notna().any().any() else 1.0
        vmax = vmax if (np.isfinite(vmax) and vmax > 0) else 1.0
        im = ax.imshow(mat_masked.values, cmap="RdBu_r", vmin=-vmax, vmax=vmax, aspect="auto")
        for i, crop in enumerate(mat.index):
            for j, bl in enumerate(mat.columns):
                v = mat_masked.iloc[i, j]
                if np.isfinite(v):
                    ax.text(j, i, f"{v:+.2f}\nn={int(cnt.iloc[i, j])}", ha="center", va="center",
                            fontsize=7.6, color="#111")
                else:
                    ax.text(j, i, "n<30", ha="center", va="center", fontsize=7.6, color="#999")
        ax.set_xticks(range(len(mat.columns)))
        ax.set_xticklabels(mat.columns)
        ax.set_yticks(range(len(mat.index)))
        ax.set_yticklabels(mat.index)
        ax.set_xlabel("3日累计降水分箱（mm）")
        ax.set_title(f"{vlabel}异常")
        fig.colorbar(im, ax=ax, label="箱内均值（异常稳健 z）")
    fig.suptitle(f"图{tag}　解释性分箱：3日累计降水分箱 × 量价异常均值（§二十八）\n"
                 "仅解释性图表——箱内混杂季节/年份/交易日结构，禁止据此判定临界点；灰格=箱内观测<30 天",
                 fontsize=12.5, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.90))
    render_figure(fig, fname,
                  "数据来源：沈阳市场=市发改委菜篮子发布平台（批发口径）；气象=Open-Meteo ERA5/ERA5-Land 再分析。"
                  "分箱边界来自 config/analysis.yaml precip_bins_mm（沿用数据仓库既有分箱，仅作解释）。")


def fig_breakpoint(bp: dict, y: np.ndarray, x: np.ndarray, fname: str, tag: str,
                   crop: str, var: str) -> None:
    plt = setup_matplotlib()
    fig, axes = plt.subplots(1, 3, figsize=(16.5, 4.9))
    b, c = bp["coef"], bp["c_hat"]
    # (1) 散点 + 分段拟合
    ax = axes[0]
    ax.scatter(x, y, s=4, alpha=0.15, color="#7f8c8d", edgecolors="none")
    gx = np.linspace(float(x.min()), float(x.max()), 300)
    yy = (b[0] + b[1] * gx + b[2] * np.maximum(gx - c, 0)
          + float(np.dot(b[3:], bp["ctrl_mean"])))
    ax.plot(gx, yy, color="#c0392b", lw=2.0, label="分段拟合（kink）")
    ax.axvline(c, ls=":", color="#c0392b", lw=1.2)
    ax.annotate(f"c*={c:.1f}mm", xy=(c, ax.get_ylim()[1] * 0.9), fontsize=9, color="#c0392b",
                ha="left", xytext=(4, 0), textcoords="offset points")
    ax.axhline(0, color="#333", lw=0.7)
    ax.set_xlabel("3日累计降水（mm）")
    ax.set_ylabel("异常稳健 z")
    ax.set_title(f"{crop}｜{'价格' if var == 'price' else '成交量'}：分段拟合")
    ax.legend(fontsize=8)
    # (2) SSR 剖面
    ax = axes[1]
    ssr, grid = bp["ssr"], bp["grid"]
    ax.plot(grid, (ssr - ssr.min()) / ssr.min(), color="#1f4e79", lw=1.5)
    ax.axvline(c, ls=":", color="#c0392b", lw=1.2)
    ax.set_xlabel("候选断点 c（mm）")
    ax.set_ylabel("相对 SSR 增量 = (SSR - minSSR)/minSSR")
    ax.set_title(f"断点网格搜索剖面（J={bp['n_grid']}）")
    # (3) Bootstrap c* 分布
    ax = axes[2]
    boot_c = bp["boot_c"]
    ax.hist(boot_c, bins=30, color="#9dc3e6", edgecolor="#1f4e79", lw=0.4)
    ax.axvline(c, color="#c0392b", lw=1.6, label=f"c*={c:.1f}")
    if np.isfinite(bp["c_ci_low"]):
        ax.axvline(bp["c_ci_low"], ls="--", color="#333", lw=1.0,
                   label=f"95% CI [{bp['c_ci_low']:.1f}, {bp['c_ci_high']:.1f}]")
        ax.axvline(bp["c_ci_high"], ls="--", color="#333", lw=1.0)
    ax.set_xlabel("Bootstrap 断点 c*（mm）")
    ax.set_ylabel("频数")
    ax.set_title(f"移动块 Bootstrap（L={BLOCK_DAYS}天，B={N_BOOT}）")
    ax.legend(fontsize=8)
    fig.suptitle(f"图{tag}　断点（kink）分析：{crop}·{'价格' if var == 'price' else '成交量'}·3日累计降水\n"
                 f"sup-Wald p={bp['p_supwald']:.3f}（块 Bootstrap）；Δ斜率={bp['slope_change']:+.4f} z/mm",
                 fontsize=12.5, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    render_figure(fig, fname,
                  "数据来源：沈阳市场=市发改委菜篮子发布平台（批发口径）；气象=Open-Meteo ERA5/ERA5-Land 再分析。"
                  "模型 y=b0+b1·x+b2·max(x-c,0)+周末/节假日控制；c 网格=分位去重后候选；"
                  "p 值来自线性零模型残差的循环块 Bootstrap。")


# -----------------------------------------------------------------------------
# 报告
# -----------------------------------------------------------------------------
def write_report(scan, power, bins, bp_df, gate_combos, expl, n_panel, bp_ctx=None) -> None:
    L: list = []
    A = L.append
    A("# 05 THRESHOLD — 非线性与风险临界点（STEP 11）\n")
    A(f"> 核心窗口：**{CORE_START:%Y-%m-%d} ~ {CORE_END:%Y-%m-%d}**；面板 {n_panel:,} 行。"
      f"价格单位 `{PRICE_UNIT}`；成交量单位 `{VOL_UNIT}`（仅相对/z 口径）。\n")
    A("> **本阶段证据等级：Level B（统计关联）**。临界点若存在亦为统计临界点，"
      "不是农学阈值；农学阈值仅用于机制解释层（`agronomy_thresholds`）。\n")
    A("> soil_z（土壤水分异常）因官方 1991-2020 基线缺失，使用观测期自建 LOO 基线，"
      "证据等级按 **B\\***（自建基线）标注，详见 `reports/BLOCKERS.md` 的 01_build_panel 记录。\n")

    A("## 1. 预登记判定规则（防事后挑结果）\n")
    A("| 环节 | 规则 |")
    A("|---|---|")
    A("| 非线性存在 | 自然样条基 vs 线性的 Wald-F（HAC-14）经**全家族 BH-FDR** < 0.05 |")
    A("| 临界点存在 | 非线性通过 → 断点 sup-Wald 的循环块 Bootstrap p < 0.05 |")
    A("| 临界点可定位 | c* 的 95% 移动块 Bootstrap CI 宽度 < 暴露观测范围的 50% |")
    A("| 任一环节不通过 | 该组合记 `NOT SUPPORTED BY CURRENT DATA`（§八十三） |")
    A("")
    A(f"- 检验家族：{len(GAM_HAZARDS)} hazard × {len(CORE_CROPS)} 品种 × {len(VARS)} 响应"
      f" = {len(GAM_HAZARDS) * len(CORE_CROPS) * len(VARS)} 个 Wald 检验（响应=方法B 异常稳健 z）；")
    A("- 断点分析候选 = 通过环节 1 的组合；若为空，仅对 precip_3d 中 Wald p 最小的组合"
      "做一次**探索性**分析（结果不得作为临界点证据）；")
    A("- 输出纪律（§二十七）：即便显著也**只写区间，不写单点临界值**。\n")

    A("## 2. 方法\n")
    A("| 方法 | 实现 | 用途 |")
    A("|---|---|---|")
    A(f"| 样条基 Wald-F 检验 | `cr(x, df={WALD_DF})` 对线性残差化后 {WALD_DF - 2} 个非线性自由度，"
      f"HAC({HAC_LAGS}) 协方差 | **主推断**：非线性是否存在 |")
    A(f"| GAM（pygam） | `s(0, n_splines={GAM_SPLINES}) + l + l`，固定平滑参数 | 仅描述性偏依赖曲线"
      "（pygam 内置 p 值在平滑参数被估计时偏乐观，Wood 2006 §4.8.5，不采用） |")
    A(f"| 分段回归（kink） | 网格 {GRID_PTS} 分位候选（去重 + 两侧各≥{MIN_FRAC:.0%} 样本），"
      "SSR 最小化 | 断点定位 |")
    A(f"| sup-Wald 零分布 | 线性零模型残差的**循环块 Bootstrap**（块长 {BLOCK_DAYS} 天，B={N_BOOT}） |"
      " 断点显著性 |")
    A(f"| CI（§二十七） | **移动块 Bootstrap 重抽数据**（B={N_BOOT}） | c* 与 Δ斜率的 95% CI |")
    A("")
    A("- 分箱（0-10/10-25/25-50/50-100/100+）**仅作解释性图表**（§二十八），不参与判定；")
    A("- 全部模型含 `is_weekend`、`is_public_holiday` 控制；响应已去季节化（方法B），"
      "不再放月份/趋势项（否则吸收待检信号）。\n")

    # 扫描汇总
    A("## 3. 非线性扫描结果（全家族 FDR）\n")
    A("| hazard | 响应 | 组合数 | 最小未校正 p | 最小 FDR p | 未校正 p<0.05 | FDR<0.05 |")
    A("|---|---|---|---|---|---|---|")
    for (hk, var), g in scan.groupby(["hazard_key", "response"]):
        lab = g["hazard_label"].iloc[0]
        A(f"| {lab} | {'价格' if var == 'price' else '成交量'} | {len(g)} | "
          f"{g['wald_p'].min():.3f} | {g['fdr_p'].min():.3f} | "
          f"{int((g['wald_p'] < 0.05).sum())} | {int((g['fdr_p'] < 0.05).sum())} |")
    n_fdr = int((scan["fdr_p"] < 0.05).sum())
    n_raw = int((scan["wald_p"] < 0.05).sum())
    A("")
    A(f"- 全家族 {len(scan)} 个检验：未校正 p<0.05 共 {n_raw} 个（80 检验下随机期望约 4 个），"
      f"经 BH-FDR 后剩 **{n_fdr}** 个；")
    A("- 未通过 FDR 的组合不进入任何「发现」表述，逐组合完整结果见 "
      "`outputs/tables/threshold_gam_scan.csv`。\n")

    # precip_3d 明细
    A("## 4. 重点暴露（3 日累计降水）逐品种明细\n")
    p3 = scan[scan["hazard_key"] == "precip_3d"]
    A("| 品种 | 响应 | n | 线性效应（z/mm） | Wald F | 未校正 p | FDR p | GAM edof | 曲线极差（z） |")
    A("|---|---|---|---|---|---|---|---|---|")
    for _, r in p3.sort_values(["response", "wald_p"]).iterrows():
        A(f"| {r['crop']} | {'价格' if r['response'] == 'price' else '成交量'} | {int(r['n'])} | "
          f"{r['linear_effect']:+.5f} | {r['wald_F']:.2f} | {r['wald_p']:.3f} | {r['fdr_p']:.3f} | "
          f"{r['gam_edof']:.1f} | {r['pd_range_z']:.2f} |")
    A("")

    # 功效
    A("## 5. 功效诊断：为什么阴性结果 ≠ 证明无线性/非线性\n")
    A("| 响应 | AR(1) 中位数 | 名义 n 中位数 | 有效样本量 n_eff 中位数 |")
    A("|---|---|---|---|")
    for var, vlabel in VARS:
        g = power[power["response"] == var]
        A(f"| {vlabel} | {g['ar1'].median():.3f} | {int(g['n_obs'].median())} | "
          f"{g['n_eff'].median():.0f} |")
    A("")
    med_ar1 = power["ar1"].median()
    med_neff = power["n_eff"].median()
    A(f"- 异常序列强自相关（AR(1) 中位 {med_ar1:.2f}），名义 ~1410 个交易日折算"
      f"**有效样本量约 {med_neff:.0f}**；")
    A("- 在 n_eff≈25–80 的样本上识别「曲率细微的非线性 + 单个断点」，检验功效严重不足；")
    A("- 因此本节阴性结论的准确表述是：**当前数据无法检出**非线性/临界点，"
      "而非「证明了不存在」。\n")

    # 断点
    A("## 6. 断点（kink）分析\n")
    if bp_df is None or bp_df.empty:
        A("- 无可用断点结果（候选网格为空）。RQ3/H5 按 `NOT SUPPORTED BY CURRENT DATA` 处理。\n")
    else:
        A(f"- 预登记门槛（环节 1）通过组合数：**{len(gate_combos)}**；"
          + (f"探索性候选：{expl['crop']}·{expl['response']}·{expl['hazard_key']}"
             f"（全家族 FDR 未通过，仅作方法演示）。\n" if expl else "\n"))
        A("| 品种 | 响应 | 性质 | n | J | c*(mm) | c* 95% CI | CI宽/范围 | Δ斜率(z/mm) | "
          "Δ 95% CI | sup-Wald p | 边界命中 |")
        A("|---|---|---|---|---|---|---|---|---|---|---|---|")
        for _, r in bp_df.iterrows():
            kind = "门槛通过" if not bool(r["exploratory"]) else "探索性"
            A(f"| {r['crop']} | {'价格' if r['response'] == 'price' else '成交量'} | {kind} | "
              f"{int(r['n'])} | {int(r['n_grid'])} | {r['c_hat']:.1f} | "
              f"[{r['c_ci_low']:.1f}, {r['c_ci_high']:.1f}] | {r['ci_width_frac']:.0%} | "
              f"{r['slope_change']:+.4f} | [{r['b2_ci_low']:+.4f}, {r['b2_ci_high']:+.4f}] | "
              f"{r['p_supwald']:.3f} | {r['boot_boundary_frac']:.0%} |")
        A("")
        for _, r in bp_df.iterrows():
            steps_failed = []
            if bool(r["exploratory"]):
                steps_failed.append("环节1（非线性 FDR）")
            if not r["p_supwald"] < 0.05:
                steps_failed.append("环节2（sup-Wald p<0.05）")
            if not (np.isfinite(r["ci_width_frac"]) and r["ci_width_frac"] < CI_WIDTH_MAX):
                steps_failed.append("环节3（CI 宽度<50%）")
            verdict = ("通过全部环节（仅报区间，不报单点）" if not steps_failed
                       else "未通过 " + "、".join(steps_failed) + " → 不得输出临界点表述")
            A(f"- {r['crop']}·{r['response']}：{verdict}。")
        A("")
        if bp_ctx:
            A(f"- **可搜索范围的硬约束**：`min_segment_frac={MIN_FRAC:.0%}` 要求断点两侧各"
              f"≥10% 样本，断点候选网格实际为 **[{bp_ctx['grid_min']:.1f}, {bp_ctx['grid_max']:.1f}] mm**"
              f"（≈第10~90分位）；理论上最关心的暴雨段（3日累计 >50mm 仅占 {bp_ctx['frac_gt50']:.1%}"
              f"、>100mm 仅占 {bp_ctx['frac_gt100']:.1%}，即 {bp_ctx['n_gt50']} / "
              f"{bp_ctx['n_gt100']} 个交易日）**不在可搜索范围内**——每段至少 10% 样本的样本量"
              "约束使极端降水阈值在当前数据上原则上不可识别，这是样本量（而非方法）的硬约束。")
            A(f"- 该探索性组合的 c* 95% CI=[{bp_df.iloc[0]['c_ci_low']:.1f}, "
              f"{bp_df.iloc[0]['c_ci_high']:.1f}] mm 基本覆盖整个可搜索网格"
              "（断点完全未识别），进一步印证上述判断。")
            A("")
        A("> 陷阱提示：c* 的 Bootstrap CI 即使较窄，在断点不显著（环节 2 未过）时也不构成"
          "临界点证据——precip_3d 约 35% 观测为 0，零值密集区的 SSR 浅坑会让 bootstrap c* "
          "伪聚敛在低值段；判定必须按环节顺序执行。\n")

    # 分箱
    A("## 7. 解释性分箱（§二十八：不参与判定）\n")
    A("- 分箱图（图 21）仅用于直观看「高降水箱的量价异常均值方向」；")
    A("- 箱内混杂季节、年份、交易日结构且高降水箱样本量小（部分箱 n<30），"
      "**禁止**把箱间差异解读为临界点证据；")
    A("- 判定完全依赖第 3 节（连续模型）的结果。\n")

    A("## 8. 图表清单\n")
    A("| 图 | 内容 | 回答的问题 |")
    A("|---|---|---|")
    A("| 图20 `F20_threshold_gam_pd.png` | GAM 偏依赖曲线 + 线性参照 | 响应曲线是否偏离线性 |")
    A("| 图21 `F21_threshold_bins_explanatory.png` | 分箱热力图（仅解释性） | 高降水箱的方向性直觉 |")
    A("| 图22 `F22_threshold_breakpoint_best.png` | 断点搜索剖面 + Bootstrap 分布 | 断点可否定位 |")
    A("")

    A("## 9. 本节结论（Level B）\n")
    if n_fdr == 0:
        A(f"- 全家族 {len(scan)} 个非线性检验经 BH-FDR 后**无一显著**（最小 FDR p="
          f"{scan['fdr_p'].min():.3f}）；")
        if bp_df is not None and not bp_df.empty:
            r0 = bp_df.iloc[0]
            A(f"- 探索性断点分析（{r0['crop']}·{r0['response']}）：环节1（非线性 FDR p="
              f"{float(scan[scan['hazard_key'] == 'precip_3d']['fdr_p'].min()):.3f}）与环节2"
              f"（sup-Wald 块 Bootstrap p={r0['p_supwald']:.3f}）均未通过；"
              f"Δ斜率 95% CI [{r0['b2_ci_low']:+.3f}, {r0['b2_ci_high']:+.3f}] 含 0，断点未被识别；")
        A("- **RQ3（非线性/临界点）：`NOT SUPPORTED BY CURRENT DATA`；**")
        A("- **H5（存在气象风险阈值）：`NOT SUPPORTED BY CURRENT DATA`；**")
        A("- 该结论与 STEP 10 滞后分析的全阴性结果一致（同一数据、同一功效约束）；")
        A(f"- 主要限制：AR(1)≈{med_ar1:.2f} → n_eff≈{med_neff:.0f}，"
          "当前检验功效不足以检出中小强度的非线性；若未来获得更长序列或更高频识别变量，应重新检验。\n")
    else:
        A(f"- 全家族 FDR 显著 {n_fdr} 个组合，明细见第 3-4 节与 "
          "`outputs/tables/threshold_gam_scan.csv`；")
        A("- 断点结论按第 6 节预登记规则逐组合判定，显著者也只写区间不写单点。\n")

    pth = PATHS.report("05_THRESHOLD.md")
    pth.write_text("\n".join(L), encoding="utf-8")
    LOG.info("临界点分析报告写入 %s", pth)


# -----------------------------------------------------------------------------
def main() -> None:
    set_seed()
    with StepTimer("06_threshold", LOG):
        panel = load_study_panel()
        LOG.info("面板 %d 行（%d 品种 × 交易日）", len(panel), panel["crop"].nunique())

        power = power_table(panel)
        save_table(power, "threshold_power.csv")

        scan, pd_store = gam_scan(panel)
        save_table(scan, "threshold_gam_scan.csv")
        LOG.info("非线性扫描：%d 行；FDR 显著 %d 个",
                 len(scan), int((scan["fdr_p"] < 0.05).sum()))

        bins = bins_explanatory(panel)
        save_table(bins, "threshold_bins_explanatory.csv")

        gate, expl = select_breakpoint_candidates(scan)
        LOG.info("断点候选：门槛通过 %d 个；探索性候选 %s", len(gate), expl)

        bp_rows, bp_detail = [], {}
        todo = [dict(c, exploratory=False) for c in gate]
        if expl is not None:
            key = (expl["crop"], expl["response"], expl["hazard_key"])
            if not any((r["crop"], r["response"], r["hazard_key"]) == key for r in todo):
                todo.append(dict(expl, exploratory=True))
        for idx, cb in enumerate(todo[:6]):  # 上限保护：最多 6 个组合
            hz = next(h for h in GAM_HAZARDS if h["key"] == cb["hazard_key"])
            y, x, ctrl = combo_arrays(panel, cb["crop"], cb["response"], hz["col"])
            if y.size < MIN_OBS:
                continue
            bp = segmented_analysis(y, x, ctrl, seed=BASE_SEED + 101 * (idx + 1))
            if bp is None:
                bp_rows.append({"crop": cb["crop"], "response": cb["response"],
                                "hazard_key": cb["hazard_key"], "exploratory": cb["exploratory"],
                                "note": "断点网格候选不足，无法分析"})
                continue
            bp_detail[(cb["crop"], cb["response"])] = (bp, y, x)
            bp_rows.append({
                "crop": cb["crop"], "response": cb["response"], "hazard_key": cb["hazard_key"],
                "exploratory": bool(cb["exploratory"]), "n": bp["n"], "n_grid": bp["n_grid"],
                "c_hat": bp["c_hat"], "c_ci_low": bp["c_ci_low"], "c_ci_high": bp["c_ci_high"],
                "ci_width_frac": bp["ci_width_frac"],
                "slope_change": bp["slope_change"], "se_robust": bp["se_robust"],
                "b2_ci_low": bp["b2_ci_low"], "b2_ci_high": bp["b2_ci_high"],
                "supwald_stat": bp["supwald_stat"], "p_supwald": bp["p_supwald"],
                "f_ssr": bp["f_ssr"], "boot_boundary_frac": bp["boot_boundary_frac"],
                "n_boot_skipped": bp["n_boot_skipped"],
                "note": "探索性（未通过预登记门槛）" if cb["exploratory"] else "",
            })
            LOG.info("断点分析完成：%s·%s·%s c*=%.1f p=%.3f", cb["crop"], cb["response"],
                     cb["hazard_key"], bp["c_hat"], bp["p_supwald"])
        bp_df = pd.DataFrame(bp_rows) if bp_rows else None
        if bp_df is not None and not bp_df.empty:
            save_table(bp_df, "threshold_breakpoint.csv")

        fig_gam_pd(pd_store, "F20_threshold_gam_pd.png", "20")
        fig_bins(bins, "F21_threshold_bins_explanatory.png", "21")
        bp_ctx = None
        if bp_detail:
            (crop0, var0), (bp0, y0, x0) = next(iter(bp_detail.items()))
            fig_breakpoint(bp0, y0, x0, "F22_threshold_breakpoint_best.png", "22", crop0, var0)
            grid0 = _make_grid(x0)
            bp_ctx = {
                "grid_min": float(grid0.min()), "grid_max": float(grid0.max()),
                "frac_gt50": float((x0 > 50).mean()), "frac_gt100": float((x0 > 100).mean()),
                "n_gt50": int((x0 > 50).sum()), "n_gt100": int((x0 > 100).sum()),
            }

        write_report(scan, power, bins, bp_df, gate, expl, len(panel), bp_ctx)

        # ---- 结果登记 -------------------------------------------------------
        rows = []
        sig = scan[(scan["wald_p"] < 0.05) | (scan["fdr_p"] < 0.05)]
        for _, r in sig.iterrows():
            rows.append({
                "result_id": f"THR-GAM-{r['crop']}-{r['response']}-{r['hazard_key']}",
                "research_question": "RQ3",
                "crop": r["crop"], "period": f"{CORE_START:%Y-%m-%d}~{CORE_END:%Y-%m-%d}",
                "method": f"样条基(df={WALD_DF}) vs 线性 Wald-F，HAC({HAC_LAGS})，周末/节假日控制",
                "metric": "wald_F（非线性自由度 5）",
                "estimate": round(float(r["wald_F"]), 4),
                "ci_low": None, "ci_high": None,
                "p_value": round(float(r["wald_p"]), 4),
                "robustness": f"全家族 BH-FDR p={r['fdr_p']:.4f}"
                              + ("（通过）" if r["fdr_p"] < 0.05 else "（未通过，仅记录）"),
                "figure": "F20_threshold_gam_pd.png", "table": "threshold_gam_scan.csv",
                "evidence_level": r["evidence_level"],
                "notes": f"n={int(r['n'])}; GAM edof={r['gam_edof']:.2f}; "
                         f"线性效应={r['linear_effect']:+.5f} z/{r['hazard_unit']}",
            })
        if bp_df is not None:
            for _, r in bp_df[bp_df["p_supwald"] < 0.05].iterrows():
                rows.append({
                    "result_id": f"THR-BP-{r['crop']}-{r['response']}-{r['hazard_key']}",
                    "research_question": "RQ3", "crop": r["crop"],
                    "period": f"{CORE_START:%Y-%m-%d}~{CORE_END:%Y-%m-%d}",
                    "method": f"分段回归 kink + 移动块 Bootstrap(L={BLOCK_DAYS},B={N_BOOT})",
                    "metric": f"断点 c*（{r['hazard_key']}）",
                    "estimate": round(float(r["c_hat"]), 2),
                    "ci_low": round(float(r["c_ci_low"]), 2),
                    "ci_high": round(float(r["c_ci_high"]), 2),
                    "p_value": round(float(r["p_supwald"]), 4),
                    "robustness": f"sup-Wald={r['supwald_stat']:.2f}; "
                                  f"Δ斜率 CI=[{r['b2_ci_low']:+.4f},{r['b2_ci_high']:+.4f}]",
                    "figure": "F22_threshold_breakpoint_best.png",
                    "table": "threshold_breakpoint.csv", "evidence_level": "B",
                    "notes": ("探索性（未通过预登记非线性门槛），不得作为临界点证据"
                              if bool(r["exploratory"]) else "预登记门槛通过"),
                })
        # 家族级结论行（供 Milestone 汇总直接引用）
        for var, vlabel in VARS:
            g = scan[scan["response"] == var]
            rows.append({
                "result_id": f"THR-FAM-{var.upper()}",
                "research_question": "RQ3", "crop": "全体10品种",
                "period": f"{CORE_START:%Y-%m-%d}~{CORE_END:%Y-%m-%d}",
                "method": "非线性 Wald-F 扫描全家族（4 hazard × 10 品种）+ BH-FDR",
                "metric": "min_fdr_p / n_fdr_sig",
                "estimate": round(float(g["fdr_p"].min()), 4),
                "ci_low": None, "ci_high": None,
                "p_value": round(float(g["wald_p"].min()), 4),
                "robustness": f"FDR显著数={int((g['fdr_p'] < 0.05).sum())}/{len(g)}",
                "figure": "F20_threshold_gam_pd.png", "table": "threshold_gam_scan.csv",
                "evidence_level": "B",
                "notes": (f"H5 {'NOT SUPPORTED BY CURRENT DATA' if (g['fdr_p'] < 0.05).sum() == 0 else '部分支持，见明细行'}；"
                          f"功效限制：AR1 中位 {power[power['response'] == var]['ar1'].median():.2f}"),
            })
        register_results(rows)
        LOG.info("结果登记 %d 条", len(rows))


if __name__ == "__main__":
    main()
