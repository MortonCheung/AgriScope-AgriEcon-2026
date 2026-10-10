# -*- coding: utf-8 -*-
"""Phase 8 / §32-§34: 每日动态风险信号 + 阈值驱动告警。

daily_signal(city, crop, as_of_date) 输出：
  current_price_percentile / momentum / HRI / market_risk / price scenario / confidence
  + signal_change_1d / signal_change_7d / risk_level_change
  + warning_level（NORMAL / WATCH / HIGH / VERY_HIGH）

阈值**完全由历史分布自动确定**（HRI/Market Risk 的 P90 / P95，past-only），
不使用 LLM 主观判断。
"""
from __future__ import annotations
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from decision_engine.common import de_path
from decision_engine.engine.engine import DecisionEngine

LEVELS = ["NORMAL", "WATCH", "HIGH", "VERY_HIGH"]


def _src(city: str) -> Dict[str, pd.DataFrame]:
    hri_p = de_path("data", "features", "hri_v1.parquet")
    mr_p = de_path("data", "features", "market_risk_v1.parquet")
    out = {}
    if city == "沈阳":
        if hri_p.exists():
            h = pd.read_parquet(hri_p)
            h["date"] = pd.to_datetime(h["date"])
            out["hri"] = h
        if mr_p.exists():
            m = pd.read_parquet(mr_p)
            m["date"] = pd.to_datetime(m["date"])
            out["mr"] = m
        ds = pd.read_parquet(de_path("data", "processed", "decision_dataset_v1.parquet"),
                            columns=["date", "crop", "price_per_kg", "price_momentum_30",
                                     "price_momentum_60", "continuous_rise_days",
                                     "same_season_price_percentile", "expanding_price_percentile",
                                     "month", "year"])
        ds["date"] = pd.to_datetime(ds["date"])
        out["price"] = ds
    else:
        rp = de_path("data", "features", f"regional_risk_{city}.parquet")
        if rp.exists():
            r = pd.read_parquet(rp)
            r["date"] = pd.to_datetime(r["date"])
            out["hri"] = r
            out["mr"] = r
        pp = de_path("data", "features", f"regional_{city}.parquet")
        if pp.exists():
            ds = pd.read_parquet(pp)
            ds["date"] = pd.to_datetime(ds["date"])
            out["price"] = ds
    return out


def warning_thresholds(city: str, crop: str) -> Dict:
    """历史分位阈值（past-only）：HRI / Market Risk 的 P90 / P95。"""
    s = _src(city)
    out = {"HRI": None, "market_risk": None}
    if "hri" in s:
        h = s["hri"]
        sub = h[h["crop"] == crop]["hri_conceptual"].dropna() if "hri_conceptual" in h else pd.Series(dtype=float)
        if len(sub) >= 100:
            out["HRI"] = {"p50": float(sub.quantile(0.50)), "p75": float(sub.quantile(0.75)),
                          "p90": float(sub.quantile(0.90)), "p95": float(sub.quantile(0.95))}
    if "mr" in s:
        m = s["mr"]
        sub = m[m["crop"] == crop]["market_risk"].dropna() if "market_risk" in m else pd.Series(dtype=float)
        if len(sub) >= 100:
            out["market_risk"] = {"p50": float(sub.quantile(0.50)), "p75": float(sub.quantile(0.75)),
                                  "p90": float(sub.quantile(0.90)), "p95": float(sub.quantile(0.95))}
    return out


def _level(value: Optional[float], thr: Optional[Dict]) -> str:
    if value is None or not thr:
        return "UNKNOWN"
    if value >= thr["p95"]:
        return "VERY_HIGH"
    if value >= thr["p90"]:
        return "HIGH"
    if value >= thr["p75"]:
        return "WATCH"
    return "NORMAL"


def daily_signal(city: str, crop: str, as_of_date: Optional[str] = None,
                 harvest_month: Optional[int] = None) -> Dict:
    s = _src(city)
    if "price" not in s:
        return {"status": "insufficient_market_data", "city": city, "crop": crop}

    def _cut(df: pd.DataFrame) -> pd.DataFrame:
        return df[df["date"] <= pd.Timestamp(as_of_date)] if as_of_date else df

    px = _cut(s["price"])
    sub = px[px["crop"] == crop].sort_values("date")
    if not len(sub):
        return {"status": "no_price_series", "city": city, "crop": crop, "as_of_date": as_of_date}
    last = sub.iloc[-1]
    prev1 = sub.iloc[-2] if len(sub) > 1 else last
    prev7 = sub.iloc[-8] if len(sub) > 8 else sub.iloc[0]

    thr = warning_thresholds(city, crop)
    hri_v = mr_v = None
    hri_level = mr_level = "UNKNOWN"
    if "hri" in s:
        h = _cut(s["hri"])
        h = h[h["crop"] == crop].sort_values("date")
        if len(h):
            hri_v = None if pd.isna(h.iloc[-1]["hri_conceptual"]) else float(h.iloc[-1]["hri_conceptual"])
            hri_level = _level(hri_v, thr.get("HRI"))
    if "mr" in s:
        m = _cut(s["mr"])
        m = m[m["crop"] == crop].sort_values("date")
        if len(m):
            mr_v = None if pd.isna(m.iloc[-1]["market_risk"]) else float(m.iloc[-1]["market_risk"])
            mr_level = _level(mr_v, thr.get("market_risk"))

    # 价格情景（上市窗口）
    price_scenario = None
    try:
        eng = DecisionEngine(as_of=as_of_date)
        mth = harvest_month or (pd.Timestamp(as_of_date) if as_of_date else pd.Timestamp.today()).month
        plan_month = mth
        fake_harvest = pd.Timestamp(year=(pd.Timestamp(as_of_date) if as_of_date else pd.Timestamp.today()).year,
                                   month=plan_month, day=15).date()
        blk = eng._price_block(city, crop, str(fake_harvest), str(fake_harvest))
        if blk.get("available"):
            price_scenario = {"low": blk["low"], "mid": blk["mid"], "high": blk["high"],
                              "statistic": blk.get("statistic"), "month": plan_month}
    except Exception as e:
        price_scenario = {"error": f"{type(e).__name__}"}

    sig = {
        "status": "ok", "city": city, "crop": crop, "as_of_date": as_of_date or str(last["date"].date()),
        "date_latest": str(pd.Timestamp(last["date"]).date()),
        "price_latest": round(float(last["price_per_kg"]), 4),
        "current_price_percentile": None if pd.isna(last.get("same_season_price_percentile")) else
        round(float(last["same_season_price_percentile"]), 3),
        "momentum_30": None if pd.isna(last.get("price_momentum_30")) else round(float(last["price_momentum_30"]), 4),
        "momentum_60": None if pd.isna(last.get("price_momentum_60")) else round(float(last["price_momentum_60"]), 4),
        "continuous_rise_days": int(last.get("continuous_rise_days", 0) or 0),
        "HRI": hri_v, "HRI_level": hri_level, "market_risk": mr_v, "market_risk_level": mr_level,
        "price_scenario": price_scenario,
        "thresholds": thr,
    }
    # 变化检测（§33）
    def _d(a, b):
        return None if (a is None or b is None) else round(float(a - b), 4)

    sig["signal_change_1d"] = {"price": _d(sig["price_latest"], float(prev1["price_per_kg"])),
                               "momentum_30": _d(sig["momentum_30"],
                                                 None if pd.isna(prev1.get("price_momentum_30")) else float(prev1["price_momentum_30"]))}
    sig["signal_change_7d"] = {"price": _d(sig["price_latest"], float(prev7["price_per_kg"])),
                               "momentum_30": _d(sig["momentum_30"],
                                                 None if pd.isna(prev7.get("price_momentum_30")) else float(prev7["price_momentum_30"]))}

    # 风险等级变化 + 汇总告警（取两者更高）
    hri_prev_level = "UNKNOWN"
    if "hri" in s:
        h = _cut(s["hri"]); h = h[h["crop"] == crop].sort_values("date")
        if len(h) > 7:
            hv = h.iloc[-8]["hri_conceptual"]
            hri_prev_level = _level(None if pd.isna(hv) else float(hv), thr.get("HRI"))
    sig["risk_level_change"] = {"HRI_from": hri_prev_level, "HRI_to": hri_level,
                                "HRI_crossed_up": (LEVELS.index(hri_level) > LEVELS.index(hri_prev_level))
                                if hri_level in LEVELS and hri_prev_level in LEVELS else None}
    order = {lv: i for i, lv in enumerate(LEVELS + ["UNKNOWN"])}
    levels = [lv for lv in [hri_level, mr_level] if lv in LEVELS]
    sig["warning_level"] = max(levels, key=lambda lv: order[lv]) if levels else "UNKNOWN"
    sig["warning_basis"] = {"HRI": hri_level, "market_risk": mr_level,
                            "rule": "阈值来自历史分布 P75/P90/P95（past-only），规则化判定，非 LLM 判断"}
    return sig


def warning_table(city: str, crops: List[str], as_of_date: Optional[str] = None) -> pd.DataFrame:
    rows = []
    for c in crops:
        s = daily_signal(city, c, as_of_date)
        if s.get("status") != "ok":
            rows.append({"crop": c, "warning_level": "UNKNOWN", "note": s.get("status")})
            continue
        rows.append({"crop": c, "date": s["date_latest"], "price": s["price_latest"],
                     "price_percentile": s["current_price_percentile"], "momentum_30": s["momentum_30"],
                     "HRI": s["HRI"], "HRI_level": s["HRI_level"],
                     "market_risk": s["market_risk"], "market_risk_level": s["market_risk_level"],
                     "warning_level": s["warning_level"],
                     "HRI_thr_p90": (s["thresholds"].get("HRI") or {}).get("p90"),
                     "HRI_thr_p95": (s["thresholds"].get("HRI") or {}).get("p95")})
    return pd.DataFrame(rows)