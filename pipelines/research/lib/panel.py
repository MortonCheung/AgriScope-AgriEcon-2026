"""panel.py — 共享时序面板工具：频率识别 / 严格无未来信息去季节化 / 气象对齐。

纪律：去季节化基线**只使用严格早于目标年的年份**（与沈阳 v2 一致）。
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

EXPOSURES = ["precipitation", "temp_max", "vpd", "wind_speed", "soil_moisture"]


def detect_freq(series: pd.DataFrame, date_col: str = "date") -> str:
    """按中位采样间隔判断频率：'D' 日 / 'W' 周。"""
    d = pd.to_datetime(series[date_col]).drop_duplicates().sort_values()
    if len(d) < 3:
        return "D"
    gap = d.diff().dt.days.dropna().median()
    return "D" if gap <= 3 else "W"


def _period_key(dates: pd.Series, freq: str) -> pd.Series:
    if freq == "W":
        iso = pd.to_datetime(dates).dt.isocalendar()
        return iso["week"].astype(int)
    return pd.to_datetime(dates).dt.dayofyear.astype(int)


def deseasonalize_strict(df: pd.DataFrame, value_col: str = "price_per_kg",
                         date_col: str = "date", freq: str = "D",
                         doy_window: int = 5) -> pd.DataFrame:
    """严格无未来信息去季节化。

    对每个观测 (year=Y, 周期 p)：期望值 = 严格更早年份 (year<Y) 中同周期 ±window 的中位数；
    尺度 = 1.4826 × MAD（同样只用更早年份）。z = (value − 期望) / 尺度。
    首个年份因无更早基线，z 为 NaN。
    """
    d = df.copy()
    d[date_col] = pd.to_datetime(d[date_col])
    d = d.sort_values(date_col).reset_index(drop=True)
    d["_year"] = d[date_col].dt.year
    p = _period_key(d[date_col], freq)
    n = _num_periods(freq)
    # 环形窗口展开为 unwrapped 距离
    vals = pd.to_numeric(d[value_col], errors="coerce").to_numpy()
    years = d["_year"].to_numpy()
    exp = np.full(len(d), np.nan)
    scl = np.full(len(d), np.nan)
    for i in range(len(d)):
        Y = years[i]
        pi = p.iloc[i]
        mask = years < Y
        if not mask.any():
            continue
        pp = p.to_numpy()[mask]
        vv = vals[mask]
        dist = np.abs(pp - pi)
        dist = np.minimum(dist, n - dist)  # 环形
        sel = (dist <= doy_window) & np.isfinite(vv)
        # 更早年全局稳健尺度（下限，防止局部 MAD→0 导致 z 爆炸）
        m_prev = mask & np.isfinite(vals)
        if m_prev.sum() >= 10:
            gmad = np.median(np.abs(vals[m_prev] - np.median(vals[m_prev])))
            floor = 1.4826 * gmad * 0.25
        else:
            floor = 0.0
        if sel.sum() >= 5:
            med = float(np.median(vv[sel]))
            mad = float(np.median(np.abs(vv[sel] - med)))
            local = 1.4826 * mad
            scale_i = max(local, floor)
            if np.isfinite(scale_i) and scale_i > 0:
                exp[i] = med
                scl[i] = scale_i
    d["expected"] = exp
    d["scale"] = scl
    with np.errstate(divide="ignore", invalid="ignore"):
        d["z"] = (vals - exp) / scl
    # 极端 z 抑制（|z|>8 视为不可靠，置 NaN）
    d.loc[np.abs(d["z"]) > 8, "z"] = np.nan
    return d


def _num_periods(freq: str) -> int:
    return 53 if freq == "W" else 366


def add_weather(panel: pd.DataFrame, weather: pd.DataFrame, freq: str,
                date_col: str = "date") -> pd.DataFrame:
    """把日度气象对齐到面板频率，并生成标准化暴露列 *_z。"""
    w = weather.copy()
    w[date_col] = pd.to_datetime(w[date_col])
    mapping = {
        "precipitation_sum": "precipitation",
        "temperature_2m_max": "temp_max",
        "vpd": "vpd",
        "wind_speed_10m_max": "wind_speed",
        "soil_moisture_0_7": "soil_moisture",
    }
    keep = [date_col] + [c for c in mapping if c in w.columns]
    w = w[keep].rename(columns=mapping)
    if freq == "W":
        w = (w.set_index(date_col)
              .resample("W")
              .agg({"precipitation": "sum", "temp_max": "mean", "vpd": "mean",
                    "wind_speed": "mean", "soil_moisture": "mean"})
              .reset_index())
        # 周标签对齐：面板用 ISO(year, week)
        panel = panel.copy()
        iso = pd.to_datetime(panel[date_col]).dt.isocalendar()
        panel["iso_year"] = iso["year"].astype(int)
        panel["iso_week"] = iso["week"].astype(int)
        wiso = pd.to_datetime(w[date_col]).dt.isocalendar()
        w["iso_year"] = wiso["year"].astype(int)
        w["iso_week"] = wiso["week"].astype(int)
        out = panel.merge(w.drop(columns=[date_col]), on=["iso_year", "iso_week"], how="left")
    else:
        out = panel.merge(w, on=date_col, how="left")
    for c in ["precipitation", "temp_max", "vpd", "wind_speed", "soil_moisture"]:
        if c in out.columns:
            mu, sd = out[c].mean(), out[c].std()
            out[c + "_z"] = (out[c] - mu) / sd if sd and sd > 0 else np.nan
    return out


def weather_coverage(weather: pd.DataFrame, start: str, end: str) -> Dict:
    w = weather[(weather["date"] >= start) & (weather["date"] <= end)]
    return {"n_days": int(len(w)), "start": str(w["date"].min().date()) if len(w) else None,
            "end": str(w["date"].max().date()) if len(w) else None}