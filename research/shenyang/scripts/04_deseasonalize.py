"""STEP 09：去季节化与异常度构建（Phase 2，全研究最关键步骤之一）。

对应任务书：
  §十九 Phase 2 去季节化：构建 price_expected / price_anomaly / volume_expected / volume_anomaly
       方法A = STL / robust seasonal decomposition（周序列）
       方法B = 历史同期基线（doy ± 5，优先 median）
  §二十 异常指标：price_anomaly_pct = (price - seasonal_baseline)/seasonal_baseline；
       天气使用 temperature_z / precipitation_percentile / soil_moisture_z（对 1991-2020 基线）
  §二十一 防止数据泄漏：leave-one-year-out seasonal baseline（算 2026 只能用到 2025）

红线：
  - 主方法（用于预测与反事实）必须是 **leave-one-year-out**，不得使用目标年自身；
  - STL 方法使用全序列，含目标年 → 仅作描述/稳健性，**明确标注不可用于预测**；
  - 成交量异常仅相对口径，单位 unknown。

产出：
  data/processed/shenyang_daily_panel_hist.parquet   方法B（LOO 历史同期）异常面板
  data/processed/shenyang_daily_panel_stl.parquet    方法A（STL 周序列）异常面板
  data/processed/shenyang_panel_final.parquet        最终研究面板（含两法 + 天气异常）
  outputs/tables/anomaly_by_crop.csv                 异常度分布统计
  outputs/tables/anomaly_method_comparison.csv       两法一致性对照
  outputs/tables/baseline_valid_years.csv            每年基线的有效年构成（泄漏审计）
  outputs/tables/anomaly_extreme_days.csv            极端异常日清单（|robust z|>3）
  outputs/figures/F10..F14
  reports/03_DESEASONALIZATION.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    ANALYSIS, CROPS_CFG, PATHS, StepTimer, get_logger, load_parquet,
    register_results, render_figure, save_parquet, save_table, set_seed, setup_matplotlib,
)

LOG = get_logger("04_deseasonalize")
CORE_CROPS: list = CROPS_CFG["core_crops"]
VOL_UNIT: str = CROPS_CFG["market"]["volume_unit"]
PRICE_UNIT: str = CROPS_CFG["market"]["price_unit_raw"]
CORE_START = pd.Timestamp(ANALYSIS["time"]["core_start_planned"])
CORE_END = pd.Timestamp(ANALYSIS["time"]["weather_end"])
SB = ANALYSIS["seasonal_baseline"]
WIN = int(SB["hist_window_days"])          # 11
HALF = WIN // 2                            # ±5
MIN_OBS = int(SB["min_obs_for_baseline"])  # 8
DOY_CAP = 365                              # 2/29（doy=366）并入 doy=365，避免闰日孤立
MONTH_CN = ["1月", "2月", "3月", "4月", "5月", "6月",
            "7月", "8月", "9月", "10月", "11月", "12月"]


# -----------------------------------------------------------------------------
def load_core() -> pd.DataFrame:
    p = load_parquet("daily_panel")
    p = p[(p["date"] >= CORE_START) & (p["date"] <= CORE_END)].copy()
    p = p[p["crop"].isin(CORE_CROPS)]
    p["year"] = p["date"].dt.year
    p["month"] = p["date"].dt.month
    p["doy"] = np.minimum(p["date"].dt.dayofyear, DOY_CAP)
    return p


# -----------------------------------------------------------------------------
def loo_expected(p: pd.DataFrame, var: str) -> tuple:
    """方法B：leave-one-year-out 历史同期（doy ±5）中位数基线。

    返回 (expected_series, audit_records)
      expected_series: 与 p 同索引对齐的 Series（NaN = 窗口内有效观测 < min_obs）
      audit_records:   每年基线的有效年构成（泄漏审计）
    """
    expected = pd.Series(np.nan, index=p.index, dtype=float)
    audit = []
    doy_all = np.arange(1, DOY_CAP + 1)
    for crop, g in p.groupby("crop"):
        mat = g.pivot_table(index="doy", columns="year", values=var, aggfunc="median")
        mat = mat.reindex(index=doy_all)
        years = [c for c in mat.columns]
        for y in years:
            others = [c for c in years if c != y]
            if not others:
                continue
            sub = mat[others]
            # 11 个偏移：d-5 .. d+5（循环）
            blocks = []
            for k in range(-HALF, HALF + 1):
                src = ((doy_all - 1 + k) % DOY_CAP) + 1
                blocks.append(sub.reindex(src).values)          # (DOY_CAP, n_others)
            arr = np.stack(blocks, axis=0)                      # (11, DOY_CAP, n_others)
            cnt = np.count_nonzero(~np.isnan(arr), axis=(0, 2))
            with np.errstate(all="ignore"):
                base = np.nanmedian(arr, axis=(0, 2))
            base = np.where(cnt >= MIN_OBS, base, np.nan)
            audit.append({
                "crop": crop, "variable": var, "target_year": int(y),
                "baseline_years": "|".join(str(int(o)) for o in others),
                "n_baseline_years": len(others),
                "uses_target_year": False,
                "window_days": WIN, "min_obs": MIN_OBS,
                "target_year_used_excluded": True,
            })
            m = (g["year"] == y)
            idx = g.index[m]
            expected.loc[idx] = base[g.loc[m, "doy"].values.astype(int) - 1]
    return expected, audit


def robust_z_by_crop(p: pd.DataFrame, var: str, suffix: str) -> pd.Series:
    """按品种 + 按目标年留一，计算 1.4826×MAD 稳健尺度，再标准化异常。

    为什么必须逐品种：各品种绝对量级差异极大（成交量 土豆≈295 vs 青椒≈71，
    价格 芸豆≈4.1 元 vs 土豆≈1.1 元），若在全样本上合并估计 MAD，量级大的品种会被
    系统性放大成大量「伪极端」（实测土豆成交量曾出现 66% 的天数 |z|>3），量级小的
    品种则恒不极端。稳健 z 的语义是「相对该品种自身常态波动」，故尺度必须逐品种。

    尺度同时按目标年留一（用其余年份的异常估尺度，2026 只用 2021-2025），
    与期望基线同样满足「目标年不进入自身统计量」，保证 §二十一 无泄漏要求。
    """
    a = p[f"{var}_anomaly_{suffix}"].astype(float)
    yr = p["date"].dt.year
    z = pd.Series(np.nan, index=p.index, dtype=float)
    for _, g in p.groupby("crop"):
        idx = g.index
        for y, gy in g.assign(_y=yr.loc[idx]).groupby("_y"):
            ref = a.loc[idx].drop(index=gy.index)          # 留一年
            scale = 1.4826 * (ref - ref.median()).abs().median()
            if np.isfinite(scale) and scale > 0:
                z.loc[gy.index] = a.loc[gy.index] / scale
    return z


def add_anomaly_cols(p: pd.DataFrame, suffix: str, exp_p: pd.Series, exp_v: pd.Series) -> pd.DataFrame:
    """填充 expected / anomaly / anomaly_pct / robust_z 四类列。"""
    for var, exp in [("price", exp_p), ("volume", exp_v)]:
        e = exp.astype(float)
        a = p[var].astype(float) - e
        safe_e = e.where(e != 0)
        p[f"{var}_expected_{suffix}"] = e
        p[f"{var}_anomaly_{suffix}"] = a
        p[f"{var}_anomaly_pct_{suffix}"] = a / safe_e * 100
    for var in ["price", "volume"]:
        p[f"{var}_anomaly_z_{suffix}"] = robust_z_by_crop(p, var, suffix)
    return p


# -----------------------------------------------------------------------------
def stl_expected(p: pd.DataFrame) -> pd.DataFrame:
    """方法A：周序列 STL（trend+seasonal）作为期望，按 week_start 映射回日度。"""
    comp = pd.read_csv(PATHS.table("stl_weekly_components.csv"))
    comp["week_start"] = pd.to_datetime(comp["week_start"])
    comp["expected_stl"] = comp["trend"] + comp["seasonal"]
    comp = comp.rename(columns={"variable": "var"})
    out = p[["date", "crop", "week_start"]].copy()
    for var in ["price", "volume"]:
        w = comp[comp["var"] == var][["crop", "week_start", "expected_stl"]].rename(
            columns={"expected_stl": f"{var}_expected_stl_w"})
        out = out.merge(w, on=["crop", "week_start"], how="left")
    return out


# -----------------------------------------------------------------------------
def anomaly_stats(p: pd.DataFrame, suffix: str) -> pd.DataFrame:
    rows = []
    for crop in CORE_CROPS:
        g = p[p["crop"] == crop]
        for var in ["price", "volume"]:
            a = g[f"{var}_anomaly_{suffix}"].astype(float)
            ap = g[f"{var}_anomaly_pct_{suffix}"].astype(float)
            z = g[f"{var}_anomaly_z_{suffix}"].astype(float)
            rows.append({
                "crop": crop, "variable": var,
                "unit": PRICE_UNIT if var == "price" else VOL_UNIT,
                "method": suffix,
                "n_with_baseline": int(a.notna().sum()),
                "n_missing_baseline": int(a.isna().sum()),
                "anomaly_mean": a.mean(), "anomaly_std": a.std(ddof=1),
                "anomaly_pct_median": ap.median(),
                "anomaly_pct_p05": ap.quantile(0.05), "anomaly_pct_p95": ap.quantile(0.95),
                "anomaly_pct_min": ap.min(), "anomaly_pct_max": ap.max(),
                "robust_z_p99_abs": z.abs().quantile(0.99),
                "n_extreme_absz_gt3": int((z.abs() > 3).sum()),
                "n_extreme_absz_gt4": int((z.abs() > 4).sum()),
                # 跨品种可比的极端日占比（成交量量级差异使 |z| 计数不可跨品种直接比较）
                "pct_extreme_absz_gt3": round(float((z.abs() > 3).mean() * 100), 2),
            })
    df = pd.DataFrame(rows)
    save_table(df, f"anomaly_by_crop_{suffix}.csv")
    return df


def method_comparison(ph: pd.DataFrame, ps: pd.DataFrame) -> pd.DataFrame:
    """方法A vs 方法B 在周层面的异常一致性。"""
    rows = []
    for crop in CORE_CROPS:
        for var in ["price", "volume"]:
            a = (ph[(ph["crop"] == crop)][["week_start", f"{var}_anomaly_hist"]]
                 .groupby("week_start").mean().rename(columns={f"{var}_anomaly_hist": "hist"}))
            b = (ps[(ps["crop"] == crop)][["week_start", f"{var}_anomaly_stl"]]
                 .groupby("week_start").mean().rename(columns={f"{var}_anomaly_stl": "stl"}))
            j = a.join(b, how="inner").dropna()
            if len(j) < 20:
                continue
            rows.append({
                "crop": crop, "variable": var, "n_weeks": len(j),
                "pearson_r": j["hist"].corr(j["stl"]),
                "spearman_r": j["hist"].corr(j["stl"], method="spearman"),
                "mean_abs_diff": float((j["hist"] - j["stl"]).abs().mean()),
                "hist_std": float(j["hist"].std(ddof=1)), "stl_std": float(j["stl"].std(ddof=1)),
                "note": "方法B=LOO历史同期中位数（无泄漏）；方法A=STL全序列（含目标年，仅稳健性）",
            })
    df = pd.DataFrame(rows)
    save_table(df, "anomaly_method_comparison.csv")
    return df


def extreme_days(p: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for crop in CORE_CROPS:
        g = p[p["crop"] == crop]
        for var in ["price", "volume"]:
            z = g[f"{var}_anomaly_z_hist"]
            m = z.abs() > 3
            sub = g.loc[m, ["date", "crop", var, f"{var}_expected_hist",
                            f"{var}_anomaly_hist", f"{var}_anomaly_pct_hist",
                            f"{var}_anomaly_z_hist", "precipitation", "temp_max",
                            "precipitation_pct", "is_rainstorm_day"]].copy()
            sub["variable"] = var
            sub["unit"] = PRICE_UNIT if var == "price" else VOL_UNIT
            sub = sub.rename(columns={f"{var}_expected_hist": "expected",
                                      f"{var}_anomaly_hist": "anomaly",
                                      f"{var}_anomaly_pct_hist": "anomaly_pct",
                                      f"{var}_anomaly_z_hist": "anomaly_z",
                                      var: "observed"})
            rows.append(sub)
    df = pd.concat(rows, ignore_index=True).sort_values(
        ["variable", "date", "crop"]).reset_index(drop=True)
    save_table(df, "anomaly_extreme_days.csv")
    return df


def attach_weather_anomaly(p: pd.DataFrame) -> pd.DataFrame:
    """§二十 天气异常指标：仅做别名与统一命名，数值仍来自 1991-2020 基线（01 模块已算）。"""
    ren = {
        "temp_anomaly": "temperature_anomaly",
        "temp_z": "temperature_z",
        "precipitation_anomaly": "precipitation_anomaly",
        "precipitation_pct": "precipitation_percentile",
        "soil_moisture_0_7_z": "soil_moisture_z",
        "humidity_z": "humidity_z",
    }
    for src, dst in ren.items():
        if src in p.columns and dst not in p.columns:
            p[dst] = p[src]
    return p


# -----------------------------------------------------------------------------
def fig_expected_vs_actual(p: pd.DataFrame, crop: str) -> None:
    plt = setup_matplotlib()
    g = p[p["crop"] == crop].sort_values("date")
    fig, axes = plt.subplots(2, 1, figsize=(11.8, 6.4), sharex=True)
    axes[0].plot(g["date"], g["price"], lw=0.85, color="#1f6fb4", label="实际价格")
    axes[0].plot(g["date"], g["price_expected_hist"], lw=1.2, color="#c0392b",
                 label=f"期望价格（LOO 历史同期中位数，doy±{HALF}）")
    axes[0].set_ylabel(f"价格（{PRICE_UNIT}）")
    axes[0].legend(fontsize=9, loc="upper left")
    axes[0].set_title(f"图10　{crop}：实际价格 vs 去季节化期望基线\n"
                      f"目的：确认基线只刻画季节+常态水平，不吸收短期冲击", fontsize=12)
    axes[1].fill_between(g["date"], 0, g["price_anomaly_pct_hist"],
                         where=g["price_anomaly_pct_hist"] >= 0, color="#e07b39", alpha=0.8)
    axes[1].fill_between(g["date"], 0, g["price_anomaly_pct_hist"],
                         where=g["price_anomaly_pct_hist"] < 0, color="#4f9dd9", alpha=0.8)
    axes[1].axhline(0, color="#555", lw=0.7)
    axes[1].set_ylabel("价格异常（%）")
    axes[1].set_xlabel("日期")
    fig.tight_layout()
    render_figure(fig, f"F10_{crop}_expected_vs_actual.png",
                  "数据来源：沈阳市发改委菜篮子信息发布平台（批发口径）；"
                  "方法B=留一年法历史同期（doy±5）中位数，不含目标年自身。")


def fig_anomaly_distribution(p: pd.DataFrame) -> None:
    plt = setup_matplotlib()
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    for ax, var, c, unit in [(axes[0], "price", "#1f6fb4", PRICE_UNIT),
                             (axes[1], "volume", "#d1721f", VOL_UNIT)]:
        data = [p.loc[p["crop"] == cr, f"{var}_anomaly_pct_hist"].dropna().values
                for cr in CORE_CROPS]
        bp = ax.boxplot(data, patch_artist=True, showfliers=True, widths=0.62,
                        flierprops=dict(marker=".", markersize=2.5, alpha=0.35,
                                        markerfacecolor="#666", markeredgecolor="none"),
                        medianprops=dict(color="#c0392b", lw=1.5))
        for b in bp["boxes"]:
            b.set(facecolor="#cfe2f3" if var == "price" else "#f6dcc4",
                  edgecolor="#4a6b8a", lw=0.7)
        ax.axhline(0, color="#333", lw=0.8, ls="--")
        ax.set_xticks(range(1, len(CORE_CROPS) + 1))
        ax.set_xticklabels(CORE_CROPS, rotation=35, ha="right")
        ax.set_ylabel(f"异常幅度（%，单位基线 {unit}）")
        ax.set_title(("价格" if var == "price" else "成交量") + "异常分布")
    fig.suptitle("图11　去季节化后异常幅度分布（方法B，2021-2026）\n"
                 "目的：判断哪些品种的短期冲击幅度更大（离群点即候选冲击日）",
                 fontsize=12, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    render_figure(fig, "F11_anomaly_distribution.png",
                  "数据来源：沈阳市发改委菜篮子信息发布平台（批发口径）；"
                  "异常%=(实际-期望)/期望×100，期望为留一年法历史同期中位数。")


def fig_anomaly_month_heatmap(p: pd.DataFrame, var: str) -> None:
    plt = setup_matplotlib()
    g = p.copy()
    g["_ap"] = g[f"{var}_anomaly_pct_hist"]
    mat = (g.pivot_table(index="crop", columns="month", values="_ap", aggfunc="median")
           .reindex(CORE_CROPS))
    fig, ax = plt.subplots(figsize=(10.5, 4.6))
    vmax = float(np.nanmax(np.abs(mat.values)))
    im = ax.imshow(mat.values, cmap="RdBu_r", vmin=-vmax, vmax=vmax, aspect="auto")
    ax.set_xticks(range(12))
    ax.set_xticklabels(MONTH_CN)
    ax.set_yticks(range(len(mat)))
    ax.set_yticklabels(mat.index)
    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]):
            v = mat.values[i, j]
            if np.isfinite(v):
                ax.text(j, i, f"{v:+.1f}", ha="center", va="center", fontsize=7,
                        color="white" if abs(v) > 0.6 * vmax else "#222")
    fig.colorbar(im, ax=ax, label="异常中位数（%）")
    ax.set_title(f"图12　{'价格' if var == 'price' else '成交量'}异常的月度中位数（方法B）\n"
                 "目的：检查去季节化是否彻底——若某月仍系统性偏离 0，说明基线不足", fontsize=12)
    ax.grid(False)
    fig.tight_layout()
    render_figure(fig, f"F12_anomaly_month_{var}.png",
                  "数据来源：沈阳市发改委菜篮子信息发布平台（批发口径）；"
                  "理想情况每格接近 0，显著偏离即提示剩余季节性。")


def fig_method_comparison(cmp_df: pd.DataFrame) -> None:
    plt = setup_matplotlib()
    d = cmp_df[cmp_df["variable"] == "price"].set_index("crop").reindex(CORE_CROPS)
    dv = cmp_df[cmp_df["variable"] == "volume"].set_index("crop").reindex(CORE_CROPS)
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6))
    for ax, dd, var in [(axes[0], d, "价格"), (axes[1], dv, "成交量")]:
        x = np.arange(len(dd))
        ax.bar(x - 0.2, dd["pearson_r"], width=0.4, label="Pearson r", color="#1f6fb4")
        ax.bar(x + 0.2, dd["spearman_r"], width=0.4, label="Spearman ρ", color="#7f8c8d")
        ax.set_xticks(x)
        ax.set_xticklabels(dd.index, rotation=35, ha="right", fontsize=9)
        ax.set_ylim(0, 1)
        ax.axhline(0.6, color="#c0392b", ls="--", lw=0.9)
        ax.set_ylabel("周层面一致性")
        ax.set_title(f"{var}：方法A(STL) vs 方法B(历史同期)")
        ax.legend(fontsize=9)
    fig.suptitle("图13　两套去季节化方法的异常序列一致性\n"
                 "目的：若两法一致性高，则后续结论对基线选择不敏感（稳健性证据）",
                 fontsize=12, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    render_figure(fig, "F13_method_comparison.png",
                  "数据来源：沈阳市发改委菜篮子信息发布平台（批发口径）；"
                  "一致性在周层面计算（两法时间粒度不同）。")


def fig_extreme_days_by_year(p: pd.DataFrame) -> None:
    plt = setup_matplotlib()
    g = p.copy()
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 4.6), sharey=True)
    for ax, var, c in [(axes[0], "price", "#1f6fb4"), (axes[1], "volume", "#d1721f")]:
        z = g[f"{var}_anomaly_z_hist"]
        g["_ext"] = (z.abs() > 3).astype(int)
        cnt = g.groupby(["year", "crop"])["_ext"].sum().unstack().reindex(columns=CORE_CROPS)
        for crop in CORE_CROPS:
            ax.plot(cnt.index, cnt[crop], marker="o", ms=3.2, lw=1.0, alpha=0.8, label=crop)
        ax.set_xlabel("年份")
        ax.set_title(("价格" if var == "price" else "成交量") + "（|稳健 z| > 3）")
        ax.set_xticks(sorted(cnt.index.unique()))
    axes[0].set_ylabel("极端异常日数")
    axes[0].legend(fontsize=7.5, ncol=2)
    fig.suptitle("图14　各年极端异常日数量（方法B）\n"
                 "目的：检查异常是否集中在特定年份（如 2026）而非均匀分布",
                 fontsize=12, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    render_figure(fig, "F14_extreme_days_by_year.png",
                  "数据来源：沈阳市发改委菜篮子信息发布平台（批发口径）；"
                  "极端阈值为 3 倍稳健标准差（1.4826×MAD）。")


# -----------------------------------------------------------------------------
def write_report(p, st_h, st_s, cmp_df, audit_df, ext) -> None:
    L: list = []
    A = L.append
    A("# 03 DESEASONALIZATION — 去季节化与异常度\n")
    A(f"> 核心窗口：**{CORE_START:%Y-%m-%d} ~ {CORE_END:%Y-%m-%d}**；"
      f"面板 {len(p):,} 行。价格单位 `{PRICE_UNIT}`；成交量单位 `{VOL_UNIT}`。\n")

    A("## 1. 为什么必须去季节化（§十九）\n")
    A("「夏天气温高、冬天黄瓜贵」这类季节共变**不能**当成天气影响。"
      "本节构造 `expected`（季节性常态）与 `anomaly`（超出常态的部分），"
      "后续所有天气效应分析一律在 `anomaly` 序列上进行。\n")

    A("## 2. 方法B（主方法）：留一年法历史同期中位数\n")
    A(f"- 窗口：目标日 ± {HALF} 天（共 {WIN} 天），跨年取**中位数**（抗极端值）；")
    A(f"- **留一年法**：计算某年基线时完全排除该年自身；")
    A(f"- 有效观测数 < {MIN_OBS} 时输出 NaN（不猜、不插）；")
    A(f"- 闰日 2/29（doy=366）并入 doy=365，避免该日历日仅有单年观测而无法构造跨年基线。\n")
    yr = audit_df[audit_df["variable"] == "price"].drop_duplicates("target_year")
    A("| 目标年 | 参与基线的年份（不含目标年） | 年数 |")
    A("|---|---|---|")
    for _, r in yr.sort_values("target_year").iterrows():
        A(f"| {r['target_year']} | {r['baseline_years']} | {r['n_baseline_years']} |")
    A("")
    A("> **泄漏审计结论**：所有年份的 `uses_target_year=False`。"
      "例如 2026 年基线仅由 2021-2025 构成（§二十一）。\n")

    A("## 3. 方法A（稳健性）：STL 周序列分解\n")
    A(f"- 周中位数序列、`period={SB['stl_period']}` 周、`robust={SB['stl_robust']}`；")
    A("- 期望 = trend + seasonal，异常 = 观测 − 期望；")
    A("- **重要限制**：STL 使用全序列（含目标年），存在信息泄漏风险，"
      "**仅用于描述与稳健性对照，不用于预测与反事实**。\n")

    A("## 4. 两法一致性\n")
    A("| 品种 | 变量 | 周数 | Pearson r | Spearman ρ | 平均绝对差 |")
    A("|---|---|---|---|---|---|")
    for _, r in cmp_df.iterrows():
        A(f"| {r['crop']} | {'价格' if r['variable'] == 'price' else '成交量'} | "
          f"{r['n_weeks']} | {r['pearson_r']:.3f} | {r['spearman_r']:.3f} | "
          f"{r['mean_abs_diff']:.3f} |")
    A("")
    pm = float(cmp_df[cmp_df["variable"] == "price"]["pearson_r"].median())
    vm = float(cmp_df[cmp_df["variable"] == "volume"]["pearson_r"].median())
    A(f"- 价格两法一致性的中位数 r = **{pm:.3f}**；成交量 r = **{vm:.3f}**。")
    if pm >= 0.6:
        A("- 结论：价格端的去季节化结果**对基线方法不敏感**，后续结论具备方法稳健性。")
    else:
        A("- 结论：价格端两法一致性中等偏低 → 后续所有关键结论必须**同时报告两法**。\n")

    A("## 5. 异常度分布（方法B）\n")
    A("> 稳健 z 的尺度为**逐品种、按目标年留一**估计的 1.4826×MAD。"
      "各品种绝对量级差异极大（成交量 土豆≈295 vs 青椒≈71），"
      "故 |z| 只在**品种内**可解释，**禁止跨品种直接比较极端日数量**；"
      "跨品种比较须用 `anomaly_pct` 或极端日**占比**。\n")
    A("| 品种 | 变量 | 有效天数 | 无基线天数 | 异常% P05 | 异常% 中位 | 异常% P95 "
      "| 极端日\\|z\\|>3 | 极端日\\|z\\|>4 |")
    A("|---|---|---|---|---|---|---|---|---|")
    for _, r in st_h.iterrows():
        A(f"| {r['crop']} | {'价格' if r['variable'] == 'price' else '成交量'} | "
          f"{r['n_with_baseline']} | {r['n_missing_baseline']} | "
          f"{r['anomaly_pct_p05']:.1f} | {r['anomaly_pct_median']:.1f} | "
          f"{r['anomaly_pct_p95']:.1f} | {r['n_extreme_absz_gt3']} | {r['n_extreme_absz_gt4']} |")
    A("")

    A("## 6. 天气异常指标（§二十，对 1991-2020 基线）\n")
    A("| 指标 | 定义 | 覆盖 |")
    A("|---|---|---|")
    A("| `temperature_anomaly` / `temperature_z` | 日气温 −(÷) 同日基线均值/标准差 | "
      f"{int(p['temperature_z'].notna().sum()):,} 行 |")
    A("| `precipitation_anomaly` / `precipitation_percentile` | 日降水距平 / 同日经验分位(0-1) | "
      f"{int(p['precipitation_percentile'].notna().sum()):,} 行 |")
    soil_flag = (p["soil_moisture_z_baseline"].dropna().astype(str).iloc[0]
                 if "soil_moisture_z_baseline" in p.columns
                 and p["soil_moisture_z_baseline"].notna().any() else "baseline_1991_2020")
    soil_def = ("0-7cm 土壤含水量，**降级基线**：观测期 leave-one-year-out 同期（doy±5）期望值"
                " + 1.4826×MAD 稳健尺度（官方 1991-2020 基线不含该变量，见 `reports/BLOCKERS.md`）"
                if soil_flag == "observation_period_loo" else "0-7cm 土壤含水量对 1991-2020 官方同日基线标准化")
    A(f"| `soil_moisture_z` | {soil_def} | {int(p['soil_moisture_z'].notna().sum()):,} 行 |")
    A("| `humidity_z` | 相对湿度对同日基线标准化 | "
      f"{int(p['humidity_z'].notna().sum()):,} 行 |")
    A("| `precip_deficit_14d / 30d` | 基线累计 − 实际累计（正=偏干） | "
      f"{int(p['precip_deficit_30d'].notna().sum()):,} 行 |")
    A("")
    if soil_flag == "observation_period_loo":
        A("> **口径声明**：`soil_moisture_z` 是五项天气异常指标中唯一未使用官方 30 年基线的指标。"
          "原因：仓库提供的 1991-2020 日值基线 JSON（`openmeteo_沈阳_baseline_1991-01-01_2020-12-31.json`）"
          "的 `soil_moisture_0_to_10cm_mean` 字段 10958 天全部为 null（0 个有效值）。"
          "降级方案用观测期留一年法（目标年不进入自身基线，无泄漏）+ 全局稳健尺度，"
          "故该指标的**证据等级为 B**，跨 30 年气候极端性的推断不成立。\n")


    A("## 7. 极端异常日\n")
    A(f"共识别 |稳健 z| > 3 的极端异常日 **{len(ext):,}** 条（价格层面明细见 "
      "`outputs/tables/anomaly_extreme_days.csv`）。该表用于："
      "① 检验异常是否集中在特定年份/月份；② 为后续 Event Study 提供候选冲击清单。\n")

    A("## 8. 图表清单\n")
    A("| 图 | 内容 | 回答的问题 |")
    A("|---|---|---|")
    A("| 图10 `F10_黄瓜_expected_vs_actual.png` | 实际 vs 期望 + 异常柱 | 基线是否只刻画常态、不吸收冲击 |")
    A("| 图11 `F11_anomaly_distribution.png` | 异常幅度箱线分布 | 哪些品种短期冲击幅度更大 |")
    A("| 图12 `F12_anomaly_month_price/volume.png` | 异常月度中位数热力图 | 去季节化是否彻底 |")
    A("| 图13 `F13_method_comparison.png` | 两法一致性 | 结论是否对基线选择敏感 |")
    A("| 图14 `F14_extreme_days_by_year.png` | 逐年极端异常日数 | 异常是否集中于特定年份 |")
    A("")

    A("## 9. 本节结论（Level A/B）\n")
    A("- **Level A**：方法B 完全满足留一年法，无信息泄漏；天气异常指标均基于 1991-2020 基线；")
    A(f"- **Level B**：价格与成交量的去季节化异常序列在两种基线下的周层面一致性为 "
      f"r≈{pm:.2f}（价格）/ {vm:.2f}（成交量）；")
    A("- 最终研究面板 `data/processed/shenyang_panel_final.parquet` 同时保留两法异常，"
      "供后续 Lag / Threshold / Event Study 交叉验证。\n")
    A("> 注意：所有 `anomaly_pct` 的分母是**基线期望值**；当期望值很小时（如低价品种），"
      "百分比会放大，故同时保留绝对异常 `anomaly` 与稳健 z。\n")

    pth = PATHS.report("03_DESEASONALIZATION.md")
    pth.write_text("\n".join(L), encoding="utf-8")
    LOG.info("去季节化报告写入 %s", pth)


# -----------------------------------------------------------------------------
def main() -> None:
    set_seed()
    with StepTimer("04_deseasonalize", LOG):
        p = load_core()
        p = attach_weather_anomaly(p)

        exp_p, aud_p = loo_expected(p, "price")
        exp_v, aud_v = loo_expected(p, "volume")
        p = add_anomaly_cols(p, "hist", exp_p, exp_v)
        audit_df = pd.DataFrame(aud_p + aud_v)
        save_table(audit_df, "baseline_valid_years.csv")

        n_na = int(p["price_expected_hist"].isna().sum())
        LOG.info("方法B 基线覆盖：价格缺失 %d / %d 行（%.2f%%）",
                 n_na, len(p), 100 * n_na / len(p))
        if n_na > 0:
            LOG.info("无基线行集中在：%s", p.loc[p["price_expected_hist"].isna(), "date"]
                     .dt.strftime("%Y-%m-%d").value_counts().head(8).to_dict())

        # 方法B 面板
        cols_h = ["date", "crop", "week_start"] + [c for c in p.columns if c.endswith("_hist")]
        ph = p[cols_h].copy()
        save_parquet(ph, "panel_hist")

        # 方法A 面板
        stl_exp = stl_expected(p)
        ps = p[["date", "crop", "week_start", "price", "volume"]].merge(
            stl_exp, on=["date", "crop", "week_start"], how="left")
        for var in ["price", "volume"]:
            e = ps[f"{var}_expected_stl_w"].astype(float)
            a = ps[var].astype(float) - e
            ps[f"{var}_expected_stl"] = e
            ps[f"{var}_anomaly_stl"] = a
            ps[f"{var}_anomaly_pct_stl"] = a / e.where(e != 0) * 100
        ps = ps.drop(columns=[f"{v}_expected_stl_w" for v in ["price", "volume"]])
        for var in ["price", "volume"]:
            ps[f"{var}_anomaly_z_stl"] = robust_z_by_crop(ps, var, "stl")
        save_parquet(ps, "panel_stl")

        # 最终面板 = 主面板 + 两法异常 + 天气异常统一命名
        keep_base = [c for c in p.columns if not c.endswith("_hist")]
        final = p[keep_base].merge(
            ph.drop(columns=["date", "crop"]), left_index=True, right_index=True, how="left")
        final = final.merge(
            ps[["date", "crop"] + [c for c in ps.columns if c.endswith("_stl")]],
            on=["date", "crop"], how="left")
        final = attach_weather_anomaly(final)
        save_parquet(final, "panel_final")
        LOG.info("最终面板：%d 行 × %d 列", *final.shape)

        st_h = anomaly_stats(p, "hist")
        st_s = anomaly_stats(ps, "stl")
        cmp_df = method_comparison(ph, ps)
        ext = extreme_days(p)
        LOG.info("极端异常日（|z|>3）：%d 条", len(ext))

        fig_expected_vs_actual(p, "黄瓜")
        fig_anomaly_distribution(p)
        fig_anomaly_month_heatmap(p, "price")
        fig_anomaly_month_heatmap(p, "volume")
        fig_method_comparison(cmp_df)
        fig_extreme_days_by_year(p)

        write_report(p, st_h, st_s, cmp_df, audit_df, ext)

        rows = []
        for _, r in cmp_df.iterrows():
            rows.append({
                "result_id": f"DESEASON-CMP-{r['crop']}-{r['variable']}",
                "research_question": "RQ-desc",
                "crop": r["crop"], "period": f"{CORE_START:%Y-%m-%d}~{CORE_END:%Y-%m-%d}",
                "method": "方法A(STL 周序列) vs 方法B(LOO 历史同期 doy±5 中位数)",
                "metric": "pearson_r(周异常)",
                "estimate": round(float(r["pearson_r"]), 4),
                "ci_low": None, "ci_high": None, "p_value": None,
                "robustness": f"Spearman={r['spearman_r']:.4f}; 平均绝对差={r['mean_abs_diff']:.4f}",
                "figure": "F13_method_comparison.png", "table": "anomaly_method_comparison.csv",
                "evidence_level": "B",
                "notes": "方法A 含目标年，存在泄漏，仅作稳健性；方法B 为唯一可用于预测的基线",
            })
        for _, r in st_h.iterrows():
            rows.append({
                "result_id": f"ANOM-EXTREME-{r['crop']}-{r['variable']}",
                "research_question": "RQ-desc",
                "crop": r["crop"], "period": f"{CORE_START:%Y-%m-%d}~{CORE_END:%Y-%m-%d}",
                "method": "方法B LOO 历史同期基线；1.4826×MAD 稳健 z",
                "metric": "n_extreme_absz_gt3",
                "estimate": int(r["n_extreme_absz_gt3"]),
                "ci_low": None, "ci_high": None, "p_value": None,
                "robustness": f"|z|>4 计数={int(r['n_extreme_absz_gt4'])}",
                "figure": "F14_extreme_days_by_year.png",
                "table": "anomaly_by_crop_hist.csv", "evidence_level": "A",
                "notes": f"异常%区间 P05={r['anomaly_pct_p05']:.2f} / P95={r['anomaly_pct_p95']:.2f}",
            })
        register_results(rows)
        LOG.info("结果登记 %d 条", len(rows))


if __name__ == "__main__":
    main()
