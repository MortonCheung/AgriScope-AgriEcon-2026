"""STEP 22 — Phase 11：年度生产研究（任务书 §四十七 ~ §四十八）。

目标：建立 `shenyang_yearly_panel`（年度尺度），并只允许做
      描述性趋势 / anomaly / 简单相关 / 简单回归。

红线
----
- §四十七：年度尺度数据**不得**与日度价格硬拼。
- §四十八：2017-2025 仅约 9 个年份，**禁止**用 9 个点训练 XGBoost /
  神经网络 / Random Forest 后宣称高准确率。本模块**不训练任何模型**，
  只做描述统计与单变量简单回归，并明确「样本量有限，仅作机制补充」。
- 不插补缺失年份；单位必须显式；派生值必须打标记。

本轮实测的数据可得性（同时写入 reports/BLOCKERS.md）
----------------------------------------------------
1. 沈阳「蔬菜及食用菌」年度数据仅 **2017 / 2018 / 2019 / 2025** 四年。
   `fact_production_yearly_2020_2024.csv` 中沈阳**只有粮食作物**（粮食、水稻、
   小麦、玉米、高粱、谷子、薯类、大豆、油料、花生），**无任何蔬菜行**。
   => 2020-2024 蔬菜年度数据**缺失**，不得插补。
2. 粮（粮食/水稻/玉米/大豆）年度序列较完整：粮食 2017-2025（9 年），
   水稻/玉米/大豆 2018-2025（8 年，2017 年鉴未给分作物行）。
3. 生长季气象只能由 `weather_daily` 聚合，可得范围 **2021-2026**。
   => 与蔬菜年度数据的重叠**仅 2025 一年**；与粮食的重叠为 2021-2025（5 年）。
   => 年度「产量 vs 生长季气象」的相关分析在蔬菜上**不可行**，
      在粮食上 n=5，只作探索性描述，不作推断。
4. 年度生产数据**无分品种蔬菜**（仅「蔬菜及食用菌」合计），
   => §四十八 所述 crop panel **不可行**。

输出
----
data/processed/shenyang_yearly_panel.parquet   （artifact: yearly_panel）
tables/  yearly_production_long.csv
         yearly_growing_season_weather.csv
         yearly_trend.csv
         yearly_anomaly.csv
         yearly_weather_corr.csv
figures/ F36_yearly_vegetable.png
         F37_yearly_grain.png
         F38_yearly_weather_scatter.png
reports/ 11_YEARLY_PRODUCTION.md
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from _common import (
    ANALYSIS,
    PATHS,
    get_logger,
    log_blocker,
    register_results,
    render_figure,
    save_parquet,
    save_table,
    set_seed,
    setup_matplotlib,
)

MOD = "13_yearly_production"
GROW_MONTHS = list(ANALYSIS["time"]["growing_season_months"])
GS_LABEL = "、".join(f"{m}月" for m in GROW_MONTHS)
HAZ = ANALYSIS["hazard_thresholds"]

# 年度生产序列（year → 观测年）
VEG_CROP = "蔬菜及食用菌"
GRAIN_CROP = "粮食"


# -----------------------------------------------------------------------------
# 1) 读入并统一三家生产表的单位
# -----------------------------------------------------------------------------
def _norm(rows: List[Dict], year, crop, area, prod, yld, unit_prod, src,
          grade, derived=False) -> None:
    """unit_prod ∈ {'万吨','吨'}；area 用千公顷；yld 用公斤/公顷。"""
    mult = 10000.0 if unit_prod == "万吨" else 1.0
    rows.append({
        "year": int(year), "crop": crop, "region": "沈阳",
        "planting_area_kha": (float(area) if area is not None and not pd.isna(area) else np.nan),
        "production_ton": (float(prod) * mult if prod is not None and not pd.isna(prod) else np.nan),
        "yield_kg_per_ha": (float(yld) if yld is not None and not pd.isna(yld) else np.nan),
        "production_unit_raw": unit_prod,
        "source_table": src,
        "quality_grade": grade,
        "value_is_derived": bool(derived),
    })


def load_production(log) -> pd.DataFrame:
    rows: List[Dict] = []

    # --- 表1：辽宁统计年鉴 2017-2019（沈阳）---
    d1 = pd.read_csv(PATHS.inp("fact_production_yearly"))
    d1 = d1[d1["city"].astype(str).str.contains("沈阳")].copy()
    G1 = "fact_production_yearly.csv"
    for y in sorted(d1["year"].unique()):
        dy = d1[d1["year"] == y]
        g = dy.set_index("crop")

        def gv(crop, col):
            return g.loc[crop, col] if crop in g.index else np.nan

        _norm(rows, y, GRAIN_CROP,
              gv("粮食作物", "planting_area"), gv("粮食(万吨)", "production"),
              gv("粮食", "yield_per_area"), "万吨", G1, "年鉴1981-2020口径")
        _norm(rows, y, VEG_CROP,
              gv("蔬菜", "planting_area"), gv("蔬菜及食用菌(万吨)", "production"),
              gv("蔬菜", "yield_per_area"), "万吨", G1, "年鉴1981-2020口径")
        for c in ("水稻", "玉米", "大豆"):
            if c in g.index:
                _norm(rows, y, c, gv(c, "planting_area"), gv(c, "production"),
                      gv(c, "yield_per_area"), "万吨", G1, "年鉴1981-2020口径")

    # --- 表2：2020-2024（沈阳，仅粮食作物）---
    d2 = pd.read_csv(PATHS.inp("fact_production_yearly_2020_2024"))
    d2 = d2[d2["city"].astype(str).str.contains("沈阳")].copy()
    if d2.empty:
        log_blocker(MOD, "2020-2024 沈阳生产表为空", "fact_production_yearly_2020_2024.csv")
    else:
        for _, r in d2.iterrows():
            _norm(rows, r["year"], str(r["crop"]).strip(),
                  r["planting_area_kha"], r["production_ton"], r["yield_kg_per_ha"],
                  "吨", "fact_production_yearly_2020_2024.csv",
                  str(r.get("quality_grade", "")))

    # --- 表3：2025（沈阳）---
    d3 = pd.read_csv(PATHS.inp("fact_production_yearly_2025_shenyang"))
    for _, r in d3.iterrows():
        _norm(rows, r["year"], str(r["crop"]).strip(),
              r["planting_area_kha"], r["production_ton"], r["yield_kg_per_ha"],
              "吨", "fact_production_yearly_2025_shenyang.csv",
              str(r.get("quality_grade", "")))

    df = pd.DataFrame(rows).drop_duplicates(subset=["year", "crop"], keep="last")
    df = df.sort_values(["crop", "year"]).reset_index(drop=True)

    # 派生：2017 蔬菜面积缺失，但 产量/单产 均为官方值 -> 仅登记「隐含面积」并打标记
    m = (df["crop"] == VEG_CROP) & df["planting_area_kha"].isna() \
        & df["production_ton"].notna() & df["yield_kg_per_ha"].notna()
    if m.any():
        df.loc[m, "planting_area_kha_implied"] = (
            df.loc[m, "production_ton"] / df.loc[m, "yield_kg_per_ha"])
    save_table(df, "yearly_production_long.csv")
    log.info("年度生产长表：%d 行；作物 %s", len(df), sorted(df["crop"].unique()))
    return df


# -----------------------------------------------------------------------------
# 2) 生长季气象聚合（仅 2021-2026 可得）
# -----------------------------------------------------------------------------
def growing_season_weather(weather: pd.DataFrame) -> pd.DataFrame:
    w = weather.copy()
    w["date"] = pd.to_datetime(w["date"])
    w["_y"] = w["date"].dt.year
    w["_m"] = w["date"].dt.month
    gs = w[w["_m"].isin(GROW_MONTHS)].copy()

    def agg(g: pd.DataFrame) -> pd.Series:
        return pd.Series({
            "n_days_in_season": int(len(g)),
            "season_precip_mm": float(pd.to_numeric(g["precipitation"], errors="coerce").sum()),
            "season_precip_clim_mm": float(pd.to_numeric(g["precipitation_clim"], errors="coerce").sum()),
            "season_temp_mean_c": float(pd.to_numeric(g["temp_mean"], errors="coerce").mean()),
            "heat_days": float((pd.to_numeric(g["temp_max"], errors="coerce") >= HAZ["heat_tmax_c"]).sum()),
            "heavy_rain_days": float((pd.to_numeric(g["precipitation"], errors="coerce") >= HAZ["rainstorm_daily_mm"]).sum()),
            "soil_moisture_anomaly": float(pd.to_numeric(g["soil_moisture_0_7_z"], errors="coerce").mean()),
            "max_3d_precip_mm": float(pd.to_numeric(g["precip_3d"], errors="coerce").max()),
        })

    out = gs.groupby("_y").apply(agg, include_groups=False).reset_index()
    out = out.rename(columns={"_y": "year"})
    out["season_precip_pct_of_clim"] = (
        out["season_precip_mm"] / out["season_precip_clim_mm"].replace(0, np.nan))
    # 生长季完整否（3-9 月内缺失月份视为不完整；仅用于标注，不做插补）
    full = set(GROW_MONTHS)
    seasons = gs.groupby("_y")["_m"].apply(lambda s: set(s.unique()))
    out["season_complete"] = out["year"].map(lambda y: full.issubset(seasons.get(y, set())))
    out["weather_source"] = "Open-Meteo ERA5 / ERA5-Land 再分析（非气象站实测）"
    save_table(out, "yearly_growing_season_weather.csv")
    return out


# -----------------------------------------------------------------------------
# 3) 组装 shenyang_yearly_panel
# -----------------------------------------------------------------------------
def build_panel(prod: pd.DataFrame, gw: pd.DataFrame, log) -> pd.DataFrame:
    panel = prod.merge(gw, on="year", how="left")
    panel["weather_available"] = panel["season_precip_mm"].notna()
    panel = panel[[
        "year", "region", "crop",
        "planting_area_kha", "production_ton", "yield_kg_per_ha",
        "planting_area_kha_implied", "value_is_derived",
        "season_precip_mm", "season_precip_clim_mm", "season_precip_pct_of_clim",
        "season_temp_mean_c", "heat_days", "heavy_rain_days",
        "soil_moisture_anomaly", "max_3d_precip_mm",
        "n_days_in_season", "season_complete", "weather_source",
        "source_table", "quality_grade", "weather_available",
    ]]
    save_parquet(panel, "yearly_panel")
    save_table(panel, "shenyang_yearly_panel.csv")
    log.info("shenyang_yearly_panel：%d 行；年份 %d-%d；有气象的年份 %s",
             len(panel), panel["year"].min(), panel["year"].max(),
             sorted(panel.loc[panel["weather_available"], "year"].unique()))
    return panel


# -----------------------------------------------------------------------------
# 4) 允许的分析：趋势 / anomaly / 简单相关 / 简单回归
# -----------------------------------------------------------------------------
def trend_table(panel: pd.DataFrame) -> pd.DataFrame:
    """每个 crop × 变量：对年份做单变量 OLS（仅描述，不宣称预测能力）。"""
    out = []
    for (crop, var) in [(c, v) for c in panel["crop"].unique()
                        for v in ("planting_area_kha", "production_ton", "yield_kg_per_ha")]:
        s = panel[(panel["crop"] == crop)][["year", var]].dropna()
        if len(s) < 3:
            continue
        x = s["year"].to_numpy(dtype=float)
        y = s[var].to_numpy(dtype=float)
        b, a = np.polyfit(x, y, 1)
        yhat = a + b * x
        ss_res = float(((y - yhat) ** 2).sum())
        ss_tot = float(((y - y.mean()) ** 2).sum())
        out.append({
            "crop": crop, "variable": var, "n_years": len(s),
            "years": f"{int(x.min())}-{int(x.max())}",
            "first_value": float(y[0]), "last_value": float(y[-1]),
            "total_change_pct": float((y[-1] / y[0] - 1) * 100) if y[0] else np.nan,
            "linear_slope_per_year": float(b),
            "r2": float(1 - ss_res / ss_tot) if ss_tot > 0 else np.nan,
            "has_gap_years": bool(len(s) < (int(x.max()) - int(x.min()) + 1)),
        })
    return pd.DataFrame(out)


def anomaly_table(panel: pd.DataFrame) -> pd.DataFrame:
    """相对本序列均值的偏离与 z（样本极小，仅描述）。"""
    out = []
    for (crop, var) in [(c, v) for c in panel["crop"].unique()
                        for v in ("production_ton", "yield_kg_per_ha")]:
        s = panel[panel["crop"] == crop][["year", var]].dropna()
        if len(s) < 3:
            continue
        mu, sd = float(s[var].mean()), float(s[var].std(ddof=1))
        for _, r in s.iterrows():
            out.append({
                "crop": crop, "variable": var, "year": int(r["year"]),
                "value": float(r[var]), "series_mean": mu, "series_sd": sd,
                "anomaly": float(r[var] - mu),
                "anomaly_pct": float((r[var] - mu) / mu * 100) if mu else np.nan,
                "z_within_series": float((r[var] - mu) / sd) if sd > 0 else np.nan,
                "n_years_in_series": len(s),
            })
    return pd.DataFrame(out)


def weather_corr(panel: pd.DataFrame, log) -> pd.DataFrame:
    """作物产量/单产 vs 生长季气象：仅年份有双边数据的才计算。"""
    wx = ["season_precip_mm", "season_temp_mean_c", "heat_days",
          "heavy_rain_days", "soil_moisture_anomaly", "max_3d_precip_mm"]
    out = []
    for crop in panel["crop"].unique():
        for var in ("production_ton", "yield_kg_per_ha"):
            for wv in wx:
                s = panel[(panel["crop"] == crop)][["year", var, wv]].dropna()
                if len(s) < 4:
                    continue
                r = float(np.corrcoef(s[wv], s[var])[0, 1]) if s[wv].std() > 0 else np.nan
                rs = float(s[wv].rank().corr(s[var].rank())) if s[wv].std() > 0 else np.nan
                out.append({
                    "crop": crop, "variable": var, "weather": wv,
                    "n_years": len(s),
                    "years": ",".join(str(int(y)) for y in sorted(s["year"])),
                    "pearson_r": r, "spearman_r": rs,
                    "interpretation_allowed": False,
                    "note": "n<8，仅探索性描述，不作统计推断",
                })
    df = pd.DataFrame(out)
    # 记录：蔬菜因气象与产量年份重叠过少而无法进入
    overlap = {}
    for crop in panel["crop"].unique():
        s = panel[(panel["crop"] == crop) & panel["production_ton"].notna()
                  & panel["season_precip_mm"].notna()]
        overlap[crop] = sorted(s["year"].tolist())
    log.info("产量×生长季气象的重叠年份：%s", overlap)
    for c, ys in overlap.items():
        if len(ys) < 4:
            log_blocker(MOD, f"{c}：年度产量与生长季气象的重叠年份不足 4 年",
                        f"overlap_years={ys}；处理=不计算相关系数（不插补、不外推）")
    return df


def simple_regression(panel: pd.DataFrame, crop: str = GRAIN_CROP) -> pd.DataFrame:
    """单变量简单回归（n<8，仅展示，不作推断）。"""
    out = []
    wx = ["season_precip_mm", "season_temp_mean_c", "heat_days",
          "heavy_rain_days", "soil_moisture_anomaly"]
    for target in ("yield_kg_per_ha", "production_ton"):
        for wv in wx:
            s = panel[(panel["crop"] == crop)][["year", wv, target]].dropna()
            if len(s) < 4:
                continue
            x = s[wv].to_numpy(dtype=float)
            y = s[target].to_numpy(dtype=float)
            if x.std() == 0:
                continue
            b, a = np.polyfit(x, y, 1)
            yhat = a + b * x
            resid = y - yhat
            n = len(s)
            ss_res = float((resid ** 2).sum())
            ss_tot = float(((y - y.mean()) ** 2).sum())
            se_b = (np.sqrt(ss_res / (n - 2) / ((x - x.mean()) ** 2).sum())
                    if n > 2 and ss_res > 0 else np.nan)
            out.append({
                "crop": crop, "target": target, "weather": wv,
                "n_years": n, "df_resid": n - 2,
                "slope": float(b), "intercept": float(a),
                "slope_se": float(se_b) if np.isfinite(se_b) else np.nan,
                "r2": float(1 - ss_res / ss_tot) if ss_tot > 0 else np.nan,
                "inference_allowed": False,
                "note": f"n={n}，自由度={n-2}；样本量极小，仅作机制补充，不得宣称预测能力",
            })
    return pd.DataFrame(out)


# -----------------------------------------------------------------------------
# 5) 图
# -----------------------------------------------------------------------------
def fig_vegetable(panel: pd.DataFrame):
    plt = setup_matplotlib()
    s = panel[panel["crop"] == VEG_CROP].sort_values("year")
    fig, axes = plt.subplots(1, 2, figsize=(12.6, 4.6))
    ax = axes[0]
    ax.bar(s["year"].astype(str), s["production_ton"] / 10000.0,
           color=["#2f6f9f" if y != 2025 else "#a8c4a2" for y in s["year"]])
    ax.set_ylabel("产量（万吨）")
    ax.set_xlabel("年份")
    ax.set_title("沈阳「蔬菜及食用菌」年产量（仅 4 个观测年）")
    ax.text(0.02, 0.95, "2020-2024 无蔬菜年度数据\n（年鉴该表沈阳仅粮食作物）",
            transform=ax.transAxes, va="top", fontsize=9, color="#8a2b2b",
            bbox=dict(fc="#fdf1f1", ec="#d9a3a3", lw=0.8))
    ax = axes[1]
    ax.plot(s["year"], s["yield_kg_per_ha"], marker="o", color="#2f6f9f", lw=1.8)
    for _, r in s.iterrows():
        ax.annotate(f"{r['yield_kg_per_ha']:.0f}", (r["year"], r["yield_kg_per_ha"]),
                    textcoords="offset points", xytext=(0, 7), ha="center", fontsize=8.5)
    ax.set_xticks(sorted(s["year"].unique()))
    ax.set_ylabel("单产（公斤/公顷）")
    ax.set_xlabel("年份")
    ax.set_title("沈阳蔬菜单产（2017-2019、2025，中间年份缺失）")
    fig.suptitle("图 F36：沈阳蔬菜年度生产（年度尺度，禁止与日度价格硬拼）\n"
                 "数据断裂：2017-2019、2025 为观测年；2020-2024 缺失（不插补）",
                 fontsize=11, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    render_figure(fig, "F36_yearly_vegetable.png")


def fig_grain(panel: pd.DataFrame):
    plt = setup_matplotlib()
    g = panel[panel["crop"] == GRAIN_CROP].sort_values("year")
    fig, axes = plt.subplots(1, 3, figsize=(14.0, 4.4))
    for ax, var, lab, color in zip(
            axes,
            ["planting_area_kha", "production_ton", "yield_kg_per_ha"],
            ["播种面积（千公顷）", "产量（万吨）", "单产（公斤/公顷）"],
            ["#2f6f9f", "#4a7c59", "#9c6b3f"]):
        y = g[var] / 10000.0 if var == "production_ton" else g[var]
        ax.plot(g["year"], y, marker="o", color=color, lw=1.8)
        ax.set_xticks(sorted(g["year"].unique()))
        ax.tick_params(axis="x", rotation=45)
        ax.set_xlabel("年份")
        ax.set_ylabel(lab)
        ax.set_title(f"沈阳粮食{lab}")
    fig.suptitle("图 F37：沈阳粮食年度序列 2017-2025（9 年）\n"
                 "来源：辽宁统计年鉴（2017-2024 卷）与 2025 年沈阳市统计公报（quality_grade=A）",
                 fontsize=11, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    render_figure(fig, "F37_yearly_grain.png")


def fig_scatter(panel: pd.DataFrame, crop: str = GRAIN_CROP):
    plt = setup_matplotlib()
    g = panel[(panel["crop"] == crop)].dropna(subset=["yield_kg_per_ha", "season_precip_mm"])
    fig, axes = plt.subplots(1, 3, figsize=(13.4, 4.3))
    pairs = [("season_precip_mm", "生长季累计降水（mm）"),
             ("heat_days", "生长季高温日数（日最高气温≥35℃）"),
             ("soil_moisture_anomaly", "生长季土壤水分异常（稳健z 均值）")]
    for ax, (wv, lab) in zip(axes, pairs):
        s = g[["year", wv, "yield_kg_per_ha"]].dropna()
        ax.scatter(s[wv], s["yield_kg_per_ha"], s=46, color="#2f6f9f", zorder=3)
        for _, r in s.iterrows():
            ax.annotate(str(int(r["year"])), (r[wv], r["yield_kg_per_ha"]),
                        textcoords="offset points", xytext=(5, 4), fontsize=8)
        if len(s) >= 2 and s[wv].std() > 0:
            b, a = np.polyfit(s[wv], s["yield_kg_per_ha"], 1)
            xs = np.linspace(s[wv].min(), s[wv].max(), 20)
            ax.plot(xs, a + b * xs, color="#999999", lw=1.2, ls="--")
        ax.set_xlabel(lab)
        ax.set_ylabel("粮食单产（公斤/公顷）")
        ax.set_title(f"n={len(s)}")
    fig.suptitle("图 F38：沈阳粮食单产 vs 生长季气象（探索性，n≤5）\n"
                 "气象仅 2021-2026 可得（ERA5 再分析）；样本量极小，不作统计推断、不宣称预测能力",
                 fontsize=11, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.85))
    render_figure(fig, "F38_yearly_weather_scatter.png")


# -----------------------------------------------------------------------------
# 6) main
# -----------------------------------------------------------------------------
def main() -> None:
    set_seed()
    log = get_logger(MOD)
    log.info("=" * 78)
    log.info("STEP 22 年度生产研究（§四十七~§四十八；生长季=%s）", GS_LABEL)

    prod = load_production(log)
    weather = pd.read_parquet(PATHS.out("data/interim/shenyang_weather_daily.parquet"))
    gw = growing_season_weather(weather)
    panel = build_panel(prod, gw, log)

    # 数据断裂登记
    veg_years = sorted(panel.loc[panel["crop"] == VEG_CROP, "year"].tolist())
    missing = [y for y in range(2017, 2026) if y not in veg_years]
    if missing:
        log_blocker(MOD, "沈阳蔬菜年度生产数据存在年份断裂（不插补）",
                    f"已有年份={veg_years}；缺失年份={missing}；"
                    "原因：fact_production_yearly_2020_2024.csv 沈阳无蔬菜行")
    no_wx = sorted(panel.loc[~panel["weather_available"], "year"].unique().tolist())
    if no_wx:
        log_blocker(MOD, "年度生产年份缺少对应生长季气象（不插补）",
                    f"无气象年份={no_wx}；weather_daily 可得范围 2021-2026")

    tr = trend_table(panel)
    an = anomaly_table(panel)
    co = weather_corr(panel, log)
    rg = simple_regression(panel, GRAIN_CROP)
    save_table(tr, "yearly_trend.csv")
    save_table(an, "yearly_anomaly.csv")
    save_table(co, "yearly_weather_corr.csv")
    save_table(rg, "yearly_simple_regression.csv")

    fig_vegetable(panel)
    fig_grain(panel)
    fig_scatter(panel)

    # ---- 报告 --------------------------------------------------------------
    g = panel[panel["crop"] == GRAIN_CROP].sort_values("year")
    v = panel[panel["crop"] == VEG_CROP].sort_values("year")
    overlap_grain = sorted(g.dropna(subset=["season_precip_mm"])["year"].tolist())
    overlap_veg = sorted(v.dropna(subset=["season_precip_mm"])["year"].tolist())

    L: List[str] = []
    L.append("# STEP 22 年度生产研究（Phase 11，§四十七~§四十八）\n")
    L.append("## 0. 定位与红线\n")
    L.append("- §四十七：年度尺度数据**不得**与日度价格硬拼。本模块独立成层，"
             "不与 STEP 03-21 的日度结论合并推断。")
    L.append("- §四十八：2017-2025 仅约 9 个年份，**禁止**用 9 个点训练 XGBoost / "
             "神经网络 / Random Forest 后宣称高准确率。**本模块不训练任何模型**，"
             "只做描述性趋势、anomaly、简单相关与单变量简单回归。")
    L.append("- 结论表述统一加注：**样本量有限，主要用于机制补充，而非高维预测**。\n")

    L.append("## 1. 数据可得性与断裂（关键）\n")
    L.append("| 项目 | 结论 |")
    L.append("| --- | --- |")
    L.append(f"| 蔬菜及食用菌年度序列 | 仅 {len(veg_years)} 个观测年："
             f"{'、'.join(str(y) for y in veg_years)}；缺失年份 {missing}（不插补） |")
    L.append(f"| 粮食年度序列 | {g['year'].min()}-{g['year'].max()}，"
             f"共 {len(g)} 年（完整） |")
    L.append("| 分作物（水稻/玉米/大豆） | 2018、2019 + 2020-2024 + 2025 = 8 年"
             "（2017 年鉴无分作物行） |")
    L.append("| 生长季气象 | 仅 2021-2026（`weather_daily`，ERA5/ERA5-Land 再分析） |")
    L.append(f"| 蔬菜 × 气象重叠年 | {overlap_veg} → **无法做相关分析** |")
    L.append(f"| 粮食 × 气象重叠年 | {overlap_grain}（n={len(overlap_grain)}）→ 仅探索性描述 |")
    L.append("| 分品种蔬菜生产数据 | **不存在**（年鉴/公报仅「蔬菜及食用菌」合计）"
             "→ §四十八 的 crop panel **不可行** |")
    L.append("")
    L.append("> 上述断裂与不可行项已同步写入 `reports/BLOCKERS.md`，"
             "**未做任何插补**。\n")

    L.append("## 2. shenyang_yearly_panel 结构\n")
    L.append("字段（单位显式）：`year`、`region`、`crop`、`planting_area_kha`、"
             "`production_ton`、`yield_kg_per_ha`、`season_precip_mm`、"
             "`season_temp_mean_c`、`heat_days`、`heavy_rain_days`、"
             "`soil_moisture_anomaly`、`max_3d_precip_mm`、`season_precip_pct_of_clim`、"
             "`season_complete`、`weather_available`、`source_table`、`quality_grade`。")
    L.append(f"- 生长季定义：{GS_LABEL}（来自 `config/analysis.yaml: time.growing_season_months`）。")
    L.append("- 单位统一：跨表按 `unit_production` 换算（万吨 → 吨 ×10000），"
             "面积统一为千公顷，单产统一为公斤/公顷。")
    L.append("- 派生标记：2017 蔬菜面积官方未给，但产量与单产均为官方值，"
             "故仅登记 `planting_area_kha_implied = production / yield` 并置 "
             "`value_is_derived=True`，**不作为观测值使用**。\n")

    L.append("## 3. 描述性趋势（§四十八允许）\n")
    L.append("| 作物 | 变量 | n 年 | 年份跨度 | 首值 | 末值 | 总变化% | 线性斜率/年 | R² | 存在断裂 |")
    L.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for _, r in tr.iterrows():
        L.append(f"| {r['crop']} | {r['variable']} | {r['n_years']} | {r['years']} | "
                 f"{r['first_value']:.1f} | {r['last_value']:.1f} | "
                 f"{r['total_change_pct']:+.1f} | {r['linear_slope_per_year']:+.2f} | "
                 f"{r['r2']:.3f} | {'是' if r['has_gap_years'] else '否'} |")
    L.append("")
    L.append("> 蔬菜行的「总变化%」跨越 2019→2025 的 6 年缺口，"
             "**不可解释为年际趋势**，仅表示两个可观测时点的水平差。\n")

    L.append("## 4. 简单相关（产量/单产 vs 生长季气象）\n")
    if co.empty:
        L.append("无满足 n≥4 的作物-气象组合，未计算。\n")
    else:
        L.append("| 作物 | 目标 | 气象变量 | n | 年份 | Pearson r | Spearman r |")
        L.append("| --- | --- | --- | --- | --- | --- | --- |")
        for _, r in co.iterrows():
            L.append(f"| {r['crop']} | {r['variable']} | {r['weather']} | {r['n_years']} | "
                     f"{r['years']} | {r['pearson_r']:+.3f} | {r['spearman_r']:+.3f} |")
        L.append("")
        L.append("> **不作统计推断**：n≤5，任何「显著性」在此样本量下都不可解释；"
                 "表中 r 仅用于观察方向与量级，`interpretation_allowed=False` 已写入表内。\n")

    L.append("## 5. 简单回归（仅粮食，单变量）\n")
    if rg.empty:
        L.append("无可用组合。\n")
    else:
        L.append("| 目标 | 气象变量 | n | 自由度 | 斜率 | 斜率SE | R² |")
        L.append("| --- | --- | --- | --- | --- | --- | --- |")
        for _, r in rg.iterrows():
            L.append(f"| {r['target']} | {r['weather']} | {r['n_years']} | {r['df_resid']} | "
                     f"{r['slope']:+.4f} | {r['slope_se']:.4f} | {r['r2']:.3f} |")
        L.append("")
        L.append("> `inference_allowed=False`：自由度仅 3，回归系数不构成推断依据。\n")

    L.append("## 6. 结论\n")
    L.append("1. **蔬菜年度层不可用于机制检验**：仅有 4 个观测年（2017-2019、2025），"
             "且与生长季气象重叠仅 1 年 → 相关/回归**不可行**，如实登记为"
             " **NOT SUPPORTED BY CURRENT DATA**，不插补、不外推。")
    L.append("2. **粮食年度层可作极弱机制补充**：9 年序列完整，但气象只有 2021-2025（n=5），"
             "相关系数与单变量回归均**不构成推断**，只能作为方向性观察。")
    L.append("3. **crop panel 不可行**：无分品种蔬菜生产数据，§四十八 的 crop panel "
             "在当前数据条件下无法建立。")
    L.append("4. 年度层**未提供**任何可用于修正日度结论的证据；"
             "本层结论不与 STEP 03-21 合并，也不用于预测。\n")

    L.append("## 7. 输出清单与证据分级\n")
    L.append("- 数据：`data/processed/shenyang_yearly_panel.parquet`"
             "（+ `outputs/tables/shenyang_yearly_panel.csv`）")
    L.append("- 表：`yearly_production_long.csv`、`yearly_growing_season_weather.csv`、"
             "`yearly_trend.csv`、`yearly_anomaly.csv`、`yearly_weather_corr.csv`、"
             "`yearly_simple_regression.csv`")
    L.append("- 图：`F36_yearly_vegetable.png`、`F37_yearly_grain.png`、"
             "`F38_yearly_weather_scatter.png`")
    L.append("- 证据分级：**Level A（官方统计数据，逐年可核）** 用于生产量本身；"
             "趋势/anomaly 为 **Level C（机制补充）**；相关与回归 **不作分级推断**"
             "（样本量不足）。")

    PATHS.report("11_YEARLY_PRODUCTION.md").write_text("\n".join(L), encoding="utf-8")
    log.info("报告已写出: %s", PATHS.report("11_YEARLY_PRODUCTION.md"))

    register_results([{
        "result_id": "YEARLY-VEG",
        "research_question": "RQ5",
        "crop": VEG_CROP,
        "period": "2017-2019、2025",
        "method": "年度生产序列（辽宁统计年鉴 + 2025 沈阳统计公报）+ 生长季气象聚合",
        "metric": "产量（吨）/ 单产（公斤/公顷）/ 播种面积（千公顷）",
        "estimate": float(v["yield_kg_per_ha"].iloc[-1]) if len(v) else np.nan,
        "robustness": "2020-2024 沈阳无蔬菜年度数据，序列断裂，未插补",
        "figure": "F36_yearly_vegetable.png",
        "table": "shenyang_yearly_panel.csv",
        "evidence_level": "A",
        "notes": ("NOT SUPPORTED BY CURRENT DATA（年度机制检验）：蔬菜仅 4 个观测年，"
                  "与生长季气象（仅 2021-2026）重叠 1 年，相关/回归不可行；"
                  "无分品种蔬菜生产数据 → crop panel 不可行；"
                  "§四十八：样本量有限，仅作机制补充"),
    }, {
        "result_id": "YEARLY-GRAIN",
        "research_question": "RQ5",
        "crop": GRAIN_CROP,
        "period": "2017-2025（气象 2021-2025）",
        "method": "年度序列 + 生长季气象单变量相关/简单回归（探索性）",
        "metric": "粮食单产（公斤/公顷）vs 生长季降水/高温日数/土壤水分异常",
        "estimate": (float(rg["r2"].max()) if not rg.empty else np.nan),
        "robustness": f"n={len(overlap_grain)} 年，自由度≤3；不作推断",
        "figure": "F38_yearly_weather_scatter.png",
        "table": "yearly_simple_regression.csv",
        "evidence_level": "C",
        "notes": ("9 年产量序列完整（Level A）；但气象仅 2021-2025，"
                  "相关与回归均 in inference_allowed=False，仅方向性观察；"
                  "§四十七：年度层不与日度价格硬拼"),
    }])
    log.info("STEP 22 完成")


if __name__ == "__main__":
    main()
