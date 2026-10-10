#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P3-09 Exact Leave-One-Year-Out（M0 vs M1×{S0,S1,S2}）。
- 每折**仅用训练年份**做标准化（防泄漏）；
- 输出 validation/LOYO_predictions.csv, validation/LOYO_metrics.csv。
"""
import os
import sys

import numpy as np
import pandas as pd
from scipy.special import logsumexp

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from m1_lib import sample  # noqa
from m1_priors import PRIORS  # noqa

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
M1 = os.path.join(BASE, "06_models", "M1_bayesian_yield_response")
FZ = os.path.join(M1, "data", "M1_dataset_frozen.csv")
SEED = 20260922
NC, WARM, DRAWS = 4, 3000, 3000


def predict(flat, ZT_ho, ZR_ho, use_R):
    a, bT, bR, ls = flat[:, 0], flat[:, 1], flat[:, 2], flat[:, 3]
    mu = a + bT * ZT_ho + (bR * ZR_ho if use_R else 0.0)
    return np.exp(mu), np.exp(ls)


def main():
    d = pd.read_csv(FZ)
    y = d["yield_kg_ha"].values.astype(float)
    T = d["time_index"].values.astype(float)
    R = d["primary_rain_exposure"].values.astype(float)
    years = d["year"].values
    n = len(y)

    rows = []
    for i in range(n):
        tr = np.ones(n, bool); tr[i] = False
        # 标准化只用训练折
        ZT = (T - T[tr].mean()) / T[tr].std(ddof=1)
        ZR = (R - R[tr].mean()) / R[tr].std(ddof=1)
        ytr = np.log(y[tr])
        rec = dict(year=int(years[i]), observed_yield=float(y[i]))
        for name, prior, use_R in [("M0", PRIORS["S0"], False),
                                   ("M1_S0", PRIORS["S0"], True),
                                   ("M1_S1", PRIORS["S1"], True),
                                   ("M1_S2", PRIORS["S2"], True)]:
            out = sample(ytr, ZT[tr], ZR[tr], prior, use_R=use_R,
                         n_chains=NC, warmup=WARM, draws=DRAWS, seed=SEED + i)
            ch = out["chain"]; flat = ch.reshape(-1, ch.shape[2])
            yhat, sg = predict(flat, ZT[i], ZR[i], use_R)
            ly = np.log(y[i])
            lpd = logsumexp(-0.5 * ((ly - np.log(yhat)) / sg) ** 2 - np.log(sg) - 0.5 * np.log(2 * np.pi)) - np.log(len(yhat))
            rec[f"{name}_pred_mean"] = float(yhat.mean())
            rec[f"{name}_pred_median"] = float(np.median(yhat))
            rec[f"{name}_50_interval"] = f"[{np.percentile(yhat,25):.0f},{np.percentile(yhat,75):.0f}]"
            rec[f"{name}_80_interval"] = f"[{np.percentile(yhat,10):.0f},{np.percentile(yhat,90):.0f}]"
            rec[f"{name}_95_interval"] = f"[{np.percentile(yhat,2.5):.0f},{np.percentile(yhat,97.5):.0f}]"
            rec[f"{name}_error"] = float(yhat.mean() - y[i])
            rec[f"{name}_log_predictive_density"] = float(lpd)
        rows.append(rec)

    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(M1, "validation", "LOYO_predictions.csv"), index=False, encoding="utf-8-sig")

    # 指标
    metrics = []
    yobs = df["observed_yield"].values
    for name in ["M0", "M1_S0", "M1_S1", "M1_S2"]:
        pm = df[f"{name}_pred_mean"].values
        err = pm - yobs
        cov50 = np.mean([_inside(df[f"{name}_50_interval"][k], yobs[k]) for k in range(n)]) * 100
        cov80 = np.mean([_inside(df[f"{name}_80_interval"][k], yobs[k]) for k in range(n)]) * 100
        cov95 = np.mean([_inside(df[f"{name}_95_interval"][k], yobs[k]) for k in range(n)]) * 100
        metrics.append(dict(model=name,
                            MAE_kg_ha=round(float(np.mean(np.abs(err))), 1),
                            RMSE_kg_ha=round(float(np.sqrt(np.mean(err ** 2))), 1),
                            mean_log_predictive_density=round(float(df[f"{name}_log_predictive_density"].mean()), 3),
                            coverage50=round(cov50, 1), coverage80=round(cov80, 1), coverage95=round(cov95, 1),
                            worst_year=int(df.loc[np.argmax(np.abs(err)), "year"])))
    mx = pd.DataFrame(metrics)
    mx.to_csv(os.path.join(M1, "validation", "LOYO_metrics.csv"), index=False, encoding="utf-8-sig")

    # 与 M0 的对比
    m0 = mx[mx.model == "M0"].iloc[0]
    lines = ["# LOYO 对比结论\n", mx.to_string(index=False), "\n## M1 vs M0\n"]
    for name in ["M1_S0", "M1_S1", "M1_S2"]:
        r = mx[mx.model == name].iloc[0]
        lines.append(f"- {name}: ΔMAE={r.MAE_kg_ha-m0.MAE_kg_ha:+.1f}；ΔRMSE={r.RMSE_kg_ha-m0.RMSE_kg_ha:+.1f}；"
                     f"ΔlogPD={r.mean_log_predictive_density-m0.mean_log_predictive_density:+.3f}")
    with open(os.path.join(M1, "validation", "LOYO_COMPARISON.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(mx.to_string(index=False))


def _inside(intv, v):
    lo, hi = intv.strip("[]").split(",")
    return float(lo) <= v <= float(hi)


if __name__ == "__main__":
    main()
