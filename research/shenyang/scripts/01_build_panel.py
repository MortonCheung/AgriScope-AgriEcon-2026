"""STEP 05：建立沈阳日度核心研究面板。

产出：
  data/interim/shenyang_climatology_daily.parquet  1991-2020 逐日气候基线（doy 级）+ 降水分位表
  data/interim/shenyang_weather_daily.parquet      完整日序列气象/土壤 + 累积特征（calendar day）
  data/interim/shenyang_market_daily.parquet       市场实际观测日 × 品种（价格 / 成交量 / 日环比）
  data/interim/shenyang_daily_panel.parquet        核心面板 = 市场观测日 × 品种 ⨝ 当日天气
  data/interim/shenyang_weekly_panel.parquet       周度面板（ISO 周，供 STL / 周尺度核验）

铁律：
  1. 气象保持完整日序列；市场价格/成交量保持实际观测日，**不做 resample("D").interpolate()**；
  2. 累积量与滞后一律按 calendar day 计算；
  3. 价格为「上一次观测」滞后或「日历日」滞后时必须显式命名区分；
  4. volume 单位未知，仅保留原值 + 相对/标准化派生，禁止出现「吨」。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    ANALYSIS, CROPS_CFG, PATHS, StepTimer, get_logger, log_blocker, read_input,
    safe_div, save_parquet, save_table, set_seed,
)

LOG = get_logger("01_build_panel")
CORE_CROPS: list = CROPS_CFG["core_crops"]
CITY = CROPS_CFG["market"]["city"]

# 1991-2020 基线变量 → 面板变量名
BASE_VAR_MAP = {
    "temperature_2m_mean": "temp_mean",
    "temperature_2m_max": "temp_max",
    "temperature_2m_min": "temp_min",
    "precipitation_sum": "precipitation",
    "relative_humidity_2m_mean": "humidity",
    "wind_speed_10m_max": "wind_speed",
    "shortwave_radiation_sum": "radiation",
    "et0_fao_evapotranspiration": "et0",
    "soil_moisture_0_to_10cm_mean": "soil_moisture_0_7",
}
PCT_WINDOW = 5  # 降水分位的日历窗口：doy ± 5 天
SOIL_VAR = "soil_moisture_0_7"   # 0-7cm 土壤含水量（ERA5-Land，m³/m³）
SOIL_Z_WINDOW = 5                # 降级基线窗口：doy ± 5（环形）
SOIL_Z_MIN_OBS = 8               # 降级基线最少有效样本


# -----------------------------------------------------------------------------
# 1. 市场原始层（批发口径）；同时补取 marts 未落库的 dayPriceRatio
# -----------------------------------------------------------------------------
def load_raw_market() -> pd.DataFrame:
    d = PATHS.inp("raw_price_dir")
    files = sorted(d.glob("*_mt1.json"))
    rows = []
    empty = 0
    for f in files:
        date = f.name[:10]
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        items = j.get("data") or []
        if not items:
            empty += 1
            continue
        for it in items:
            rows.append({
                "date": date,
                "crop": it.get("productName"),
                "grade": it.get("grade"),
                "region_raw": it.get("regionName"),
                "market_type": str(it.get("marketType")),
                "price_raw": it.get("price"),
                "unit_raw": it.get("unit"),
                "volume_raw": it.get("volume"),
                "day_price_ratio_raw": it.get("dayRriceRatio"),
                "day_volume_ratio_raw": it.get("dayVolumeRatio"),
                "raw_file": str(f.relative_to(PATHS.warehouse_root)),
            })
    df = pd.DataFrame(rows)
    LOG.info("原始批发 JSON %d 个（空响应 %d），解析出 %d 行", len(files), empty, len(df))
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.normalize()
    for a, b in [("price_raw", "price"), ("volume_raw", "volume"),
                 ("day_price_ratio_raw", "day_price_ratio"),
                 ("day_volume_ratio_raw", "day_volume_ratio")]:
        df[b] = pd.to_numeric(df[a], errors="coerce")
    df = df[df["market_type"] == "1"].copy()
    df["city"] = CITY
    df["price_unit_raw"] = df["unit_raw"]
    return df


def build_market_daily(raw: pd.DataFrame) -> pd.DataFrame:
    """市场观测日 × 品种。核心 10 种蔬菜；零成交不剔除但显式标记。"""
    df = raw[raw["crop"].isin(CORE_CROPS)].copy()
    key = ["date", "crop"]
    dup = df.duplicated(subset=key, keep=False)
    if dup.any():
        LOG.warning("批发原始层存在业务主键重复 %d 行，已记录到 QA（保留 Raw，此处按记录序取首条）", int(dup.sum()))
        df = df.sort_values(key + ["raw_file"]).drop_duplicates(subset=key, keep="first")
    df = df[key + ["price", "volume", "day_price_ratio", "day_volume_ratio",
                   "grade", "price_unit_raw", "region_raw", "raw_file"]]
    df = df.sort_values(key).reset_index(drop=True)
    df["volume_is_zero"] = df["volume"] == 0
    df["volume_missing"] = df["volume"].isna()
    LOG.info("市场观测日表：%d 行 / %d 日 / %d 品种（%s ~ %s）",
             len(df), df["date"].nunique(), df["crop"].nunique(),
             df["date"].min().date(), df["date"].max().date())
    return df


# -----------------------------------------------------------------------------
# 2. 气象 / 土壤完整日序列
# -----------------------------------------------------------------------------
def build_weather_daily() -> pd.DataFrame:
    w = read_input("fact_weather_daily", parse_dates=["date"])
    w = w[w["city"] == CITY].copy()
    w = w.drop(columns=[c for c in ["soil_moisture"] if c in w.columns])  # 该列全空
    w = w.rename(columns={
        "precip": "precipitation",
        "wind_max": "wind_speed",              # 变量 wind_speed_10m_max（km/h）
        "sunshine_radiation": "radiation",     # 变量 shortwave_radiation_sum（MJ/m²）
    })

    e = read_input("fact_weather_extra_daily", parse_dates=["date"])
    e = e[e["city"] == CITY].copy()
    e = e.drop(columns=[c for c in ["city", "data_type", "weather_source"] if c in e.columns])

    s = read_input("fact_soil_daily", parse_dates=["date"])
    s = s[s["city"] == CITY].copy()
    s = s.rename(columns={
        "soil_water_layer_1": "soil_moisture_0_7",
        "soil_water_layer_2": "soil_moisture_7_28",
        "soil_water_layer_3": "soil_moisture_28_100",
    })
    s = s.drop(columns=[c for c in ["city", "data_type", "source", "aggregation_method"] if c in s.columns])

    df = (w.merge(e, on="date", how="outer", validate="one_to_one")
            .merge(s, on="date", how="outer", validate="one_to_one")
            .sort_values("date").reset_index(drop=True))
    df["vpd"] = df["vpd_max"]
    df["is_rain_day"] = (df["precipitation"] >= 0.1).astype(int)
    df["is_hot_day"] = (df["temp_max"] >= ANALYSIS["hazard_thresholds"]["heat_tmax_c"]).astype(int)
    df["is_frost_day"] = (df["temp_min"] <= ANALYSIS["hazard_thresholds"]["frost_tmin_c"]).astype(int)
    df["is_rainstorm_day"] = (df["precipitation"] >= ANALYSIS["hazard_thresholds"]["rainstorm_daily_mm"]).astype(int)
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    df["doy"] = df["date"].dt.dayofyear
    LOG.info("气象完整日序列：%d 天（%s ~ %s），列 %d",
             len(df), df["date"].min().date(), df["date"].max().date(), df.shape[1])

    # ---- 日历日累积特征 ----
    c = ANALYSIS["cumulative"]
    for k in c["precip_windows_days"]:
        df[f"precip_{k}d"] = df["precipitation"].rolling(k, min_periods=1).sum()
        if k > 1:
            df[f"precip_{k}d_anom"] = np.nan  # 相对基线的距平在 climatology 之后补
    for k in c["hot_day_windows_days"]:
        df[f"hot_days_{k}d"] = df["is_hot_day"].rolling(k, min_periods=1).sum()
    for k in c["vpd_windows_days"]:
        df[f"vpd_{k}d"] = df["vpd"].rolling(k, min_periods=1).mean()
    for k in c["soil_moisture_windows_days"]:
        for lay in c["soil_moisture_layers"]:
            if lay in df.columns:
                df[f"{lay}_{k}d"] = df[lay].rolling(k, min_periods=1).mean()
    # 连续无有效降水日数（当日含）
    dry = (df["precipitation"] < 1.0).astype(int)
    grp = (dry == 0).cumsum()
    df["dry_spell_days"] = dry.groupby(grp).cumsum()
    # 连续降雨日数（≥0.1mm）
    wet = df["is_rain_day"]
    grp2 = (wet == 0).cumsum()
    df["wet_spell_days"] = wet.groupby(grp2).cumsum()
    return df


# -----------------------------------------------------------------------------
# 3. 1991-2020 逐日气候基线
# -----------------------------------------------------------------------------
def build_climatology_daily() -> tuple:
    p = PATHS.inp("baseline_daily_json")
    data = json.loads(p.read_text(encoding="utf-8"))
    daily = data["daily"]
    df = pd.DataFrame({"date": pd.to_datetime(daily["time"])})
    for k, v in BASE_VAR_MAP.items():
        if k in daily:
            df[v] = daily[k]
    df["doy"] = df["date"].dt.dayofyear
    # 处理 2 月 29 日：统一映射到 doy=59（与 2/28 合并），避免闰年错位
    leap = (df["date"].dt.month == 2) & (df["date"].dt.day == 29)
    df.loc[leap, "doy"] = 59

    stats_cols = [v for v in BASE_VAR_MAP.values() if v in df.columns]
    clim = df.groupby("doy")[stats_cols].agg(["mean", "std"])
    clim.columns = [f"clim_{a}_{b}" for a, b in clim.columns]
    clim = clim.reset_index()
    clim["clim_valid_years"] = df.groupby("doy").size().values

    # 降水分位表：doy ± PCT_WINDOW 内的 30 年样本 → 100 级分位
    qs = np.linspace(0, 1, 101)
    recs = []
    for doy in sorted(df["doy"].unique()):
        d = np.abs(df["doy"].values - doy)
        d = np.minimum(d, 366 - d)  # 环形距离
        sample = df.loc[d <= PCT_WINDOW, "precipitation"].dropna().values
        if sample.size < 30:
            continue
        recs.append({"doy": int(doy), **{f"precip_q{int(q*100):03d}": float(np.quantile(sample, q)) for q in qs}})
    pq = pd.DataFrame(recs)
    LOG.info("气候基线：%d 个 doy，%d 个变量；降水分位表 %d 行（窗口 ±%d 天）",
             len(clim), len(stats_cols), len(pq), PCT_WINDOW)
    return clim, pq


def precip_percentile(values: np.ndarray, doys: np.ndarray, pq: pd.DataFrame) -> np.ndarray:
    """把日降水映射到 1991-2020 同期经验分位（0-1）。"""
    qcols = [c for c in pq.columns if c.startswith("precip_q")]
    grid = np.linspace(0, 1, len(qcols))
    table = pq.set_index("doy")[qcols]
    out = np.full(len(values), np.nan)
    for i, (v, d) in enumerate(zip(values, doys)):
        if np.isnan(v) or d not in table.index:
            continue
        curve = table.loc[d].values.astype(float)
        out[i] = float(np.interp(v, curve, grid))
    return out


def soil_z_from_observation(df: pd.DataFrame) -> pd.DataFrame:
    """1991-2020 基线缺土壤含水量时的降级方案（阻断已记录到 reports/BLOCKERS.md）。

    期望值用观测期 **leave-one-year-out** 同期窗口（doy±5，环形）均值：
    目标年自身不进入其基线，因此无信息泄漏，口径与价格去季节化方法B一致。
    尺度不用逐 doy 标准差 —— 基线仅 4~5 年，逐日标准差可能偶然趋近 0 而把 z 放大成伪极端；
    改用与 `04_deseasonalize.add_anomaly_cols` 相同的**全局稳健尺度**（1.4826×MAD）。
    证据等级相应从 A（官方 30 年基线）降为 B（观测期自建基线）。
    """
    d = df.copy()
    d["_doy"] = np.minimum(d["date"].dt.dayofyear, 365)  # 2/29 并入 365
    doy_all = np.arange(1, 366)
    mat = (d.pivot_table(index="_doy", columns="year", values=SOIL_VAR, aggfunc="mean")
             .reindex(index=doy_all))
    years = list(mat.columns)
    exp = pd.Series(np.nan, index=d.index, dtype=float)
    for y in years:
        others = [c for c in years if c != y]
        if not others:
            continue
        sub = mat[others].values                                   # (365, n_others)
        blocks = [sub[(doy_all - 1 + k) % 365] for k in range(-SOIL_Z_WINDOW, SOIL_Z_WINDOW + 1)]
        arr = np.stack(blocks, axis=0)                             # (11, 365, n_others)
        cnt = np.count_nonzero(~np.isnan(arr), axis=(0, 2))
        with np.errstate(all="ignore"):
            m = np.nanmean(arr, axis=(0, 2))
        m = np.where(cnt >= SOIL_Z_MIN_OBS, m, np.nan)
        idx = d.index[d["year"] == y]
        exp.loc[idx] = m[d.loc[idx, "_doy"].values - 1]
    d["soil_moisture_0_7_mean_obs"] = exp
    d["soil_moisture_0_7_anomaly_obs"] = d[SOIL_VAR] - exp
    a = d["soil_moisture_0_7_anomaly_obs"].astype(float)
    scale = 1.4826 * (a - a.median()).abs().median()
    d["soil_moisture_0_7_scale_obs"] = scale
    d["soil_moisture_0_7_z"] = a / scale if np.isfinite(scale) and scale > 0 else np.nan
    d["soil_moisture_z_baseline"] = "observation_period_loo"
    return d.drop(columns=["_doy"])


def attach_climatology(weather: pd.DataFrame, clim: pd.DataFrame, pq: pd.DataFrame) -> pd.DataFrame:
    df = weather.merge(clim, on="doy", how="left", validate="many_to_one")
    df["temp_anomaly"] = df["temp_mean"] - df["clim_temp_mean_mean"]
    df["temp_z"] = safe_div(df["temp_mean"] - df["clim_temp_mean_mean"], df["clim_temp_mean_std"])
    df["temp_max_z"] = safe_div(df["temp_max"] - df["clim_temp_max_mean"], df["clim_temp_max_std"])
    df["precipitation_clim"] = df["clim_precipitation_mean"]
    df["precipitation_anomaly"] = df["precipitation"] - df["clim_precipitation_mean"]
    df["precipitation_pct"] = precip_percentile(
        df["precipitation"].values, df["doy"].values, pq)
    # 土壤含水量：1991-2020 基线 JSON 的 soil_moisture_0_to_10cm_mean 全为 null → 降级
    if df["clim_soil_moisture_0_7_std"].notna().any():
        df["soil_moisture_0_7_z"] = safe_div(
            df[SOIL_VAR] - df["clim_soil_moisture_0_7_mean"], df["clim_soil_moisture_0_7_std"])
        df["soil_moisture_z_baseline"] = "baseline_1991_2020"
        df = df.drop(columns=["clim_soil_moisture_0_7_mean", "clim_soil_moisture_0_7_std"])
    else:
        log_blocker(
            "01_build_panel",
            "1991-2020 气候基线 JSON 不含土壤含水量"
            "（soil_moisture_0_to_10cm_mean 全为 null，10958 天 0 个有效值），"
            "无法按任务书 §二十 用官方基线标准化 soil_moisture_z",
            "降级处理：以 2021-2026 观测期 leave-one-year-out 同期（doy±5 环形）均值自建期望值，"
            "目标年不进入自身基线（无泄漏）；尺度用全局稳健尺度 1.4826×MAD（与价格/成交量异常一致）；"
            "新增列 soil_moisture_0_7_mean_obs / _anomaly_obs / _scale_obs / soil_moisture_z_baseline "
            "以显式标注口径；该指标证据等级由 A 降为 B（观测期自建基线，非官方 30 年基线）。",
        )
        df = df.drop(columns=["clim_soil_moisture_0_7_mean", "clim_soil_moisture_0_7_std"])
        df = soil_z_from_observation(df)
    df["humidity_z"] = safe_div(df["humidity"] - df["clim_humidity_mean"], df["clim_humidity_std"])
    # 累积降水的基线距平（用基线日均值累加，口径一致）
    for k in ANALYSIS["cumulative"]["precip_windows_days"]:
        if k == 1:
            continue
        clim_k = df["clim_precipitation_mean"].rolling(k, min_periods=1).sum()
        df[f"precip_{k}d_anom"] = df[f"precip_{k}d"] - clim_k
    # 干旱强度：过去 k 日降水亏缺（基线 - 实际），正=偏干
    for k in [14, 30]:
        act = df["precipitation"].rolling(k, min_periods=1).sum()
        cl = df["clim_precipitation_mean"].rolling(k, min_periods=1).sum()
        df[f"precip_deficit_{k}d"] = cl - act
    return df


# -----------------------------------------------------------------------------
# 4. 日历（节假日 / 星期 / 季节）
# -----------------------------------------------------------------------------
def build_calendar(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    cal = read_input("dim_calendar", parse_dates=["date"])
    cal = cal[["date", "is_weekend", "is_public_holiday", "holiday_name",
               "days_from_spring_festival", "iso_year", "iso_week", "weekday"
               if "weekday" in cal.columns else "date"]].copy()
    full = pd.DataFrame({"date": pd.date_range(start, end, freq="D")})
    out = full.merge(cal, on="date", how="left")
    # dim_calendar 仅覆盖 2021-01-01 起；2020 年用 holidays 库补齐并显式标注来源
    try:
        import holidays as _hol
        cn = _hol.country_holidays("CN", years=sorted(set(out["date"].dt.year)))
        missing = out["is_public_holiday"].isna()
        out.loc[missing, "is_public_holiday"] = out.loc[missing, "date"].map(
            lambda d: int(d.date() in cn))
        out.loc[missing, "holiday_name"] = out.loc[missing, "date"].map(
            lambda d: cn.get(d.date(), None))
        out["holiday_source"] = np.where(missing, "python-holidays(CN)", "warehouse/dim_calendar")
    except Exception as exc:  # noqa: BLE001
        LOG.warning("holidays 库不可用（%s），2020 年节假日留空", exc)
        out["holiday_source"] = "warehouse/dim_calendar"

    out["is_public_holiday"] = out["is_public_holiday"].fillna(0).astype(int)
    out["is_weekend"] = out["is_weekend"].fillna(out["date"].dt.dayofweek >= 5).astype(int)
    out["iso_year"] = out["date"].dt.isocalendar().year.astype(int)
    out["iso_week"] = out["date"].dt.isocalendar().week.astype(int)
    out["day_of_week"] = out["date"].dt.dayofweek
    out["month"] = out["date"].dt.month
    out["year"] = out["date"].dt.year
    out["day_of_year"] = out["date"].dt.dayofyear
    out["week_start"] = out["date"] - pd.to_timedelta(out["day_of_week"], unit="D")
    out["week_end"] = out["week_start"] + pd.Timedelta(days=6)
    # 法定长假连续放假标记（≥3 天连续节日 → 节假日效应期）
    hol = out["is_public_holiday"].values.astype(int)
    grp = np.cumsum(np.r_[0, np.diff(hol) == -1][: len(hol)])
    streak = pd.Series(hol).groupby(grp).cumsum().values
    out["holiday_streak_day"] = streak
    return out


# -----------------------------------------------------------------------------
# 5. 核心面板
# -----------------------------------------------------------------------------
def build_core_panel(market: pd.DataFrame, weather: pd.DataFrame,
                     calendar: pd.DataFrame) -> tuple:
    wx_cols = [c for c in weather.columns if c != "date"]
    panel = market.merge(weather, on="date", how="left", validate="many_to_one")
    panel = panel.merge(
        calendar[["date", "is_weekend", "is_public_holiday", "holiday_name",
                  "day_of_week", "month", "year", "day_of_year", "iso_year",
                  "iso_week", "week_start", "week_end", "holiday_streak_day",
                  "holiday_source", "days_from_spring_festival"]],
        on="date", how="left", validate="many_to_one")

    # ---- 价格自身滞后：显式区分「上一次观测滞后」与「日历日滞后」 ----
    panel = panel.sort_values(["crop", "date"]).reset_index(drop=True)
    g = panel.groupby("crop", sort=False)
    panel["price_prev_obs"] = g["price"].shift(1)
    panel["price_prev_obs_date"] = g["date"].shift(1)
    panel["price_calendar_lag_days"] = (panel["date"] - panel["price_prev_obs_date"]).dt.days
    panel["price_change_pct_prev_obs"] = safe_div(
        panel["price"] - panel["price_prev_obs"], panel["price_prev_obs"]) * 100
    panel["volume_prev_obs"] = g["volume"].shift(1)
    panel["volume_change_pct_prev_obs"] = safe_div(
        panel["volume"] - panel["volume_prev_obs"], panel["volume_prev_obs"]) * 100
    panel["price_log"] = np.log(panel["price"].where(panel["price"] > 0))
    panel["volume_log"] = np.log(panel["volume"].where(panel["volume"] > 0))

    # 天气滞后（calendar day，天气序列本身连续，直接按日位移）
    wx_sorted = weather.sort_values("date").reset_index(drop=True)
    lag_map = {}
    for lag in range(0, ANALYSIS["lag"]["max_lag_days"] + 1):
        lag_map[lag] = wx_sorted.set_index("date").shift(lag)
    for lag in [1, 2, 3, 5, 7, 10, 14, 21, 30]:
        for v in ["precipitation", "precip_3d", "precip_7d", "temp_mean", "temp_max",
                  "vpd", "soil_moisture_0_7", "temp_anomaly", "precipitation_pct"]:
            panel[f"{v}_lag{lag}d"] = panel["date"].map(lag_map[lag][v])
    LOG.info("核心面板：%d 行 × %d 列（%s ~ %s）",
             len(panel), panel.shape[1], panel["date"].min().date(), panel["date"].max().date())

    covered = panel[panel["temp_mean"].notna()]
    LOG.info("核心面板中天气可对齐行数：%d（%.2f%%），未覆盖 %d 行（%s ~ %s 无气象）",
             len(covered), 100 * len(covered) / len(panel), len(panel) - len(covered),
             panel.loc[panel["temp_mean"].isna(), "date"].min(),
             panel.loc[panel["temp_mean"].isna(), "date"].max())
    return panel, wx_cols


def build_weekly_panel(panel: pd.DataFrame, weather: pd.DataFrame) -> pd.DataFrame:
    """ISO 周 × 品种：市场用周内实际观测聚合（不插值），天气用完整日序列聚合。"""
    m = panel.copy()
    m["week_start"] = m["date"] - pd.to_timedelta(m["date"].dt.dayofweek, unit="D")
    mkt = m.groupby(["week_start", "crop"]).agg(
        price_mean=("price", "mean"),
        price_median=("price", "median"),
        price_std=("price", "std"),
        price_min=("price", "min"),
        price_max=("price", "max"),
        volume_mean=("volume", "mean"),
        volume_median=("volume", "median"),
        volume_std=("volume", "std"),
        observations=("price", "size"),
        obs_days=("date", "nunique"),
    ).reset_index()

    wx = weather.copy()
    wx["week_start"] = wx["date"] - pd.to_timedelta(wx["date"].dt.dayofweek, unit="D")
    wagg = wx.groupby("week_start").agg(
        temp_mean=("temp_mean", "mean"),
        temp_max=("temp_max", "max"),
        temp_min=("temp_min", "min"),
        precip_sum=("precipitation", "sum"),
        precip_max_daily=("precipitation", "max"),
        rain_days=("is_rain_day", "sum"),
        rainstorm_days=("is_rainstorm_day", "sum"),
        hot_35c_days=("is_hot_day", "sum"),
        frost_days=("is_frost_day", "sum"),
        humidity_mean=("humidity", "mean"),
        wind_max=("wind_speed", "max"),
        radiation_sum=("radiation", "sum"),
        et0_sum=("et0", "sum"),
        vpd_mean=("vpd", "mean"),
        soil_moisture_0_7=("soil_moisture_0_7", "mean"),
        soil_moisture_7_28=("soil_moisture_7_28", "mean"),
        soil_moisture_28_100=("soil_moisture_28_100", "mean"),
        temp_anomaly=("temp_anomaly", "mean"),
        precipitation_anomaly=("precipitation_anomaly", "sum"),
        precipitation_pct_max=("precipitation_pct", "max"),
        dry_spell_max=("dry_spell_days", "max"),
        weather_days=("date", "size"),
    ).reset_index()

    wk = mkt.merge(wagg, on="week_start", how="left", validate="many_to_one")
    wk = wk.sort_values(["crop", "week_start"]).reset_index(drop=True)
    g = wk.groupby("crop", sort=False)
    wk["price_mean_prev_week"] = g["price_mean"].shift(1)
    wk["price_wow_pct"] = safe_div(wk["price_mean"] - wk["price_mean_prev_week"],
                                   wk["price_mean_prev_week"]) * 100
    wk["volume_wow_pct"] = safe_div(wk["volume_mean"] - g["volume_mean"].shift(1),
                                    g["volume_mean"].shift(1)) * 100
    LOG.info("周度面板：%d 行（%s ~ %s），%d 品种",
             len(wk), wk["week_start"].min().date(), wk["week_start"].max().date(),
             wk["crop"].nunique())
    return wk


# -----------------------------------------------------------------------------
def main() -> None:
    set_seed()
    with StepTimer("01_build_panel", LOG):
        raw = load_raw_market()
        market = build_market_daily(raw)
        weather = build_weather_daily()
        clim, pq = build_climatology_daily()
        weather = attach_climatology(weather, clim, pq)
        cal = build_calendar(market["date"].min(), weather["date"].max())
        panel, _ = build_core_panel(market, weather, cal)
        weekly = build_weekly_panel(panel, weather)

        save_parquet(clim.merge(pq, on="doy", how="left"), "climatology_daily")
        save_parquet(weather, "weather_daily")
        save_parquet(market, "market_daily")
        save_parquet(panel, "daily_panel")
        save_parquet(weekly, "panel_weekly")

        # 原始市场层留档（供 QA 与血缘追溯）
        save_parquet(raw, "data/interim/shenyang_market_raw_wholesale.parquet")
        save_table(raw.head(200), "market_raw_wholesale_head200.csv")

        LOG.info("核心面板日期范围：%s ~ %s；含气象对齐的最后观测日：%s",
                 panel["date"].min().date(), panel["date"].max().date(),
                 panel.loc[panel["temp_mean"].notna(), "date"].max().date())


if __name__ == "__main__":
    main()
