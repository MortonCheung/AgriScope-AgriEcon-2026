# -*- coding: utf-8 -*-
"""Phase 10：结构化输出 Schema + 数字安全校验（§4.2 / §12.4）。

数字安全：finite / required-positive / low<=point<=high / 量级 / 单位。
量级硬边界（hard sanity bounds）**由历史分布推出**，禁止手写「0–100 元」。
异常一律 reject（不缓存、不输出）。
"""
from __future__ import annotations
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

UNIT = "CNY/kg"
DIRECTIONS = ("up", "down", "flat")

FORECAST_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["forecast_horizon", "point_forecast", "range_low", "range_high",
                 "direction", "confidence", "drivers", "downside_risks",
                 "assumptions", "uncertainty", "unit", "method", "context_hash"],
    "properties": {
        "forecast_horizon": {"type": "integer"},
        "point_forecast": {"type": "number", "positive": True},
        "range_low": {"type": "number", "positive": True},
        "range_high": {"type": "number", "positive": True},
        "direction": {"enum": list(DIRECTIONS)},
        "confidence": {"type": "number", "min": 0, "max": 1},
        "drivers": {"type": "array", "items": "string"},
        "downside_risks": {"type": "array", "items": "string"},
        "assumptions": {"type": "array", "items": "string"},
        "uncertainty": {"type": "string"},
        "unit": {"const": UNIT},
        "method": {"type": "string"},
        "context_hash": {"type": "string"},
    },
}

RESIDUAL_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["adjustment_pct", "confidence", "rationale", "method", "context_hash"],
    "properties": {
        "adjustment_pct": {"type": "number"},      # 相对统计 baseline 的百分比调整
        "confidence": {"type": "number", "min": 0, "max": 1},
        "rationale": {"type": "string"},
        "method": {"type": "string"},
        "context_hash": {"type": "string"},
    },
}

CRITIC_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["warnings", "recommendation_strength", "model_disagreement", "method", "context_hash"],
    "properties": {
        "warnings": {"type": "array", "items": "string"},
        "recommendation_strength": {"enum": ["weak", "moderate", "strong"]},
        "model_disagreement": {"type": "number", "min": 0},
        "method": {"type": "string"},
        "context_hash": {"type": "string"},
    },
}


def hard_bounds(dataset: pd.DataFrame, crop: str, *, cutoff: str) -> Tuple[float, float]:
    """Historical validation uses cutoff-observable prices only; fail closed if missing."""
    mask = (dataset["crop"] == crop) & (pd.to_datetime(dataset["date"]) <= pd.Timestamp(cutoff))
    p = dataset.loc[mask, "price_per_kg"].astype(float).values
    if not len(p) or not np.isfinite(p).all() or np.min(p) <= 0:
        raise ValueError("missing_valid_cutoff_safe_bounds")
    return (float(np.min(p) * 0.5), float(np.max(p) * 3.0))


def _finite(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and np.isfinite(float(v))


def _check_keys(obj: Dict[str, Any], schema: Dict[str, Any], errors: List[str]) -> None:
    for k in schema["required"]:
        if k not in obj:
            errors.append(f"missing:{k}")


def _binding(obj: dict, errors: list, context_hash: str | None, method: str | None) -> None:
    for key, expected in (("context_hash", context_hash), ("method", method)):
        if not isinstance(obj.get(key), str) or not obj.get(key):
            errors.append(f"invalid:{key}")
        elif expected is not None and obj[key] != expected:
            errors.append(f"{key}_mismatch")


def validate_forecast(obj: Any, horizon: int, bounds: Tuple[float, float], *,
                      unit: str = UNIT, context_hash: str | None = None,
                      method: str | None = None) -> Dict[str, Any]:
    errors: List[str] = []
    if not isinstance(obj, dict):
        return {"ok": False, "errors": ["not_an_object"], "obj": obj}
    _check_keys(obj, FORECAST_SCHEMA, errors)
    if errors:
        return {"ok": False, "errors": errors, "obj": obj}

    _binding(obj, errors, context_hash, method)
    if not all(_finite(value) and value > 0 for value in bounds) or bounds[0] > bounds[1]:
        errors.append("invalid_validation_bounds")
    for k in ["point_forecast", "range_low", "range_high"]:
        if not _finite(obj[k]):
            errors.append(f"non_finite:{k}")
        elif float(obj[k]) <= 0:
            errors.append(f"non_positive:{k}")
    if not _finite(obj.get("confidence")):
        errors.append("non_finite:confidence")
    else:
        c = float(obj["confidence"])
        if not (0.0 <= c <= 1.0):
            errors.append("confidence_out_of_range")
    if obj.get("direction") not in DIRECTIONS:
        errors.append("bad_direction")
    if obj.get("unit") != unit:
        errors.append("unit_mismatch")
    if (isinstance(obj.get("forecast_horizon"), bool) or
            not isinstance(obj.get("forecast_horizon"), int) or obj["forecast_horizon"] != int(horizon)):
        errors.append("horizon_mismatch")
    for k in ["drivers", "downside_risks", "assumptions"]:
        if not isinstance(obj.get(k), list) or not all(isinstance(v, str) for v in obj[k]):
            errors.append(f"not_a_list:{k}")
    if not isinstance(obj.get("uncertainty"), str):
        errors.append("bad_uncertainty")

    if not errors:
        lo, hi = float(obj["range_low"]), float(obj["range_high"])
        pt = float(obj["point_forecast"])
        if not (lo <= pt <= hi):
            errors.append("interval_order_violated")
        b_lo, b_hi = bounds
        if not (b_lo <= pt <= b_hi):
            errors.append(f"magnitude_out_of_bounds:{b_lo:.3f}~{b_hi:.3f}")
        if not (b_lo <= lo <= b_hi and b_lo <= hi <= b_hi):
            errors.append("range_magnitude_out_of_bounds")
    return {"ok": not errors, "errors": errors, "obj": obj}


def validate_residual(obj: Any, *, context_hash: str | None = None,
                      method: str | None = None) -> Dict[str, Any]:
    errors: List[str] = []
    if not isinstance(obj, dict):
        return {"ok": False, "errors": ["not_an_object"], "obj": obj}
    _check_keys(obj, RESIDUAL_SCHEMA, errors)
    if errors:
        return {"ok": False, "errors": errors, "obj": obj}
    _binding(obj, errors, context_hash, method)
    if not _finite(obj.get("adjustment_pct")):
        errors.append("non_finite:adjustment_pct")
    if not _finite(obj.get("confidence")) or not (0.0 <= float(obj["confidence"]) <= 1.0):
        errors.append("bad_confidence")
    if not isinstance(obj.get("rationale"), str):
        errors.append("bad_rationale")
    return {"ok": not errors, "errors": errors, "obj": obj}


def validate_critic(obj: Any, *, context_hash: str | None = None,
                    method: str | None = None) -> Dict[str, Any]:
    errors: List[str] = []
    if not isinstance(obj, dict):
        return {"ok": False, "errors": ["not_an_object"], "obj": obj}
    _check_keys(obj, CRITIC_SCHEMA, errors)
    if errors:
        return {"ok": False, "errors": errors, "obj": obj}
    _binding(obj, errors, context_hash, method)
    if not isinstance(obj.get("warnings"), list) or not all(isinstance(v, str) for v in obj["warnings"]):
        errors.append("bad_warnings")
    if obj.get("recommendation_strength") not in ("weak", "moderate", "strong"):
        errors.append("bad_strength")
    if not _finite(obj.get("model_disagreement")) or float(obj["model_disagreement"]) < 0:
        errors.append("bad_disagreement")
    return {"ok": not errors, "errors": errors, "obj": obj}


__all__ = ["FORECAST_SCHEMA", "RESIDUAL_SCHEMA", "CRITIC_SCHEMA",
           "validate_forecast", "validate_residual", "validate_critic",
           "hard_bounds", "UNIT", "DIRECTIONS"]
