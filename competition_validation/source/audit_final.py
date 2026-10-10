#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""experiments/analysis/audit_final.py — 论文最终实验审计。

回答审查清单中的可证伪问题：
  A. 修复前后是否使用同一候选池 / 时间窗口 / 价格数据（跨代码树哈希比对）
  B. 旧公式 vs 新公式在**完全相同的样本与切点**上的对照（隔离 P0-4 基线定义效应）
  C. 随机策略多种子重复（固定规则）
  D. 重叠感知推断：HAC 滞后、块长度敏感性
  E. 多重比较校正（Bonferroni / BH-FDR）
  F. 风险指标与最差表现
  G. 逐年稳健性
  H. HRI 检验的多重比较与非重叠退化
  I. 预测准确度（WAPE）与市场收益分离

输出 -> experiments/results/audit/*.csv
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
os.environ.setdefault("PROJECT_ROOT", str(EXP / "root"))
sys.path.insert(0, str(EXP / "code" / "src"))

import numpy as np
import pandas as pd
from scipy import stats

OUT = EXP / "results" / "audit"
OUT.mkdir(parents=True, exist_ok=True)

H = 30
NBOOT = 4000
SEED = 42
MIN_WEEKS_SRC = 40

# ---------------------------------------------------------------- A. 候选池/价格同一性
PANEL_DUMP = r'''
import os, sys, json, hashlib
import pandas as pd, numpy as np
sys.path.insert(0, os.environ["DSRC"])
os.environ["PROJECT_ROOT"] = os.environ["PROJROOT"]
from decision_engine.final import backtest as BT
p = BT.build_panel()
cols = ["date","crop","forecast","anchor_price","realized_mean","realized_return","realized_worst","market_risk"]
d = p[cols].sort_values(["date","crop"]).reset_index(drop=True)
d["date"] = d["date"].astype(str)
h = hashlib.sha256(pd.util.hash_pandas_object(d, index=False).values.tobytes()).hexdigest()[:16]
out = {"panel_rows": int(len(p)),
       "n_dates": int(p["date"].nunique()),
       "n_crops": int(p["crop"].nunique()),
       "date_min": str(p["date"].min().date()), "date_max": str(p["date"].max().date()),
       "price_cols_hash": h,
       "crops": sorted(p["crop"].unique().tolist())}
print("PANELJSON=" + json.dumps(out, ensure_ascii=False))
'''


def panel_identity():
    rows = []
    for tag, dsrc in [("未修复代码", EXP / "code_original" / "src"), ("已修复代码", EXP / "code" / "src")]:
        env = dict(os.environ, DSRC=str(dsrc), PROJROOT=str(EXP / "root"), PYTHONHASHSEED="0")
        r = subprocess.run([sys.executable, "-c", PANEL_DUMP], env=env, capture_output=True, text=True, cwd=str(EXP))
        line = [l for l in r.stdout.splitlines() if l.startswith("PANELJSON=")]
        if not line:
            raise RuntimeError(f"panel dump failed for {tag}: {r.stderr[-800:]}")
        d = json.loads(line[0][len("PANELJSON="):])
        d["code_tree"] = tag
        rows.append(d)
    df = pd.DataFrame(rows)
    same = (df["panel_rows"].nunique() == 1 and df["price_cols_hash"].nunique() == 1
            and df["n_dates"].nunique() == 1)
    df["价格/预测列哈希一致"] = same
    df.to_csv(OUT / "A_panel_identity.csv", index=False, encoding="utf-8-sig")
    return df, same


# ---------------------------------------------------------------- 通用推断工具
def circ_block(x, n, block, rng):
    m = len(x); nb = int(np.ceil(n / block))
    st = rng.randint(0, m, size=nb)
    return x[np.concatenate([(np.arange(s, s + block) % m) for s in st])[:n]]


def boot_ci_p(d, block, n_boot=NBOOT, seed=SEED):
    d = np.asarray(d, float); d = d[np.isfinite(d)]
    if len(d) < 8:
        return np.nan, np.nan, np.nan, np.nan
    obs = float(d.mean()); c = d - obs
    rng = np.random.RandomState(seed)
    bs = np.array([circ_block(c, len(d), block, rng).mean() for _ in range(n_boot)])
    lo, hi = np.percentile(bs, [2.5, 97.5])
    p = float(np.mean(np.abs(bs) >= abs(obs)))
    return obs, float(obs - hi), float(obs - lo), max(p, 1.0 / n_boot)


def hac(d, lags):
    import statsmodels.api as sm
    d = np.asarray(d, float); d = d[np.isfinite(d)]
    if len(d) < 8:
        return np.nan, np.nan
    o = sm.OLS(d, np.ones((len(d), 1))).fit(cov_type="HAC", cov_kwds={"maxlags": max(1, int(lags))})
    return float(o.tvalues[0]), float(o.pvalues[0])


def bh_fdr(p):
    p = np.asarray(p, float)
    ok = np.isfinite(p)
    out = np.full(len(p), np.nan)
    if not ok.any():
        return out
    q = p[ok]
    n = len(q)
    order = np.argsort(q)
    ranked = q[order]
    adj = ranked * n / (np.arange(1, n + 1))
    adj = np.minimum.accumulate(adj[::-1])[::-1]
    res = np.empty(n); res[order] = np.clip(adj, 0, 1)
    out[ok] = res
    return out


# ---------------------------------------------------------------- B/C/D/E/F/G. 策略
def _pool_pct(s):
    return pd.to_numeric(s, errors="coerce").rank(pct=True, na_option="bottom").fillna(0.5)


def old_scores(g):
    """原（未修复）策略打分公式，用于在相同样本上做同口径对照。"""
    d = g.copy()
    d["hri_n"] = _pool_pct(d["HRI"])
    d["mr_n"] = (pd.to_numeric(d["market_risk"], errors="coerce") / 100).fillna(0.5)
    d["fc_n"] = _pool_pct(d["forecast"])
    d["low_n"] = _pool_pct(d["fc_low"].fillna(d["forecast"]))
    d["s_profit_abs"] = d["forecast"]                 # 原 Profit_only（绝对价格）
    d["s_chase_abs"] = d["anchor_price"]              # 原 Chase_price（绝对价格）
    d["s_balanced_old"] = 0.35 * d["fc_n"] + 0.20 * d["low_n"] - 0.15 * d["mr_n"] - 0.12 * d["hri_n"]
    d["s_lowrisk"] = -(d["mr_n"] + d["hri_n"])
    d["s_robust_old"] = d["fc_low"].fillna(d["forecast"]) - 0.5 * d["hri_n"] * d["forecast"]
    return d


def new_scores(g):
    from decision_engine.final.backtest import strategy_scores
    return strategy_scores(g)


def run_family(panel, dates, scorer, strat_cols, tag, with_seasonal=True):
    """在**同一 panel 与同一 dates** 上按给定打分函数运行，返回逐切点逐策略记录。"""
    from decision_engine.final.backtest import _seasonal_pick, _seasonal_hist
    hist = _seasonal_hist() if with_seasonal else None
    rows = []
    for t in dates:
        g = panel[panel["date"] == t]
        if len(g) < 4:
            continue
        sc = scorer(g)
        thr = g["HRI"].quantile(0.90)
        for name, col in strat_cols.items():
            idx = sc[col].idxmax()
            r = g.loc[idx]
            rows.append({"snapshot": tag, "date": str(pd.Timestamp(t).date()), "strategy": name,
                         "crop": r["crop"], "realized_return": float(r["realized_return"]),
                         "realized_worst": float(r["realized_worst"]),
                         "HRI": float(r["HRI"]) if pd.notna(r["HRI"]) else np.nan,
                         "high_hri": bool(pd.notna(r["HRI"]) and r["HRI"] >= thr),
                         "predicted_return": float(r["forecast"] / r["anchor_price"] - 1)})
        if with_seasonal:
            sidx = _seasonal_pick(sc, hist)
            r = sc.loc[sidx]
            rows.append({"snapshot": tag, "date": str(pd.Timestamp(t).date()), "strategy": "Seasonal",
                         "crop": r["crop"], "realized_return": float(r["realized_return"]),
                         "realized_worst": float(r["realized_worst"]),
                         "HRI": float(r["HRI"]) if pd.notna(r["HRI"]) else np.nan,
                         "high_hri": bool(pd.notna(r["HRI"]) and r["HRI"] >= thr),
                         "predicted_return": float(r["forecast"] / r["anchor_price"] - 1)})
    return pd.DataFrame(rows)


OLD_STRATS = {"Profit_only_ABS": "s_profit_abs", "Chase_price_ABS": "s_chase_abs",
              "Balanced_old": "s_balanced_old", "Risk_only": "s_lowrisk",
              "Most_Robust_OLD": "s_robust_old"}
NEW_STRATS = {"Highest_forecast_return": "s_profit", "Highest_price_level": "s_price_level",
              "Chase_price_momentum": "s_chase", "Balanced_old": "s_balanced_old",
              "Balanced_fix_v1": "s_balanced_fix_v1", "Balanced_fix_v2": "s_balanced_fix_v2",
              "Low_risk": "s_lowrisk", "Most_Robust": "s_robust"}


def expectation_records(panel, dates, tag):
    """均匀随机选择的解析期望（=池内均值），作为所有策略的统一对照基准。"""
    rows = []
    for t in dates:
        g = panel[panel["date"] == t]
        if len(g) < 4:
            continue
        hr = pd.to_numeric(g["HRI"], errors="coerce")
        thr = hr.quantile(0.90)
        rr = pd.to_numeric(g["realized_return"], errors="coerce")
        rows.append({"snapshot": tag, "date": str(pd.Timestamp(t).date()), "strategy": "Random_expectation",
                     "crop": "__POOL__", "realized_return": float(rr.mean()),
                     "realized_worst": float(pd.to_numeric(g["realized_worst"], errors="coerce").mean()),
                     "HRI": float(hr.mean()), "high_hri": float((hr >= thr).mean()) >= 0.10,
                     "predicted_return": float(np.nanmean(pd.to_numeric(g["forecast"], errors="coerce") /
                                                          pd.to_numeric(g["anchor_price"], errors="coerce") - 1))})
    return pd.DataFrame(rows)


def same_sample_formula_compare(panel):
    from decision_engine.final.backtest import _select_cutoffs
    dates7 = _select_cutoffs(sorted(panel["date"].unique()), 7)
    dates30 = _select_cutoffs(sorted(panel["date"].unique()), 30)
    frames = []
    for tag, scorer, strats in [("旧公式", old_scores, OLD_STRATS), ("新公式", new_scores, NEW_STRATS)]:
        for step, ds in [(7, dates7), (30, dates30)]:
            f = run_family(panel, ds, scorer, strats, tag)
            f["cutoff_step_days"] = step
            e = expectation_records(panel, ds, tag)
            e["cutoff_step_days"] = step
            frames.append(pd.concat([f, e], ignore_index=True))
    rec = pd.concat(frames, ignore_index=True)
    rec.to_csv(OUT / "B_same_sample_formula_records.csv", index=False, encoding="utf-8-sig")
    summ = (rec.groupby(["cutoff_step_days", "snapshot", "strategy"])
            .agg(n=("realized_return", "size"),
                 mean=("realized_return", "mean"),
                 median=("realized_return", "median"),
                 downside=("realized_return", lambda s: float(s[s < 0].mean()) if (s < 0).any() else 0.0),
                 worst=("realized_return", "min"),
                 p05=("realized_return", lambda s: float(s.quantile(0.05))),
                 std=("realized_return", "std"),
                 p_down=("realized_return", lambda s: float((s < 0).mean())),
                 high_hri_rate=("high_hri", "mean"))
            .reset_index())
    summ.to_csv(OUT / "B_same_sample_formula_summary.csv", index=False, encoding="utf-8-sig")
    return rec, summ


def random_multiseed(panel, dates, n_rep=500, tag="Random_multiseed"):
    """固定规则多种子：每个切点用 seed=(rep, 日期 ordinal) 均匀抽 1 个作物。"""
    rows = []
    crops_by_date = {t: panel[panel["date"] == t] for t in dates}
    for rep in range(n_rep):
        acc, worst_acc = [], []
        for t, g in crops_by_date.items():
            if len(g) < 4:
                continue
            rng = np.random.RandomState((rep * 1000003 + pd.Timestamp(t).toordinal()) % (2 ** 31 - 1))
            idx = g.index[rng.permutation(len(g))[0]]
            acc.append(float(g.loc[idx, "realized_return"]))
            worst_acc.append(float(g.loc[idx, "realized_worst"]))
        rows.append({"seed_rep": rep, "n": len(acc), "mean_market_return": float(np.mean(acc)),
                     "median_market_return": float(np.median(acc)),
                     "p_down": float(np.mean(np.array(acc) < 0)),
                     "worst": float(np.min(acc)), "mean_worst_path": float(np.mean(worst_acc)),
                     "std": float(np.std(acc, ddof=1))})
    d = pd.DataFrame(rows)
    d.to_csv(OUT / f"C_random_multiseed_{tag}.csv", index=False, encoding="utf-8-sig")
    return d


def inference_sensitivity(rec, tag):
    """D/E：块长度与 HAC 滞后敏感性 + 多重比较校正。"""
    piv = rec.pivot_table(index="date", columns="strategy", values="realized_return", aggfunc="first")
    piv = piv.sort_index()
    n = len(piv)
    ref_col = None
    for c in ["Random_expectation"]:
        if c in piv.columns:
            ref_col = c
    rows = []
    for s in piv.columns:
        if s == ref_col:
            continue
        d = (piv[s] - piv[ref_col]).dropna().values
        r = {"snapshot": tag, "strategy": s, "n": len(d), "mean_diff": float(np.mean(d))}
        for blk in [1, 3, 5, 10]:
            _, lo, hi, p = boot_ci_p(d, blk, n_boot=2000)
            r[f"p_boot_block{blk}"] = p
            if blk == 3:
                r["ci_lo"], r["ci_hi"] = lo, hi
        for lag in [1, 2, 5, 8]:
            t_, p_ = hac(d, lag)
            r[f"p_hac_lag{lag}"] = p_
            if lag == 1:
                r["hac_t_lag1"] = t_
        rows.append(r)
    out = pd.DataFrame(rows)
    out["p_boot_min"] = out[[c for c in out.columns if c.startswith("p_boot_block")]].min(axis=1)
    out["p_boot_max"] = out[[c for c in out.columns if c.startswith("p_boot_block")]].max(axis=1)
    out["p_hac_max"] = out[[c for c in out.columns if c.startswith("p_hac_lag")]].max(axis=1)
    k = len(out)
    out["bonferroni_boot_min"] = np.minimum(1, out["p_boot_min"] * k)
    out["bonferroni_boot_max"] = np.minimum(1, out["p_boot_max"] * k)
    out["bonferroni_hac_max"] = np.minimum(1, out["p_hac_max"] * k)
    out["bh_fdr_boot"] = bh_fdr(out["p_boot_block3"].values)
    out["bh_fdr_hac"] = bh_fdr(out["p_hac_lag1"].values)
    out["显著_未校正(block3&lag1)"] = (out["p_boot_block3"] < 0.05) & (out["p_hac_lag1"] < 0.05)
    out["显著_Bonferroni"] = (out["bonferroni_boot_min"] < 0.05) & (out["bonferroni_hac_max"] < 0.05)
    # 保守口径：块长取最不利（p 最大）、HAC 滞后取最不利（p 最大）后再做 Bonferroni
    out["显著_Bonferroni_保守"] = (out["bonferroni_boot_max"] < 0.05) & (out["bonferroni_hac_max"] < 0.05)
    out["显著_BH-FDR"] = (out["bh_fdr_boot"] < 0.05) & (out["bh_fdr_hac"] < 0.05)
    out.to_csv(OUT / f"DE_inference_{tag}.csv", index=False, encoding="utf-8-sig")
    return out


def per_year(rec, tag):
    d = rec.copy(); d["year"] = pd.to_datetime(d["date"]).dt.year
    o = (d.groupby(["year", "strategy"])
         .agg(n=("realized_return", "size"), mean=("realized_return", "mean"),
              median=("realized_return", "median"),
              downside=("realized_return", lambda s: float(s[s < 0].mean()) if (s < 0).any() else 0.0),
              worst=("realized_return", "min"), p_down=("realized_return", lambda s: float((s < 0).mean())),
              high_hri_rate=("high_hri", "mean")).reset_index())
    o["snapshot"] = tag
    o.to_csv(OUT / f"G_by_year_{tag}.csv", index=False, encoding="utf-8-sig")
    return o


# ---------------------------------------------------------------- H. HRI 多重检验
def hri_multiple_testing():
    p = EXP / "results" / "B01_fixed" / "exports" / "tables" / "hri_timeseries_validation.csv"
    d = pd.read_csv(p)
    d = d[d["city"] == "沈阳"].copy()
    d["p_hac"] = pd.to_numeric(d["hac_p"], errors="coerce")
    d["p_boot"] = pd.to_numeric(d["p_block_bootstrap"], errors="coerce")
    d["bh_fdr_p_hac_all30"] = bh_fdr(d["p_hac"].values)
    d["bh_fdr_p_boot_all30"] = bh_fdr(d["p_boot"].values)
    d["robust_raw"] = d["robust_significant"]
    d["robust_after_BH(hac)"] = (d["bh_fdr_p_hac_all30"] < 0.05)
    d["robust_after_BH(boot)"] = (d["bh_fdr_p_boot_all30"] < 0.05)
    d["n_nonoverlap_available"] = d["p_nonoverlap"].notna()
    d.to_csv(OUT / "H_hri_multiple_testing.csv", index=False, encoding="utf-8-sig")
    s = []
    for w in [4, 8, 12]:
        sw = d[d["window_w"] == w]
        s.append({"window_w": w, "crops": len(sw),
                  "raw显著": int(sw["raw_significant"].sum()),
                  "robust原判": int(sw["robust_raw"].sum()),
                  "BH后(hac)_显著": int(sw["robust_after_BH(hac)"].sum()),
                  "BH后(boot)_显著": int(sw["robust_after_BH(boot)"].sum()),
                  "两项均过BH": int((sw["robust_after_BH(hac)"] & sw["robust_after_BH(boot)"]).sum()),
                  "非重叠可用作物数": int(sw["n_nonoverlap_available"].sum()),
                  "p_boot达到下界(0.0005)作物数": int((sw["p_boot"] <= 1.0 / 2000 + 1e-9).sum())})
    sm = pd.DataFrame(s)
    sm.to_csv(OUT / "H_hri_summary_multiple_testing.csv", index=False, encoding="utf-8-sig")
    return d, sm


# ---------------------------------------------------------------- I. 预测准确度
def forecast_accuracy():
    sel = pd.read_csv(EXP / "results" / "B01_fixed" / "exports" / "tables" / "price_model_selection.csv")
    s = sel[(sel["city"] == "沈阳") & (sel["horizon"] == H)].copy()
    s["WAPE_相对基线改善%"] = (s["baseline_WAPE"] - s["mean_WAPE"]) / s["baseline_WAPE"] * 100
    keep = ["crop", "model", "route", "mean_WAPE", "baseline_WAPE", "beats_baseline",
            "WAPE_相对基线改善%", "improvement_vs_baseline_pct"]
    s[keep].sort_values("crop").to_csv(OUT / "I_forecast_accuracy_h30.csv", index=False, encoding="utf-8-sig")
    return s[keep]


# ---------------------------------------------------------------- main
if __name__ == "__main__":
    from decision_engine.final.backtest import build_panel, _select_cutoffs

    print("== A. 候选池/价格同一性 ==")
    pid, same = panel_identity()
    print(pid.drop(columns=["crops"]).to_string(index=False))
    print("价格/预测列跨代码树一致:", same)

    panel = build_panel()
    print(f"\npanel: rows={len(panel)} dates={panel['date'].nunique()} "
          f"crops={panel['crop'].nunique()} {panel['date'].min().date()}~{panel['date'].max().date()}")

    print("\n== B. 同一样本/同一 HRI 下的公式对照（隔离 P0-4） ==")
    rec, summ = same_sample_formula_compare(panel)
    print(summ.to_string(index=False))

    print("\n== C. 随机策略多种子（固定规则） ==")
    dates30 = _select_cutoffs(sorted(panel["date"].unique()), 30)
    dates7 = _select_cutoffs(sorted(panel["date"].unique()), 7)
    r30 = random_multiseed(panel, dates30, tag="step30")
    r7 = random_multiseed(panel, dates7, tag="step7")
    for nm, r in [("step30", r30), ("step7", r7)]:
        print(f"{nm}: 均值分布 mean={r['mean_market_return'].mean():.4f} "
              f"[{r['mean_market_return'].quantile(.025):.4f},{r['mean_market_return'].quantile(.975):.4f}] "
              f"std={r['mean_market_return'].std():.4f} 最差单次={r['mean_market_return'].min():.4f}")

    print("\n== D/E. 重叠感知推断 + 多重比较（新） ==")
    rec_new = rec[rec["snapshot"] == "新公式"]
    inf30 = inference_sensitivity(rec_new[rec_new["cutoff_step_days"] == 30], "new_step30")
    inf7 = inference_sensitivity(rec_new[rec_new["cutoff_step_days"] == 7], "new_step7")
    cols = ["strategy", "n", "mean_diff", "ci_lo", "ci_hi", "p_boot_block3", "p_hac_lag1",
            "p_hac_max", "bonferroni_boot_min", "bh_fdr_boot", "bh_fdr_hac",
            "显著_未校正(block3&lag1)", "显著_Bonferroni", "显著_BH-FDR"]
    print("\n[step30]"); print(inf30[cols].sort_values("mean_diff", ascending=False).to_string(index=False))
    print("\n[step7]"); print(inf7[cols].sort_values("mean_diff", ascending=False).to_string(index=False))

    print("\n== G. 逐年（新公式 step30） ==")
    yr = per_year(rec_new[rec_new["cutoff_step_days"] == 30], "new_step30")
    print(yr.pivot_table(index="strategy", columns="year", values="mean").round(4).to_string())

    print("\n== H. HRI 多重检验 ==")
    hd, hsm = hri_multiple_testing()
    print(hsm.to_string(index=False))

    print("\n== I. 预测准确度（沈阳 h=30） ==")
    fa = forecast_accuracy()
    print(fa.to_string(index=False))
    print("\nwritten ->", OUT)
