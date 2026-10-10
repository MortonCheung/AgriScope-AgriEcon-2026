"""a05_crop_heterogeneity.py — A05 作物异质性与恢复能力（六城统一）。

- 异质性：合并回归 z ~ z_(t-1) + exp_z + exp_z×crop，对交互项做联合检验（F），
  报告各作物斜率是否一致。
- 恢复：定义价格异常脉冲（|z| 超过阈值），测量回到 |z|<1 的期数；报告右删失率
  （观测期内未恢复的比例），不给出稳健性排序。
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from ..lib import contract, emit, loaders, panel, stats

MODULE = "A05"
SLUG = "crop-heterogeneity-recovery"
TITLE = "作物响应差异与市场恢复特征"
CITY_FREQ = {"chaoyang": "D", "jinzhou": "D", "dalian": "W", "shenyang": "D"}
SPIKE = 2.0
RECOVER = 1.0


def run(city: str) -> Dict:
    if city not in CITY_FREQ:
        return emit.emit_not_supported(city=city, module=MODULE, slug=SLUG, title=TITLE,
                                       reason="无满足最小覆盖的价格序列，无法做作物异质性与恢复分析。")
    cfg = loaders.load_cities()[city]
    an = loaders.load_analysis()
    hac = int(an["stats"]["hac_lags"]); win = int(an["price"]["deseason"]["doy_window"])
    min_obs = int(an["price"]["min_days_weather"]); alpha = float(an["global"]["alpha"])
    freq = CITY_FREQ[city]
    weather = loaders.load_weather(city)
    veg = loaders.veg_crops()
    pool = [c for c in veg if len(loaders.load_primary_series(city, c)) >= min_obs]

    # 组装 merged 面板 + 恢复
    blocks, rec_rows = [], []
    for crop in pool:
        s = panel.deseasonalize_strict(loaders.load_primary_series(city, crop), "price_per_kg", "date",
                                       freq=freq, doy_window=win)
        s = panel.add_weather(s, weather, freq, "date")
        s = s.dropna(subset=["z"]).sort_values("date").reset_index(drop=True)
        s["z_lag1"] = s["z"].shift(1)
        s["crop"] = crop
        blocks.append(s)
        # 恢复
        z = s["z"].to_numpy()
        idx = np.where(np.abs(z) > SPIKE)[0]
        spans, cens = [], 0
        for i in idx:
            j = i + 1
            while j < len(z) and abs(z[j]) > RECOVER:
                j += 1
            if j < len(z):
                spans.append(j - i)
            else:
                cens += 1
        rec_rows.append({"crop": crop, "n_spikes": int(len(idx)), "n_recovered": len(spans),
                         "n_censored": cens,
                         "censoring_rate": round(cens / len(idx), 3) if len(idx) else np.nan,
                         "median_recovery_periods": float(np.median(spans)) if spans else np.nan})
    alld = pd.concat(blocks, ignore_index=True)

    # 异质性：每种暴露的合并交互 F 检验
    het_rows, per_crop = [], []
    for ex in panel.EXPOSURES:
        col = ex + "_z"
        if col not in alld.columns:
            continue
        d = alld.dropna(subset=[col, "z_lag1", "z"]).copy()
        if len(d) < 3 * len(pool):
            continue
        # 每作物斜率
        sub_betas = {}
        for crop, g in d.groupby("crop"):
            if len(g) < 40:
                continue
            r = stats.hac_ols(g["z"].to_numpy(), g[["z_lag1", col]].to_numpy(), maxlags=hac)
            sub_betas[crop] = float(r["coef"][1])
            per_crop.append({"exposure": ex, "crop": crop, "beta": float(r["coef"][1]),
                             "ci_low": float(r["coef"][1] - 1.96 * r["se"][1]),
                             "ci_high": float(r["coef"][1] + 1.96 * r["se"][1]),
                             "p_raw": float(r["p"][1]), "n": r["n"]})
        # 交互联合检验（crop dummies × exposure）
        dd = d.dropna(subset=[col, "z_lag1", "z"])
        X = pd.get_dummies(dd["crop"], prefix="c", drop_first=True).astype(float)
        X["z_lag1"] = dd["z_lag1"].to_numpy(); X[col] = dd[col].to_numpy()
        inter = X[[c for c in X.columns if c.startswith("c_")]].mul(dd[col].to_numpy(), axis=0)
        inter.columns = [f"{c}×exp" for c in inter.columns]
        Xf = pd.concat([X, inter], axis=1)
        try:
            import statsmodels.api as sm
            full = sm.OLS(dd["z"].to_numpy(), sm.add_constant(Xf.to_numpy(), has_constant="add")).fit()
            base_cols = X.shape[1] + 1
            R = np.zeros((inter.shape[1], Xf.shape[1] + 1))
            for r_i in range(inter.shape[1]):
                R[r_i, base_cols + r_i] = 1
            ft = full.f_test(R)
            p_het = float(ft.pvalue)
        except Exception:  # noqa: BLE001
            p_het = np.nan
        het_rows.append({"exposure": ex, "p_heterogeneity": p_het,
                         "n_crops": len(sub_betas),
                         "beta_min": min(sub_betas.values()) if sub_betas else np.nan,
                         "beta_max": max(sub_betas.values()) if sub_betas else np.nan})
    het = pd.DataFrame(het_rows)
    if not het.empty:
        het["q"] = stats.bh_fdr(het["p_heterogeneity"].to_numpy())
    rec = pd.DataFrame(rec_rows)

    pc = pd.DataFrame(per_crop)
    if len(pc):
        pc["q"] = np.nan
        for ex, g in pc.groupby("exposure"):
            pc.loc[g.index, "q"] = stats.bh_fdr(g["p_raw"].to_numpy())  # 家族=暴露内作物
    w = contract.StudyWriter(city, MODULE, SLUG, f"{cfg['name']}市{TITLE}")
    w.save_table(het, f"{MODULE}_heterogeneity.csv")
    w.save_table(pc, f"{MODULE}_per_crop_beta.csv")
    w.save_table(rec, f"{MODULE}_recovery_by_crop.csv")

    n_het_sig = int((het["q"] < alpha).sum()) if not het.empty else 0
    cens_med = float(rec["censoring_rate"].median()) if not rec.empty else np.nan
    rec_med = float(rec["median_recovery_periods"].median()) if not rec.empty else np.nan
    fig = _fig(cfg["name"], het, rec)
    w.save_fig(fig, f"{MODULE}_heterogeneity.png")
    metrics = {"city": city, "freq": freq, "n_crops": len(pool), "n_het_tests": int(len(het)),
               "n_het_sig": n_het_sig, "median_censoring_rate": cens_med,
               "median_recovery_periods": rec_med, "alpha": alpha}
    w.dump_metrics(f"{MODULE}_summary.json", metrics)

    het_txt = "；".join([f"{r['exposure']}（q={r['q']:.3f}）" for _, r in het[het["q"] < alpha].iterrows()]) or "无"
    rec_txt = "；".join([f"{r['crop']} {r['median_recovery_periods']:.0f} 期（删失 {r['censoring_rate']:.0%}）"
                        for _, r in rec.sort_values("median_recovery_periods").head(5).iterrows()])
    abstract = (
        f"本研究检验{cfg['name']}不同蔬菜对气象的响应是否存在品种差异，以及价格异常脉冲的市场恢复特征。"
        f"价格为该城主源（{cfg['price_level_note']}），频率{'日度' if freq=='D' else '周度'}。"
        f"异质性用合并回归 z_t = α + φ·z_(t-1) + β·exp_z + γ·(exp_z×作物) 并对交互项做联合 F 检验；"
        f"恢复用脉冲（|z|>{SPIKE}）后回到 |z|<{RECOVER} 的期数，报告右删失率。"
        f"{len(het)} 项暴露异质性检验中 {n_het_sig} 项 FDR 显著；恢复右删失率中位数 {cens_med:.0%}。\n\n"
        f"**关键词**：作物异质性；交互检验；恢复期；右删失；{cfg['name']}"
    )
    frontend_summary = (f"{cfg['name']}：异质性 {n_het_sig}/{len(het)} 显著；恢复右删失率中位 {cens_med:.0%}。")
    data_scope = (f"### 2.1 研究对象\n{cfg['name']}主要蔬菜（{'、'.join(pool)}）。\n\n"
                  f"### 2.2 数据来源\n价格：{cfg['price_level_note']}；气象：ERA5 再分析网格。\n\n"
                  f"### 2.3 变量\n- z：严格去季节化价格异常；- 脉冲：|z|>{SPIKE}；- 恢复：回到 |z|<{RECOVER}。")
    methods = (f"### 3.1 异质性\n合并回归含暴露×作物交互，联合 F 检验（按暴露分组 BH-FDR）。\n\n"
               f"### 3.2 恢复\n脉冲后持续时间；未在观测期内恢复记为右删失，报告删失率。\n\n"
               f"### 3.3 说明\n恢复时间受观测期长度限制，不作稳健性排序。")
    results_text = [
        ("作物响应异质性", f"{len(het)} 项暴露检验中 **{n_het_sig} 项 FDR 显著**：{het_txt}。"
                           f"（表 {MODULE}_heterogeneity.csv、{MODULE}_per_crop_beta.csv）"),
        ("市场恢复", f"脉冲后恢复到 |z|<{RECOVER} 的期中位数 {rec_med:.0f} 期；"
                     f"右删失率中位 {cens_med:.0%}（{rec_txt}）。（表 {MODULE}_recovery_by_crop.csv）"),
    ]
    discussion = ("品种差异若成立，提示不同蔬菜对气象的敏感性不同；但本模块为探索性联合检验，需谨慎解读。"
                  f"恢复方面：本城脉冲后回到 |z|<{RECOVER} 的期中位数为 {rec_med:.1f} 期，"
                  f"右删失率中位 {cens_med:.0%}"
                  f"（{'多数脉冲在观测期内完整回落' if cens_med < 0.2 else '仍有相当比例脉冲在观测期末未完整回落'}），"
                  "故恢复期仅作描述，不据此给出跨作物韧性排序。")
    limitations = [
        f"1. **价格口径**：{cfg['price_level_note']}。",
        f"2. **恢复右删失**：{cens_med:.0%} 的脉冲在观测期末未完整回落，恢复期受观测期长度限制。",
        "3. **异质性为探索性**：交互联合检验显著不等于逐对显著；家族=暴露（仅 5 项），检验力有限。",
        "4. **再分析网格**：ERA5 平滑极端值。",
    ]
    conclusion = (f"{cfg['name']}：{len(het)} 项暴露异质性检验中 {n_het_sig} 项 FDR 显著"
                  f"（{'探索性品种差异' if n_het_sig else '未发现稳定品种差异'}）；"
                  f"脉冲恢复期中位 {rec_med:.1f} 期、右删失率中位 {cens_med:.0%}，不给出韧性排序。")
    explorer = {
        "selectors": [{"key": "crop", "label": "作物", "options": pool},
                      {"key": "exposure", "label": "暴露", "options": list(panel.EXPOSURES)}],
        "metrics": ["n_het_sig", "median_censoring_rate", "median_recovery_periods"],
        "series": [{"id": "per_crop_beta", "table": f"{MODULE}_per_crop_beta.csv", "x": "crop",
                    "y": "beta", "facet": "exposure"}],
        "tables": [f"{MODULE}_heterogeneity.csv", f"{MODULE}_per_crop_beta.csv", f"{MODULE}_recovery_by_crop.csv"],
        "figures": [f"{MODULE}_heterogeneity.png"], "sources": [],
        "methodology": methods, "limitations": limitations,
    }
    return emit.emit_study(
        city=city, module=MODULE, slug=SLUG, title=f"{cfg['name']}市{TITLE}",
        abstract=abstract, frontend_summary=frontend_summary,
        keywords=["作物异质性", "交互检验", "恢复期", "右删失", cfg["name"]],
        research_questions=[f"{cfg['name']}不同蔬菜的气象响应是否不同？价格脉冲如何恢复？"],
        data_scope=data_scope, methods=methods, results=results_text, discussion=discussion,
        limitations=limitations, conclusion=conclusion, explorer=explorer,
        tables=[f"{MODULE}_heterogeneity.csv", f"{MODULE}_per_crop_beta.csv", f"{MODULE}_recovery_by_crop.csv"],
        figures=[f"{MODULE}_heterogeneity.png"],
        claims=[{"claim_id": f"{city}-A05-C1", "study_id": "A05", "city": cfg["name"],
                 "claim_text": f"异质性 {n_het_sig}/{len(het)} 显著；恢复删失率中位 {cens_med:.0%}",
                 "claim_type": "exploratory", "table_id": f"{MODULE}_heterogeneity.csv",
                 "estimate": n_het_sig, "sample_size": int(alld.shape[0]),
                 "status": "PARTIAL" if n_het_sig else "NOT_SUPPORTED"}])


def _fig(city_name, het, rec):
    from ..lib.plotting import setup_plt, C_MAIN, C_ALT
    plt = setup_plt()
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))
    if not het.empty:
        axes[0].bar(het["exposure"], -np.log10(het["p_heterogeneity"].clip(lower=1e-6)), color=C_MAIN)
        axes[0].axhline(-np.log10(0.05), color="red", ls="--", lw=1, label="p=0.05")
        axes[0].set_ylabel("-log10(p) 异质性"); axes[0].legend()
        axes[0].tick_params(axis="x", rotation=20)
    if not rec.empty:
        axes[1].barh(rec["crop"], rec["median_recovery_periods"], color=C_ALT)
        axes[1].set_xlabel("恢复期中位数"); axes[1].invert_yaxis()
    fig.suptitle(f"{city_name}市 作物异质性与恢复")
    return fig