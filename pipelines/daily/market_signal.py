# -*- coding: utf-8 -*-
"""市场信号变化层（§8 §9）：Daily 在**没有用户场景**时只输出市场状态与信号变化。

为什么不做"每日种植推荐"：
  种植推荐需要 面积 / 预算 / 种植时间 / 风险偏好 / 成本 / 亩产 等用户条件；
  没有这些条件时，Final Model 自身会返回 `USER_INPUT_REQUIRED`。
  因此 Daily 不生成 rank / decision_score / 个性化方案，避免制造虚假个性化推荐。

本模块提供：
  - market_signal：每作物当日市场状态（价格/变化/历史位置/HRI/Market Risk/Signal/置信度）
  - market_signal_change：与上一快照逐项对比（price / hri / market_risk / signal_level / data_date）

不含任何 v1 依赖（不读 decision_dataset_v1 / hri_v1 / 旧推荐器）。
"""
from __future__ import annotations

import pandas as pd

from . import config as C
from . import io_utils as IO
from .final_adapter import LEVELS, _ORDER

SIGNAL_PATH = C.PROCESSED_DAILY_DIR / "market_signal.json"

BASIS = "market_signal_only"
NO_SCENARIO_NOTE = ("无用户场景（面积/预算/成本/亩产/风险偏好）→ 不输出种植推荐或排名；"
                    "Final Model 对无场景请求返回 USER_INPUT_REQUIRED。")


def _d(a, b):
    if a is None or b is None:
        return None
    try:
        return round(float(a) - float(b), 6)
    except (TypeError, ValueError):
        return None


def build_market_signal(latest_features: pd.DataFrame,
                        assessments: dict,
                        data_date: str | None) -> dict:
    """每作物市场状态（不含任何用户场景）。"""
    crops = []
    for _, row in latest_features.sort_values("crop").iterrows():
        crop = row["crop"]
        ca = assessments.get(crop)
        crops.append({
            "crop": crop,
            "data_date": str(pd.Timestamp(row["date"]).date()),
            "price": None if pd.isna(row["latest_price"]) else round(float(row["latest_price"]), 4),
            "price_level": C.MODEL_PRICE_LEVEL,
            "change_1d": None if pd.isna(row["change_1d"]) else round(float(row["change_1d"]), 6),
            "change_7d": None if pd.isna(row["change_7d"]) else round(float(row["change_7d"]), 6),
            "change_30d": None if pd.isna(row["change_30d"]) else round(float(row["change_30d"]), 6),
            "historical_percentile": None if pd.isna(row["historical_percentile"])
            else round(float(row["historical_percentile"]), 4),
            "hri": None if ca is None or not ca.hri else ca.hri.get("value"),
            "hri_level": None if ca is None or not ca.hri else ca.hri.get("level"),
            "market_risk": None if ca is None or not ca.market_risk else ca.market_risk.get("value"),
            "market_risk_level": None if ca is None or not ca.market_risk
            else ca.market_risk.get("level"),
            "daily_signal": None if ca is None else ca.daily_signal,
            "confidence": None if ca is None or not ca.confidence
            else ca.confidence.get("overall_confidence"),
            "final_status": None if ca is None else ca.final_status,
            "model_status": None if ca is None else ca.model_status,
            "warnings": [] if ca is None else list(ca.final_warnings),
        })
    return {"basis": BASIS, "user_scenario": None, "note": NO_SCENARIO_NOTE,
            "data_date": data_date, "crops": crops}


def build_change(prev_signal: dict | None, cur_signal: dict) -> list[dict]:
    """与上一快照的市场信号逐项对比（不涉及用户场景）。"""
    prev = {c["crop"]: c for c in (prev_signal or {}).get("crops", [])}
    out = []
    for c in cur_signal.get("crops", []):
        crop = c["crop"]
        p = prev.get(crop, {})
        ps, cs = p.get("daily_signal"), c.get("daily_signal")
        crossed = None
        if ps in LEVELS and cs in LEVELS:
            crossed = _ORDER[cs] > _ORDER[ps]
        item = {
            "crop": crop,
            "data_date": c["data_date"],
            "prev_data_date": p.get("data_date"),
            "price": c["price"], "prev_price": p.get("price"),
            "price_change": _d(c["price"], p.get("price")),
            "hri": c["hri"], "hri_change": _d(c["hri"], p.get("hri")),
            "market_risk": c["market_risk"],
            "market_risk_change": _d(c["market_risk"], p.get("market_risk")),
            "signal_level": cs, "prev_signal_level": ps,
            "signal_level_change": (None if (ps is None or cs is None)
                                    else _ORDER.get(cs, 0) - _ORDER.get(ps, 0)),
            "signal_crossed_up": crossed,
        }
        item["changed"] = any(v not in (None, 0) for v in
                              (item["price_change"], item["hri_change"],
                               item["market_risk_change"], item["signal_level_change"]))
        out.append(item)
    return out


def build(latest_features: pd.DataFrame, assessments: dict, data_date: str | None,
          prev_snapshot: dict | None, write: bool = True) -> dict:
    cur = build_market_signal(latest_features, assessments, data_date)
    cur["changes"] = build_change((prev_snapshot or {}).get("market_signal"), cur)
    if write:
        IO.atomic_write_json(SIGNAL_PATH, cur)
    return cur