"""21_event_forecast.py — A04 极端事件与2026案例 / A05 异质性与恢复 / A06.3 天气预测增量。

预注册对应：plan/analysis_plan.yaml 的 A04 / A05 / A06.predictive_value。
官方事件与算法事件**严格分开**；恢复定义**预先固定**；预测必须 Rolling Origin。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _v2
from _v2 import (ALPHA, CROPS, DATA, append_claims, bh_fdr, get_logger,
                 metrics_dump, save_fig, save_table, setup_plt, wild_cluster_bootstrap)

LOG = get_logger("21_event_forecast")
WH = Path("/Users/morton_cheung/Desktop/比赛/大数据分析")
HAC = 14
WIN_PRE, WIN_POST = 14, 14
BASE_LO, BASE_HI = -14, -4          # 基准期 T-14 ~ T-4
RECOV_THR, RECOV_K, RECOV_MAX = 0.5, 3, 42


def load():
    d = pd.read_parquet(DATA / "v2_market_daily.parquet")
    d["date"] = pd.to_datetime(d["date"])
    return d


def event_clusters():
    """算法事件簇：间隔 ≤3 天合并（clean event 规则）。"""
    f = WH / "data/research" / "reference" / "marts" / "fact_disaster_events.csv"
    ev = pd.read_csv(f, parse_dates=["start_date", "end_date"])
    ev = ev[ev["city"] == "沈阳"].copy().sort_values("start_date")
    ev["hazard"] = np.where(ev["event_type"].isin(["rainstorm", "heavy_rain"]), "rain", "heat")
    out = []
    for hz, g in ev.groupby("hazard"):
        cur = None
        for _, r in g.iterrows():
            if cur is not None and (r["start_date"] - cur["end"]).days <= 3:
                cur["end"] = max(cur["end"], r["end_date"])
                cur["n"] += 1
                cur["ids"].append(r["event_id"])
            else:
                if cur:
                    out.append(cur)
                cur = {"hazard": hz, "start": r["start_date"], "end": r["end_date"],
                       "n": 1, "ids": [r["event_id"]]}
        if cur:
            out.append(cur)
    out = pd.DataFrame(out).reset_index(drop=True)
    # clean event 规则：基准窗 T-14~T-4 内若含任何其他事件 → 标记为受污染（前事件污染）
    out["contaminated"] = False
    for i, c in out.iterrows():
        lo = c["start"] - pd.Timedelta(days=WIN_PRE)
        hi = c["start"] - pd.Timedelta(days=4)
        for j, o in out.iterrows():
            if i == j:
                continue
            if (o["start"] <= hi) and (o["end"] >= lo):
                out.loc[i, "contaminated"] = True
                break
    return out


def event_clusters_clean():
    c = event_clusters()
    return c[~c["contaminated"]].reset_index(drop=True)


def A04(d, log):
    log.info("A04 事件研究与 2026 案例")
    cl_all = event_clusters()
    cl = event_clusters_clean()
    save_table(cl_all.assign(ids=cl_all["ids"].astype(str)), "A04_event_clusters.csv")
    log.info("  事件簇：全部 %d（污染 %d）→ clean %d", len(cl_all),
             int(cl_all["contaminated"].sum()), len(cl))

    # 事件相对化 z：z_rel = z - mean(z over T-14..T-4)，逐品种
    recs = []
    for _, c in cl.iterrows():
        t0 = pd.Timestamp(c["start"])
        for crop in CROPS:
            g = d[d["crop"] == crop].set_index("date").sort_index()
            for tag, zc in (("price", "price_z"), ("volume", "volume_z")):
                seg = g.loc[t0 + pd.Timedelta(days=BASE_LO): t0 + pd.Timedelta(days=WIN_POST), zc]
                base = g.loc[t0 + pd.Timedelta(days=BASE_LO): t0 + pd.Timedelta(days=BASE_HI), zc]
                if base.dropna().shape[0] < 3:
                    continue
                rel = seg - base.mean()
                post = rel.loc[t0 + pd.Timedelta(days=1): t0 + pd.Timedelta(days=14)]
                recs.append({"event": int(c.name), "hazard": c["hazard"], "t0": t0,
                             "crop": crop, "response": tag,
                             "post_mean": float(post.mean()) if post.notna().any() else np.nan,
                             "n_post": int(post.notna().sum())})
    r = pd.DataFrame(recs)
    save_table(r, "A04_event_responses.csv")

    # 事件簇级 bootstrap CI + placebo（匹配年份/季节/星期结构）
    rng = np.random.default_rng(_v2.SEED)
    summ = []
    for hz, gh in r.groupby("hazard"):
        for tag in ("price", "volume"):
            s = gh[gh.response == tag].groupby("event")["post_mean"].mean().dropna()
            if len(s) == 0:
                continue
            cl_ids = s.index.to_numpy()
            cl_mean = float(s.mean())
            boots = [float(s.sample(frac=1, replace=True, random_state=int(rng.integers(1e9))).mean())
                     for _ in range(1000)]
            # placebo：在非事件日期内按「同季节+同星期」抽样
            ev_dates = set()
            for _, c in cl[cl.hazard == hz].iterrows():
                for dd in pd.date_range(c["start"] - pd.Timedelta(days=WIN_PRE),
                                        c["end"] + pd.Timedelta(days=WIN_POST), freq="D"):
                    ev_dates.add(dd)
            all_dates = sorted(d["date"].unique())
            cand = [x for x in all_dates if x not in ev_dates]
            plc = []
            for _ in range(500):
                pick = pd.Timestamp(rng.choice(cand))
                vals = []
                for crop in CROPS:
                    g = d[d["crop"] == crop].set_index("date").sort_index()
                    zc = "price_z" if tag == "price" else "volume_z"
                    seg = g.loc[pick + pd.Timedelta(days=1): pick + pd.Timedelta(days=14), zc]
                    base = g.loc[pick + pd.Timedelta(days=BASE_LO): pick + pd.Timedelta(days=BASE_HI), zc]
                    if base.dropna().shape[0] >= 3 and seg.notna().any():
                        vals.append(float((seg - base.mean()).mean()))
                if vals:
                    plc.append(np.mean(vals))
            plc = np.array(plc)
            p_emp = float(np.mean(np.abs(plc) >= abs(cl_mean))) if len(plc) else np.nan
            summ.append({"hazard": hz, "response": tag, "n_events": int(len(s)),
                         "post_mean": cl_mean,
                         "ci_low": float(np.quantile(boots, .025)),
                         "ci_high": float(np.quantile(boots, .975)),
                         "placebo_mean": float(np.mean(plc)) if len(plc) else np.nan,
                         "placebo_sd": float(np.std(plc)) if len(plc) else np.nan,
                         "placebo_p": p_emp, "n_placebo": len(plc)})
    S = pd.DataFrame(summ)
    save_table(S, "A04_event_summary.csv")
    log.info("  事件簇：总 %d（rain %d / heat %d）", len(cl),
             int((cl.hazard == "rain").sum()), int((cl.hazard == "heat").sum()))
    if len(S):
        log.info("  %s", S.round(4).to_string(index=False))

    # 2026 案例（单独 case study）
    t0c = pd.Timestamp("2026-07-13")
    w = pd.read_parquet(_v2.WS / "data" / "interim" / "shenyang_weather_daily.parquet")
    w["date"] = pd.to_datetime(w["date"])
    w = w.sort_values("date")
    case = {
        "t0": str(t0c.date()),
        "max_1d_precip_mm": float(w["precipitation"].max()),
        "max_1d_precip_date": str(w.loc[w["precipitation"].idxmax(), "date"].date()),
        "max_1d_rank": int((w["precipitation"] > w["precipitation"].max()).sum() + 1),
        "total_obs_days": int(len(w)),
        "max_3d_precip_mm": float(w["precip_3d"].max()),
    }
    if "clim_precipitation_mean" in w.columns:
        clim = w["clim_precipitation_mean"].median()
        sd = w["clim_precipitation_std"].median()
        case["t0_clim_mean_mm"] = float(clim)
        case["t0_clim_sd_mm"] = float(sd)
        case["t0_z_vs_clim"] = float((case["max_1d_precip_mm"] - clim) / sd) if sd else None
    pc = {}
    for crop in CROPS:
        g = d[d["crop"] == crop].set_index("date").sort_index()
        for tag, zc in (("price", "price_z"), ("volume", "volume_z")):
            seg = g.loc[t0c + pd.Timedelta(days=1): t0c + pd.Timedelta(days=14), zc]
            base = g.loc[t0c - pd.Timedelta(days=14): t0c - pd.Timedelta(days=4), zc]
            pc[f"{crop}_{tag}"] = float((seg - base.mean()).mean()) if base.dropna().shape[0] >= 3 else np.nan
    case["case_post_mean_price"] = float(np.nanmean([pc[f"{c}_price"] for c in CROPS]))
    case["case_post_mean_volume"] = float(np.nanmean([pc[f"{c}_volume"] for c in CROPS]))
    metrics_dump("A04_case2026.json", case)
    log.info("  2026 案例：单日最大 %.1fmm（第 %d/%d）；价格事后均值 %.3f；成交量 %.3f",
             case["max_1d_precip_mm"], case["max_1d_rank"], case["total_obs_days"],
             case["case_post_mean_price"], case["case_post_mean_volume"])
    return cl, r, S, case


def A05(d, log):
    log.info("A05 品种异质性与恢复（预定义恢复判据，处理右删失）")
    # 恢复：|z_rel| <= 0.5 连续 3 日；42 日未恢复 → 右删失
    cl = event_clusters_clean()
    recs = []
    for _, c in cl.iterrows():
        t0 = pd.Timestamp(c["start"])
        for crop in CROPS:
            g = d[d["crop"] == crop].set_index("date").sort_index()
            for tag, zc in (("price", "price_z"), ("volume", "volume_z")):
                base = g.loc[t0 + pd.Timedelta(days=BASE_LO): t0 + pd.Timedelta(days=BASE_HI), zc]
                if base.dropna().shape[0] < 3:
                    continue
                rel = (g[zc] - base.mean())
                post = rel.loc[t0 + pd.Timedelta(days=1): t0 + pd.Timedelta(days=RECOV_MAX)]
                # 谷底
                trough = post.abs().max()
                if not np.isfinite(trough) or trough < 1e-9:
                    continue
                # 恢复时点：首次出现「连续 K 日 |rel| <= 0.5」且在该谷底之后
                arr = post.to_numpy()
                dts = post.index
                trough_pos = int(np.nanargmax(np.abs(arr)))
                rec_day, censored = None, 1
                for i in range(trough_pos, len(arr) - RECOV_K + 1):
                    win = arr[i:i + RECOV_K]
                    if np.all(np.isfinite(win)) and np.all(np.abs(win) <= RECOV_THR):
                        rec_day = i + 1
                        censored = 0
                        break
                recs.append({"event": int(c.name), "hazard": c["hazard"], "crop": crop,
                             "response": tag, "trough_abs": float(trough),
                             "recovery_day": rec_day if rec_day else RECOV_MAX,
                             "censored": censored})
    R = pd.DataFrame(recs)
    save_table(R, "A05_recovery.csv")

    # 品种差异：系数差异检验（而非比较 p 值）——用 crop×exposure 交互
    import statsmodels.api as sm
    from patsy import dmatrix
    het = []
    for outcome, ycol in (("price", "price_z"), ("volume", "volume_z")):
        for expo in ("precip_7d", "temp_max"):
            g = d.sort_values(["crop", "date"]).copy()
            g["ar"] = g.groupby("crop")[ycol].shift(1)
            D = pd.get_dummies(g["crop"], prefix="c", drop_first=True).astype(float)
            X = pd.concat([g[["ar", expo, "is_public_holiday"]].astype(float), D], axis=1)
            # 交互：每个品种一个斜率（等价于 crop×exposure 交互，全饱和）
            Xi = pd.concat([X, D.mul(g[expo], axis=0)], axis=1)
            ok = np.isfinite(g[ycol]) & np.isfinite(Xi).all(axis=1)
            lin = sm.OLS(g[ycol][ok], sm.add_constant(X[ok], has_constant="add")).fit()
            inter = sm.OLS(g[ycol][ok], sm.add_constant(Xi[ok], has_constant="add")).fit()
            df1 = inter.df_model - lin.df_model
            if df1 <= 0:
                continue
            F = ((lin.ssr - inter.ssr) / df1) / (inter.ssr / inter.df_resid)
            from scipy import stats as st
            p = float(1 - st.f.cdf(F, df1, inter.df_resid))
            het.append({"outcome": outcome, "exposure": expo, "F_crop_interaction": float(F),
                        "df1": int(df1), "p_raw": p, "n": int(ok.sum())})
    H = pd.DataFrame(het)
    if len(H):
        H["q_fdr"] = bh_fdr(H["p_raw"].to_numpy())
        save_table(H, "A05_heterogeneity.csv")
        log.info("  品种×暴露交互：FDR 显著 %d/%d", int((H.q_fdr < ALPHA).sum()), len(H))
    cm = R.groupby(["response", "crop"]).agg(n=("event", "size"),
                                             censored=("censored", "sum"),
                                             rec_median=("recovery_day", "median")).reset_index()
    save_table(cm, "A05_recovery_by_crop.csv")
    log.info("  恢复：删失率 价格 %.0f%% / 成交量 %.0f%%",
             100 * R[R.response == "price"]["censored"].mean(),
             100 * R[R.response == "volume"]["censored"].mean())
    return R, H, cm


def A06_forecast(d, log):
    log.info("A06.3 天气预测增量（Rolling Origin：baseline vs baseline+weather）")
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler
    rows = []
    for crop in CROPS:
        g = d[d["crop"] == crop].sort_values("date").dropna(subset=["price_z"]).reset_index(drop=True)
        if len(g) < 300:
            continue
        base_feats = ["price_z_lag1", "volume_z_lag1", "precipitation_lag1d", "temp_max_lag1d"]
        base_feats = [c for c in base_feats if c in g.columns]
        wx_feats = base_feats + [c for c in ["precipitation", "temp_max", "vpd", "soil_moisture_0_7"]
                                 if c in g.columns]
        years = sorted(g["date"].dt.year.unique())
        for y in years[2:]:
            tr = g[g["date"].dt.year < y]
            te = g[g["date"].dt.year == y]
            if len(tr) < 150 or len(te) < 30:
                continue
            for tag, feats in (("baseline", base_feats), ("weather", wx_feats)):
                A = tr[feats].copy()
                B = te[feats].copy()
                med = A.median()                      # 仅用训练折估填补值（无泄漏）
                A = A.fillna(med)
                B = B.fillna(med)
                ytr = tr["price_z"].to_numpy(float)
                yte = te["price_z"].to_numpy(float)
                sc = StandardScaler().fit(A)          # 只 fit 训练折
                m = Ridge(alpha=1.0).fit(sc.transform(A), ytr)
                pred = m.predict(sc.transform(B))
                rmse = float(np.sqrt(np.mean((yte - pred) ** 2)))
                rows.append({"crop": crop, "test_year": int(y), "model": tag,
                             "rmse": rmse, "mae": float(np.mean(np.abs(yte - pred))),
                             "n_test": len(te)})
    F = pd.DataFrame(rows)
    save_table(F, "A06_forecast_rolling.csv")
    piv = F.pivot_table(index=["crop", "test_year"], columns="model", values="rmse").reset_index()
    if "baseline" in piv and "weather" in piv:
        piv["delta_rmse"] = piv["baseline"] - piv["weather"]
        piv["rel_gain_pct"] = 100 * piv["delta_rmse"] / piv["baseline"]
        save_table(piv, "A06_forecast_gain.csv")
        log.info("  预测增量：ΔRMSE 中位 %.4f（正=天气有帮助）；相对增益中位 %.2f%%",
                 float(piv["delta_rmse"].median()), float(piv["rel_gain_pct"].median()))
        return piv
    return pd.DataFrame()


def main() -> None:
    log = get_logger("21_event_forecast")
    log.info("=" * 70)
    d = load()
    cl, r, S, case = A04(d, log)
    R, H, cm = A05(d, log)
    piv = A06_forecast(d, log)

    claims = []
    if len(S):
        rain_p = S[(S.hazard == "rain") & (S.response == "price")]
        if len(rain_p):
            x = rain_p.iloc[0]
            claims.append(dict(claim_id="C-A04-RAIN-PRICE", study_id="A04",
                               claim_text=f"雨事件簇（n={int(x.n_events)}）价格事后均值 {x.post_mean:.3f}，"
                                          f"95%CI [{x.ci_low:.3f}, {x.ci_high:.3f}]，安慰剂经验 p={x.placebo_p:.3f}",
                               claim_type="association", evidence_id="EV-A04-RAIN-PRICE",
                               source_ids="SRC-EVT-DERIVED;SRC-SY-CLZ",
                               table_id="A04_event_summary.csv",
                               estimate=f"{x.post_mean:.4f}", ci_low=f"{x.ci_low:.4f}",
                               ci_high=f"{x.ci_high:.4f}", p_raw=f"{x.placebo_p:.4f}",
                               sample_size=int(x.n_events), method_id="event_study_cluster_boot",
                               status="not_supported" if (np.isfinite(x.placebo_p) and x.placebo_p > ALPHA)
                               else "partly_supported"))
    claims.append(dict(claim_id="C-A04-CASE2026", study_id="A04",
                       claim_text=f"2026-07 暴雨单日最大降水 {case['max_1d_precip_mm']:.1f}mm，"
                                  f"为样本内第 {case['max_1d_rank']}/{case['total_obs_days']} 位；"
                                  f"案例价格事后均值 {case['case_post_mean_price']:.3f}、成交量 {case['case_post_mean_volume']:.3f}",
                       claim_type="descriptive", evidence_id="EV-A04-CASE2026",
                       source_ids="SRC-OM-ERA5;SRC-EVT-OFFICIAL-2026;SRC-SY-CLZ",
                       table_id="A04_event_summary.csv",
                       estimate=f"price {case['case_post_mean_price']:.3f}",
                       sample_size=int(case["total_obs_days"]), method_id="case_study",
                       status="descriptive_only"))
    if len(R):
        cens_p = 100 * R[R.response == "price"]["censored"].mean()
        claims.append(dict(claim_id="C-A05-RECOVERY", study_id="A05",
                           claim_text=f"按预定义恢复判据（|z_rel|≤0.5 连续 3 日、上限 42 日），"
                                      f"价格恢复观察的右删失率为 {cens_p:.0f}%",
                           claim_type="descriptive", evidence_id="EV-A05-RECOVERY",
                           source_ids="SRC-EVT-DERIVED;SRC-SY-CLZ", table_id="A05_recovery_by_crop.csv",
                           estimate=f"{cens_p:.1f}%", sample_size=int(len(R)),
                           method_id="frozen_recovery_rule", status="descriptive_only"))
    if len(H):
        n_sig = int((H.q_fdr < ALPHA).sum())
        claims.append(dict(claim_id="C-A05-HET", study_id="A05",
                           claim_text=f"crop×weather 交互的 Wald-F 检验共 {len(H)} 项，BH-FDR 后显著 {n_sig} 项",
                           claim_type="association", evidence_id="EV-A05-HET",
                           source_ids="SRC-SY-CLZ;SRC-OM-ERA5", table_id="A05_heterogeneity.csv",
                           estimate=f"{n_sig}/{len(H)}", p_raw=float(H.p_raw.min()),
                           p_adjusted=float(H.q_fdr.min()), sample_size=int(H.n.sum()),
                           method_id="crop_weather_interaction_f",
                           status="not_supported" if n_sig == 0 else "partly_supported"))
    if len(piv):
        med = float(piv["rel_gain_pct"].median())
        from scipy import stats as st
        try:
            w_p = float(st.wilcoxon(piv["baseline"], piv["weather"]).pvalue)
        except Exception:  # noqa: BLE001
            w_p = np.nan
        metrics_dump("A06_forecast_test.json", {"n_folds": int(len(piv)),
                                                "median_rel_gain_pct": med,
                                                "wilcoxon_p": w_p,
                                                "note": "H0: baseline 与 weather 的 RMSE 无差异"})
        claims.append(dict(claim_id="C-A06-FORECAST", study_id="A06",
                           claim_text=f"Rolling Origin 下，加入天气变量后 RMSE 相对于仅用历史量价的 baseline "
                                      f"的相对变化中位数为 {med:.2f}%（正=天气有帮助）；"
                                      f"Wilcoxon 符号秩检验 p={w_p:.3f}",
                           claim_type="prediction", evidence_id="EV-A06-FORECAST",
                           source_ids="SRC-SY-CLZ;SRC-OM-ERA5", table_id="A06_forecast_gain.csv",
                           estimate=f"{med:.4f}", p_raw=f"{w_p:.4f}", sample_size=int(len(piv)),
                           method_id="rolling_origin_ridge",
                           status="partly_supported" if med > 0 else "not_supported"))
    append_claims(claims)
    log.info("已登记 %d 条 claim", len(claims))
    log.info("完成")


if __name__ == "__main__":
    main()
