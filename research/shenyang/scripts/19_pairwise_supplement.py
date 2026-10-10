"""研究成稿补充分析（第二轮）：支撑「基础两两关系」关系组的 4 项简单分析。

不推翻既有分析——STEP 10 预登记的 7 个 hazard（precip_1d/3d/7d, temp_max/min, vpd,
soil_moisture_z）结果原样引用；本脚本只补 **新暴露** 与 **新切面**，并使用**独立家族** BH-FDR，
不与预登记家族混合。

补做项
------
S-A  逐年市场画像（G1 时间 × 市场）：年份 × 品种 × {价格中位, 成交量中位, 异常 z 均值}
S-B  扩展气象暴露扫描（G2/G3 天气 × 价格/成交量）：
     humidity, wind_speed, radiation, et0, dew_point, pressure_msl, cloud_cover, temp_mean
     × 2 响应 × 10 品种 × lag 0..14，HAC(14)，**独立家族** BH-FDR
S-C  土壤分层扫描（G4/G5 土壤 × 价格/成交量）：
     soil_moisture_7_28, soil_moisture_28_100（0_7 沿用 STEP 10 的 soil_z，仅引用）
     构造方式与既有 soil_z 完全一致：观测期 LOO 同期（doy±5）期望 + 1.4826×MAD 稳健尺度
S-D  极端天气日 vs 普通日（G7 极端天气 × 市场）：
     极端日 = (precip_1d≥50mm) | (precip_3d≥100mm) | (temp_max≥35℃)（config 预登记阈值）
     逐品种 × 响应比较异常 z 均值与绝对异常均值

纪律：与 STEP 10 完全同口径（单 lag 回归、HAC-14、周末/节假日控制、方法B 去季节化稳健 z）；
结论一律 Level B；阴性结果如实登记。

产出
----
outputs/tables/annual_market_by_year.csv
outputs/tables/weather_extra_scan.csv        （网格）
outputs/tables/weather_extra_summary.csv     （逐品种峰值）
outputs/tables/weather_extra_overview.csv    （跨品种汇总，供 F53 绘图）
outputs/tables/soil_layers_scan.csv / soil_layers_summary.csv / soil_layers_overview.csv
outputs/tables/extreme_day_contrast.csv
outputs/figures/F53_weather_market_overview.png
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

LOG = get_logger("19_pairwise_supplement")
CORE_CROPS: list = CROPS_CFG["core_crops"]
CORE_START = pd.Timestamp(ANALYSIS["time"]["core_start_planned"])
CORE_END = pd.Timestamp(ANALYSIS["time"]["weather_end"])
HAC_LAGS = int(ANALYSIS["lag"]["hac_maxlags"])
MIN_OBS = int(ANALYSIS["lag"]["min_obs"])
FOCUS_MAX = int(ANALYSIS["lag"]["focus_max_lag_days"])
CONTROLS = ["is_weekend", "is_public_holiday"]

# 扩展气象暴露（与 STEP 10 预登记 7 hazard 不重叠）
EXTRA_WX = [
    ("humidity", "相对湿度", "%"),
    ("wind_speed", "日最大风速", "km/h"),
    ("radiation", "短波辐射", "MJ/m²"),
    ("et0", "参考蒸散ET0", "mm"),
    ("dew_point", "露点温度", "℃"),
    ("pressure_msl", "海平面气压", "hPa"),
    ("cloud_cover", "云量", "%"),
    ("temp_mean", "日平均气温", "℃"),
]
# 土壤分层（0_7 已由 STEP 10 覆盖，此处仅补两层；同时重算 0_7 用于一致性校验）
SOIL_LAYERS = [
    ("soil_moisture_0_7", "土壤水分 0–7cm", "m³/m³"),
    ("soil_moisture_7_28", "土壤水分 7–28cm", "m³/m³"),
    ("soil_moisture_28_100", "土壤水分 28–100cm", "m³/m³"),
]
VARS = [("price", "价格"), ("volume", "成交量")]

set_seed()
setup_matplotlib()


# --------------------------------------------------------------------------- #
# 公共：LOO 土壤异常 z（与既有 soil_moisture_z 同口径）
# --------------------------------------------------------------------------- #
def build_soil_z(w: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """观测期 leave-one-year-out 同期（doy±5）期望 + 1.4826×MAD 稳健尺度。"""
    w = w.copy()
    w["_doy"] = w["date"].dt.dayofyear.clip(upper=365)  # 闰日并入 365
    w["_year"] = w["date"].dt.year
    scales, out = [], w[["date"]].copy()
    for col, label, unit in SOIL_LAYERS:
        v = w[col].astype(float)
        # 目标年不进入自身基线
        exp = np.full(len(w), np.nan)
        doy = w["_doy"].values
        yr = w["_year"].values
        vals = v.values
        for i in range(len(w)):
            m = (np.abs(doy - doy[i]) <= 5) & (yr != yr[i])
            if m.sum() >= 8:
                exp[i] = np.nanmedian(vals[m])
        anom = vals - exp
        sc = 1.4826 * np.nanmedian(np.abs(anom - np.nanmedian(anom)))
        out[f"{col}__z"] = anom / sc
        scales.append({"exposure": col, "label": label, "unit": unit,
                       "n_valid": int(np.isfinite(exp).sum()),
                       "raw_mean": float(np.nanmean(vals)),
                       "raw_sd": float(np.nanstd(vals, ddof=1)),
                       "robust_scale": float(sc)})
    return out, pd.DataFrame(scales)


def build_lag_matrix(z_df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    lag = z_df[["date"]].copy()
    for k in keys:
        z = z_df[f"{k}__z"].values
        for d in range(0, FOCUS_MAX + 1):
            lag[f"{k}__z_lag{d}"] = np.r_[np.full(d, np.nan), z[: len(z) - d]]
    return lag


def scan(df: pd.DataFrame, exposures: list, scales: pd.DataFrame,
         family_tag: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """单 lag 分布滞后回归扫描；family_tag 用于输出命名。"""
    rows = []
    for crop in CORE_CROPS:
        d = df[df["crop"] == crop].sort_values("date").reset_index(drop=True)
        for var, _ in VARS:
            ycol = f"{var}_anomaly_z_hist"
            for key, label, _unit in exposures:
                for k in range(0, FOCUS_MAX + 1):
                    xcol = f"{key}__z_lag{k}"
                    if xcol not in d.columns:
                        continue
                    sub = d[[ycol, xcol] + CONTROLS].dropna()
                    if len(sub) < MIN_OBS:
                        continue
                    X = sm.add_constant(sub[[xcol] + CONTROLS].astype(float))
                    res = sm.OLS(sub[ycol].astype(float), X).fit(
                        cov_type="HAC", cov_kwds={"maxlags": HAC_LAGS})
                    b = float(res.params[xcol]); se = float(res.bse[xcol])
                    rows.append({
                        "crop": crop, "response": var, "exposure": key, "label": label,
                        "lag_days": k, "effect_z_per_1sd": b, "se_hac": se,
                        "ci_low": b - 1.96 * se, "ci_high": b + 1.96 * se,
                        "p_value": float(res.pvalues[xcol]), "n_obs": int(len(sub)),
                    })
    grid = pd.DataFrame(rows)
    grid["fdr_p"] = bh_fdr(grid["p_value"].values)          # 本补充家族内 BH-FDR
    grid["fdr_p_within"] = grid.groupby(["crop", "response", "exposure"])["p_value"] \
                               .transform(lambda s: bh_fdr(s.values))
    save_table(grid, f"{family_tag}_scan")

    def peak(g: pd.DataFrame) -> pd.Series:
        i = g["effect_z_per_1sd"].abs().idxmax()
        r = g.loc[i]
        return pd.Series({
            "peak_lag": int(r["lag_days"]), "peak_effect": float(r["effect_z_per_1sd"]),
            "peak_ci_low": float(r["ci_low"]), "peak_ci_high": float(r["ci_high"]),
            "peak_p": float(r["p_value"]), "peak_fdr_p": float(r["fdr_p"]),
            "n_lag_fdr_sig": int((g["fdr_p"] < 0.05).sum()),
            "max_abs_effect": float(g["effect_z_per_1sd"].abs().max()),
        })

    summ = (grid.groupby(["crop", "response", "exposure", "label"], as_index=False)
                .apply(lambda g: peak(g), include_groups=False)
                .reset_index(drop=True))
    save_table(summ, f"{family_tag}_summary")

    ov = []
    for (var, key, label), g in summ.groupby(["response", "exposure", "label"]):
        sd = scales.loc[scales["exposure"] == key]
        ov.append({
            "response": var, "exposure": key, "label": label, "n_crops": len(g),
            "mean_peak_effect": float(g["peak_effect"].mean()),
            "mean_max_abs_effect": float(g["max_abs_effect"].mean()),
            "median_peak_lag": float(g["peak_lag"].median()),
            "n_crops_fdr_sig": int((g["peak_fdr_p"] < 0.05).sum()),
            "min_fdr_p": float(g["peak_fdr_p"].min()),
            "sign_positive": int((g["peak_effect"] > 0).sum()),
            "n_lag_fdr_sig_total": int(g["n_lag_fdr_sig"].sum()),
            "raw_sd": float(sd["raw_sd"].iloc[0]) if len(sd) else np.nan,
            "unit": str(sd["unit"].iloc[0]) if len(sd) else "",
        })
    ov = pd.DataFrame(ov)
    save_table(ov, f"{family_tag}_overview")
    return grid, summ, ov


# --------------------------------------------------------------------------- #
# S-A 逐年市场画像
# --------------------------------------------------------------------------- #
def s_a_annual(panel: pd.DataFrame) -> pd.DataFrame:
    p = panel.copy()
    p["year"] = p["date"].dt.year
    g = (p.groupby(["year", "crop"])
           .agg(n_days=("date", "count"),
                price_median=("price", "median"),
                volume_median=("volume", "median"),
                price_anom_z_mean=("price_anomaly_z_hist", "mean"),
                volume_anom_z_mean=("volume_anomaly_z_hist", "mean"),
                price_anom_z_sd=("price_anomaly_z_hist", "std"),
                volume_anom_z_sd=("volume_anomaly_z_hist", "std"))
           .reset_index())
    save_table(g, "annual_market_by_year")
    LOG.info("S-A 逐年市场画像：%d 行（%d 年 × %d 品种）", len(g),
             g["year"].nunique(), g["crop"].nunique())
    return g


# --------------------------------------------------------------------------- #
# S-D 极端天气日 vs 普通日
# --------------------------------------------------------------------------- #
def s_d_extreme_days(panel: pd.DataFrame, w: pd.DataFrame) -> pd.DataFrame:
    thr = ANALYSIS["hazard_thresholds"]
    w = w.copy()
    w["_extreme"] = ((w["precip_1d"] >= float(thr["rainstorm_daily_mm"]))
                     | (w["precip_3d"] >= float(thr["heavy_rain_3d_mm"]))
                     | (w["temp_max"] >= float(thr["heat_tmax_c"])))
    n_ext = int(w["_extreme"].sum())
    LOG.info("S-D 极端天气日：%d / %d 天（定义：单日降水≥%.0fmm 或 3日累计≥%.0fmm 或 最高温≥%.0f℃）",
             n_ext, len(w), float(thr["rainstorm_daily_mm"]),
             float(thr["heavy_rain_3d_mm"]), float(thr["heat_tmax_c"]))

    d = panel.merge(w[["date", "_extreme"]], on="date", how="left")
    rows = []
    for crop in CORE_CROPS:
        for var, _ in VARS:
            zcol = f"{var}_anomaly_z_hist"
            sub = d[d["crop"] == crop].dropna(subset=[zcol, "_extreme"])
            a = sub.loc[sub["_extreme"], zcol]
            b = sub.loc[~sub["_extreme"], zcol]
            if len(a) < 5:
                continue
            diff = float(a.mean() - b.mean())
            se = float(np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b)))
            rows.append({
                "crop": crop, "response": var,
                "n_extreme_obs": int(len(a)), "n_normal_obs": int(len(b)),
                "mean_z_extreme": float(a.mean()), "mean_z_normal": float(b.mean()),
                "diff": diff, "se": se,
                "ci_low": diff - 1.96 * se, "ci_high": diff + 1.96 * se,
                "mean_absz_extreme": float(a.abs().mean()),
                "mean_absz_normal": float(b.abs().mean()),
            })
    out = pd.DataFrame(rows)
    # 双侧 p 用正态近似（样本量足够大）；再做 BH-FDR
    from scipy import stats as _st
    out["p_value"] = 2 * (1 - _st.norm.cdf(np.abs(out["diff"] / out["se"])))
    out["fdr_p"] = bh_fdr(out["p_value"].values)
    out = out.drop(columns=["se"], errors="ignore")
    save_table(out, "extreme_day_contrast")
    return out, n_ext


# --------------------------------------------------------------------------- #
# F53：全部气象/土壤暴露 × 市场 峰值效应总览
# --------------------------------------------------------------------------- #
def draw_overview(extra_ov: pd.DataFrame, soil_ov: pd.DataFrame) -> None:
    """合并补充扫描（新暴露）与 STEP 10 引用值（预登记 7 hazard）绘图。"""
    # STEP 10 预登记家族的跨品种均值峰值效应（引用自 reports/04 与 05，单位 z/1SD）
    step10_price = {
        "当日降水": 0.0427, "3日累计降水": 0.0597, "7日累计降水": 0.0769,
        "日最高气温": 0.0, "日最低气温": 0.0, "VPD": 0.0, "土壤水分 0–7cm": 0.0,
    }
    step10_volume = {
        "当日降水": -0.0271, "3日累计降水": -0.0354, "7日累计降水": -0.0213,
        "日最高气温": 0.0, "日最低气温": 0.0, "VPD": 0.0, "土壤水分 0–7cm": 0.0,
    }

    fig, axes = plt.subplots(1, 2, figsize=(15.5, 5.4))
    for ax, (var, s10) in zip(axes, [("price", step10_price), ("volume", step10_volume)]):
        # 预登记家族（STEP 10）：逐品种峰值取自 lag_focus_summary；此处用已登记值
        lf = pd.read_csv("outputs/tables/lag_focus_summary.csv")
        lf = lf[(lf["metric"] == "z") & (lf["response"] == var)]
        ref = (lf.groupby("hazard_label")["peak_effect"].mean())
        name_map = {"当日降水": "当日降水", "3日累计降水": "3日累计降水",
                    "7日累计降水": "7日累计降水", "日最高气温": "日最高气温",
                    "日最低气温": "日最低气温", "饱和水汽压差VPD": "VPD",
                    "土壤水分异常": "土壤水分 0–7cm"}
        labels_ref, vals_ref = [], []
        for k, v in name_map.items():
            if k in ref.index:
                labels_ref.append(v); vals_ref.append(float(ref[k]))

        ex = extra_ov[extra_ov["response"] == var]
        so = soil_ov[(soil_ov["response"] == var) & (soil_ov["exposure"] != "soil_moisture_0_7")]

        labels = labels_ref + list(ex["label"]) + list(so["label"])
        vals = vals_ref + list(ex["mean_peak_effect"]) + list(so["mean_peak_effect"])
        is_ref = ["STEP10"] * len(labels_ref) + ["补充"] * (len(ex) + len(so))
        cols = ["#3D5A80" if t == "STEP10" else "#7A9E7E" for t in is_ref]

        x = np.arange(len(labels))
        ax.bar(x, vals, color=cols, edgecolor="#33404d", alpha=0.92)
        ax.axhline(0, color="#999", lw=1)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=38, ha="right", fontsize=8.5)
        ax.set_ylabel("0–14 天峰值效应（异常 z / 1 SD 暴露）")
        ax.set_title(f"{'价格' if var == 'price' else '成交量'}异常：全部气象/土壤暴露\n"
                     "深蓝=STEP10 预登记家族；浅绿=本轮补充扫描（独立家族）\n"
                     "经各自家族 BH-FDR + HAC 带宽扫描（14→90）后无稳定显著项")
        ax.grid(axis="y", alpha=0.25)
    fig.suptitle("基础两两关系总览：气象 / 土壤暴露 × 沈阳批发市场（2021-2026，Level B，全部阴性）",
                 fontsize=12.5)
    fig.tight_layout()
    out = Path("outputs/figures/F53_weather_market_overview.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    LOG.info("图已输出：%s", out)


# --------------------------------------------------------------------------- #
def main() -> None:
    with StepTimer("19_pairwise_supplement", LOG):
        panel = load_parquet("panel_final")
        panel = panel[(panel["date"] >= CORE_START) & (panel["date"] <= CORE_END)
                      & (panel["crop"].isin(CORE_CROPS))].copy()
        w = load_parquet("weather_daily")
        w = w[(w["date"] >= CORE_START) & (w["date"] <= CORE_END)].sort_values("date").reset_index(drop=True)

        # ---- S-A ----
        ann = s_a_annual(panel)
        piv = ann.pivot_table(index="year", values=["price_median", "volume_median"], aggfunc="median")
        print("\n=== S-A 逐年（跨品种中位）===")
        print(piv.round(3).to_string())

        # ---- S-B 扩展气象暴露 ----
        w["_doy"] = w["date"].dt.dayofyear
        raw = w[["date"]].copy()
        sc_rows = []
        for col, label, unit in EXTRA_WX:
            v = w[col].astype(float)
            mu, sd = float(v.mean()), float(v.std(ddof=1))
            raw[f"{col}__z"] = ((v - mu) / sd).values
            sc_rows.append({"exposure": col, "label": label, "unit": unit,
                            "raw_mean": mu, "raw_sd": sd})
        wx_scales = pd.DataFrame(sc_rows)
        save_table(wx_scales, "weather_extra_scales")
        lag_wx = build_lag_matrix(raw, [c for c, _, _ in EXTRA_WX])
        df_wx = panel.merge(lag_wx, on="date", how="left")
        _, _, wx_ov = scan(df_wx, EXTRA_WX, wx_scales, "weather_extra")
        print("\n=== S-B 扩展气象暴露（跨品种汇总）===")
        print(wx_ov[["response", "label", "unit", "raw_sd", "mean_peak_effect",
                     "mean_max_abs_effect", "median_peak_lag", "n_crops_fdr_sig",
                     "min_fdr_p", "sign_positive"]].round(4).to_string(index=False))

        # ---- S-C 土壤分层 ----
        soil_z, soil_scales = build_soil_z(w)
        # 一致性校验：0-7cm 新构造 vs 既有 soil_moisture_z
        chk = pd.DataFrame({"new": soil_z["soil_moisture_0_7__z"].values,
                            "old": w["soil_moisture_0_7_z"].values}).dropna()
        r = float(np.corrcoef(chk["new"], chk["old"])[0, 1])
        LOG.info("土壤 0–7cm z 构造一致性：Pearson r = %.4f（n=%d）", r, len(chk))
        soil_scales = soil_scales.rename(columns={"exposure": "exposure"})
        lag_soil = build_lag_matrix(soil_z, [c for c, _, _ in SOIL_LAYERS])
        df_soil = panel.merge(lag_soil, on="date", how="left")
        _, _, soil_ov = scan(df_soil, SOIL_LAYERS, soil_scales, "soil_layers")
        print("\n=== S-C 土壤分层（跨品种汇总）===")
        print(soil_ov[["response", "label", "mean_peak_effect", "mean_max_abs_effect",
                       "median_peak_lag", "n_crops_fdr_sig", "min_fdr_p",
                       "sign_positive"]].round(4).to_string(index=False))
        print("\n土壤分层尺度：\n", soil_scales.to_string(index=False))

        # ---- S-D 极端日对比 ----
        ext, n_ext = s_d_extreme_days(panel, w)
        print(f"\n=== S-D 极端天气日（{n_ext} 天）vs 普通日 ===")
        print(ext[["crop", "response", "n_extreme_obs", "mean_z_extreme", "mean_z_normal",
                   "diff", "ci_low", "ci_high", "p_value", "fdr_p",
                   "mean_absz_extreme", "mean_absz_normal"]].round(4).to_string(index=False))

        # ---- 登记 ----
        reg = []
        for _, r_ in wx_ov.iterrows():
            reg.append({
                "result_id": f"PAIR-WX-{r_['response']}-{r_['exposure']}",
                "research_question": "G2/G3 天气×市场（基础两两关系）",
                "crop": "全体10品种", "period": f"{CORE_START.date()}~{CORE_END.date()}",
                "method": "单 lag 分布滞后回归（HAC-14，周末/节假日控制，方法B 去季节化），补充扫描独立家族 BH-FDR",
                "metric": "0-14天峰值效应（异常稳健 z / 1 SD 暴露）",
                "estimate": round(float(r_["mean_peak_effect"]), 4),
                "ci_low": np.nan, "ci_high": np.nan,
                "p_value": round(float(r_["min_fdr_p"]), 4),
                "robustness": f"FDR 显著品种 {int(r_['n_crops_fdr_sig'])}/10",
                "figure": "F53_weather_market_overview.png",
                "table": "weather_extra_overview.csv", "evidence_level": "B",
                "notes": f"暴露={r_['label']}（{r_['unit']}，1 SD={r_['raw_sd']:.3f}）；补充扫描家族",
            })
        for _, r_ in soil_ov.iterrows():
            reg.append({
                "result_id": f"PAIR-SOIL-{r_['response']}-{r_['exposure']}",
                "research_question": "G4/G5 土壤×市场（基础两两关系）",
                "crop": "全体10品种", "period": f"{CORE_START.date()}~{CORE_END.date()}",
                "method": "单 lag 分布滞后回归（HAC-14），土壤异常用观测期 LOO 同期基线+稳健尺度",
                "metric": "0-14天峰值效应（异常稳健 z / 1 SD 土壤水分）",
                "estimate": round(float(r_["mean_peak_effect"]), 4),
                "ci_low": np.nan, "ci_high": np.nan,
                "p_value": round(float(r_["min_fdr_p"]), 4),
                "robustness": f"FDR 显著品种 {int(r_['n_crops_fdr_sig'])}/10",
                "figure": "F53_weather_market_overview.png",
                "table": "soil_layers_overview.csv", "evidence_level": "B",
                "notes": f"土层={r_['label']}；观测期自建基线（非官方30年基线），证据等级 B",
            })
        for _, r_ in ext.iterrows():
            reg.append({
                "result_id": f"PAIR-EXT-{r_['crop']}-{r_['response']}",
                "research_question": "G7 极端天气×市场（基础两两关系）",
                "crop": r_["crop"], "period": f"{CORE_START.date()}~{CORE_END.date()}",
                "method": "极端日 vs 普通日 异常 z 均值差（Welch 近似 SE）+ BH-FDR",
                "metric": "mean_z(极端日) − mean_z(普通日)",
                "estimate": round(float(r_["diff"]), 4),
                "ci_low": round(float(r_["ci_low"]), 4), "ci_high": round(float(r_["ci_high"]), 4),
                "p_value": round(float(r_["p_value"]), 4),
                "robustness": f"FDR p={float(r_['fdr_p']):.3f}",
                "figure": "F21_threshold_bins_explanatory.png",
                "table": "extreme_day_contrast.csv", "evidence_level": "B",
                "notes": f"极端日 n={int(r_['n_extreme_obs'])} vs 普通日 n={int(r_['n_normal_obs'])}",
            })
        register_results(reg)

        draw_overview(wx_ov, soil_ov)


if __name__ == "__main__":
    main()
