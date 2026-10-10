# -*- coding: utf-8 -*-
"""C10: 能力注册表（代码化，§47/§48/§49/§50）。

- 统一状态枚举 STATUS（各模块不得自造字符串）
- 城市能力 CITY_CAPABILITY（由数据审计决定）
- 作物能力（逐 city×crop 从 Final 产物读取）
- horizon 能力：7/14/30 可用模型点预测；60/90 仅 scenario_only
"""
from __future__ import annotations
from typing import Dict, List, Optional

import pandas as pd

from decision_engine.final.fcommon import (REPORTS_DIR, SNAPSHOT_DIR, SHENYANG_CROPS,
                                           CITY_TIERS)

# ---------------------------------------------------------------- 状态枚举
STATUS_OK = "OK"
STATUS = [
    "OK", "LOW_CONFIDENCE", "PARTIAL", "SCENARIO_ONLY", "USER_INPUT_REQUIRED",
    "INSUFFICIENT_MARKET_DATA", "NO_FEASIBLE_PLAN", "NO_FEASIBLE_WINDOW",
    "NO_CLEAR_WINNER", "NO_DIVERSIFICATION_BENEFIT", "MODEL_ERROR",
]

# 可用模型点预测的 horizon（其余为 scenario-only）
MODEL_HORIZONS = [7, 14, 30]
SCENARIO_HORIZONS = [60, 90]
ALL_HORIZONS = [7, 14, 30, 60, 90]

# ---------------------------------------------------------------- 城市能力
CITY_CAPABILITY: Dict[str, Dict] = {
    "沈阳": {
        "tier": "FULL", "price_level": "wholesale",
        "crops": SHENYANG_CROPS, "model_horizons": MODEL_HORIZONS,
        "scenario_horizons": SCENARIO_HORIZONS,
        "has_price_model": True, "has_hri": True, "has_market_risk": True,
        "basis": "shenyang_core/market_daily.parquet（发改委菜篮子，单一 wholesale，2021-2026 日频）",
    },
    "朝阳": {
        "tier": "EXTENDED", "price_level": "market_average",
        "crops": SHENYANG_CROPS, "model_horizons": [7, 14, 30],
        "scenario_horizons": ALL_HORIZONS,
        "has_price_model": True, "has_hri": True, "has_market_risk": True,
        "basis": "chaoyang_extended/market_daily.parquet（发改委全市均价 market_average 单层，密度低于沈阳）",
        "limitation": "扩展模型，仅作参考；覆盖率与稳定性弱于沈阳",
    },
    "锦州": {
        "tier": "LIMITED", "price_level": "mixed_ocr",
        "crops": [], "model_horizons": [], "scenario_horizons": [],
        "has_price_model": False, "has_hri": False, "has_market_risk": False,
        "basis": "jinzhou_extended/market_daily.parquet（多 price_level / OCR 转录，口径不单一）",
        "limitation": "多层级混用 + OCR 来源，不满足 Final 单一价格口径要求 → 不提供模型输出",
    },
    "大连": {"tier": "INSUFFICIENT_MARKET_DATA", "has_price_model": False},
    "铁岭": {"tier": "INSUFFICIENT_MARKET_DATA", "has_price_model": False},
    "丹东": {"tier": "INSUFFICIENT_MARKET_DATA", "has_price_model": False},
}

CITY_ALIASES = {"沈阳市": "沈阳", "Shenyang": "沈阳", "朝阳区": "朝阳"}


def normalize_city(city: Optional[str]) -> Optional[str]:
    if city is None:
        return None
    c = str(city).strip()
    return CITY_ALIASES.get(c, c)


def city_capability(city: str) -> Dict:
    c = normalize_city(city)
    if c in CITY_CAPABILITY:
        return {"city": c, **CITY_CAPABILITY[c]}
    return {"city": c, "tier": "UNKNOWN", "has_price_model": False,
            "status": "INSUFFICIENT_MARKET_DATA",
            "note": "未登记城市：默认拒绝，不做跨城 fallback"}


def horizon_capability(city: str, horizon: int) -> Dict:
    cap = city_capability(city)
    h = int(horizon)
    if not cap.get("has_price_model"):
        return {"horizon": h, "mode": "none", "scenario_only": True,
                "reason": "city_insufficient_market_data"}
    if h in (cap.get("model_horizons") or []):
        return {"horizon": h, "mode": "model", "scenario_only": False}
    return {"horizon": h, "mode": "scenario_only", "scenario_only": True,
            "reason": "该 horizon 超出模型验证能力（60/90d 明显退化）→ 仅情景"}


# ---------------------------------------------------------------- 作物能力
def _selection() -> pd.DataFrame:
    p = REPORTS_DIR / "tables" / "price_model_selection.csv"
    try:
        return pd.read_csv(p)
    except Exception:
        return pd.DataFrame()


def _interval_summary() -> pd.DataFrame:
    p = REPORTS_DIR / "tables" / "interval_calibration_summary.csv"
    try:
        return pd.read_csv(p)
    except Exception:
        return pd.DataFrame()


def crop_capability(city: str, crop: str) -> Dict:
    sel = _selection()
    cap = city_capability(city)
    base = {"city": cap.get("city"), "crop": crop,
            "price_model": None, "available_horizons": [],
            "scenario_range_availability": None, "profit_source": None,
            "hri_availability": False, "confidence": None}
    if not cap.get("has_price_model") or not len(sel):
        base["status"] = "INSUFFICIENT_MARKET_DATA"
        return base
    sub = sel[(sel["city"] == cap["city"]) & (sel["crop"] == crop)]
    if not len(sub):
        base["status"] = "INSUFFICIENT_MARKET_DATA"
        return base
    h30 = sub[sub["horizon"] == 30]
    model = None
    if len(h30):
        r = h30.iloc[0]
        model = {"algorithm": r["model"], "route": r["route"],
                 "mean_WAPE": round(float(r["mean_WAPE"]), 3),
                 "baseline": r["best_baseline"],
                 "baseline_WAPE": round(float(r["baseline_WAPE"]), 3),
                 "beats_baseline": bool(r["beats_baseline"])}
    base.update({
        "status": "OK",
        "price_model": model,
        "available_horizons": sorted(sub["horizon"].astype(int).tolist()),
        "scenario_range_availability": "scenario_range" if len(h30) else None,
        "profit_source": "graded (see profit_grading.csv / profit_engine.csv)",
        "hri_availability": bool(cap.get("has_hri")),
        "confidence": None,
    })
    return base


def crop_capability_table() -> pd.DataFrame:
    rows = []
    for city, cap in CITY_CAPABILITY.items():
        for crop in (cap.get("crops") or []):
            rows.append(crop_capability(city, crop))
    df = pd.DataFrame(rows)
    return df


def city_capability_table() -> pd.DataFrame:
    rows = []
    for city, cap in CITY_CAPABILITY.items():
        rows.append({"city": city, "tier": cap.get("tier"),
                     "price_level": cap.get("price_level"),
                     "has_price_model": cap.get("has_price_model"),
                     "model_horizons": cap.get("model_horizons"),
                     "scenario_horizons": cap.get("scenario_horizons"),
                     "n_crops": len(cap.get("crops") or []),
                     "basis": cap.get("basis") or cap.get("limitation")})
    return pd.DataFrame(rows)


def write_capabilities() -> Dict[str, int]:
    from decision_engine.final.fcommon import ensure_dir
    ensure_dir(REPORTS_DIR / "tables")
    ct = city_capability_table()
    cr = crop_capability_table()
    ct.to_csv(REPORTS_DIR / "tables" / "city_capability.csv", index=False, encoding="utf-8-sig")
    cr.to_csv(REPORTS_DIR / "tables" / "crop_capability.csv", index=False, encoding="utf-8-sig")
    return {"cities": len(ct), "crop_rows": len(cr)}


if __name__ == "__main__":
    print(write_capabilities())
    print(city_capability_table().to_string(index=False))
    print(crop_capability("沈阳", "土豆"))