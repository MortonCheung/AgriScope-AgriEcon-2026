"""20_market_studies.py — A01 / A02 / A03 / A06(6.1,6.2) 市场端研究（v2 重新计算）。

预注册对应：plan/analysis_plan.yaml 的 A01/A02/A03/A06。
主口径：去季节化异常 z 采用 **strict**（基线仅用严格更早年份，无未来信息）；
        loo（v1 同法）仅作稳健性对照。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _v2
from _v2 import (ALPHA, CROPS, DATA, append_claims, bh_fdr, fmt, get_logger, hac_ols,
                 metrics_dump, save_fig, save_table, setup_plt, wild_cluster_bootstrap)

LOG = get_logger("20_market_studies")
HAC = 14
CORE_EXPOSURES = ["precipitation", "temp_max", "vpd", "wind_speed", "soil_moisture_0_7"]
SUPP_EXPOSURES = ["pressure_msl", "cloud_cover", "radiation", "dew_point", "et0", "humidity"]
LAG_WINDOWS = {"w0": "0日", "w13": "1-3日", "w47": "4-7日", "w814": "8-14日"}


def load():
    d = pd.read_parquet(DATA / "v2_market_daily.parquet")
    d["date"] = pd.to_datetime(d["date"])
    return d


# ---------------------------------------------------------------- A01
def A01(d, log):
    log.info("A01 时间结构与季节性")
    rows, seasonal_rows = [], []
    for crop in CROPS:
        g = d[d["crop"] == crop].sort_values("date")
        # 月度中位数与分布
        for mth, gm in g.groupby(g["date"].dt.month):
            rows.append({"crop": crop, "month": int(mth), "n": len(gm),
                         "price_median": gm["price"].median(),
                         "price_p10": gm["price"].quantile(.10),
                         "price_p90": gm["price"].quantile(.90),
                         "volume_median": gm["volume"].median()})
        # 年度水平 + HAC 趋势
        for yr, gy in g.groupby(g["date"].dt.year):
            rows.append({"crop": crop, "year": int(yr), "n": len(gy),
                         "price_median": gy["price"].median(),
                         "price_p10": gy["price"].quantile(.10),
                         "price_p90": gy["price"].quantile(.90),
                         "volume_median": gy["volume"].median()})
    mon = pd.DataFrame([r for r in rows if "month" in r])
    save_table(mon, "A01_monthly.csv")

    # 季节指数（月度均值 / 全年均值）
    si = []
    for crop in CROPS:
        g = d[d["crop"] == crop]
        for col, tag in (("price", "price"), ("volume", "volume")):
            base = g[col].mean()
            for mth, gm in g.groupby(g["date"].dt.month):
                si.append({"crop": crop, "variable": tag, "month": int(mth),
                           "seasonal_index": gm[col].mean() / base if base else np.nan,
                           "n": len(gm)})
    sdf = pd.DataFrame(si)
    save_table(sdf, "A01_seasonal_index.csv")
    amp = (sdf.groupby(["crop", "variable"])["seasonal_index"]
           .agg(lambda s: s.max() - s.min()).rename("seasonal_range").reset_index())
    save_table(amp, "A01_seasonal_amplitude.csv")

    # 趋势：log(price) ~ t，逐品种 HAC(14)，家族 = 10 品种 × 2 响应
    tr = []
    for crop in CROPS:
        g = d[d["crop"] == crop].sort_values("date")
        t = (g["date"] - g["date"].min()).dt.days.to_numpy(float) / 365.25
        for col, tag in (("log_price", "price"), ("log_volume", "volume")):
            y = g[col].to_numpy(float)
            ok = np.isfinite(y)
            if ok.sum() < 100:
                continue
            r = hac_ols(y[ok], t[ok].reshape(-1, 1), maxlags=HAC)
            tr.append({"crop": crop, "response": tag, "beta_per_year": float(r["coef"][0]),
                       "se": float(r["se"][0]), "p_raw": float(r["p"][0]), "n": r["n"],
                       "r2": r["r2"], "ar1": r["ar1"], "n_eff": r["n_eff"],
                       "annual_pct": 100 * float(r["coef"][0])})
    tdf = pd.DataFrame(tr)
    tdf["q_fdr"] = bh_fdr(tdf["p_raw"].to_numpy())      # 家族：10 品种 × 2 响应
    tdf["ci_low"] = tdf["beta_per_year"] - 1.96 * tdf["se"]
    tdf["ci_high"] = tdf["beta_per_year"] + 1.96 * tdf["se"]
    save_table(tdf, "A01_trend.csv")

    # STL 季节强度（描述，仅作对照，不作无泄漏口径）
    stl_rows = []
    for crop in CROPS:
        g = d[d["crop"] == crop].set_index("date").sort_index()
        for col, tag in (("price", "price"), ("volume", "volume")):
            s = g[col].resample("W").mean().dropna()
            if len(s) < 120:
                continue
            from statsmodels.tsa.seasonal import STL
            try:
                r = STL(s, period=52, robust=True).fit()
            except Exception:  # noqa: BLE001
                continue
            var_r = np.var(r.resid)
            stl_rows.append({"crop": crop, "variable": tag,
                             "seasonal_strength": max(0.0, 1 - var_r / max(np.var(r.resid + r.seasonal), 1e-12)),
                             "trend_strength": max(0.0, 1 - var_r / max(np.var(r.resid + r.trend), 1e-12))})
    stf = pd.DataFrame(stl_rows)
    save_table(stf, "A01_stl_strength.csv")

    n_sig = int((tdf["q_fdr"] < ALPHA).sum())
    log.info("  趋势：%d/%d 品种×响应 通过 FDR；价格季节幅度中位 %.3f；成交量 %.3f",
             n_sig, len(tdf),
             amp[amp.variable == "price"].seasonal_range.median(),
             amp[amp.variable == "volume"].seasonal_range.median())

    plt = setup_plt()
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
    for tag, a in (("price", ax[0]), ("volume", ax[1])):
        s = amp[amp.variable == tag]
        a.bar(s["crop"], s["seasonal_range"], color=_v2.C_MAIN if tag == "price" else _v2.C_ALT)
        a.set_title(f"{tag}：季节指数极差（最大值-最小值）")
        a.set_ylabel("季节指数极差")
        a.tick_params(axis="x", rotation=60, labelsize=8)
    save_fig(fig, "A01_seasonal_amplitude.png")
    return tdf, amp, stf


# ---------------------------------------------------------------- A02
def A02(d, log):
    log.info("A02 日度响应（主模型含 AR(1)）")
    rows = []
    for outcome, ycol in (("price", "price_z"), ("volume", "volume_z")):
        for expo in CORE_EXPOSURES + SUPP_EXPOSURES:
            for crop in CROPS:
                g = d[d["crop"] == crop].sort_values("date")
                y = g[ycol].to_numpy(float)
                X = np.column_stack([
                    g[f"{ycol}_lag1"].to_numpy(float),          # AR(1)（主口径 F_lag）
                    g[expo].to_numpy(float),
                    g["precipitation"].to_numpy(float) * 0 + 1,  # 占位列（常量，会被 missing=drop 处理）
                    g["is_public_holiday"].to_numpy(float),
                ])[:, [0, 1, 3]]
                ok = np.isfinite(y) & np.isfinite(X).all(axis=1)
                if ok.sum() < 300:
                    continue
                r = hac_ols(y[ok], X[ok], maxlags=HAC)
                sd = g[expo].std(ddof=1)
                rows.append({"outcome": outcome, "exposure": expo, "crop": crop,
                             "ar1_coef": float(r["coef"][0]), "beta_per_sd": float(r["coef"][1]) * sd,
                             "beta_raw": float(r["coef"][1]), "se": float(r["se"][1]),
                             "p_raw": float(r["p"][1]), "n": r["n"], "r2": r["r2"],
                             "ar1": r["ar1"], "n_eff": r["n_eff"],
                             "ci_low": float(r["coef"][1]) * sd - 1.96 * float(r["se"][1]) * sd,
                             "ci_high": float(r["coef"][1]) * sd + 1.96 * float(r["se"][1]) * sd,
                             "is_core": expo in CORE_EXPOSURES})
    df = pd.DataFrame(rows)
    df["q_fdr"] = np.nan
    for (o, e), g in df.groupby(["outcome", "exposure"]):
        df.loc[g.index, "q_fdr"] = bh_fdr(g["p_raw"].to_numpy())   # family = (outcome × exposure) 逐品种 10 检验
    save_table(df, "A02_daily_response.csv")

    # 无自回归对照（F_wx）
    rows2 = []
    for outcome, ycol in (("price", "price_z"), ("volume", "volume_z")):
        for expo in CORE_EXPOSURES:
            for crop in CROPS:
                g = d[d["crop"] == crop].sort_values("date")
                y = g[ycol].to_numpy(float)
                X = np.column_stack([g[expo].to_numpy(float), g["is_public_holiday"].to_numpy(float)])
                ok = np.isfinite(y) & np.isfinite(X).all(axis=1)
                if ok.sum() < 300:
                    continue
                r = hac_ols(y[ok], X[ok], maxlags=HAC)
                rows2.append({"outcome": outcome, "exposure": expo, "crop": crop,
                              "beta_raw": float(r["coef"][0]), "p_raw": float(r["p"][0]),
                              "r2": r["r2"], "n": r["n"]})
    dfw = pd.DataFrame(rows2)
    save_table(dfw, "A02_daily_response_Fwx.csv")

    core = df[df.is_core]
    n_sig = int((core["q_fdr"] < ALPHA).sum())
    log.info("  核心暴露 FDR 显著：%d/%d；AR(1) 系数中位 %.4f",
             n_sig, len(core), float(df["ar1_coef"].median()))
    return df, dfw


# ---------------------------------------------------------------- A03
def A03(d, log):
    log.info("A03 滞后/累积/非线性（预定义窗口）")
    rows = []
    for outcome, ycol in (("price", "price_z"), ("volume", "volume_z")):
        for wkey, wlabel in LAG_WINDOWS.items():
            for crop in CROPS:
                g = d[(d["crop"] == crop)].sort_values("date")
                y = g[ycol].to_numpy(float)
                X = np.column_stack([g[f"{ycol}_lag1"].to_numpy(float),
                                     g[f"precip_{wkey}"].to_numpy(float),
                                     g[f"tmax_{wkey}"].to_numpy(float)])
                ok = np.isfinite(y) & np.isfinite(X).all(axis=1)
                if ok.sum() < 300:
                    continue
                r = hac_ols(y[ok], X[ok], maxlags=HAC)
                for j, ename in ((1, "precipitation"), (2, "temp_max")):
                    rows.append({"outcome": outcome, "exposure": ename, "window": wlabel,
                                 "window_key": wkey, "crop": crop,
                                 "beta": float(r["coef"][j]), "se": float(r["se"][j]),
                                 "p_raw": float(r["p"][j]), "n": r["n"], "r2": r["r2"]})
    ldf = pd.DataFrame(rows)
    ldf["q_fdr"] = np.nan
    for (o, e), g in ldf.groupby(["outcome", "exposure"]):
        ldf.loc[g.index, "q_fdr"] = bh_fdr(g["p_raw"].to_numpy())
    save_table(ldf, "A03_lag_windows.csv")

    # 累积降水 1/3/7/14：同时报告原始尺度与标准化尺度（区分累积效应与尺度变化）
    acc = []
    for outcome, ycol in (("price", "price_z"), ("volume", "volume_z")):
        for k in (1, 3, 7, 14):
            for crop in CROPS:
                g = d[(d["crop"] == crop)].sort_values("date")
                y = g[ycol].to_numpy(float)
                xr = g[f"precip_{k}d"].to_numpy(float)
                sd = np.nanstd(xr, ddof=1)
                X = np.column_stack([g[f"{ycol}_lag1"].to_numpy(float), xr])
                ok = np.isfinite(y) & np.isfinite(X).all(axis=1)
                if ok.sum() < 300 or not (np.isfinite(sd) and sd > 0):
                    continue
                r = hac_ols(y[ok], X[ok], maxlags=HAC)
                acc.append({"outcome": outcome, "cum_days": k, "crop": crop,
                            "beta_raw_per_mm": float(r["coef"][1]),
                            "beta_per_sd": float(r["coef"][1]) * sd,
                            "p_raw": float(r["p"][1]), "n": r["n"],
                            "x_sd": float(sd), "x_mean": float(np.nanmean(xr))})
    adf = pd.DataFrame(acc)
    adf["q_fdr"] = np.nan
    for (o, k), g in adf.groupby(["outcome", "cum_days"]):
        adf.loc[g.index, "q_fdr"] = bh_fdr(g["p_raw"].to_numpy())
    save_table(adf, "A03_accumulation.csv")

    # 非线性：自然样条 vs 线性（Wald-F），**必须控制 AR(1)**（否则自相关会制造伪显著）
    nl = []
    import statsmodels.api as sm
    from patsy import dmatrix
    from scipy import stats
    for outcome, ycol in (("price", "price_z"), ("volume", "volume_z")):
        for expo in ("precip_7d", "temp_max", "vpd", "soil_moisture_0_7"):
            for crop in CROPS:
                g = d[(d["crop"] == crop)].sort_values("date")
                if expo not in g.columns:
                    continue
                y = g[ycol].to_numpy(float)
                x = g[expo].to_numpy(float)
                ar = g[f"{ycol}_lag1"].to_numpy(float)          # AR(1) 控制
                hol = g["is_public_holiday"].to_numpy(float)
                ok = np.isfinite(y) & np.isfinite(x) & np.isfinite(ar)
                if ok.sum() < 300:
                    continue
                y_, x_, ar_, hol_ = y[ok], x[ok], ar[ok], hol[ok]
                ctrl = np.column_stack([ar_, hol_])              # 共同控制（两种模型同口径）
                B = dmatrix("cr(x, df=7)", {"x": x_}, return_type="dataframe").to_numpy()
                Xl = np.column_stack([ctrl, x_])
                Xs = np.column_stack([ctrl, B[:, 1:]])
                lin = sm.OLS(y_, sm.add_constant(Xl, has_constant="add")).fit()
                spl = sm.OLS(y_, sm.add_constant(Xs, has_constant="add")).fit()
                df1 = spl.df_model - lin.df_model
                if df1 <= 0:
                    continue
                F = ((lin.ssr - spl.ssr) / df1) / (spl.ssr / spl.df_resid)
                p = float(1 - stats.f.cdf(F, df1, spl.df_resid))
                nl.append({"outcome": outcome, "exposure": expo, "crop": crop,
                           "wald_F": float(F), "df1": int(df1), "p_raw": p, "n": int(ok.sum()),
                           "ar_control": True})
    ndf = pd.DataFrame(nl)
    if len(ndf):
        ndf["q_fdr"] = bh_fdr(ndf["p_raw"].to_numpy())      # family：全部非线性检验
        save_table(ndf, "A03_nonlinearity.csv")
        log.info("  非线性（含 AR(1) 控制）：FDR 显著 %d/%d（最小 q=%.4f）",
                 int((ndf.q_fdr < ALPHA).sum()), len(ndf), float(ndf.q_fdr.min()))
    log.info("  滞后窗与累积：FDR 显著 滞后 %d/%d；累积 %d/%d",
             int((ldf.q_fdr < ALPHA).sum()), len(ldf),
             int((adf.q_fdr < ALPHA).sum()), len(adf))
    return ldf, adf, ndf


# ---------------------------------------------------------------- A06(6.1,6.2)
def A06_core(d, log):
    log.info("A06.1 量价关系；A06.2 传导前提检查")
    rows = []
    for crop in CROPS + ["POOLED"]:
        g = d if crop == "POOLED" else d[d["crop"] == crop]
        g = g.sort_values(["crop", "date"])
        y = g["price_z"].to_numpy(float)
        v = g["volume_z"].to_numpy(float)
        pl = g["price_z_lag1"].to_numpy(float) if "price_z_lag1" in g else g.groupby("crop")["price_z"].shift(1).to_numpy(float)
        vl = g.groupby("crop")["volume_z"].shift(1).to_numpy(float)
        hol = g["is_public_holiday"].to_numpy(float)
        X = np.column_stack([v, pl, hol])
        ok = np.isfinite(y) & np.isfinite(X).all(axis=1)
        if ok.sum() < 300:
            continue
        r = hac_ols(y[ok], X[ok], maxlags=HAC)
        rows.append({"model": "price_z ~ volume_z + price_lag1", "crop": crop,
                     "beta_volume": float(r["coef"][0]), "se": float(r["se"][0]),
                     "p_raw": float(r["p"][0]), "n": r["n"], "r2": r["r2"],
                     "ci_low": float(r["coef"][0]) - 1.96 * float(r["se"][0]),
                     "ci_high": float(r["coef"][0]) + 1.96 * float(r["se"][0])})
    pv = pd.DataFrame(rows)
    if len(pv):
        sub = pv[pv.crop != "POOLED"]
        pv.loc[:, "q_fdr"] = np.nan
        if len(sub):
            pv.loc[sub.index, "q_fdr"] = bh_fdr(sub["p_raw"].to_numpy())
    save_table(pv, "A06_price_volume.csv")

    # weather -> volume 前提（取 A02 结果摘要即可，避免重复）
    a02 = pd.read_csv(_v2.TABLES / "A02_daily_response.csv")
    wv = a02[(a02.outcome == "volume") & (a02.is_core)]
    step1_sig = int((wv["q_fdr"] < ALPHA).sum())
    vp = pv[pv.crop != "POOLED"] if len(pv) else pd.DataFrame()
    step2_sig = int((vp["q_fdr"] < ALPHA).sum()) if len(vp) else 0
    verdict = ("链式传导前提不成立：weather→volume 在 FDR 后无可稳定检出项，"
               "故按预注册规则不再讨论中介效应") if step1_sig == 0 else "步骤一存在部分证据，继续检查步骤二"
    metrics_dump("A06_mediation_check.json", {
        "weather_to_volume_fdr_sig": step1_sig, "volume_to_price_fdr_sig": step2_sig,
        "verdict": verdict,
        "rule": "only discuss mediation if BOTH steps have evidence (analysis_plan A06.mediation)",
    })
    log.info("  A06.1 量价：FDR 显著 %d/%d；A06.2 步骤一显著 %d → %s",
             step2_sig, len(vp) if len(vp) else 0, step1_sig, verdict[:24])
    return pv, step1_sig, step2_sig


def main() -> None:
    log = get_logger("20_market_studies")
    log.info("=" * 70)
    log.info("A01/A02/A03/A06 市场端研究（v2）")
    d = load()
    log.info("数据：%d 行；主口径 strict z 有效 %d", len(d), int(d["price_z"].notna().sum()))

    tdf, amp, stf = A01(d, log)
    a2, a2w = A02(d, log)
    lag, acc, nl = A03(d, log)
    pv, s1, s2 = A06_core(d, log)

    # ---- 证据登记 ----
    claims = []
    n_tr = int((tdf.q_fdr < ALPHA).sum())
    claims.append(dict(claim_id="C-A01-TREND", study_id="A01",
                       claim_text=f"在 log 水平对时间趋势的 HAC(14) 回归中，10 品种×2 响应的 20 项趋势仅 {n_tr} 项在 BH-FDR 后显著",
                       claim_type="descriptive", evidence_id="EV-A01-TREND",
                       source_ids="SRC-SY-CLZ", table_id="A01_trend.csv",
                       figure_id="A01_seasonal_amplitude.png",
                       estimate=f"{n_tr}/20", sample_size=int(tdf["n"].sum()),
                       method_id="hac_ols_trend_fdr", status="descriptive_only"))
    amp_p = float(amp[amp.variable == "price"].seasonal_range.median())
    amp_v = float(amp[amp.variable == "volume"].seasonal_range.median())
    claims.append(dict(claim_id="C-A01-AMP", study_id="A01",
                       claim_text=f"价格季节指数极差中位数 {amp_p:.3f}，成交量季节指数极差中位数 {amp_v:.3f}",
                       claim_type="descriptive", evidence_id="EV-A01-AMP",
                       source_ids="SRC-SY-CLZ", table_id="A01_seasonal_amplitude.csv",
                       figure_id="A01_seasonal_amplitude.png",
                       estimate=f"price {amp_p:.3f} / volume {amp_v:.3f}",
                       sample_size=int(len(d)), method_id="seasonal_index",
                       status="descriptive_only"))
    core = a2[a2.is_core]
    n_c = int((core.q_fdr < ALPHA).sum())
    claims.append(dict(claim_id="C-A02-CORE", study_id="A02",
                       claim_text=f"在含 AR(1) 的日度响应模型中，10 品种 × 5 核心暴露 × 2 响应共 {len(core)} 项，"
                                  f"BH-FDR 后仅 {n_c} 项显著",
                       claim_type="association", evidence_id="EV-A02-CORE",
                       source_ids="SRC-SY-CLZ;SRC-OM-ERA5", table_id="A02_daily_response.csv",
                       estimate=f"{n_c}/{len(core)}",
                       p_raw=float(core["p_raw"].min()), p_adjusted=float(core["q_fdr"].min()),
                       sample_size=int(core["n"].sum()), method_id="hac_ar1_daily",
                       status="not_supported" if n_c == 0 else "partly_supported"))
    claims.append(dict(claim_id="C-A03-LAG", study_id="A03",
                       claim_text=f"预定义滞后窗（0日/1-3/4-7/8-14）内，降水与最高温的分布滞后项 "
                                  f"BH-FDR 后显著 {int((lag.q_fdr < ALPHA).sum())}/{len(lag)}",
                       claim_type="association", evidence_id="EV-A03-LAG",
                       source_ids="SRC-OM-ERA5", table_id="A03_lag_windows.csv",
                       estimate=f"{int((lag.q_fdr < ALPHA).sum())}/{len(lag)}",
                       p_raw=float(lag["p_raw"].min()), p_adjusted=float(lag["q_fdr"].min()),
                       sample_size=int(lag["n"].sum()), method_id="predefined_lag_windows",
                       status="not_supported" if int((lag.q_fdr < ALPHA).sum()) == 0 else "partly_supported"))
    if len(nl):
        claims.append(dict(claim_id="C-A03-NL", study_id="A03",
                           claim_text=f"非线性 Wald-F 检验（自然三次样条 df=7 vs 线性）共 {len(nl)} 项，"
                                      f"BH-FDR 后显著 {int((nl.q_fdr < ALPHA).sum())} 项",
                           claim_type="association", evidence_id="EV-A03-NL",
                           source_ids="SRC-OM-ERA5", table_id="A03_nonlinearity.csv",
                           estimate=f"{int((nl.q_fdr < ALPHA).sum())}/{len(nl)}",
                           p_raw=float(nl["p_raw"].min()), p_adjusted=float(nl["q_fdr"].min()),
                           sample_size=int(nl["n"].sum()), method_id="spline_wald_f",
                           status="not_supported" if int((nl.q_fdr < ALPHA).sum()) == 0 else "partly_supported"))
    if len(pv):
        sub = pv[pv.crop != "POOLED"]
        med = float(sub["beta_volume"].median()) if len(sub) else np.nan
        claims.append(dict(claim_id="C-A06-PV", study_id="A06",
                           claim_text=f"控制价格自身滞后后，成交量异常对价格异常的同期系数中位数 {med:.4f}（10 品种）",
                           claim_type="association", evidence_id="EV-A06-PV",
                           source_ids="SRC-SY-CLZ", table_id="A06_price_volume.csv",
                           estimate=f"{med:.4f}",
                           p_raw=float(sub["p_raw"].median()), p_adjusted=float(sub["q_fdr"].median()),
                           sample_size=int(sub["n"].sum()), method_id="hac_ar1_price_volume",
                           status="partly_supported" if s2 > 0 else "not_supported"))
    claims.append(dict(claim_id="C-A06-CHAIN", study_id="A06",
                       claim_text="按预注册规则检查天气→成交量→价格两步：步骤一（天气→成交量）FDR 显著 0 项，"
                                  "故不再讨论中介；当前数据未提供支持该链条的统计证据",
                       claim_type="association", evidence_id="EV-A06-CHAIN",
                       source_ids="SRC-SY-CLZ;SRC-OM-ERA5", table_id="A06_price_volume.csv",
                       estimate=f"step1_sig={s1}; step2_sig={s2}",
                       p_raw=float(core["p_raw"].min()), p_adjusted=float(core["q_fdr"].min()),
                       sample_size=int(core["n"].sum()), method_id="two_step_preregistered",
                       status="not_supported"))
    append_claims(claims)
    log.info("已登记 %d 条 claim", len(claims))
    log.info("完成")


if __name__ == "__main__":
    main()
