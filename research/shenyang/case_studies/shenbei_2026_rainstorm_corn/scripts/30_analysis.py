#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Step10-13：
  10 暴雨异常度（历史气候基线、百分位、Z-score、滚动累计、Rx1day/Rx5day/R95p/CWD、SPI-1）
  11 沈北玉米历史生产基线小结
  12 暴雨—玉米物候暴露
  13 灾害传导机制证据清单
输出到 05_analysis/* 与 08_figures/*
"""
import os

import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN = os.path.join(BASE, "03_clean")
MARTS = os.path.join(BASE, "04_marts")
ANA = os.path.join(BASE, "05_analysis")
FIG = os.path.join(BASE, "08_figures")

EVENT_D = pd.Timestamp("2026-07-13")
WS, WE = pd.Timestamp("1991-01-01"), pd.Timestamp("2020-12-31")  # 1991-2020 基线


def _ensure(p):
    os.makedirs(p, exist_ok=True)


def load_daily():
    d = pd.read_parquet(os.path.join(CLEAN, "weather", "pnb_daily_1991_2026.parquet"))
    d["date"] = pd.to_datetime(d["date"])
    return d.sort_values("date").reset_index(drop=True)


# ---------------------------------------------------------------- 气候基线
def climate_baseline(d):
    out = os.path.join(ANA, "02_climate_baseline")
    _ensure(out)
    base = d[(d["date"] >= WS) & (d["date"] <= WE)].copy()
    jul = base[base["date"].dt.month == 7]
    series = {}
    for q in [50, 90, 95, 99, 99.9]:
        series[f"jul_daily_precip_p{q}"] = float(np.percentile(jul["precipitation_sum"], q))
    series.update({
        "jul_daily_precip_mean": float(jul["precipitation_sum"].mean()),
        "jul_daily_precip_std": float(jul["precipitation_sum"].std(ddof=1)),
        "jul_daily_precip_max": float(jul["precipitation_sum"].max()),
        "jul_monthly_total_mean": float(jul.groupby(jul["date"].dt.year)["precipitation_sum"].sum().mean()),
        "jul_monthly_total_p90": float(np.percentile(jul.groupby(jul["date"].dt.year)["precipitation_sum"].sum(), 90)),
        "jul_monthly_total_p99": float(np.percentile(jul.groupby(jul["date"].dt.year)["precipitation_sum"].sum(), 99)),
        "jul_wetday_freq": float((jul["precipitation_sum"] >= 0.1).mean()),
        "annual_precip_mean_1991_2020": float(base.groupby(base["date"].dt.year)["precipitation_sum"].sum().mean()),
    })
    pd.Series(series).to_frame("value").to_csv(os.path.join(out, "climate_baseline_july.csv"), encoding="utf-8-sig")
    print("[ana] climate_baseline_july:", {k: round(v, 2) for k, v in series.items()})
    return series, base, jul


# ---------------------------------------------------------------- 极端降雨
def extreme_rainfall(d, base, jul, cb):
    out = os.path.join(ANA, "03_extreme_rainfall")
    _ensure(out)

    # 年度极端指数（1991-2020 基线期）
    rows = []
    for y, g in base.groupby(base["date"].dt.year):
        pr = g["precipitation_sum"].values
        roll5 = pd.Series(pr).rolling(5, min_periods=1).sum().values
        wet = pr >= 1.0
        # 最大连续湿润日
        cwd = mx = 0
        for w in wet:
            mx = mx + 1 if w else 0
            cwd = max(cwd, mx)
        r95 = np.percentile(pr[pr > 0], 95) if (pr > 0).sum() > 0 else np.nan
        rows.append(dict(year=y, Rx1day=pr.max(), Rx5day=roll5.max(),
                         R95p=pr[pr > r95].sum() if not np.isnan(r95) else np.nan,
                         CWD=cwd, annual_precip=pr.sum()))
    idx = pd.DataFrame(rows)
    idx.to_csv(os.path.join(out, "extreme_indices_annual_1991_2020.csv"), index=False, encoding="utf-8-sig")

    # 2026 事件百分位
    s = cb["jul_daily_precip_mean"], cb["jul_daily_precip_std"]
    jul_daily_2020 = jul["precipitation_sum"]
    v13 = float(d.loc[d["date"] == EVENT_D, "precipitation_sum"].iloc[0])
    ev = pd.DataFrame([
        ("2026-07-13 日降水", v13, "mm",
         float((jul_daily_2020 < v13).mean() * 100),
         float((v13 - s[0]) / s[1]), "ERA5网格点再分析"),
    ], columns=["item", "value", "unit", "percentile_vs_1991_2020_july", "z_score", "note"])
    # 7月月总量
    d26 = d[(d["date"] >= "2026-07-01") & (d["date"] <= "2026-07-31")]
    jul26_total = float(d26["precipitation_sum"].sum())
    july_totals = jul.groupby(jul["date"].dt.year)["precipitation_sum"].sum()
    mu, sd = july_totals.mean(), july_totals.std(ddof=1)
    ev = pd.concat([ev, pd.DataFrame([
        ("2026年7月月总降水", jul26_total, "mm",
         float((july_totals < jul26_total).mean() * 100), float((jul26_total - mu) / sd),
         "ERA5网格点再分析；1991-2020 各年7月总量分布")],
        columns=ev.columns)], ignore_index=True)
    # 5日累计（Rx5day）2026 vs 历史
    d26w = d[(d["date"] >= "2026-07-01") & (d["date"] <= "2026-07-31")].copy()
    rx5_2026 = d26w["precipitation_sum"].rolling(5, min_periods=1).sum().max()
    ev = pd.concat([ev, pd.DataFrame([
        ("2026年7月 Rx5day（最大5日累计）", float(rx5_2026), "mm",
         float((idx["Rx5day"] < rx5_2026).mean() * 100), float((rx5_2026 - idx["Rx5day"].mean()) / idx["Rx5day"].std(ddof=1)),
         "ERA5网格点再分析")], columns=ev.columns)], ignore_index=True)
    ev.to_csv(os.path.join(out, "extreme_rainfall_2026.csv"), index=False, encoding="utf-8-sig")

    # SPI-1（7月，基于1991-2025各年7月总量，Gamma拟合）
    july_totals_all = d[(d["date"] >= "1991-01-01") & (d["date"] <= "2025-12-31")].copy()
    jt = july_totals_all[july_totals_all["date"].dt.month == 7].groupby(
        july_totals_all[july_totals_all["date"].dt.month == 7]["date"].dt.year)["precipitation_sum"].sum()
    try:
        from scipy.stats import gamma
        a, loc, scale = gamma.fit(jt.values, floc=0)
        spi = gamma.cdf(jul26_total, a, loc, scale)
        record = {"jul_total_2026_mm": jul26_total, "gamma_a": a, "gamma_scale": scale,
                  "spi1_percentile": spi, "period": "1991-2025 各年7月总量"}
        pd.Series(record).to_frame("value").to_csv(os.path.join(out, "spi1_july_2026.csv"), encoding="utf-8-sig")
    except Exception as e:  # noqa
        pd.Series({"note": f"scipy unavailable: {e}"}).to_frame("value").to_csv(
            os.path.join(out, "spi1_july_2026.csv"), encoding="utf-8-sig")
    print("[ana] extreme_rainfall_2026:", ev[["item", "value", "percentile_vs_1991_2020_july", "z_score"]].to_dict("records"))
    return ev


# ---------------------------------------------------------------- 物候暴露
def phenology_exposure():
    out = os.path.join(ANA, "05_phenology")
    _ensure(out)
    ph = pd.read_csv(os.path.join(CLEAN, "phenology", "corn_phenology_2026.csv"))
    feat = pd.read_csv(os.path.join(MARTS, "rainfall_event_features.csv"))
    feat["date"] = pd.to_datetime(feat["date"])
    ev = feat[(feat["date"] >= "2026-07-12") & (feat["date"] <= "2026-07-14")]
    recs = []
    for _, r in ph.iterrows():
        s, e = pd.Timestamp(r["start"]), pd.Timestamp(r["end"])
        overlap = ev[(ev["date"] >= s) & (ev["date"] <= e)]
        if len(overlap):
            recs.append(dict(stage=r["stage"], stage_start=r["start"], stage_end=r["end"],
                             stage_confidence=r["confidence"],
                             event_overlap_start=str(overlap["date"].min().date()),
                             event_overlap_end=str(overlap["date"].max().date()),
                             overlap_precip_mm=float(overlap["precip_mm"].sum()),
                             overlap_max_1h_mm=float(overlap["max_1h"].max()),
                             evidence=r["evidence"], source_id=r["source_id"]))
    df = pd.DataFrame(recs)
    df["event_2day_precip_mm"] = float(ev["precip_mm"].sum())
    df["note"] = "文献/区域粒度物候区间，非沈北2026实测物候；仅用于暴露判断"
    df.to_csv(os.path.join(out, "corn_phenology_exposure_2026.csv"), index=False, encoding="utf-8-sig")
    print("[ana] phenology exposure stages overlapping event:", list(df["stage"]) if len(df) else "NONE")
    return df


if __name__ == "__main__":
    d = load_daily()
    cb, base, jul = climate_baseline(d)
    extreme_rainfall(d, base, jul, cb)
    phenology_exposure()
    print("=== analysis done ===")
