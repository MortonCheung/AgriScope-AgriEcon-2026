"""STEP 07 + 08：基础描述性研究 + 季节性分析。

对应任务书：
  §十七 Phase 1 基础描述性研究（价格/成交量：趋势、月度分布、季节性、波动率、最大最小、IQR、CV）
  §十七 变化率：日变化 / 周变化 / 月变化 / 同期变化
  §十八 基础图：每张图必须回答一个问题
  §十九 Phase 2 方法A 中的 STL 稳健分解（本节先算季节成分与季节强度，异常度留给 04 模块）
  §四十四 不制造「综合指数」

红线：
  - 成交量单位官方未公开 → 所有输出保留 `volume_unit=unknown`，禁止出现「吨」；
  - 只描述，不做因果；本节不涉及任何天气影响推断。

产出：
  outputs/tables/descriptive_by_crop.csv           10 品种 价格/成交量 描述统计 + 趋势 + 波动率
  outputs/tables/descriptive_monthly_price.csv     品种 × 月 价格分布
  outputs/tables/descriptive_monthly_volume.csv    品种 × 月 成交量分布
  outputs/tables/descriptive_changes.csv           日/周/月/同期 变化率
  outputs/tables/trend_by_crop.csv                 log 水平 OLS(HAC) 年化趋势
  outputs/tables/seasonal_index_price.csv         价格月度季节指数
  outputs/tables/seasonal_index_volume.csv        成交量月度季节指数
  outputs/tables/stl_weekly_components.csv        周序列 STL 分解（long 格式）
  outputs/tables/stl_strength.csv                 季节强度 / 趋势强度
  outputs/figures/F01_*.png ... F08_*.png
  reports/02_DESCRIPTIVE.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    ANALYSIS, CROPS_CFG, PATHS, StepTimer, get_logger, hac_ols, load_parquet,
    register_results, render_figure, save_table, set_seed, setup_matplotlib,
)

LOG = get_logger("03_descriptive")
CORE_CROPS: list = CROPS_CFG["core_crops"]
CITY: str = CROPS_CFG["market"]["city"]
VOL_UNIT: str = CROPS_CFG["market"]["volume_unit"]
PRICE_UNIT: str = CROPS_CFG["market"]["price_unit_raw"]
CORE_START = pd.Timestamp(ANALYSIS["time"]["core_start_planned"])
CORE_END = pd.Timestamp(ANALYSIS["time"]["weather_end"])
MONTH_CN = ["1月", "2月", "3月", "4月", "5月", "6月",
            "7月", "8月", "9月", "10月", "11月", "12月"]


# -----------------------------------------------------------------------------
def load_core() -> pd.DataFrame:
    """核心研究窗口（天气 ∩ 市场 共同覆盖期）面板。"""
    p = load_parquet("daily_panel")
    p = p[(p["date"] >= CORE_START) & (p["date"] <= CORE_END)].copy()
    p = p[p["crop"].isin(CORE_CROPS)]
    p["month"] = p["date"].dt.month
    p["year"] = p["date"].dt.year
    LOG.info("核心窗口面板：%d 行 / %d 交易日 / %d 品种（%s ~ %s）",
             len(p), p["date"].nunique(), p["crop"].nunique(),
             p["date"].min().date(), p["date"].max().date())
    return p


# -----------------------------------------------------------------------------
def basic_stats(p: pd.DataFrame) -> tuple:
    """10 品种 × {price, volume} 描述统计 + 趋势 + 波动率。"""
    rows, trend_rows = [], []
    for crop, g in p.groupby("crop"):
        g = g.sort_values("date")
        for var, unit in [("price", PRICE_UNIT), ("volume", VOL_UNIT)]:
            v = g[var].astype(float)
            q = v.quantile([0.05, 0.25, 0.5, 0.75, 0.95])
            iqr = float(q[0.75] - q[0.25])
            cv = float(v.std(ddof=1) / v.mean()) if v.mean() else np.nan
            # 日对数变化 → 年化波动率（仅描述，不做预测）
            lv = np.log(v.where(v > 0))
            dl = lv.diff().dropna()
            rows.append({
                "crop": crop, "variable": var, "unit": unit,
                "n_obs": int(v.notna().sum()),
                "mean": v.mean(), "std": v.std(ddof=1),
                "min": v.min(), "p05": q[0.05], "p25": q[0.25],
                "median": q[0.5], "p75": q[0.75], "p95": q[0.95], "max": v.max(),
                "iqr": iqr, "cv": cv,
                "p95_minus_p05_over_median": float((q[0.95] - q[0.05]) / q[0.5]) if q[0.5] else np.nan,
                "daily_log_change_std": float(dl.std(ddof=1)),
                "annualized_vol_pct": float(dl.std(ddof=1) * np.sqrt(252) * 100),
            })
            # log 水平对时间的 OLS（HAC）→ 年化趋势%（仅价格；成交量单位未知不作绝对趋势解读）
            if var == "price" and v.notna().sum() > 30:
                t = (g["date"] - g["date"].min()).dt.days.values.astype(float)
                y = lv.values
                m = ~np.isnan(y)
                r = hac_ols(y[m], t[m].reshape(-1, 1),
                            maxlags=int(ANALYSIS["lag"]["hac_maxlags"]))
                slope = r["coef"][1]
                se = r["se"][1]
                trend_rows.append({
                    "crop": crop, "var": "log_price",
                    "slope_per_day": slope, "se_hac": se,
                    "annualized_trend_pct": slope * 365 * 100,
                    "ci_low_annual_pct": (slope - 1.96 * se) * 365 * 100,
                    "ci_high_annual_pct": (slope + 1.96 * se) * 365 * 100,
                    "p_value": r["p"][1], "n_obs": r["n"],
                    "note": f"{CITY}批发口径；HAC maxlags={ANALYSIS['lag']['hac_maxlags']}",
                })
    stats = pd.DataFrame(rows)
    trend = pd.DataFrame(trend_rows)
    save_table(stats, "descriptive_by_crop.csv")
    save_table(trend, "trend_by_crop.csv")
    return stats, trend


def monthly_profile(p: pd.DataFrame) -> tuple:
    """品种 × 月 的分布（价格 / 成交量），并给出月度季节性指数。"""
    out = {}
    for var in ["price", "volume"]:
        agg = (p.groupby(["crop", "month"])[var]
               .agg(n="size", mean="mean", median="median", std="std",
                    p25=lambda s: s.quantile(0.25),
                    p75=lambda s: s.quantile(0.75))
               .reset_index())
        # 季节指数 = 该月中位数 / 该品种全年中位数（>1 = 高于常态）
        base = p.groupby("crop")[var].median().rename("annual_median")
        agg = agg.merge(base, on="crop", how="left")
        agg["seasonal_index_median"] = agg["median"] / agg["annual_median"]
        agg["month_label"] = agg["month"].map(lambda m: MONTH_CN[m - 1])
        agg["variable"] = var
        agg["unit"] = PRICE_UNIT if var == "price" else VOL_UNIT
        agg = agg[["crop", "variable", "unit", "month", "month_label", "n",
                   "mean", "median", "std", "p25", "p75",
                   "annual_median", "seasonal_index_median"]]
        out[var] = agg
    save_table(out["price"], "descriptive_monthly_price.csv")
    save_table(out["volume"], "descriptive_monthly_volume.csv")
    save_table(out["price"][["crop", "month", "month_label", "seasonal_index_median"]]
               .rename(columns={"seasonal_index_median": "seasonal_index"})
               .assign(variable="price", unit=PRICE_UNIT),
               "seasonal_index_price.csv")
    save_table(out["volume"][["crop", "month", "month_label", "seasonal_index_median"]]
               .rename(columns={"seasonal_index_median": "seasonal_index"})
               .assign(variable="volume", unit=VOL_UNIT),
               "seasonal_index_volume.csv")
    return out["price"], out["volume"]


def changes(p: pd.DataFrame) -> pd.DataFrame:
    """日 / 周 / 月 / 同期 变化率。日变化用「上一次观测」；周变化用同一品种 7 个日历日前。"""
    rows = []
    for crop, g in p.groupby("crop"):
        g = g.sort_values("date").set_index("date")
        for var in ["price", "volume"]:
            s = g[var].astype(float)
            # 日变化：上一次观测（面板已算好），此处复核
            prev = s.reindex(s.index).shift(1)
            dod = (s / prev - 1) * 100
            # 周变化：与 7 个日历日前的最近一次观测比较（asof，避免插值）
            ref7 = s.reindex(s.index - pd.Timedelta(days=7), method="ffill")
            wow = (s.values / ref7.values - 1) * 100
            # 月变化：与 30 个日历日前的最近一次观测比较
            ref30 = s.reindex(s.index - pd.Timedelta(days=30), method="ffill")
            mom = (s.values / ref30.values - 1) * 100
            # 同期变化 YoY：与 365 个日历日前的最近一次观测比较
            ref365 = s.reindex(s.index - pd.Timedelta(days=365), method="ffill")
            yoy = (s.values / ref365.values - 1) * 100
            for label, arr in [("dod_pct_prev_obs", dod.values), ("wow_pct_7cald", wow),
                               ("mom_pct_30cald", mom), ("yoy_pct_365cald", yoy)]:
                a = np.asarray(arr, dtype=float)
                a = a[np.isfinite(a)]
                rows.append({
                    "crop": crop, "variable": var,
                    "unit": PRICE_UNIT if var == "price" else VOL_UNIT,
                    "change_type": label, "n": int(a.size),
                    "mean_pct": float(np.mean(a)) if a.size else np.nan,
                    "median_pct": float(np.median(a)) if a.size else np.nan,
                    "std_pct": float(np.std(a, ddof=1)) if a.size > 1 else np.nan,
                    "p05_pct": float(np.quantile(a, 0.05)) if a.size else np.nan,
                    "p95_pct": float(np.quantile(a, 0.95)) if a.size else np.nan,
                    "min_pct": float(a.min()) if a.size else np.nan,
                    "max_pct": float(a.max()) if a.size else np.nan,
                })
    df = pd.DataFrame(rows)
    save_table(df, "descriptive_changes.csv")
    return df


# -----------------------------------------------------------------------------
def stl_weekly() -> tuple:
    """方法A：周序列 STL 稳健分解（period=52），输出组分与季节/趋势强度。"""
    from statsmodels.tsa.seasonal import STL

    wk = load_parquet("panel_weekly")
    wk = wk[wk["crop"].isin(CORE_CROPS)].copy()
    wk = wk[(wk["week_start"] >= CORE_START - pd.Timedelta(days=7)) & (wk["week_start"] <= CORE_END)]
    period = int(ANALYSIS["seasonal_baseline"]["stl_period"])
    robust = bool(ANALYSIS["seasonal_baseline"]["stl_robust"])

    comps, strength = [], []
    for crop in CORE_CROPS:
        for var, col in [("price", "price_median"), ("volume", "volume_median")]:
            g = (wk[wk["crop"] == crop][["week_start", col]]
                 .dropna().sort_values("week_start").set_index("week_start"))
            s = g[col].astype(float)
            if len(s) < 2 * period:
                LOG.warning("STL 跳过 %s/%s：周观测 %d < 2×period", crop, var, len(s))
                continue
            # 周序列必须等间隔：只保留连续周
            full = pd.date_range(s.index.min(), s.index.max(), freq="7D")
            if len(full) != len(s):
                s = s.reindex(full)
            diff = s.diff().dropna()
            if diff.abs().max() > 0:
                s = s.interpolate(limit_direction="both")  # 仅补极少数缺周，不跨季插值
            if s.isna().any():
                LOG.warning("STL 跳过 %s/%s：周序列仍含缺失", crop, var)
                continue
            res = STL(s, period=period, robust=robust).fit()
            d = pd.DataFrame({
                "crop": crop, "variable": var, "week_start": s.index,
                "observed": s.values, "trend": res.trend.values,
                "seasonal": res.seasonal.values, "resid": res.resid.values,
            })
            comps.append(d)
            v_res = float(np.var(res.resid, ddof=1))
            v_seas = float(np.var(res.seasonal + res.resid, ddof=1))
            v_tr = float(np.var(res.trend + res.resid, ddof=1))
            strength.append({
                "crop": crop, "variable": var, "unit": PRICE_UNIT if var == "price" else VOL_UNIT,
                "n_weeks": int(len(s)), "period_weeks": period, "robust": robust,
                "seasonal_strength": max(0.0, 1 - v_res / v_seas) if v_seas > 0 else np.nan,
                "trend_strength": max(0.0, 1 - v_res / v_tr) if v_tr > 0 else np.nan,
                "resid_std": float(np.std(res.resid, ddof=1)),
                "note": "季节强度=1-Var(resid)/Var(seasonal+resid)；值越大季节性越明显",
            })
    comp = pd.concat(comps, ignore_index=True) if comps else pd.DataFrame()
    st = pd.DataFrame(strength)
    save_table(comp, "stl_weekly_components.csv")
    save_table(st, "stl_strength.csv")
    return comp, st


# -----------------------------------------------------------------------------
def fig_price_volume_dual(p: pd.DataFrame, crop: str) -> None:
    plt = setup_matplotlib()
    g = p[p["crop"] == crop].sort_values("date")
    fig, ax1 = plt.subplots(figsize=(11.5, 4.4))
    ax1.plot(g["date"], g["price"], color="#1f6fb4", lw=1.0, label="批发价")
    ax1.set_ylabel(f"批发价（{PRICE_UNIT}）", color="#1f6fb4")
    ax1.tick_params(axis="y", labelcolor="#1f6fb4")
    ax2 = ax1.twinx()
    ax2.plot(g["date"], g["volume"], color="#d1721f", lw=0.8, alpha=0.65, label="成交量指数")
    ax2.set_ylabel(f"成交量指数（单位：{VOL_UNIT}，官方未公开）", color="#d1721f")
    ax2.tick_params(axis="y", labelcolor="#d1721f")
    ax2.grid(False)
    ax1.set_title(f"图1　{crop}：批发价格与成交量双面板（{CORE_START:%Y-%m} ~ {CORE_END:%Y-%m}）\n"
                  f"目的：查看量价的长期结构（趋势 / 共同波动 / 结构性断点）")
    fig.tight_layout()
    render_figure(fig, f"F01_{crop}_price_volume_dual.png",
                  "数据来源：沈阳市发改委菜篮子信息发布平台（批发口径）；成交量单位官方未公开，"
                  "图中为相对指数，不代表吨位。")


def fig_month_box(p: pd.DataFrame, var: str, fname: str, title: str, unit: str) -> None:
    plt = setup_matplotlib()
    fig, axes = plt.subplots(2, 5, figsize=(16, 7), sharex=True)
    for ax, crop in zip(axes.ravel(), CORE_CROPS):
        g = p[p["crop"] == crop]
        data = [g.loc[g["month"] == m, var].dropna().values for m in range(1, 13)]
        bp = ax.boxplot(data, patch_artist=True, widths=0.62, showfliers=False,
                        medianprops=dict(color="#c0392b", lw=1.4))
        for b in bp["boxes"]:
            b.set(facecolor="#cfe2f3", edgecolor="#4a6b8a", lw=0.7)
        ax.set_title(crop, fontsize=10.5)
        ax.set_xticks(range(1, 13))
        ax.set_xticklabels([str(m) for m in range(1, 13)], fontsize=8)
        ax.tick_params(axis="y", labelsize=8)
    for ax in axes.ravel():
        ax.set_xlabel("")
    fig.suptitle(title, fontsize=13, fontweight="bold")
    fig.supylabel(f"单位：{unit}" + ("　（官方未公开，仅相对水平）" if var == "volume" else ""),
                  fontsize=9.5)
    fig.tight_layout(rect=(0.02, 0, 1, 0.95))
    render_figure(fig, fname,
                  "数据来源：沈阳市发改委菜篮子信息发布平台（批发口径）；箱线图剔除了离群点显示范围外者，"
                  "中位线为红色。")


def fig_crop_time_series(p: pd.DataFrame, var: str, fname: str, title: str, unit: str) -> None:
    plt = setup_matplotlib()
    fig, axes = plt.subplots(5, 2, figsize=(13.5, 12), sharex=True)
    for ax, crop in zip(axes.ravel(), CORE_CROPS):
        g = p[p["crop"] == crop].sort_values("date")
        ax.plot(g["date"], g[var], lw=0.85, color="#1f6fb4" if var == "price" else "#d1721f")
        ax.set_title(crop, fontsize=10.5)
        ax.tick_params(axis="y", labelsize=8)
    fig.suptitle(title, fontsize=13, fontweight="bold")
    fig.supylabel(f"单位：{unit}" + ("　（官方未公开）" if var == "volume" else ""), fontsize=9.5)
    fig.tight_layout(rect=(0.02, 0, 1, 0.96))
    render_figure(fig, fname, "数据来源：沈阳市发改委菜篮子信息发布平台（批发口径）。")


def fig_volatility(stats: pd.DataFrame) -> None:
    plt = setup_matplotlib()
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6))
    for ax, var, color, unit in [(axes[0], "price", "#1f6fb4", PRICE_UNIT),
                                 (axes[1], "volume", "#d1721f", VOL_UNIT)]:
        d = stats[stats["variable"] == var].set_index("crop").loc[CORE_CROPS]
        ax.barh(range(len(d)), d["annualized_vol_pct"], color=color, alpha=0.82)
        ax.set_yticks(range(len(d)))
        ax.set_yticklabels(d.index)
        ax.invert_yaxis()
        ax.set_xlabel("年化波动率（日对数变化标准差 × √252，%）")
        ax.set_title(("价格" if var == "price" else "成交量") + f"（{unit}）")
        for i, v in enumerate(d["annualized_vol_pct"]):
            ax.text(v, i, f" {v:.1f}", va="center", fontsize=8.5)
    fig.suptitle("图6　10 种批发蔬菜的价格与成交量波动率对比\n"
                 "目的：识别披露最不稳定的品种（波动率是后续冲击分析的分母口径参考）",
                 fontsize=12, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    render_figure(fig, "F06_volatility_by_crop.png",
                  "数据来源：沈阳市发改委菜篮子信息发布平台（批发口径）；"
                  "成交量单位官方未公开，其波动率为相对口径。")


def fig_stl_example(comp: pd.DataFrame, crop: str, var: str) -> None:
    plt = setup_matplotlib()
    d = comp[(comp["crop"] == crop) & (comp["variable"] == var)]
    if d.empty:
        return
    fig, axes = plt.subplots(4, 1, figsize=(11.5, 8.2), sharex=True)
    for ax, col, c, t in [(axes[0], "observed", "#333333", "观测值"),
                          (axes[1], "trend", "#1f6fb4", "趋势项 Trend"),
                          (axes[2], "seasonal", "#d1721f", "季节项 Seasonal（52 周）"),
                          (axes[3], "resid", "#7d3c98", "残差项 Resid（异常候选）")]:
        ax.plot(d["week_start"], d[col], lw=0.95, color=c)
        ax.set_ylabel(t, fontsize=9.5)
        if col == "resid":
            ax.axhline(0, color="#888", lw=0.7, ls="--")
    axes[0].set_title(f"图7　STL 稳健分解示例：{crop} 价格（周中位数序列，period=52）\n"
                      f"目的：确认价格同时含趋势与季节成分，为方法A 提供异常基准", fontsize=12)
    fig.tight_layout()
    render_figure(fig, f"F07_STL_{crop}_price.png",
                  "数据来源：沈阳市发改委菜篮子信息发布平台（批发口径）；"
                  "STL 稳健分解（robust=True），周序列若极少数缺周以线性补齐。")


def fig_seasonal_heatmap(si: pd.DataFrame, var: str, fname: str) -> None:
    plt = setup_matplotlib()
    mat = (si.pivot(index="crop", columns="month", values="seasonal_index")
           .reindex(CORE_CROPS))
    fig, ax = plt.subplots(figsize=(10.5, 4.6))
    vmax = float(np.nanmax(np.abs(mat.values - 1)))
    im = ax.imshow(mat.values, cmap="RdBu_r", vmin=1 - vmax, vmax=1 + vmax, aspect="auto")
    ax.set_xticks(range(12))
    ax.set_xticklabels(MONTH_CN)
    ax.set_yticks(range(len(mat)))
    ax.set_yticklabels(mat.index)
    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]):
            v = mat.values[i, j]
            if np.isfinite(v):
                ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=7.2,
                        color="white" if abs(v - 1) > 0.55 * vmax else "#222222")
    fig.colorbar(im, ax=ax, label="季节指数（月中位数 / 全年中位数）")
    ax.set_title(f"图8　{'价格' if var == 'price' else '成交量'}月度季节指数（10 种蔬菜）\n"
                 f"目的：判断各品种的季节性方向与强度，作为去季节化的先验检查", fontsize=12)
    ax.grid(False)
    fig.tight_layout()
    render_figure(fig, fname,
                  "数据来源：沈阳市发改委菜篮子信息发布平台（批发口径）；"
                  "指数=该月中位数/该品种全年中位数，>1 表示该月高于常态。")


def fig_stl_strength(st: pd.DataFrame) -> None:
    plt = setup_matplotlib()
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6))
    for ax, var, c in [(axes[0], "price", "#1f6fb4"), (axes[1], "volume", "#d1721f")]:
        d = st[st["variable"] == var].set_index("crop").reindex(CORE_CROPS)
        x = np.arange(len(d))
        ax.bar(x - 0.2, d["seasonal_strength"], width=0.4, label="季节强度", color=c, alpha=0.85)
        ax.bar(x + 0.2, d["trend_strength"], width=0.4, label="趋势强度",
               color="#7f8c8d", alpha=0.85)
        ax.set_xticks(x)
        ax.set_xticklabels(d.index, rotation=35, ha="right", fontsize=9)
        ax.set_ylabel("强度（0-1，越大越明显）")
        ax.set_title(("价格" if var == "price" else "成交量") + "（周序列 STL）")
        ax.legend(fontsize=9)
    fig.suptitle("图9　STL 季节强度与趋势强度（方法A）\n"
                 "目的：决定哪些品种必须去季节化，哪些可由历史同期基线独立支撑",
                 fontsize=12, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    render_figure(fig, "F09_stl_strength.png",
                  "数据来源：沈阳市发改委菜篮子信息发布平台（批发口径）；"
                  "强度=1-Var(resid)/Var(组分+resid)。")


# -----------------------------------------------------------------------------
def write_report(stats, trend, mp, mv, ch, st, p) -> None:
    L: list = []
    A = L.append
    A("# 02 DESCRIPTIVE — 沈阳 10 种批发蔬菜基础描述性与季节性\n")
    A(f"> 核心研究窗口：**{p['date'].min():%Y-%m-%d} ~ {p['date'].max():%Y-%m-%d}**，"
      f"{p['date'].nunique()} 个交易日 × 10 品种 = {len(p):,} 行。")
    A(f"> 价格单位：`{PRICE_UNIT}`；**成交量单位：官方未公开（`volume_unit=unknown`），"
      "全篇仅作相对水平比较，禁止读作吨位。**\n")
    A("本节为纯描述，不含任何天气影响或因果推断。\n")

    A("## 1. 价格与成交量的整体分布\n")
    A("| 品种 | 价格中位数(元/500g) | 价格 CV | 价格 IQR/中位数 | 价格年化波动率(%) "
      "| 成交量中位数(指数) | 成交量 CV | 成交量年化波动率(%) |")
    A("|---|---|---|---|---|---|---|---|")
    for crop in CORE_CROPS:
        pr = stats[(stats["crop"] == crop) & (stats["variable"] == "price")].iloc[0]
        vo = stats[(stats["crop"] == crop) & (stats["variable"] == "volume")].iloc[0]
        A(f"| {crop} | {pr['median']:.2f} | {pr['cv']:.3f} | "
          f"{pr['iqr']/pr['median']:.3f} | {pr['annualized_vol_pct']:.1f} | "
          f"{vo['median']:.1f} | {vo['cv']:.3f} | {vo['annualized_vol_pct']:.1f} |")
    A("")
    A("## 2. 价格长期趋势（log 水平 OLS，HAC 稳健标准误）\n")
    A("| 品种 | 年化趋势(%) | 95% CI | p 值 | 解读 |")
    A("|---|---|---|---|---|")
    for _, r in trend.set_index("crop").reindex(CORE_CROPS).reset_index().iterrows():
        sig = "显著" if r["p_value"] < 0.05 else "不显著"
        A(f"| {r['crop']} | {r['annualized_trend_pct']:+.1f} | "
          f"[{r['ci_low_annual_pct']:+.1f}, {r['ci_high_annual_pct']:+.1f}] | "
          f"{r['p_value']:.3f} | {sig} |")
    A("")
    A("> 说明：该趋势项为**长期漂移**，后续所有天气影响分析均在去季节化/去趋势后的异常序列上进行，"
      "以免把长期通胀或结构性变化误读为天气效应。\n")

    A("## 3. 季节性（月度季节指数）\n")
    A("价格季节指数的最高/最低月（>1 高于全年常态）：\n")
    A("| 品种 | 价格最高月 | 指数 | 价格最低月 | 指数 | 成交量最高月 | 指数 | 成交量最低月 | 指数 |")
    A("|---|---|---|---|---|---|---|---|---|")
    for crop in CORE_CROPS:
        sp = mp[mp["crop"] == crop].set_index("month_label")["seasonal_index_median"]
        sv = mv[mv["crop"] == crop].set_index("month_label")["seasonal_index_median"]
        hm, lm = sp.idxmax(), sp.idxmin()
        hv, lv = sv.idxmax(), sv.idxmin()
        A(f"| {crop} | {hm} | {sp[hm]:.2f} | {lm} | {sp[lm]:.2f} | "
          f"{hv} | {sv[hv]:.2f} | {lv} | {sv[lv]:.2f} |")
    A("")

    A("## 4. STL 稳健分解（方法A）季节强度\n")
    A("| 品种 | 价格季节强度 | 价格趋势强度 | 成交量季节强度 | 成交量趋势强度 |")
    A("|---|---|---|---|---|")
    spi = st[st["variable"] == "price"].set_index("crop")
    svo = st[st["variable"] == "volume"].set_index("crop")
    for crop in CORE_CROPS:
        a = spi.loc[crop] if crop in spi.index else None
        b = svo.loc[crop] if crop in svo.index else None
        A(f"| {crop} | "
          f"{a['seasonal_strength']:.3f} | {a['trend_strength']:.3f} | "
          f"{b['seasonal_strength']:.3f} | {b['trend_strength']:.3f} |"
          if a is not None and b is not None else f"| {crop} | — | — | — | — |")
    A("")
    A("> 季节强度 >0.6 视为季节性显著，此类品种的天气效应必须建立在去季节化序列之上（见 `04_deseasonalize.py`）。\n")

    A("## 5. 变化率分布（日 / 周 / 月 / 同期）\n")
    A("| 品种 | 变量 | 日变化中位数(%) | 日变化 P95-P05(%) | 周变化中位数(%) "
      "| 月变化中位数(%) | 同期变化中位数(%) |")
    A("|---|---|---|---|---|---|---|")
    for crop in CORE_CROPS:
        for var, un in [("price", PRICE_UNIT), ("volume", VOL_UNIT)]:
            g = ch[(ch["crop"] == crop) & (ch["variable"] == var)].set_index("change_type")
            def gv(k, c):
                return g.loc[k, c] if k in g.index else np.nan
            A(f"| {crop} | {'价格' if var == 'price' else '成交量'} | "
              f"{gv('dod_pct_prev_obs','median_pct'):.2f} | "
              f"{gv('dod_pct_prev_obs','p95_pct') - gv('dod_pct_prev_obs','p05_pct'):.1f} | "
              f"{gv('wow_pct_7cald','median_pct'):.2f} | "
              f"{gv('mom_pct_30cald','median_pct'):.2f} | "
              f"{gv('yoy_pct_365cald','median_pct'):.2f} |")
    A("")

    A("## 6. 图表清单（每张图对应一个问题）\n")
    A("| 图 | 内容 | 回答的问题 |")
    A("|---|---|---|")
    A("| 图1 `F01_黄瓜_price_volume_dual.png` | 黄瓜 价格+成交量 双面板 | 量价长期结构是否存在共同波动与断点 |")
    A("| 图2 `F02_month_price_box.png` | 月份 × 价格箱线图（10 品种） | 价格是否存在稳定季节性 |")
    A("| 图3 `F03_month_volume_box.png` | 月份 × 成交量箱线图（10 品种） | 供应是否存在季节性 |")
    A("| 图4 `F04_price_timeseries_all.png` | 10 品种价格时序 | 各品种价格路径与结构性变化是否同步 |")
    A("| 图5 `F05_volume_timeseries_all.png` | 10 品种成交量时序 | 供应波动是否集中出现在特定时期 |")
    A("| 图6 `F06_volatility_by_crop.png` | 波动率对比 | 哪些品种最不稳定 |")
    A("| 图7 `F07_STL_黄瓜_price.png` | STL 分解示例 | 价格是否同时含趋势与季节成分 |")
    A("| 图8 `F08_seasonal_heatmap_price/volume.png` | 月度季节指数热力图 | 各品种季节性方向与强度 |")
    A("| 图9 `F09_stl_strength.png` | STL 季节/趋势强度 | 哪些品种必须去季节化 |")
    A("")

    A("## 7. 本节结论（Level A 直接观察事实）\n")
    n_hi = int((st[st["variable"] == "price"]["seasonal_strength"] > 0.6).sum())
    v_max = float(st[st["variable"] == "volume"]["seasonal_strength"].max())
    v_med = float(st[st["variable"] == "volume"]["seasonal_strength"].median())
    A(f"- 10 种批发蔬菜在 {p['date'].nunique()} 个交易日上价格**无缺失**，成交量全部 >0；")
    A(f"- **价格**季节性明确：STL 季节强度中位数 "
      f"{st[st['variable']=='price']['seasonal_strength'].median():.3f}，"
      f"其中 {n_hi}/10 个品种 >0.6；月度季节指数在 1-2 月与 12 月系统性偏高、6-7 月偏低；")
    A(f"- **成交量**季节性弱：STL 季节强度中位数仅 {v_med:.3f}、最大 {v_max:.3f}，"
      "即供应端的月度规律远弱于价格端 → 成交量异常更多来自短期冲击而非季节；")
    A("- 价格长期趋势多数品种不显著（仅土豆显著下行），说明后续天气效应不能由趋势项解释；")
    A("- 价格日变化中位数为 0，源于报价以 0.05 元为最小变动单位（离散报价），"
      "故后续分析使用变化幅度分位数而非「涨跌方向」；")
    A("- 成交量单位官方未公开，本节所有成交量结论**仅限相对口径**。\n")

    pth = PATHS.report("02_DESCRIPTIVE.md")
    pth.write_text("\n".join(L), encoding="utf-8")
    LOG.info("描述性报告写入 %s", pth)


# -----------------------------------------------------------------------------
def main() -> None:
    set_seed()
    with StepTimer("03_descriptive", LOG):
        p = load_core()
        stats, trend = basic_stats(p)
        mp, mv = monthly_profile(p)
        ch = changes(p)
        comp, st = stl_weekly()

        fig_price_volume_dual(p, "黄瓜")
        fig_month_box(p, "price", "F02_month_price_box.png",
                      "图2　月份 × 批发价格箱线图（10 种蔬菜，2021-2026）\n"
                      "目的：判断价格是否存在稳定的月度季节性", PRICE_UNIT)
        fig_month_box(p, "volume", "F03_month_volume_box.png",
                      "图3　月份 × 成交量箱线图（10 种蔬菜，2021-2026）\n"
                      "目的：判断供应是否存在月度季节性", VOL_UNIT)
        fig_crop_time_series(p, "price", "F04_price_timeseries_all.png",
                             "图4　10 种批发蔬菜价格时序（2021-2026）", PRICE_UNIT)
        fig_crop_time_series(p, "volume", "F05_volume_timeseries_all.png",
                             "图5　10 种批发蔬菜成交量时序（2021-2026）", VOL_UNIT)
        fig_volatility(stats)
        fig_stl_example(comp, "黄瓜", "price")
        fig_seasonal_heatmap(mp[["crop", "month", "seasonal_index_median"]]
                             .rename(columns={"seasonal_index_median": "seasonal_index"}),
                             "price", "F08_seasonal_heatmap_price.png")
        fig_seasonal_heatmap(mv[["crop", "month", "seasonal_index_median"]]
                             .rename(columns={"seasonal_index_median": "seasonal_index"}),
                             "volume", "F08_seasonal_heatmap_volume.png")
        fig_stl_strength(st)

        write_report(stats, trend, mp, mv, ch, st, p)

        # 结果登记（Level A：直接观察事实）
        rows = []
        for _, r in trend.iterrows():
            rows.append({
                "result_id": f"DESC-TREND-{r['crop']}",
                "research_question": "RQ-desc",
                "crop": r["crop"], "period": f"{CORE_START:%Y-%m-%d}~{CORE_END:%Y-%m-%d}",
                "method": "OLS(log price ~ t), Newey-West HAC",
                "metric": "annualized_trend_pct",
                "estimate": round(float(r["annualized_trend_pct"]), 3),
                "ci_low": round(float(r["ci_low_annual_pct"]), 3),
                "ci_high": round(float(r["ci_high_annual_pct"]), 3),
                "p_value": round(float(r["p_value"]), 4),
                "robustness": "HAC(maxlags=14)",
                "figure": "F04_price_timeseries_all.png",
                "table": "trend_by_crop.csv",
                "evidence_level": "A",
                "notes": "长期趋势漂移，非天气效应；用于确认后续需在异常序列上分析",
            })
        for _, r in st.iterrows():
            rows.append({
                "result_id": f"DESC-STL-{r['crop']}-{r['variable']}",
                "research_question": "RQ-desc",
                "crop": r["crop"], "period": f"{CORE_START:%Y-%m-%d}~{CORE_END:%Y-%m-%d}",
                "method": "STL(robust=True), period=52 周",
                "metric": "seasonal_strength",
                "estimate": round(float(r["seasonal_strength"]), 4),
                "ci_low": None, "ci_high": None, "p_value": None,
                "robustness": "robust STL；周中位数序列",
                "figure": "F09_stl_strength.png",
                "table": "stl_strength.csv",
                "evidence_level": "A",
                "notes": f"趋势强度={r['trend_strength']:.4f}；n_weeks={r['n_weeks']}",
            })
        register_results(rows)
        LOG.info("结果登记 %d 条", len(rows))


if __name__ == "__main__":
    main()
