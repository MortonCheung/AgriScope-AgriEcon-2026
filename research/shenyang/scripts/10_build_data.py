"""10_build_data.py — 在 v2 内重建分析数据（所有派生量在 v2 重算，不复用 v1 结论）。

产出：
  data/v2_market_daily.parquet     市场日度（10 品种 × 交易日）+ v2 去季节化异常 + 核心气象暴露
  data/v2_district_yearly.parquet 区县年度面板（A07/A08 用）+ v2 派生的气象暴露
  results/metrics/data_build.json  构建审计（行数/缺失/方法/AR(1)）

去季节化（v2 重算，方法沿用预注册的「留一年法历史同期中位数」）：
  expected(doy) = median( price | 同品种, doy±5 环形, 年份 ≠ 目标年 )
  anomaly       = price - expected
  scale         = 1.4826 × MAD( anomaly | 同品种, 年份 ≠ 目标年 )        # 稳健尺度，按年留一
  z             = anomaly / scale ;  pct = anomaly / expected × 100
无未来信息：计算某年基线时该年自身不进入。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _v2 import (DATA, CROPS, GS_MONTHS, METRICS, get_logger, load_district_panel,
                 load_district_weather_yearly, load_market_panel, load_weather_daily,
                 metrics_dump, save_table)

LOG = get_logger("10_build_data")
HALF = 5                     # doy ± 5
MIN_OBS = 8

# 核心气象暴露（当日值列名 → 统一名）
WX_MAP = {
    "precipitation": "precipitation", "temp_mean": "temp_mean", "temp_max": "temp_max",
    "temp_min": "temp_min", "temp_anomaly": "temp_anomaly", "vpd": "vpd",
    "humidity": "humidity", "humidity_z": "humidity_z", "wind_speed": "wind_speed",
    "soil_moisture_0_7": "soil_moisture_0_7", "soil_moisture_0_7_z": "soil_moisture_z",
    "temp_z": "temp_z", "dry_spell_days": "dry_spell_days", "wet_spell_days": "wet_spell_days",
    "radiation": "radiation", "et0": "et0", "pressure_msl": "pressure_msl",
    "cloud_cover": "cloud_cover", "dew_point": "dew_point", "sunshine_duration": "sunshine_duration",
}


def ring_dist(doy: np.ndarray, d: int) -> np.ndarray:
    return np.abs(((doy - d + 182) % 365) - 182)


def anomaly_v2(df: pd.DataFrame, var: str, log) -> pd.DataFrame:
    """按品种 × 目标年 计算 expected / anomaly / z / pct。

    **主口径 strict（无任何未来信息）**：基线只使用 **严格早于目标年** 的年份（doy±5 环形中位数）。
      理由：v1 的「留一年法」排除了目标年但**保留了未来年份**（1.1 审计问题 #10），
      对训练/早年年份构成未来信息泄漏 → v2 修正为严格口径。
    **对照口径 loo（v1 同法）**：排除目标年、保留其他所有年份，仅作稳健性对照。
    稳健尺度：1.4826×MAD，同样按「严格更早年份」/「非目标年」留一。
    """
    out = df[["date", "crop", var]].copy().sort_values(["crop", "date"]).reset_index(drop=True)
    out["year"] = out["date"].dt.year
    out["doy"] = np.minimum(out["date"].dt.dayofyear, 365)
    res = {}
    for tag in ("strict", "loo"):
        res[f"{tag}_exp"] = np.full(len(out), np.nan)
        res[f"{tag}_z"] = np.full(len(out), np.nan)
    for crop, g in out.groupby("crop"):
        idx = g.index.to_numpy()
        doy = g["doy"].to_numpy()
        yrs = g["year"].to_numpy()
        val = g[var].to_numpy(float)
        years = np.unique(yrs)
        for tag in ("strict", "loo"):
            exp_arr = res[f"{tag}_exp"]
            z_arr = res[f"{tag}_z"]
            # 第一步：为每一条观测算「其自身年份」的基线期望（基数集合因 tag 而异）
            e_all = np.full(len(g), np.nan)
            for y in years:
                base = (yrs < y) if tag == "strict" else (yrs != y)
                for i in np.flatnonzero(yrs == y):
                    m = base & (ring_dist(doy, doy[i]) <= HALF)
                    if m.sum() >= MIN_OBS:
                        b = np.nanmedian(val[m])
                        if np.isfinite(b) and b > 0:
                            e_all[i] = b
            exp_arr[idx] = e_all
            # 第二步：按目标年用「基线年份的异常」估稳健尺度，再标准化目标年观测
            for y in years:
                my = yrs == y
                base = (yrs < y) if tag == "strict" else (yrs != y)
                bm = base & np.isfinite(e_all)
                if bm.sum() < MIN_OBS:
                    continue
                a = val[bm] - e_all[bm]
                sc = 1.4826 * np.nanmedian(np.abs(a - np.nanmedian(a)))
                if np.isfinite(sc) and sc > 0:
                    z_arr[idx[my]] = (val[my] - e_all[my]) / sc
    out[f"{var}_expected"] = res["strict_exp"]              # 主口径
    out[f"{var}_anomaly"] = out[var] - res["strict_exp"]
    out[f"{var}_z"] = res["strict_z"]
    out[f"{var}_pct"] = np.where(res["strict_exp"] > 0,
                                 out[f"{var}_anomaly"] / res["strict_exp"] * 100, np.nan)
    out[f"{var}_z_loo"] = res["loo_z"]                       # 对照口径
    out[f"{var}_expected_loo"] = res["loo_exp"]
    log.info("  %s：strict z 有效 %d/%d（%.0f%%）；loo z 有效 %d",
             var, int(np.isfinite(out[f'{var}_z']).sum()), len(out),
             100 * np.isfinite(out[f"{var}_z"]).mean(), int(np.isfinite(out[f"{var}_z_loo"]).sum()))
    return out[["date", "crop", f"{var}_expected", f"{var}_anomaly", f"{var}_z", f"{var}_pct",
                f"{var}_expected_loo", f"{var}_z_loo"]]


def build_market(log) -> pd.DataFrame:
    p = load_market_panel()
    p = p[p["crop"].isin(CROPS)].copy()
    base = p[["date", "crop", "price", "volume", "is_public_holiday", "doy", "year"]].copy()
    log.info("市场面板：%d 行；%s ~ %s；%d 品种", len(base),
             base["date"].min().date(), base["date"].max().date(), base["crop"].nunique())

    ap = anomaly_v2(p[["date", "crop", "price"]], "price", log)
    av = anomaly_v2(p[["date", "crop", "volume"]], "volume", log)
    d = base.merge(ap, on=["date", "crop"], how="left").merge(av, on=["date", "crop"], how="left")

    # 价格/成交量自身滞后（上一交易日观测）
    d = d.sort_values(["crop", "date"]).reset_index(drop=True)
    g = d.groupby("crop", sort=False)
    for c in ("price", "volume"):
        d[f"{c}_lag1"] = g[c].shift(1)
        d[f"{c}_z_lag1"] = g[f"{c}_z"].shift(1)
    d["log_price"] = np.log(d["price"].where(d["price"] > 0))
    d["log_volume"] = np.log(d["volume"].where(d["volume"] > 0))

    # 气象（当日 + 预定义滞后窗 + 累积降水）
    w = load_weather_daily().sort_values("date").reset_index(drop=True)
    wx = w[["date"] + [c for c in WX_MAP if c in w.columns]].rename(columns=WX_MAP)
    d = d.merge(wx, on="date", how="left")

    # 累积降水（1/3/7/14 日）
    ws = w.set_index("date")
    for k in (1, 3, 7, 14):
        d[f"precip_{k}d"] = d["date"].map(ws["precipitation"].rolling(k, min_periods=1).sum())
    # 预定义滞后窗（0日 / 1-3 / 4-7 / 8-14）：窗口内日均
    for label, (a, b) in {"w0": (0, 0), "w13": (1, 3), "w47": (4, 7), "w814": (8, 14)}.items():
        cols = [d["date"].map(ws["precipitation"].shift(k)) for k in range(a, b + 1)]
        d[f"precip_{label}"] = pd.concat(cols, axis=1).mean(axis=1)
        cols_t = [d["date"].map(ws["temp_max"].shift(k)) for k in range(a, b + 1)]
        d[f"tmax_{label}"] = pd.concat(cols_t, axis=1).mean(axis=1)
    # 天气滞后特征（仅滞后，用于 F_wx 口径）
    for k in (1, 3, 7, 14):
        for c in ("precipitation", "temp_max", "vpd", "soil_moisture_0_7"):
            d[f"{c}_lag{k}d"] = d["date"].map(ws[c].shift(k))
    # 标准化（全序列 SD；仅用于「每 +1 SD」口径，不涉及目标变量）
    for c in ("precipitation", "temp_max", "temp_mean", "vpd", "humidity", "wind_speed",
              "soil_moisture_0_7", "et0", "radiation", "pressure_msl", "cloud_cover", "dew_point"):
        if c in d.columns:
            sd = d[c].std(ddof=1)
            d[f"{c}_sd"] = sd if (np.isfinite(sd) and sd > 0) else np.nan
    return d


def build_district(log) -> pd.DataFrame:
    d = load_district_panel()
    d = d[d["district"].isin(__import__("_v2").DISTRICTS)].copy()
    # A08 主要使用 2018-2024；2015-2017 仅康平 → 标记 supplement
    d["is_supplement"] = d["year"] < 2018
    # v2 派生：标准化单产（逐作物 z）与 log 单产
    d["yield_value"] = pd.to_numeric(d["yield_value"], errors="coerce")
    d["production"] = pd.to_numeric(d["production"], errors="coerce")
    d["sown_area"] = pd.to_numeric(d["sown_area"], errors="coerce")
    d["log_yield"] = np.log(d["yield_value"].where(d["yield_value"] > 0))
    for c in ("growing_season_temp_mean", "growing_season_precip", "max_1d_precip",
              "max_3d_precip", "max_5d_precip", "heavy_rain_days", "hot_days",
              "humidity_mean", "vpd_mean", "et0_sum"):
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce")
    log.info("区县面板：%d 行；%d 区县；%s；主样本(2018-2024) %d 行",
             len(d), d["district"].nunique(), sorted(d["year"].unique()),
             int((~d["is_supplement"]).sum()))
    return d


def main() -> None:
    import _v2
    log = get_logger("10_build_data")
    log.info("=" * 70)
    log.info("构建 v2 分析数据（去季节化在 v2 内重算）")

    m = build_market(log)
    p1 = DATA / "v2_market_daily.parquet"
    m.to_parquet(p1, index=False)
    log.info("已写 %s：%d 行 × %d 列", p1.name, m.shape[0], m.shape[1])

    d = build_district(log)
    p2 = DATA / "v2_district_yearly.parquet"
    d.to_parquet(p2, index=False)
    log.info("已写 %s：%d 行 × %d 列", p2.name, d.shape[0], d.shape[1])

    # 审计
    ar1 = {}
    for c in CROPS[:3]:
        s = m.loc[m["crop"].eq(c)].sort_values("date")["price_z"].dropna()
        ar1[c] = float(np.corrcoef(s[:-1], s[1:])[0, 1]) if len(s) > 3 else None
    metrics_dump("data_build.json", {
        "market_rows": int(len(m)), "districts_rows": int(len(d)),
        "market_missing": {c: int(m[c].isna().sum()) for c in
                           ["price_z", "volume_z", "precipitation", "temp_max", "vpd",
                            "soil_moisture_0_7"] if c in m.columns},
        "price_z_ar1_sample": ar1,
        "district_main_rows": int((~d["is_supplement"]).sum()),
        "method": "LOO(doy±5) median expected + 1.4826*MAD robust scale (leave-one-year-out)",
    })
    save_table(m.head(200), "_preview_market_daily.csv")
    log.info("完成")


if __name__ == "__main__":
    main()
