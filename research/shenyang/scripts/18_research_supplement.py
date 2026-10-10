"""研究成稿补充分析（本轮仅补 2 项：确有数据、且只差一步即可回答的研究点）。

补做项
------
R02  成交量长期趋势（原 03_descriptive 只做 log_price ~ t，未做成交量）
     OLS(log volume ~ t) + Newey-West HAC(maxlags=14)，逐品种，与价格趋势同口径。
     volume_unit = unknown → 只报年化百分比变化，禁止写吨。

R10  累积降雨窗口比较（原 05_lag_analysis 只覆盖 1d/3d/7d，缺 5d/14d）
     单 lag 分布滞后回归（与 STEP 10 完全同口径）：hazard = precip_{1,3,5,7,14}d，
     k = 0..14 自然日，逐品种 × {price, volume}，响应 = 方法B 去季节化稳健 z，
     控制 is_weekend / is_public_holiday，HAC(14)，全家族 BH-FDR。

纪律：不新开模型族、不新造数据；结论一律 Level B（统计关联），阴性结果如实登记。

产出
----
outputs/tables/trend_volume_by_crop.csv
outputs/tables/precip_window_comparison.csv
outputs/tables/precip_window_summary.csv
outputs/figures/F52_precip_window_comparison.png
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    ANALYSIS, CROPS_CFG, StepTimer, bh_fdr, get_logger, load_parquet,
    register_results, save_table, set_seed, setup_matplotlib,
)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

LOG = get_logger("18_research_supplement")
CORE_CROPS: list = CROPS_CFG["core_crops"]
VOL_UNIT: str = CROPS_CFG["market"]["volume_unit"]
CORE_START = pd.Timestamp(ANALYSIS["time"]["core_start_planned"])
CORE_END = pd.Timestamp(ANALYSIS["time"]["weather_end"])
HAC_LAGS = int(ANALYSIS["lag"]["hac_maxlags"])
MIN_OBS = int(ANALYSIS["lag"]["min_obs"])
FOCUS_MAX = int(ANALYSIS["lag"]["focus_max_lag_days"])
CONTROLS = ["is_weekend", "is_public_holiday"]

WINDOWS = [
    ("precip_1d", "1日"),
    ("precip_3d", "3日"),
    ("precip_5d", "5日"),
    ("precip_7d", "7日"),
    ("precip_14d", "14日"),
]
VARS = [("price", "价格"), ("volume", "成交量")]

set_seed()
setup_matplotlib()


# --------------------------------------------------------------------------- #
# R02 成交量长期趋势
# --------------------------------------------------------------------------- #
def r02_volume_trend(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for crop in CORE_CROPS:
        d = panel[panel["crop"] == crop].sort_values("date").dropna(subset=["volume"])
        if len(d) < 100 or (d["volume"] <= 0).any():
            LOG.warning("%s 成交量样本不足或含非正值，跳过趋势估计", crop)
            continue
        t = (d["date"] - d["date"].min()).dt.days.astype(float).values
        y = np.log(d["volume"].astype(float).values)
        X = sm.add_constant(t)
        res = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": HAC_LAGS})
        b, se = float(res.params[1]), float(res.bse[1])
        ann = (np.exp(b * 365.25) - 1.0) * 100.0
        lo = (np.exp((b - 1.96 * se) * 365.25) - 1.0) * 100.0
        hi = (np.exp((b + 1.96 * se) * 365.25) - 1.0) * 100.0
        rows.append({
            "crop": crop, "var": "log_volume", "unit": VOL_UNIT,
            "slope_per_day": b, "se_hac": se,
            "annualized_trend_pct": ann, "ci_low_annual_pct": lo, "ci_high_annual_pct": hi,
            "p_value": float(res.pvalues[1]), "n_obs": int(len(d)),
            "note": "沈阳批发口径；HAC maxlags=14；单位 unknown，仅年化百分比可比",
        })
    out = pd.DataFrame(rows)
    save_table(out, "trend_volume_by_crop")
    register_results([
        {
            "result_id": f"SUPP-TRENDVOL-{r['crop']}",
            "research_question": "R02",
            "crop": r["crop"], "period": f"{CORE_START.date()}~{CORE_END.date()}",
            "method": "OLS(log volume ~ t), Newey-West HAC",
            "metric": "annualized_trend_pct",
            "estimate": round(r["annualized_trend_pct"], 4),
            "ci_low": round(r["ci_low_annual_pct"], 4), "ci_high": round(r["ci_high_annual_pct"], 4),
            "p_value": round(r["p_value"], 6), "robustness": f"HAC(maxlags={HAC_LAGS})",
            "figure": "F05_volume_timeseries_all.png", "table": "trend_volume_by_crop.csv",
            "evidence_level": "A",
            "notes": "成交量单位 unknown，仅年化百分比；长期漂移，非天气效应",
        }
        for _, r in out.iterrows()
    ])
    LOG.info("R02 成交量趋势：%d 个品种完成", len(out))
    return out


# --------------------------------------------------------------------------- #
# R10 累积降雨窗口比较
# --------------------------------------------------------------------------- #
def build_precip_z() -> tuple[pd.DataFrame, pd.DataFrame]:
    """把 5 个降水窗口按完整日序列标准化为 z（1 SD 口径，与 STEP 10 一致）。"""
    w = load_parquet("weather_daily")
    w = w[(w["date"] >= CORE_START) & (w["date"] <= CORE_END)].sort_values("date").reset_index(drop=True)
    gaps = int((w["date"].diff().dt.days.dropna() != 1).sum())
    if gaps:
        LOG.warning("气象日序列存在 %d 处断裂，滞后语义受影响", gaps)
    raw = w[["date"]].copy()
    scales = []
    for col, label in WINDOWS:
        v = w[col].astype(float)
        mu, sd = float(v.mean()), float(v.std(ddof=1))
        raw[f"{col}__z"] = ((v - mu) / sd).values
        scales.append({
            "hazard_key": col, "label": label, "unit": "mm",
            "n_days": int(v.notna().sum()), "mean": mu, "sd": sd,
            "p95": float(v.quantile(0.95)), "max": float(v.max()),
        })
    # 自然日滞后矩阵（行位移 = 自然日位移，因日序列无断裂）
    lag = raw[["date"]].copy()
    for col, _ in WINDOWS:
        z = raw[f"{col}__z"].values
        for k in range(0, FOCUS_MAX + 1):
            lag[f"{col}__z_lag{k}"] = np.r_[np.full(k, np.nan), z[: len(z) - k]]
    return lag, pd.DataFrame(scales)


def r10_precip_windows(panel: pd.DataFrame) -> pd.DataFrame:
    lag, scales = build_precip_z()
    save_table(scales, "precip_window_scales")
    df = panel.merge(lag, on="date", how="left")

    rows = []
    for crop in CORE_CROPS:
        d = df[df["crop"] == crop].sort_values("date").reset_index(drop=True)
        for var, _vlab in VARS:
            ycol = f"{var}_anomaly_z_hist"
            for col, label in WINDOWS:
                for k in range(0, FOCUS_MAX + 1):
                    xcol = f"{col}__z_lag{k}"
                    sub = d[[ycol, xcol] + CONTROLS].dropna()
                    if len(sub) < MIN_OBS:
                        continue
                    X = sm.add_constant(sub[[xcol] + CONTROLS].astype(float))
                    res = sm.OLS(sub[ycol].astype(float), X).fit(
                        cov_type="HAC", cov_kwds={"maxlags": HAC_LAGS})
                    b = float(res.params[xcol]); se = float(res.bse[xcol])
                    rows.append({
                        "crop": crop, "response": var, "window": col, "window_label": label,
                        "lag_days": k,
                        "effect_z_per_1sd": b, "se_hac": se,
                        "ci_low": b - 1.96 * se, "ci_high": b + 1.96 * se,
                        "p_value": float(res.pvalues[xcol]), "n_obs": int(len(sub)),
                        "sd_mm": float(scales.loc[scales["hazard_key"] == col, "sd"].iloc[0]),
                    })
    grid = pd.DataFrame(rows)
    grid["fdr_p"] = bh_fdr(grid["p_value"].values)
    # 系列内（品种×响应×窗口 内部 15 个 lag）二级 FDR
    grid["fdr_p_within"] = grid.groupby(["crop", "response", "window"])["p_value"] \
                               .transform(lambda s: bh_fdr(s.values))
    save_table(grid, "precip_window_grid")

    # 汇总：每个 品种×响应×窗口 的 0-14 天峰值
    def peak(g: pd.DataFrame) -> pd.Series:
        i = g["effect_z_per_1sd"].abs().idxmax()
        r = g.loc[i]
        return pd.Series({
            "peak_lag": int(r["lag_days"]),
            "peak_effect": float(r["effect_z_per_1sd"]),
            "peak_ci_low": float(r["ci_low"]), "peak_ci_high": float(r["ci_high"]),
            "peak_p": float(r["p_value"]), "peak_fdr_p": float(r["fdr_p"]),
            "n_lag_fdr_sig": int((g["fdr_p"] < 0.05).sum()),
            "n_lag_fdr_sig_within": int((g["fdr_p_within"] < 0.05).sum()),
            "max_abs_effect": float(g["effect_z_per_1sd"].abs().max()),
            "n_obs_min": int(g["n_obs"].min()),
        })

    summ = (grid.groupby(["crop", "response", "window", "window_label"], as_index=False)
                .apply(lambda g: peak(g))
                .reset_index(drop=True))
    summ["sd_mm"] = summ["window"].map(dict(zip(scales["hazard_key"], scales["sd"])))
    save_table(summ, "precip_window_comparison")

    # 跨品种汇总（每个 响应×窗口）
    agg = []
    for (var, col, label), g in summ.groupby(["response", "window", "window_label"]):
        agg.append({
            "response": var, "window": col, "window_label": label, "n_crops": len(g),
            "mean_peak_effect": float(g["peak_effect"].mean()),
            "mean_max_abs_effect": float(g["max_abs_effect"].mean()),
            "median_peak_lag": float(g["peak_lag"].median()),
            "n_crops_fdr_sig": int((g["peak_fdr_p"] < 0.05).sum()),
            "min_fdr_p": float(g["peak_fdr_p"].min()),
            "n_lag_fdr_sig_total": int(g["n_lag_fdr_sig"].sum()),
            "sign_positive": int((g["peak_effect"] > 0).sum()),
        })
    agg = pd.DataFrame(agg)
    save_table(agg, "precip_window_summary")

    register_results([
        {
            "result_id": f"SUPP-WIN-{r['response']}-{r['window']}",
            "research_question": "R10",
            "crop": "全体10品种",
            "period": f"{CORE_START.date()}~{CORE_END.date()}",
            "method": "单 lag 分布滞后回归（HAC-14，周末/节假日控制，方法B 去季节化），5 个降水窗口全家族 BH-FDR",
            "metric": "0-14天峰值效应（异常稳健 z / 1 SD 降水）",
            "estimate": round(r["mean_peak_effect"], 4),
            "ci_low": np.nan, "ci_high": np.nan,
            "p_value": round(r["min_fdr_p"], 4),
            "robustness": f"FDR 显著品种 {r['n_crops_fdr_sig']}/10；显著 lag 数 {r['n_lag_fdr_sig_total']}",
            "figure": "F52_precip_window_comparison.png",
            "table": "precip_window_summary.csv",
            "evidence_level": "B",
            "notes": f"窗口={r['window_label']}；1 SD={r.get('sd_mm', np.nan)}",
        }
        for _, r in agg.iterrows()
    ])
    return summ, agg, scales


def draw_r10(summ: pd.DataFrame, agg: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
    order = [c for c, _ in WINDOWS]
    labels = [l for _, l in WINDOWS]
    x = np.arange(len(order))

    for ax, (var, title) in zip(axes, [("price", "价格异常"), ("volume", "成交量异常")]):
        sub = agg[agg["response"] == var].set_index("window").reindex(order)
        means = sub["mean_peak_effect"].values
        # 跨品种峰值的标准误（10 品种均值 ± 1.96·SE）
        se = np.array([
            summ[(summ["response"] == var) & (summ["window"] == w)]["peak_effect"].std(ddof=1)
            / np.sqrt(len(summ[(summ["response"] == var) & (summ["window"] == w)]))
            for w in order
        ])
        ax.bar(x, means, yerr=1.96 * se, capsize=4, color="#4C78A8",
               edgecolor="#2F4F6F", alpha=0.9)
        ax.axhline(0, color="#888", lw=1)
        ax.set_xticks(x); ax.set_xticklabels(labels)
        ax.set_xlabel("降水累积窗口")
        ax.set_ylabel("0–14 天峰值效应（异常 z / 1 SD）")
        ax.set_title(f"{title}：不同累积窗口的峰值响应\n"
                     f"（10 品种均值 ±95%CI；FDR 显著品种数均为 "
                     f"{int(sub['n_crops_fdr_sig'].max())}/10）")
        for i, (m, s) in enumerate(zip(means, se)):
            ax.text(i, m + (1.96 * s if m >= 0 else -1.96 * s) + (0.006 if m >= 0 else -0.006),
                    f"{m:+.3f}", ha="center", va="bottom" if m >= 0 else "top", fontsize=9)
    fig.suptitle("R10 累积降雨窗口比较：窗口越长，市场响应是否越强？（沈阳 2021-2026，Level B）",
                 fontsize=12)
    fig.tight_layout()
    out = Path("outputs/figures/F52_precip_window_comparison.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    LOG.info("图已输出：%s", out)


# --------------------------------------------------------------------------- #
def main() -> None:
    with StepTimer("18_research_supplement", LOG):
        p = load_parquet("panel_final")
        p = p[(p["date"] >= CORE_START) & (p["date"] <= CORE_END)
              & (p["crop"].isin(CORE_CROPS))].copy()

        vt = r02_volume_trend(p)
        print("\n=== R02 成交量年化趋势（%，HAC-14）===")
        print(vt.to_string(index=False))

        summ, agg, scales = r10_precip_windows(p)
        print("\n=== R10 降水窗口尺度（1 SD）===")
        print(scales.to_string(index=False))
        print("\n=== R10 跨品种汇总 ===")
        print(agg.to_string(index=False))
        draw_r10(summ, agg)


if __name__ == "__main__":
    main()
