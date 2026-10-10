"""Fail-closed audit of observation, feature and externally published context."""
from __future__ import annotations

import re
from typing import Any, Dict
import pandas as pd
import numpy as np

from llm.common import canonical_json


def audit_packet(packet: Dict[str, Any], dataset: pd.DataFrame | None = None,
                 host_metadata: dict | None = None) -> Dict[str, Any]:
    blind = packet.get("mode") == "blind"
    result = {"mode": packet.get("mode", "context"), "checks": {},
              "violations": [], "passed": True}

    def check(kind, ok, detail):
        result["checks"][kind] = {"ok": bool(ok), "detail": detail}
        if not ok:
            result["violations"].append({"kind": kind, "detail": detail})
            result["passed"] = False

    cut = pd.Timestamp(host_metadata["cutoff"]) if blind and host_metadata else (
        None if blind else pd.Timestamp(packet["cutoff"]))
    if blind:
        check("anonymous_identity", packet.get("city") == "CITY_A" and packet.get("crop") == "CROP_A",
              "generic case identifiers only")
        text = canonical_json(packet)
        check("anonymous_source", not re.search(r"沈阳|shenyang|西红柿|土豆|20\d{2}-\d{2}-\d{2}", text, re.I),
              "no real region/crop/source date")
        check("relative_price", packet.get("unit") == "ratio_to_current_price" and packet.get("current_price") == 1.,
              "all prices use current=1 ratio")
        check("relative_time", packet.get("anchor_observation_date") == "T0" and
              bool(re.fullmatch(r"T\+\d+d", str(packet.get("cutoff")))) and
              packet.get("feature_available_at") == "T0", "relative cutoff and feature timestamp")
        check("blind_external_context", not packet.get("events") and not packet.get("production", {}).get("available"),
              "blind benchmark has no real event/production context")
    else:
        anchor = pd.Timestamp(packet["anchor_observation_date"])
        check("price_observation", anchor <= cut, "anchor <= cutoff")
        check("feature", pd.Timestamp(packet.get("feature_available_at", packet["anchor_observation_date"])) <= cut,
              "feature timestamp <= cutoff")
    history = packet.get("history_recent", [])
    monthly = packet.get("history_monthly", [])
    check("historical_relative_offsets", bool(history) and all(
        isinstance(row.get("day_offset"), int) and row["day_offset"] <= 0 and
        np.isfinite(row.get("price", np.nan)) and row.get("price", 0) > 0 for row in history),
        "only observed prices with offsets <= 0")
    check("historical_recent_is_tail", bool(history) and all(
        history[i]["day_offset"] < history[i + 1]["day_offset"] for i in range(len(history) - 1))
        and history[-1]["day_offset"] == 0,
        "recent window is strictly increasing and ends at the anchor")
    # 月份聚合必须严格早于 anchor 月份（offset>=1），且 min<=mean<=max、n>0。
    def monthly_ok(bucket: dict) -> bool:
        if not (isinstance(bucket.get("month_offset"), int) and bucket["month_offset"] >= 1
                and isinstance(bucket.get("n"), int) and bucket["n"] > 0):
            return False
        values = [bucket.get(key, np.nan) for key in ("mean", "min", "max")]
        if not all(np.isfinite(value) and value > 0 for value in values):
            return False
        mean, low, high = values
        # 浮点求和会产生 1 ULP 级误差（如常量 2.7 的均值=2.7000000000000006 > max=2.7），
        # 用相对容差比较，仍保持 min<=mean<=max 的实质校验。
        tol = 1e-9 * max(abs(mean), abs(low), abs(high), 1e-12)
        return low <= mean + tol and mean <= high + tol

    check("historical_monthly_aggregates", all(monthly_ok(bucket) for bucket in monthly),
          "older history only as cutoff-safe monthly aggregates (offset>=1, min<=mean<=max)")

    publications = list(packet.get("events", []))
    for key in ("production", "supply", "climate"):
        value = packet.get(key, {})
        if isinstance(value, dict) and value.get("available"):
            publications.append(value)
    for key in ("hri", "market_risk", "climate_exposure"):
        value = packet.get("risk", {}).get(key, {})
        if isinstance(value, dict) and value.get("available"):
            publications.append(value)
    for i, event in enumerate(publications):
        try:
            published = pd.Timestamp(event["publication_date"])
            ok = bool(cut is not None and pd.notna(published) and published <= cut and
                      event.get("source") and event.get("available_at_cutoff") is True)
        except (KeyError, ValueError, TypeError):
            ok = False
        check(f"publication_{i}", ok, "source + publication_date <= cutoff + available_at_cutoff required")

    if dataset is not None and (not blind or host_metadata):
        crop = host_metadata["crop"] if host_metadata else packet["crop"]
        sub = dataset.loc[(dataset.crop == crop) & (pd.to_datetime(dataset.date) <= cut)].sort_values("date")
        scale = host_metadata["scale"] if host_metadata else 1.
        prices = np.asarray([row["price"] for row in history], float)
        raw = sub.price_per_kg.to_numpy(float) / scale
        # 明细被压缩为「最近 N 个观测」：唯一允许的差异是长度，且必须是**尾部**逐值相等。
        same_tail = len(prices) <= len(raw) and bool(len(prices)) and np.allclose(
            raw[-len(prices):], prices, rtol=1e-10, atol=1e-10)
        check("dataset_pit_reconstruction", same_tail,
              "provider recent history equals the host cutoff-sliced price tail")
        full = sub.price_per_kg.to_numpy(float) / scale
        bounds = packet.get("price_bounds")
        check("dataset_pit_bounds", bool(bounds and len(bounds) == 2 and
              np.isclose(bounds[0], float(full.min()) * .5, rtol=1e-10) and
              np.isclose(bounds[1], float(full.max()) * 3., rtol=1e-10)),
              "magnitude bounds derive from the full cutoff history")
    return result


__all__ = ["audit_packet"]
