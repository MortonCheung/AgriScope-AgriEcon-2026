"""Cutoff-safe numeric packets; reversible blind metadata never enters provider input."""
from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from long_horizon.common import load_frozen_dataset
from llm.common import UNIT, PRICE_LEVEL, stable_hash

CITY = "沈阳"
DEFAULT_CONFIG = {"season_window_days": 30, "short_model_horizons": [7, 14, 30],
                  "unit": UNIT, "price_level": PRICE_LEVEL,
                  "calendar": "gregorian", "time_index": "calendar",
                  "history_recent_obs": 120,      # 逐日明细只保留最近 N 个观测
                  "history_monthly": True}        # 更早的历史按月聚合成 mean/min/max/n
RELATIVE_UNIT = "ratio_to_current_price"


def _history(dataset: pd.DataFrame, crop: str, cutoff: str) -> pd.DataFrame:
    dates = pd.to_datetime(dataset["date"])
    sub = dataset.loc[(dataset["crop"] == crop) & (dates <= pd.Timestamp(cutoff)),
                      ["date", "price_per_kg"]].copy()
    sub["date"] = pd.to_datetime(sub["date"])
    sub = sub.sort_values("date")
    if sub.empty or not np.isfinite(sub["price_per_kg"]).all() or (sub["price_per_kg"] <= 0).any():
        raise ValueError("invalid_or_missing_cutoff_history")
    if sub["date"].duplicated().any():
        raise ValueError("duplicate_crop_observation_date")
    return sub


def _previous_season(sub: pd.DataFrame, cut: pd.Timestamp, days: int) -> Optional[float]:
    end = cut - pd.Timedelta(days=365)
    prices = sub.loc[(sub.date > end - pd.Timedelta(days=days)) & (sub.date <= end), "price_per_kg"]
    return float(prices.mean()) if len(prices) else None


def _compress_history(sub: pd.DataFrame, last_date: pd.Timestamp,
                      recent_obs: int) -> tuple[list, list, dict]:
    """把「截断前的全量逐日价格」压缩为「最近 N 个逐日观测 + 更早月份聚合」。

    目的（§6 Prompt/Context 压缩）：保留预测所需结构（近期形态、季节轮廓、水平与波动），
    去掉与本次预测无关的逐日长尾。聚合值全部由程序计算，且只使用 cutoff 之前已发生的观测。
    """
    rows = [{"day_offset": int((date - last_date).days), "price": float(value)}
            for date, value in zip(sub.date, sub.price_per_kg)]
    split = max(0, len(rows) - recent_obs)
    recent, older = rows[split:], rows[:split]
    monthly: list = []
    if older:
        frame = sub.iloc[:split].copy()
        frame["_ym"] = frame.date.dt.to_period("M")
        anchor_period = last_date.to_period("M")
        for ym, group in frame.groupby("_ym", sort=False):
            price = group.price_per_kg.astype(float)
            monthly.append({
                "month_offset": int((anchor_period - ym).n),
                "mean": float(price.mean()), "min": float(price.min()),
                "max": float(price.max()), "n": int(len(price)),
            })
        monthly.sort(key=lambda item: item["month_offset"])
    meta = {"n_obs_total": len(rows), "recent_obs": len(recent),
            "monthly_buckets": len(monthly),
            "first_date": str(sub.iloc[0].date.date()), "last_date": str(last_date.date()),
            "compression": "recent_daily_plus_older_monthly_aggregates"}
    return recent, monthly, meta


def _short_model(sub: pd.DataFrame, row: pd.Series, crop: str, horizons: list[int]) -> dict:
    """Historical benchmark must never load Final artifacts refitted through 2026."""
    last = float(row.price_per_kg)
    cut = pd.Timestamp(row.date)
    return {f"d{h}": {"value": _previous_season(sub, cut, h) or last,
                       "source": "cutoff_safe_seasonal_rule_baseline",
                       "is_short_model": False,
                       "final_artifact": "NOT_USED_POST_CUTOFF_TRAINING"}
            for h in horizons}


def build_packet(crop: str, cutoff: str, horizon: int,
                 config: Optional[Dict[str, Any]] = None,
                 dataset: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    cfg = {**DEFAULT_CONFIG, **{key: value for key, value in (config or {}).items() if key in DEFAULT_CONFIG}}
    if cfg["unit"] != UNIT or cfg["price_level"] != PRICE_LEVEL:
        raise ValueError("packet_price_unit_or_level_mismatch")
    sub = _history(dataset if dataset is not None else load_frozen_dataset(), crop, cutoff)
    cut, last_date = pd.Timestamp(cutoff), pd.Timestamp(sub.iloc[-1].date)
    price = sub.price_per_kg.astype(float)
    current = float(price.iloc[-1])
    recent = sub.loc[sub.date > last_date - pd.Timedelta(days=30), "price_per_kg"]
    recent90 = sub.loc[sub.date > last_date - pd.Timedelta(days=90), "price_per_kg"]
    same_month = sub.loc[sub.date.dt.month == cut.month, "price_per_kg"]
    returns = {}
    for lag in (7, 14, 30, 60, 90):
        prev = sub.loc[sub.date <= last_date - pd.Timedelta(days=lag), "price_per_kg"]
        returns[f"d{lag}"] = current / float(prev.iloc[-1]) - 1 if len(prev) else None
    rolling_peak = recent90.cummax()
    max_dd = float((recent90 / rolling_peak - 1).min())
    span = int((last_date - sub.iloc[0].date).days) + 1
    unavailable = lambda reason: {"available": False, "status": "NOT_FOUND", "reason": reason}
    recent_rows, monthly_rows, hist_meta = _compress_history(sub, last_date, int(cfg["history_recent_obs"]))
    return {
        "schema_version": "lh_context_v2", "mode": "context", "city": CITY, "crop": crop,
        "cutoff": str(cut.date()), "anchor_observation_date": str(last_date.date()),
        "feature_available_at": str(last_date.date()), "horizon": int(horizon),
        "unit": cfg["unit"], "price_level": PRICE_LEVEL, "current_price": current,
        "history_recent": recent_rows,
        "history_monthly": monthly_rows if cfg["history_monthly"] else [],
        "history_meta": hist_meta,
        # 量级校验边界必须来自**全量**历史（而非被压缩的明细），否则会误判合法输出为越界。
        "price_bounds": [float(price.min()) * .5, float(price.max()) * 3.],
        "returns": returns,
        "rolling": {"mean_30": float(recent.mean()), "median_30": float(recent.median()),
                    "volatility_30": float(np.std(np.diff(np.log(recent)))) if len(recent) > 1 else 0.,
                    "drawdown_30": current / float(recent.max()) - 1,
                    "max_drawdown_90": max_dd},
        "seasonality": {"same_month_history": same_month.astype(float).tolist(),
                        "same_month_count": len(same_month),
                        "seasonal_percentile": float((same_month <= current).mean()) if len(same_month) else None,
                        "seasonal_p10": float(same_month.quantile(.1)) if len(same_month) else None,
                        "seasonal_p50": float(same_month.quantile(.5)) if len(same_month) else None,
                        "seasonal_p90": float(same_month.quantile(.9)) if len(same_month) else None,
                        "historical_profile": {int(k): float(v) for k, v in
                                               sub.groupby(sub.date.dt.month).price_per_kg.mean().items()}},
        "short_model": _short_model(sub, sub.iloc[-1], crop, cfg["short_model_horizons"]),
        "risk": {"hri": unavailable("NO_PIT_PER_CUTOFF_SOURCE"),
                 "market_risk": unavailable("NO_PIT_PER_CUTOFF_SOURCE"),
                 "climate_exposure": unavailable("NO_DATED_CLIMATE_SOURCE"),
                 "program_proxy": {"expanding_price_percentile": float((price <= current).mean()),
                                   "volatility_30": float(np.std(np.diff(np.log(recent)))) if len(recent) > 1 else 0.}},
        "supply": unavailable("NO_STRUCTURED_SOURCE_FOR_CROP"),
        "production": unavailable("NO_DATED_CITY_DAILY_PHENOLOGY_SOURCE"),
        "events": [], "events_available": False, "events_status": "NOT_FOUND",
        "data_quality": {"n_obs": len(sub), "first_date": str(sub.iloc[0].date.date()),
                         "last_date": str(last_date.date()),
                         "missing_calendar_days_pct": 100 * (1 - len(sub) / span),
                         "n_years": int(sub.date.dt.year.nunique()),
                         "source": "frozen Final dataset / shenyang_core wholesale market_daily"},
        "config": cfg,
    }


def build_case_context(crop: str, cutoff: str, horizon: int, *, mode: str = "context",
                       config: Optional[Dict[str, Any]] = None,
                       dataset: Optional[pd.DataFrame] = None) -> tuple[dict, dict]:
    """Return (provider packet, host-only inverse transform and PIT validation bounds)."""
    from llm.schemas import hard_bounds
    ds = dataset if dataset is not None else load_frozen_dataset()
    packet = build_packet(crop, cutoff, horizon, config, ds)
    scale = float(packet["current_price"]) if mode == "blind" else 1.
    raw_bounds = hard_bounds(ds, crop, cutoff=cutoff)
    host = {"crop": crop, "city": CITY, "cutoff": cutoff, "scale": scale, "unit": UNIT,
            "bounds": [value / scale for value in raw_bounds],
            "anchor_observation_date": packet["anchor_observation_date"]}
    if mode == "blind":
        anchor = pd.Timestamp(packet["anchor_observation_date"])
        first = pd.Timestamp(packet["data_quality"]["first_date"])
        packet.update({"mode": "blind", "city": "CITY_A", "crop": "CROP_A",
                       "cutoff": f"T+{(pd.Timestamp(cutoff) - anchor).days}d",
                       "anchor_observation_date": "T0", "feature_available_at": "T0",
                       "unit": RELATIVE_UNIT, "current_price": 1.})
        for row in packet["history_recent"]:
            row["price"] /= scale
        for bucket in packet["history_monthly"]:
            for key in ("mean", "min", "max"):
                bucket[key] /= scale
        packet["price_bounds"] = [value / scale for value in packet["price_bounds"]]
        # history_meta 含绝对首末日期：blind 模式必须匿名化，否则会泄露真实时间锚点。
        packet["history_meta"] = {**packet["history_meta"],
                                  "first_date": f"T-{(anchor - first).days}d", "last_date": "T0"}
        for key in ("mean_30", "median_30"):
            packet["rolling"][key] /= scale
        seasonal = packet["seasonality"]
        seasonal["same_month_history"] = [v / scale for v in seasonal["same_month_history"]]
        for key in ("seasonal_p10", "seasonal_p50", "seasonal_p90"):
            if seasonal[key] is not None:
                seasonal[key] /= scale
        seasonal["historical_profile"] = {f"M-{(pd.Timestamp(cutoff).month - month) % 12}": value / scale
                                           for month, value in seasonal["historical_profile"].items()}
        for short in packet["short_model"].values():
            short["value"] /= scale
        packet["data_quality"].update({"first_date": f"T-{(anchor - first).days}d",
                                        "last_date": "T0", "n_years": None,
                                        "source": "HOST_VERIFIED_ANONYMOUS_OBSERVATIONS"})
        packet["config"] = {"time_index": "relative", "calendar": "relative_index",
                            "unit": RELATIVE_UNIT, "short_model_horizons": [7, 14, 30]}
    elif mode != "context":
        raise ValueError("unknown_context_mode")
    return packet, host


def build_blind_packet(crop: str, cutoff: str, horizon: int,
                       config: Optional[Dict[str, Any]] = None,
                       dataset: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    return build_case_context(crop, cutoff, horizon, mode="blind", config=config, dataset=dataset)[0]


def restore_forecast(payload: dict, host: dict) -> dict:
    result = dict(payload)
    for key in ("point_forecast", "range_low", "range_high"):
        if key in result:
            result[key] = float(result[key]) * float(host["scale"])
    result["unit"] = host["unit"]
    return result


def packet_hash(packet: Dict[str, Any]) -> str:
    return stable_hash({k: v for k, v in packet.items() if k != "generated_at"}, n=64)


__all__ = ["build_packet", "build_blind_packet", "build_case_context", "restore_forecast",
           "packet_hash", "DEFAULT_CONFIG", "CITY", "RELATIVE_UNIT"]
