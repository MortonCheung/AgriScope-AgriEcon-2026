#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P3-04 / P3-07：模型规格、环境、正式贝叶斯拟合（M0 与 M1×{S0,S1,S2}）、采样诊断、Prior→Posterior 更新。
输出：
  MODEL_SPECIFICATION.md, MODEL_ENVIRONMENT.md
  fits/M0_posterior.npz, fits/M1_S0_posterior.npz, fits/M1_S1_posterior.npz, fits/M1_S2_posterior.npz
  fits/posterior_summary.csv
  diagnostics/sampler_diagnostics.csv, SAMPLER_DIAGNOSTICS.md
  diagnostics/prior_posterior_update.csv, PRIOR_DOMINANCE_AUDIT.md
  diagnostics/trace_plot.png, posterior_plot.png
"""
import os
import platform
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from m1_lib import sample, split_rhat, ess_bulk, ess_tail, summarize, PARAM_NAMES  # noqa
from m1_priors import PRIORS, PRIOR_CHANGELOG  # noqa

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
M1 = os.path.join(BASE, "06_models", "M1_bayesian_yield_response")
FZ = os.path.join(M1, "data", "M1_dataset_frozen.csv")
SEED = 20260922
NC, WARM, DRAWS = 4, 5000, 5000


def load():
    d = pd.read_csv(FZ)
    y = np.log(d["yield_kg_ha"].values.astype(float))
    T = d["time_index"].values.astype(float)
    R = d["primary_rain_exposure"].values.astype(float)
    ZT = (T - T.mean()) / T.std(ddof=1)
    ZR = (R - R.mean()) / R.std(ddof=1)
    return d, y, ZT, ZR, dict(T_mean=T.mean(), T_sd=T.std(ddof=1), R_mean=R.mean(), R_sd=R.std(ddof=1))


def main():
    d, y, ZT, ZR, std = load()

    # ---------------- MODEL_SPECIFICATION.md ----------------
    with open(os.path.join(M1, "MODEL_SPECIFICATION.md"), "w", encoding="utf-8") as f:
        f.write(f"""# MODEL_SPECIFICATION.md

## 结构
```
log(Y_t) = alpha + beta_T * Z(T_t) + beta_R * Z(R_t) + eps_t ,  eps_t ~ Normal(0, sigma)
```
- `Y_t` = 沈北玉米单产 (kg/ha)（**log 尺度**：保证正产量、系数≈比例变化、反事实差异易转百分比）
- `Z(T_t)` = 标准化时间趋势（训练样本均值/标准差）
- `Z(R_t)` = 标准化抽雄吐丝期主极端降水 `repro_precip_max_5d`（mm）
- 先验：`alpha,beta_T,beta_R,log sigma` 见 `scripts/m1_priors.py`（S0/S1/S2）

## 对照模型
- **M0**（Baseline，趋势模型）：`log(Y_t)=alpha+beta_T*Z(T_t)+eps_t`
- **M1**（趋势+极端降雨）：上式

## 标准化与数据泄漏防护
- **全样本正式模型**：使用 2018–2025 全样本均值/标准差。
- **LOYO**：**每一折仅用该折训练年份**计算均值/标准差（见 `76_p3_exact_loyo.py`），**绝不使用被留出年份**。

## 量纲与单位
- 单产 kg/ha；降水 mm；`beta_R` 的单位是“每 1 个训练标准差降水”对 `log` 单产的影响。
- 训练样本：`R`均值={std['R_mean']:.1f} mm，`R`标准差={std['R_sd']:.1f} mm；`T`均值={std['T_mean']:.1f}，`T`标准差={std['T_sd']:.3f}。
""")

    # ---------------- MODEL_ENVIRONMENT.md ----------------
    with open(os.path.join(M1, "MODEL_ENVIRONMENT.md"), "w", encoding="utf-8") as f:
        f.write(f"""# MODEL_ENVIRONMENT.md

| 项 | 值 |
|---|---|
| Python | {platform.python_version()} |
| platform | {platform.platform()} |
| numpy | {np.__version__} |
| pandas | {pd.__version__} |
| scipy | {scipy.__version__} |
| random_seed | {SEED} |
| sampler | 自实现自适应随机游走 Metropolis（Haario 协方差自适应），4 链 |
| chains / warmup / draws | {NC} / {WARM} / {DRAWS} |
| target_accept（等价） | 通过自适应步长使接受率落在 ~0.234 附近（见 sampler_diagnostics.csv） |

## 为什么不用 PyMC
当前环境 **Python 3.9.6**，PyMC 5.x 要求 Python ≥3.10；PyMC 4.x 与 numpy 2.0 不兼容。
故按规格“**优先复用/局部安装**”的原则，**在同一进程内自实现贝叶斯采样器**，
并提供 **split-R-hat / bulk ESS / tail ESS / 接受率** 全套诊断，保证**可复现**。
本偏离已在 `PHASE_3_RESEARCH_REPORT.md` 中明确说明。
""")

    # ---------------- 拟合 ----------------
    fits = {}
    rows = []
    diag = []

    def do_fit(name, prior, use_R, save=None):
        out = sample(y, ZT, ZR, prior, use_R=use_R, n_chains=NC, warmup=WARM, draws=DRAWS, seed=SEED)
        ch = out["chain"]
        rhat = split_rhat(ch)
        eb = ess_bulk(ch); et = ess_tail(ch)
        for j, pn in enumerate(PARAM_NAMES):
            diag.append(dict(model=name, param=pn, rhat=round(float(rhat[j]), 4),
                             ess_bulk=round(float(eb[j]), 1), ess_tail=round(float(et[j]), 1)))
        diag.append(dict(model=name, param="_accept_rate", rhat=np.nan,
                         ess_bulk=round(out["accept"], 3), ess_tail=np.nan))
        s = summarize(ch)
        flat = ch.reshape(-1, ch.shape[2])
        for j, pn in enumerate(PARAM_NAMES):
            rows.append(dict(model=name, param=pn, mean=round(float(s["mean"][j]), 4),
                             median=round(float(s["median"][j]), 4), sd=round(float(s["sd"][j]), 4),
                             q2_5=round(float(s["q025"][j]), 4), q97_5=round(float(s["q975"][j]), 4),
                             q5=round(float(s["q05"][j]), 4), q95=round(float(s["q95"][j]), 4)))
        if use_R:
            br = flat[:, 2]
            rows.append(dict(model=name, param="P(beta_R<0)", mean=round(float((br < 0).mean()), 4)))
        return out, ch, flat

    o0, ch0, flat0 = do_fit("M0", PRIORS["S0"], use_R=False)
    np.savez_compressed(os.path.join(M1, "fits", "M0_posterior.npz"), chain=ch0, accept=o0["accept"])
    for k in ["S0", "S1", "S2"]:
        o, ch, flat = do_fit(f"M1_{k}", PRIORS[k], use_R=True)
        np.savez_compressed(os.path.join(M1, "fits", f"M1_{k}_posterior.npz"),
                            chain=ch, accept=o["accept"], prior=np.array([PRIORS[k]["beta_R"][0], PRIORS[k]["beta_R"][1]]))
        fits[k] = flat

    pd.DataFrame(diag).to_csv(os.path.join(M1, "diagnostics", "sampler_diagnostics.csv"),
                              index=False, encoding="utf-8-sig")
    pd.DataFrame(rows).to_csv(os.path.join(M1, "fits", "posterior_summary.csv"),
                              index=False, encoding="utf-8-sig")

    # 采样诊断 md
    dg = pd.DataFrame(diag)
    worst_rhat = dg.dropna(subset=["rhat"]).rhat.max()
    min_ess = dg[dg.param != "_accept_rate"].ess_bulk.min()
    with open(os.path.join(M1, "diagnostics", "SAMPLER_DIAGNOSTICS.md"), "w", encoding="utf-8") as f:
        f.write("# SAMPLER_DIAGNOSTICS.md（P3-07）\n\n")
        f.write(f"- 最大 R-hat = **{worst_rhat:.4f}**（判据 ≤1.01）\n")
        f.write(f"- 最小 bulk ESS = **{min_ess:.0f}**\n")
        f.write(f"- 接受率：M0={o0['accept']:.3f}；"
                + "；".join([f"M1_{k}={grep_accept(diag, k):.3f}" for k in ['S0', 'S1', 'S2']]) + "\n\n")
        f.write(dg.to_string(index=False))
        f.write("\n\n## 判据\n- R-hat ≤ 1.01；bulk/tail ESS 合理；无 divergence（本采样器无 HMC divergence，"
                "以接受率与 R-hat/ESS 作为收敛证据）。\n")
        f.write(f"\n**结论：{'收敛合格' if worst_rhat <= 1.01 else '未达标，需重采'}**\n")

    # ---------------- Prior → Posterior 更新 ----------------
    upd = []
    for k in ["S0", "S1", "S2"]:
        for j, pn in enumerate(PARAM_NAMES):
            pm, ps = PRIORS[k][pn] if pn in PRIORS[k] else (np.nan, np.nan)
            post = fits[k][:, j]
            upd.append(dict(model=f"M1_{k}", parameter=pn,
                            prior_mean=round(pm, 4), prior_sd=round(ps, 4),
                            posterior_mean=round(float(post.mean()), 4),
                            posterior_median=round(float(np.median(post)), 4),
                            posterior_sd=round(float(post.std(ddof=1)), 4),
                            CrI95=f"[{np.quantile(post,0.025):.4f}, {np.quantile(post,0.975):.4f}]",
                            sd_ratio_post_over_prior=round(float(post.std(ddof=1) / ps), 3) if ps else np.nan))
    udf = pd.DataFrame(upd)
    udf.to_csv(os.path.join(M1, "diagnostics", "prior_posterior_update.csv"), index=False, encoding="utf-8-sig")

    with open(os.path.join(M1, "diagnostics", "PRIOR_DOMINANCE_AUDIT.md"), "w", encoding="utf-8") as f:
        f.write("# PRIOR_DOMINANCE_AUDIT.md（P3-10）\n\n")
        f.write("判据（针对 `beta_R`）：posterior_sd/prior_sd <0.5 → DATA_INFORMATIVE；0.5–0.9 → MIXED；>0.9 → PRIOR_DOMINATED\n\n")
        for k in ["S0", "S1", "S2"]:
            r = udf[(udf.model == f"M1_{k}") & (udf.parameter == "beta_R")].iloc[0]
            ratio = r.sd_ratio_post_over_prior
            cls = "DATA_INFORMATIVE" if ratio < 0.5 else ("MIXED" if ratio < 0.9 else "PRIOR_DOMINATED")
            f.write(f"- **M1_{k}**: beta_R posterior sd/prior sd = **{ratio}** → `{cls}`；"
                    f"P(beta_R<0) = {float((fits[k][:,2]<0).mean()):.3f}\n")
        f.write("\n> 若为 PRIOR_DOMINATED / MIXED，反事实必须标记为“文献约束下的情景推演”，"
                "不得写成“沈北数据证明”。\n")
    print(udf[udf.parameter.isin(["beta_R", "alpha", "beta_T", "log_sigma"])].to_string(index=False))
    print("worst_rhat", worst_rhat, "min_ess", min_ess, "accept", o0["accept"],
          [grep_accept(diag, k) for k in ["S0", "S1", "S2"]])


def grep_accept(diag, k):
    for r in diag:
        if r["model"] == f"M1_{k}" and r["param"] == "_accept_rate":
            return r["ess_bulk"]
    return float("nan")


if __name__ == "__main__":
    main()
