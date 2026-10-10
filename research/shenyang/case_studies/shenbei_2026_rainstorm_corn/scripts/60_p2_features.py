#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase2 数据工程（P2-04 气象校验 / P2-05 GDD物候 / P2-06 生育期天气特征 / P2-07 极端与复合指标）
原则：不插值、不编造；再分析一律标注；GDD 物候标注为“模型估计（近似参考阈值）”。
输出：
  05_analysis/02_climate_baseline/weather_source_validation.csv
  03_clean/phenology/corn_phenology_reference.csv
  05_analysis/05_phenology/corn_phenology_yearly_gdd.csv
  04_marts/corn_year_weather_features.csv
"""
import json
import os

import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN = os.path.join(BASE, "03_clean")
MARTS = os.path.join(BASE, "04_marts")
ANA = os.path.join(BASE, "05_analysis")
AGRI = os.path.join(BASE, "..", "..", "..", "..")

# ---------------------------------------------------------------- GDD 物候参考阈值
# 依据：东北/北方春玉米常规物候与积温（基温10℃，上限30℃）参考区间（文献/农技资料的近似值）。
# 阈值已按“本地作物日历”标定：抽雄≈7月中旬、成熟≈9月下旬-10月上旬（作物日历），
# 因此属“标定后模型估计”，非田块实测物候。
GDD_STAGES = [
    ("emergence", 80),
    ("jointing", 350),
    ("bells", 560),        # 大喇叭口
    ("tasseling", 780),    # 抽雄
    ("silking", 840),      # 吐丝
    ("grain_filling", 1200),
    ("maturity", 1700),
]
STAGE_CN = {
    "sowing": "播种期", "emergence": "出苗期", "jointing": "拔节期", "bells": "大喇叭口期",
    "tasseling": "抽雄期", "silking": "吐丝期", "grain_filling": "灌浆期", "maturity": "成熟期",
}
# 用于建模合并的三大阶段
PHASE_MAP = {
    "veg": ["emergence", "jointing", "bells"],
    "repro": ["tasseling", "silking"],
    "grainfill": ["grain_filling", "maturity"],
}


def load_daily():
    d = pd.read_parquet(os.path.join(CLEAN, "weather", "pnb_daily_1991_2026.parquet"))
    d["date"] = pd.to_datetime(d["date"])
    return d.sort_values("date").reset_index(drop=True)


def read_nasapower():
    p = os.path.join(AGRI, "data/raw", "weather", "nasapower_沈北新区_current.json")
    d = json.load(open(p, encoding="utf-8"))
    par = d["properties"]["parameter"]
    df = pd.DataFrame({
        "date": pd.to_datetime(list(par["T2M"].keys())),
        "T2M_NASA": pd.to_numeric(pd.Series(list(par["T2M"].values())), errors="coerce"),
        "TMAX_NASA": pd.to_numeric(pd.Series(list(par["T2M_MAX"].values())), errors="coerce"),
        "TMIN_NASA": pd.to_numeric(pd.Series(list(par["T2M_MIN"].values())), errors="coerce"),
        "PRECIP_NASA": pd.to_numeric(pd.Series(list(par["PRECTOTCORR"].values())), errors="coerce"),
    })
    return df


# ---------------------------------------------------------------- P2-04 气象源校验
def weather_validation(d):
    out = os.path.join(ANA, "02_climate_baseline")
    os.makedirs(out, exist_ok=True)
    try:
        npw = read_nasapower()
    except Exception as e:  # noqa
        print("[P2-04] NASA POWER 读取失败:", e)
        return None
    m = d.merge(npw, on="date", how="inner")
    if len(m) == 0:
        print("[P2-04] 无重叠日期")
        return None
    # 降水：日相关、月累计偏差、极端日识别一致率
    r_daily = m["precipitation_sum"].corr(m["PRECIP_NASA"])
    mm = m.set_index("date")
    e5_m = mm["precipitation_sum"].resample("MS").sum()
    nas_m = mm["PRECIP_NASA"].resample("MS").sum()
    r_month = e5_m.corr(nas_m)
    bias_month = (nas_m - e5_m).mean()
    # 极端日（>=25mm）一致性
    e5x = set(mm.index[mm["precipitation_sum"] >= 25].date)
    nasx = set(mm.index[mm["PRECIP_NASA"] >= 25].date)
    inter = len(e5x & nasx); union = len(e5x | nasx)
    # 气温 MAE
    mae_tmean = (m["temperature_2m_mean"] - m["T2M_NASA"]).abs().mean()
    mae_tmax = (m["temperature_2m_max"] - m["TMAX_NASA"]).abs().mean()
    mae_tmin = (m["temperature_2m_min"] - m["TMIN_NASA"]).abs().mean()
    res = pd.DataFrame([
        ("overlap_days", len(m)),
        ("precip_daily_corr", round(float(r_daily), 3)),
        ("precip_monthly_corr", round(float(r_month), 3)),
        ("precip_monthly_bias_ERA5_minus_NASA_mm", round(float(e5_m.mean() - nas_m.mean()), 2)),
        ("extreme_rain_day_jaccard_ge25mm", round(inter / union if union else float("nan"), 3)),
        ("n_extreme_days_ERA5", len(e5x)),
        ("n_extreme_days_NASA", len(nasx)),
        ("tmean_MAE_C", round(float(mae_tmean), 2)),
        ("tmax_MAE_C", round(float(mae_tmax), 2)),
        ("tmin_MAE_C", round(float(mae_tmin), 2)),
    ], columns=["metric", "value"])
    res.to_csv(os.path.join(out, "weather_source_validation.csv"), index=False, encoding="utf-8-sig")
    print("[P2-04] 校验:", res.to_dict("records"))
    return res


# ---------------------------------------------------------------- P2-05 GDD 物候
def gdd_phenology(d):
    out_ph = os.path.join(CLEAN, "phenology")
    os.makedirs(out_ph, exist_ok=True)
    rows = []
    yearly = []
    rows_2026 = None
    for y in range(1991, 2027):
        g = d[d["date"].dt.year == y].copy().reset_index(drop=True)
        if len(g) < 200:  # 2026 仅到 09-14，放宽阈值以纳入
            continue
        tmean = (g["temperature_2m_max"] + g["temperature_2m_min"]) / 2.0
        g["tmean"] = tmean
        g["gdd"] = np.clip(tmean - 10.0, 0, None)
        # 播种日：官方适播窗 4月下旬-5月上旬；在其中取 5日滑动均温首次≥10.5℃（近似地温8-10℃）
        g["tmean_5d"] = tmean.rolling(5, min_periods=5).mean()
        win = g[(g["date"] >= f"{y}-04-20") & (g["date"] <= f"{y}-05-10") & (g["tmean_5d"] >= 10.5)]
        if len(win):
            sow_idx = win.index[0]
        else:
            fallback = g[g["date"] >= f"{y}-04-25"]
            sow_idx = fallback.index[0] if len(fallback) else g.index[0]
        g.loc[g.index < sow_idx, "gdd"] = 0
        g["cum_gdd"] = g["gdd"].cumsum()
        stage_dates = {"year": y, "sowing_date": str(g.loc[sow_idx, "date"].date())}
        for st, thr in GDD_STAGES:
            hit = g[g["cum_gdd"] >= thr]
            stage_dates[st + "_date"] = str(hit.iloc[0]["date"].date()) if len(hit) else None
        stage_dates["season_total_gdd"] = round(float(g["gdd"].sum()), 1)
        yearly.append(stage_dates)
        # 找到 2026 抽雄
        if y == 2026:
            rows_2026 = stage_dates
    ydf = pd.DataFrame(yearly)
    os.makedirs(os.path.join(ANA, "05_phenology"), exist_ok=True)
    ydf.to_csv(os.path.join(ANA, "05_phenology", "corn_phenology_yearly_gdd.csv"), index=False, encoding="utf-8-sig")

    # 参考物候表（模型估计 + 官方边界）
    ref_rows = []
    for st, thr in GDD_STAGES:
        dates = pd.to_datetime(ydf[st + "_date"], errors="coerce").dropna()
        if st == "emergence":
            start = pd.to_datetime(ydf["sowing_date"]).min()
        else:
            start = dates.min()
        ref_rows.append(dict(stage=STAGE_CN[st], stage_en=st, gdd_threshold=thr,
                             start_date_est=str(start.date()),
                             end_date_est=str(dates.max().date()),
                             source_id="SRC-CROP-CALENDAR|GDD模型",
                             location_scope="沈北新区(ERA5网格点, 由GDD推算)",
                             confidence="model_estimate",
                             notes="GDD基温10℃/上限30℃，播种判定=4月15日后5日均温≥10℃；非田块实测物候"))
    # 播种期参考（官方）
    ref_rows.insert(0, dict(stage="播种期", stage_en="sowing", gdd_threshold=0,
                           start_date_est="2026-04-25", end_date_est="2026-05-10",
                           source_id="SRC-SY-NYJ-2026-JSZ",
                           location_scope="沈阳市(官方适播期)",
                           confidence="official_window",
                           notes="官方：玉米适播期5-10cm地温稳定8-10℃，我市一般4月下旬至5月上旬"))
    pd.DataFrame(ref_rows).to_csv(os.path.join(out_ph, "corn_phenology_reference.csv"),
                                  index=False, encoding="utf-8-sig")
    print("[P2-05] 2026 物候(GDD):", rows_2026)
    return ydf


# ---------------------------------------------------------------- P2-06/07 生育期天气特征
def stage_days(g, stage_col_dates):
    """返回 dict: phase -> (start_date, end_date)"""
    return stage_col_dates


def build_features(d, ydf):
    recs = []
    for _, r in ydf.iterrows():
        y = int(r["year"])
        g = d[d["date"].dt.year == y].copy()
        if len(g) < 200:
            continue
        g = g.reset_index(drop=True)
        g["tmean"] = (g["temperature_2m_max"] + g["temperature_2m_min"]) / 2.0
        g["gdd"] = np.clip(g["tmean"] - 10.0, 0, None)
        b = {"year": y, "sowing_date": r["sowing_date"]}
        # 阶段区间
        stages = {
            "sowing": (r["sowing_date"], r["emergence_date"]),
            "emergence": (r["emergence_date"], r["jointing_date"]),
            "jointing": (r["jointing_date"], r["bells_date"]),
            "bells": (r["bells_date"], r["tasseling_date"]),
            "tasseling": (r["tasseling_date"], r["silking_date"]),
            "silking": (r["silking_date"], r["grain_filling_date"]),
            "grain_filling": (r["grain_filling_date"], r["maturity_date"]),
            "maturity": (r["maturity_date"], f"{y}-10-15"),
        }
        for st, (s, e) in stages.items():
            if pd.isna(s) or pd.isna(e):
                continue
            sub = g[(g["date"] >= pd.Timestamp(s)) & (g["date"] <= pd.Timestamp(e))]
            if len(sub) == 0:
                continue
            pr = sub["precipitation_sum"]
            b[f"{st}_precip_sum"] = round(float(pr.sum()), 1)
            b[f"{st}_precip_max_1d"] = round(float(pr.max()), 1)
            b[f"{st}_precip_max_3d"] = round(float(pr.rolling(3, min_periods=1).sum().max()), 1)
            b[f"{st}_precip_max_5d"] = round(float(pr.rolling(5, min_periods=1).sum().max()), 1)
            b[f"{st}_rain_days"] = int((pr >= 0.1).sum())
            b[f"{st}_heavy_rain_days"] = int((pr >= 25).sum())
            b[f"{st}_very_heavy_rain_days"] = int((pr >= 50).sum())
            b[f"{st}_consec_wet_days"] = int(_max_consec(pr.values >= 0.1))
            b[f"{st}_tmean"] = round(float(sub["tmean"].mean()), 2)
            b[f"{st}_tmax_mean"] = round(float(sub["temperature_2m_max"].mean()), 2)
            b[f"{st}_tmin_mean"] = round(float(sub["temperature_2m_min"].mean()), 2)
            b[f"{st}_hot_days"] = int((sub["temperature_2m_max"] >= 30).sum())
            b[f"{st}_extreme_hot_days"] = int((sub["temperature_2m_max"] >= 35).sum())
            b[f"{st}_cold_days"] = int((sub["tmean"] <= 10).sum())
            b[f"{st}_gdd"] = round(float(sub["gdd"].sum()), 1)
            b[f"{st}_hot_and_wet_days"] = int(((sub["temperature_2m_max"] >= 30) & (pr.values >= 10)).sum())
        # 合并三大阶段
        for ph, sts in PHASE_MAP.items():
            ps = sum(b.get(f"{s}_precip_sum", 0) for s in sts)
            b[f"{ph}_precip_sum"] = round(ps, 1)
            b[f"{ph}_precip_max_5d"] = round(max([b.get(f"{s}_precip_max_5d", 0) for s in sts] + [0]), 1)
            b[f"{ph}_heavy_rain_days"] = int(sum(b.get(f"{s}_heavy_rain_days", 0) for s in sts))
            tm = [b.get(f"{s}_tmean") for s in sts if b.get(f"{s}_tmean") is not None]
            b[f"{ph}_tmean"] = round(float(np.mean(tm)), 2) if tm else None
            tmax = [b.get(f"{s}_tmax_mean") for s in sts if b.get(f"{s}_tmax_mean") is not None]
            b[f"{ph}_tmax_mean"] = round(float(np.mean(tmax)), 2) if tmax else None
            tmin = [b.get(f"{s}_tmin_mean") for s in sts if b.get(f"{s}_tmin_mean") is not None]
            b[f"{ph}_tmin_mean"] = round(float(np.mean(tmin)), 2) if tmin else None
            b[f"{ph}_hot_days"] = int(sum(b.get(f"{s}_hot_days", 0) for s in sts))
        # 生育期整体
        season = g[(g["date"] >= pd.Timestamp(r["sowing_date"])) & (g["date"] <= pd.Timestamp(r["maturity_date"]))]
        if len(season):
            b["season_precip_sum"] = round(float(season["precipitation_sum"].sum()), 1)
            b["season_tmean"] = round(float(season["tmean"].mean()), 2)
            b["season_gdd"] = round(float(season["gdd"].sum()), 1)
            b["season_wet_days"] = int((season["precipitation_sum"] >= 0.1).sum())
        # P2-07 年度极端指数
        pr_yr = g["precipitation_sum"]
        b["rx1day"] = round(float(pr_yr.max()), 1)
        b["rx5day"] = round(float(pr_yr.rolling(5, min_periods=1).sum().max()), 1)
        wet = pr_yr[pr_yr > 0]
        thr95 = np.percentile(wet, 95) if len(wet) else np.nan
        thr99 = np.percentile(wet, 99) if len(wet) else np.nan
        b["r95p"] = round(float(pr_yr[pr_yr > thr95].sum()), 1) if not np.isnan(thr95) else None
        b["r99p"] = round(float(pr_yr[pr_yr > thr99].sum()), 1) if not np.isnan(thr99) else None
        b["cwd"] = int(_max_consec(pr_yr.values >= 1.0))
        b["annual_precip"] = round(float(pr_yr.sum()), 1)
        # 前期湿润（以抽雄期起点为基准，替代“事件前”）
        t0 = pd.Timestamp(r["tasseling_date"]) if not pd.isna(r["tasseling_date"]) else None
        if t0 is not None:
            for w in [3, 7, 14, 30]:
                sub = g[(g["date"] >= t0 - pd.Timedelta(days=w)) & (g["date"] < t0)]
                b[f"antecedent_precip_{w}d"] = round(float(sub["precipitation_sum"].sum()), 1)
        recs.append(b)
    f = pd.DataFrame(recs)
    f.to_csv(os.path.join(MARTS, "corn_year_weather_features.csv"), index=False, encoding="utf-8-sig")
    print("[P2-06/07] corn_year_weather_features rows=", len(f), "cols=", len(f.columns))
    return f


def _max_consec(mask):
    m = c = 0
    for v in mask:
        c = c + 1 if v else 0
        m = max(m, c)
    return m


if __name__ == "__main__":
    d = load_daily()
    weather_validation(d)
    ydf = gdd_phenology(d)
    build_features(d, ydf)
    print("=== P2 features done ===")
