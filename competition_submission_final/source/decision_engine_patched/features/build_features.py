# -*- coding: utf-8 -*-
"""Phase 1: 严格 point-in-time 特征工程 + 目标变量。

核心约束：
  - 所有特征只使用 t 及 t 之前（含 t）的信息；
  - lag 语义 = 观测滞后（同一作物上一个/倒数第 k 个观测），因为沈阳序列
    是"工作日观测"（1410 个观测日，非连续自然日，缺周末与部分节假日）；
  - 另提供"日历滞后"（最近一个 <= t-k 自然日的观测）；
  - 目标变量使用未来数据（作为标签），但在建模时绝不允许进入 X；
  - 历史分位与季节分位严格 past-only（不跨年份回填未来）。
"""
from __future__ import annotations
from collections import defaultdict
from typing import Dict, List

import numpy as np
import pandas as pd

OBS_LAGS = [1, 2, 3, 5, 7, 10, 14, 21, 30, 45, 60, 90]
CAL_LAGS = [7, 14, 30, 60, 90]
ROLL_WINDOWS = [7, 14, 30, 60, 90]
RET_WINDOWS = [7, 14, 30, 60, 90]
SLOPE_WINDOWS = [7, 30, 60]
VOL_WINDOWS = [7, 30, 60]

FEATURE_DICT: List[Dict] = []


def _reg(name, group, definition, window, pit, missing):
    FEATURE_DICT.append({
        "feature": name, "group": group, "definition": definition,
        "window": window, "pit_rule": pit, "missing_policy": missing,
    })


def add_price_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["crop", "date"]).reset_index(drop=True)
    g = df.groupby("crop", sort=False)
    price = "price_per_kg"

    # ---------- A. 观测滞后 ----------
    for k in OBS_LAGS:
        col = f"price_lag_obs_{k}"
        df[col] = g[price].shift(k)
        _reg(col, "price_lag", f"倒数第 {k+1} 个观测的价格（观测滞后）", f"obs-{k}",
             "仅用 <=t 的观测", "不足则 NA，不插值")

    # ---------- B. 日历滞后 ----------
    df["_d"] = pd.to_datetime(df["date"])
    for k in CAL_LAGS:
        col = f"price_lag_cal_{k}"
        vals = np.full(len(df), np.nan)
        for crop, sub in df.groupby("crop", sort=False):
            s = pd.Series(sub[price].values, index=sub["_d"])
            cal = pd.date_range(s.index.min(), s.index.max(), freq="D")
            s_cal = s.reindex(cal).ffill()
            target_dates = sub["_d"] - pd.Timedelta(days=k)
            vals[sub.index.values] = s_cal.reindex(target_dates).values
        df[col] = vals
        _reg(col, "price_lag", f"最近一个 <= t-{k} 自然日的观测价格（日历滞后）", f"cal-{k}",
             "仅用 <=t 的观测", "不足则 NA，不用未来插值")

    # ---------- C. Rolling ----------
    for w in ROLL_WINDOWS:
        df[f"price_ma{w}"] = g[price].transform(lambda s: s.rolling(w, min_periods=w).mean())
        _reg(f"price_ma{w}", "rolling", f"近 {w} 个观测的均值（含 t）", f"obs-{w}", "含 t，严格 <=t", "前 w-1 观测 NA")
    for w in [7, 30]:
        df[f"price_median{w}"] = g[price].transform(lambda s: s.rolling(w, min_periods=w).median())
        _reg(f"price_median{w}", "rolling", f"近 {w} 个观测的中位数（含 t）", f"obs-{w}", "含 t", "前 w-1 观测 NA")
    for w in ROLL_WINDOWS:
        df[f"price_std{w}"] = g[price].transform(lambda s: s.rolling(w, min_periods=w).std())
        _reg(f"price_std{w}", "volatility", f"近 {w} 观测价格标准差（含 t）", f"obs-{w}", "含 t", "前 w-1 观测 NA")

    # ---------- D. Momentum ----------
    for w in RET_WINDOWS:
        lag = df[f"price_lag_obs_{w}"] if w in OBS_LAGS else g[price].shift(w)
        df[f"price_return_{w}"] = df[price] / lag.replace(0, np.nan) - 1
        _reg(f"price_return_{w}", "momentum", f"t 相对 {w} 观察前的收益率", f"obs-{w}", "<=t", "分母为 0 或缺失→NA")
    for w in [30, 60, 90]:
        df[f"price_momentum_{w}"] = df[price] / df[f"price_ma{w}"].replace(0, np.nan) - 1
        _reg(f"price_momentum_{w}", "momentum", f"价格相对自身 {w} 观测均值的偏离度", f"obs-{w}", "含 t", "均值为 0/缺失→NA")

    # ---------- E. Trend ----------
    up = (g[price].diff() > 0).astype(int)
    dn = (g[price].diff() < 0).astype(int)
    df["continuous_rise_days"] = up.groupby([df["crop"], up.eq(0).cumsum()]).cumsum()
    df["continuous_fall_days"] = dn.groupby([df["crop"], dn.eq(0).cumsum()]).cumsum()
    _reg("continuous_rise_days", "trend", "截至 t 的连续上涨观测数", "upto-t", "<=t", "起点为 0")
    _reg("continuous_fall_days", "trend", "截至 t 的连续下跌观测数", "upto-t", "<=t", "起点为 0")

    lp = np.log(g[price].transform(lambda s: s))
    df["_logp"] = lp
    for w in SLOPE_WINDOWS:
        mp = max(3, w // 3)
        df[f"rolling_slope_{w}"] = g["_logp"].transform(
            lambda s: s.rolling(w, min_periods=mp).apply(
                lambda x: np.polyfit(np.arange(len(x)), x, 1)[0], raw=True))
        _reg(f"rolling_slope_{w}", "trend", f"近 {w} 观测对数价格线性趋势斜率", f"obs-{w}", "含 t", "窗口不足→NA")

    # ---------- F. Volatility / Drawdown ----------
    ret1 = g[price].transform(lambda s: s.pct_change())
    df["_ret1"] = ret1
    for w in VOL_WINDOWS:
        df[f"volatility_{w}"] = g["_ret1"].transform(lambda s: s.rolling(w, min_periods=max(4, w // 2)).std())
        _reg(f"volatility_{w}", "volatility", f"近 {w} 观测日收益率标准差", f"obs-{w}", "含 t", "窗口不足→NA")
    df["rolling_max_30"] = g[price].transform(lambda s: s.rolling(30, min_periods=30).max())
    df["drawdown_30"] = df[price] / df["rolling_max_30"].replace(0, np.nan) - 1
    _reg("rolling_max_30", "drawdown", "近 30 观测最高价（含 t）", "obs-30", "含 t", "前 29 观测 NA")
    _reg("drawdown_30", "drawdown", "相对近 30 观测最高价的回撤（<=0）", "obs-30", "含 t", "窗口不足→NA")

    def _mdd(x):
        cm = np.maximum.accumulate(x)
        return float(np.min(x / cm - 1))

    df["max_drawdown_90"] = g[price].transform(
        lambda s: s.rolling(90, min_periods=45).apply(_mdd, raw=True))
    _reg("max_drawdown_90", "drawdown", "近 90 观测窗口内最大回撤", "obs-90", "含 t", "窗口不足→NA")

    # ---------- G. Historical percentile（严格 past-only） ----------
    df["expanding_price_percentile"] = g[price].transform(
        lambda s: s.expanding(min_periods=30).rank(pct=True))
    _reg("expanding_price_percentile", "percentile",
         "当前价在自身历史（t 之前+当天）中的分位", "expanding", "仅 <=t", "少于 30 观测→NA")

    # 同月历史分位：仅使用严格更早的自然日（同月跨年）
    mp = np.full(len(df), np.nan)
    for (crop, month), sub in df.groupby(["crop", "month"], sort=False):
        sub = sub.sort_values("_d")
        ranks = sub[price].expanding(min_periods=20).rank(pct=True)
        mp[sub.index.values] = ranks.values
    df["same_month_price_percentile"] = mp
    _reg("same_month_price_percentile", "percentile",
         "当前价在同作物同月（历史年份，严格更早日期）中的分位", "same-month", "严格 <=t", "少于 20 样本→NA")

    # 同季历史分位：doy ±15 天的历史观测（严格更早日期）
    sp = np.full(len(df), np.nan)
    for crop, sub in df.groupby("crop", sort=False):
        sub = sub.sort_values("_d")
        p = sub[price].values
        doy = sub["day_of_year"].values.astype(float)
        n = len(sub)
        for i in range(n):
            if i == 0:
                continue
            d = np.abs(doy[:i] - doy[i])
            d = np.minimum(d, 365.25 - d)
            mask = d <= 15
            vals = p[:i][mask]
            if len(vals) >= 20:
                sp[sub.index.values[i]] = (np.sum(vals <= p[i]) + 1) / (len(vals) + 1)
    df["same_season_price_percentile"] = sp
    _reg("same_season_price_percentile", "percentile",
         "当前价在历史同季窗口（doy±15 天，严格更早日期）中的分位", "same-season", "严格 <=t", "少于 20 样本→NA")

    # ---------- H. 历史季节分位 P10/P50/P90（严格历史年份） ----------
    hist = defaultdict(lambda: defaultdict(list))  # (crop, month) -> year -> values
    for (crop, month, year), sub in df.groupby(["crop", "month", "year"], sort=False):
        hist[(crop, month)][year] = sub[price].values
    p10 = np.full(len(df), np.nan)
    p50 = np.full(len(df), np.nan)
    p90 = np.full(len(df), np.nan)
    cnt = np.full(len(df), 0)
    ycnt = np.full(len(df), 0)
    avail = np.zeros(len(df), dtype=bool)
    for i, (crop, month, year) in enumerate(zip(df["crop"], df["month"], df["year"])):
        pool, years = [], 0
        for y, vals in hist[(crop, month)].items():
            if y < year:
                pool.append(vals)
                years += 1
        if pool:
            allv = np.concatenate(pool)
            cnt[i] = len(allv)
            ycnt[i] = years
            if len(allv) >= 20 and years >= 2:
                p10[i], p50[i], p90[i] = np.percentile(allv, [10, 50, 90])
                avail[i] = True
    df["seasonal_p10"] = p10
    df["seasonal_p50"] = p50
    df["seasonal_p90"] = p90
    df["seasonal_sample_count"] = cnt
    df["seasonal_year_count"] = ycnt
    df["seasonal_feature_available"] = avail
    for c in ["seasonal_p10", "seasonal_p50", "seasonal_p90"]:
        _reg(c, "seasonal_quantile",
             f"历史同月（严格更早年份）{c.split('_')[-1].upper()} 分位", "same-month-prior-years",
             "仅 year<t.year 且 date<t", "样本<20 或年份<2 → NA")
    _reg("seasonal_sample_count", "seasonal_quantile", "季节分位样本数", "same-month-prior-years", "严格 <=t", "—")
    _reg("seasonal_year_count", "seasonal_quantile", "季节分位覆盖年份数", "same-month-prior-years", "严格 <=t", "—")
    _reg("seasonal_feature_available", "seasonal_quantile", "季节分位是否可用", "-", "严格 <=t", "—")

    # ---------- 季节位置 ----------
    df["price_vs_seasonal_p50"] = df[price] / df["seasonal_p50"].replace(0, np.nan) - 1
    _reg("price_vs_seasonal_p50", "seasonal_quantile", "当前价相对历史同月 P50 的偏离", "same-month-prior-years", "严格 <=t", "缺失→NA")

    df = df.drop(columns=["_d", "_logp", "_ret1"])
    return df


def add_targets(df: pd.DataFrame) -> pd.DataFrame:
    """未来窗口目标（日历天窗口，窗口必须完整落在数据范围内）。"""
    df = df.sort_values(["crop", "date"]).reset_index(drop=True)
    df["_d"] = pd.to_datetime(df["date"])
    last_date = df["_d"].max()

    for h in [7, 14, 30]:
        mean_col = f"target_mean_price_next_{h}d"
        med_col = f"target_median_price_next_{h}d"
        min_col = f"target_min_price_next_{h}d"
        max_col = f"target_max_price_next_{h}d"
        cnt_col = f"target_obs_count_next_{h}d"
        vals_mean = np.full(len(df), np.nan)
        vals_med = np.full(len(df), np.nan)
        vals_min = np.full(len(df), np.nan)
        vals_max = np.full(len(df), np.nan)
        vals_cnt = np.zeros(len(df), dtype=int)
        for crop, sub in df.groupby("crop", sort=False):
            sub = sub.sort_values("_d")
            dates = sub["_d"].values.astype("datetime64[D]")
            prices = sub["price_per_kg"].values.astype(float)
            idx = sub.index.values
            for j, (d, t_end_ok) in enumerate(zip(dates, (dates + np.timedelta64(h, "D")) <=
                                                  np.datetime64(last_date, "D"))):
                if not t_end_ok:
                    continue
                lo = np.searchsorted(dates, d, side="right")
                hi = np.searchsorted(dates, d + np.timedelta64(h, "D"), side="right")
                if hi <= lo:
                    continue
                w = prices[lo:hi]
                vals_mean[idx[j]] = w.mean()
                vals_med[idx[j]] = np.median(w)
                vals_min[idx[j]] = w.min()
                vals_max[idx[j]] = w.max()
                vals_cnt[idx[j]] = len(w)
        df[mean_col] = vals_mean
        df[cnt_col] = vals_cnt
        if h == 30:
            df[med_col] = vals_med
            df[min_col] = vals_min
            df[max_col] = vals_max

    # 单点目标：<= t+h 的最近观测
    for h in [7, 14, 30]:
        col = f"target_price_t{h}"
        vals = np.full(len(df), np.nan)
        for crop, sub in df.groupby("crop", sort=False):
            sub = sub.sort_values("_d")
            dates = sub["_d"].values.astype("datetime64[D]")
            prices = sub["price_per_kg"].values.astype(float)
            idx = sub.index.values
            for j, d in enumerate(dates):
                if d + np.timedelta64(h, "D") > np.datetime64(last_date, "D"):
                    continue
                pos = np.searchsorted(dates, d + np.timedelta64(h, "D"), side="right") - 1
                if pos > j:
                    vals[idx[j]] = prices[pos]
        df[col] = vals

    df = df.drop(columns=["_d"])
    return df


def feature_dictionary() -> pd.DataFrame:
    rows = list(FEATURE_DICT)
    # 手工补充基础列与目标列说明
    extra = [
        ("price_raw", "base", "官方原始价格（元/斤，wholesale）", "-", "观测", "-"),
        ("price_per_500g", "base", "元/500g = price_raw", "-", "观测", "-"),
        ("price_per_kg", "base", "元/kg = price_per_500g × 2", "-", "观测", "-"),
        ("volume_raw", "volume", "成交量原始值（单位 unknown，仅相对口径）", "-", "观测", "禁止解释为吨"),
        ("volume_change_1d", "volume", "成交量环比（相对上一观测）", "obs-1", "<=t", "NA"),
        ("volume_change_7d", "volume", "成交量 7 观测变化", "obs-7", "<=t", "NA"),
        ("volume_ma7", "volume", "成交量 7 观测均值", "obs-7", "含 t", "NA"),
        ("volume_ma30", "volume", "成交量 30 观测均值", "obs-30", "含 t", "NA"),
        ("volume_zscore", "volume", "成交量 expanding z 分数", "expanding", "<=t", "少于30→NA"),
        ("volume_percentile", "volume", "成交量 expanding 分位", "expanding", "<=t", "少于30→NA"),
        ("target_mean_price_next_7d", "target", "未来 7 自然天窗口平均价（元/kg）", "fwd-7", "未来（仅作标签）", "窗口不完整→NA"),
        ("target_mean_price_next_14d", "target", "未来 14 自然天窗口平均价", "fwd-14", "未来（仅作标签）", "窗口不完整→NA"),
        ("target_mean_price_next_30d", "target", "未来 30 自然天窗口平均价【主目标】", "fwd-30", "未来（仅作标签）", "窗口不完整→NA"),
        ("target_median_price_next_30d", "target", "未来 30 天窗口中位价", "fwd-30", "未来（仅作标签）", "窗口不完整→NA"),
        ("target_min_price_next_30d", "target", "未来 30 天窗口最低价", "fwd-30", "未来（仅作标签）", "窗口不完整→NA"),
        ("target_max_price_next_30d", "target", "未来 30 天窗口最高价", "fwd-30", "未来（仅作标签）", "窗口不完整→NA"),
        ("target_price_t7", "target", "t+7 前最近观测价", "fwd-7", "未来（仅作标签）", "窗口不完整→NA"),
        ("target_price_t14", "target", "t+14 前最近观测价", "fwd-14", "未来（仅作标签）", "窗口不完整→NA"),
        ("target_price_t30", "target", "t+30 前最近观测价", "fwd-30", "未来（仅作标签）", "窗口不完整→NA"),
        ("target_obs_count_next_7d", "target_meta", "未来 7 天窗口内观测数", "fwd-7", "未来", "—"),
        ("target_obs_count_next_14d", "target_meta", "未来 14 天窗口内观测数", "fwd-14", "未来", "—"),
        ("target_obs_count_next_30d", "target_meta", "未来 30 天窗口内观测数", "fwd-30", "未来", "—"),
    ]
    for name, group, definition, window, pit, missing in extra:
        rows.append({"feature": name, "group": group, "definition": definition,
                     "window": window, "pit_rule": pit, "missing_policy": missing})
    return pd.DataFrame(rows)