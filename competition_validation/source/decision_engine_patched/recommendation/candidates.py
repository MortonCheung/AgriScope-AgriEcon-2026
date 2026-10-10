# -*- coding: utf-8 -*-
"""Phase 2 / §6 §8 §9 §19 §26: 候选种植方案自动生成。

流程：
  作物池（该城市有价格模型） → 参考成本/亩产（user > reference > proxy，标注）
  → 上市窗口离散化（默认 10 天窗，农事可行 + 用户时间约束）
  → 由上市窗口反推种植窗口（记录 planting_date_source）
  → 面积阶梯（预算/面积/单作物上限约束，步长按规模自适应）
  → candidate_id（稳定、可复现）

硬约束：plant ≥ earliest_plant_date；harvest ≤ latest_harvest_date；面积 ≤ available_area；
        预算约束 total_cost ≤ budget；农事硬拒绝（如露地越冬喜温作物）。
"""
from __future__ import annotations
import hashlib
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from decision_engine.common import de_path
from decision_engine.recommendation import calendar as cal
from decision_engine.recommendation import reference_inputs as ri

SHENYANG_CROPS = ["土豆", "西红柿", "黄瓜", "韭菜", "青椒", "尖椒", "茄子", "芹菜", "芸豆", "甘蓝"]
AREA_FRACTIONS = [1.0, 0.75, 0.5, 0.25]

# 非种植标的（畜产品/加工品）：不进入"种植方案"候选
NON_PLANTABLE = ["猪肉", "鲜猪肉", "五花猪肉", "生猪", "仔猪", "牛肉", "羊肉", "鸡肉", "鸡胸肉",
                 "鸡蛋", "鲜奶", "牛奶", "鲤鱼", "带鱼", "淡水鱼", "海鲜", "水果", "香蕉", "柑橘",
                 "苹果", "梨", "豆油", "面粉", "大米", "农副产品", "生活必需品", "粮食"]

# 允许参与推荐的作物类别（叶菜/果菜/根茎/豆类/白菜类）
PLANTABLE_KEYWORDS = ["菜", "豆", "葱", "瓜", "茄", "椒", "薯", "萝卜", "玉米", "大豆", "马铃薯"]


def available_crops(city: str) -> List[str]:
    """该城市有价格模型且**可作为种植标的**的作物清单（排除畜产品/加工品）。"""
    if city == "沈阳":
        return list(SHENYANG_CROPS)
    p = de_path("data", "features", f"regional_{city}.parquet")
    if not p.exists():
        return []
    d = pd.read_parquet(p, columns=["crop"])
    cnt = d["crop"].value_counts()
    pool = [c for c in cnt[cnt >= 200].index.tolist()
            if c not in NON_PLANTABLE and any(k in c for k in PLANTABLE_KEYWORDS)]
    return sorted(pool)


def area_step(available_area_mu: float) -> float:
    """§26 面积离散步长。"""
    if available_area_mu <= 50:
        return 1.0
    if available_area_mu <= 200:
        return 5.0
    return 10.0


def _round_step(x: float, step: float) -> float:
    return float(max(step, round(x / step) * step))


def _candidate_id(city: str, crop: str, plant: pd.Timestamp, harvest: pd.Timestamp, area: float) -> str:
    raw = f"{city}|{crop}|{plant.date()}|{harvest.date()}|{area:.1f}"
    return "C" + hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]


def _discretize_windows(windows: List[Dict], max_per_crop: int) -> List[Dict]:
    """在可行窗口内均匀抽样，保证跨月多样性。"""
    ok = [w for w in windows if w.get("feasible")]
    if len(ok) <= max_per_crop:
        return ok
    by_month: Dict[int, List[Dict]] = {}
    for w in ok:
        by_month.setdefault(pd.Timestamp(w["window_start"]).month, []).append(w)
    picked: List[Dict] = []
    per_month = max(1, max_per_crop // max(1, len(by_month)))
    for m, ws in sorted(by_month.items()):
        idx = np.linspace(0, len(ws) - 1, min(per_month, len(ws))).round().astype(int)
        picked.extend([ws[i] for i in idx])
    picked = sorted(picked, key=lambda w: w["window_start"])[:max_per_crop]
    return picked


def generate_candidate_plans(
    city: str,
    available_area_mu: float,
    budget: float,
    earliest_plant_date: str,
    latest_harvest_date: str,
    risk_preference: str = "balanced",
    allowed_crops: Optional[List[str]] = None,
    excluded_crops: Optional[List[str]] = None,
    cost_per_mu_by_crop: Optional[Dict[str, float]] = None,
    expected_yield_by_crop: Optional[Dict[str, float]] = None,
    max_area_per_crop: Optional[float] = None,
    min_area_per_crop: float = 1.0,
    harvest_window_days: int = 10,
    max_windows_per_crop: int = 8,
    max_candidates: int = 800,
    allow_proxy: bool = True,
) -> Dict:
    crops_pool = available_crops(city)
    if not crops_pool:
        return {"status": "insufficient_market_data", "city": city,
                "reason": f"{city} 无可用价格序列（v1 审计结论：无连续官方价格）",
                "candidates": [], "meta": {"crop_pool": []}}

    if allowed_crops:
        crops_pool = [c for c in crops_pool if c in allowed_crops]
    if excluded_crops:
        crops_pool = [c for c in crops_pool if c not in excluded_crops]

    epd, lhd = pd.Timestamp(earliest_plant_date), pd.Timestamp(latest_harvest_date)
    if lhd <= epd:
        return {"status": "invalid_input", "reason": "latest_harvest_date 必须晚于 earliest_plant_date",
                "candidates": [], "meta": {}}

    ref = ri.reference_table(city, crops_pool, cost_per_mu_by_crop, expected_yield_by_crop)
    step = area_step(available_area_mu)
    cap_area = available_area_mu if max_area_per_crop is None else min(available_area_mu, max_area_per_crop)

    candidates, rejected = [], []
    for _, r in ref.iterrows():
        crop = r["crop"]
        if not r["usable"]:
            rejected.append({"crop": crop, "reason": "成本/亩产不可用（需用户输入）",
                             "cost_level": r["cost_level"], "yield_level": r["yield_level"]})
            continue
        cost, yld = float(r["cost_per_mu"]), float(r["yield_kg_per_mu"])

        # 预算/面积决定单作物最大可行面积
        max_by_budget = budget / cost if cost > 0 else cap_area
        max_area = min(cap_area, max_by_budget)
        if max_area < min_area_per_crop:
            rejected.append({"crop": crop, "reason": f"预算/面积上限不足（max_area={max_area:.1f} 亩 < 最小地块）"})
            continue

        lo_days, hi_days = cal.ASSUMED_GROWING_DAYS.get(crop, (75, 105))
        harvest_floor = epd + pd.Timedelta(days=lo_days)      # 用户plant起点 + 最短生育期
        if harvest_floor > lhd:
            rejected.append({"crop": crop, "reason": "时间窗口不足以完成一个生育期"})
            continue

        windows = cal.feasible_harvest_windows(city, crop, harvest_floor, lhd,
                                               window_days=harvest_window_days)
        windows = _discretize_windows(windows, max_windows_per_crop)
        if not windows:
            rejected.append({"crop": crop, "reason": "无农事可行上市窗口"})
            continue

        areas = sorted({_round_step(max_area * f, step) for f in AREA_FRACTIONS})
        areas = [a for a in areas if a >= min_area_per_crop]
        for w in windows:
            plant_start, plant_end = w["plant_start"], w["plant_end"]
            if plant_start < epd or pd.Timestamp(w["window_end"]) > lhd:
                rejected.append({"crop": crop, "reason": "种植/上市越界用户时间约束",
                                 "plant_start": str(plant_start.date())})
                continue
            for area in areas:
                total_cost = area * cost
                if total_cost > budget:
                    continue
                candidates.append({
                    "candidate_id": _candidate_id(city, crop, plant_start, w["window_end"], area),
                    "city": city, "crop": crop,
                    "plant_date": str(plant_start.date()),
                    "plant_window_end": str(plant_end.date()),
                    "harvest_start": str(pd.Timestamp(w["window_start"]).date()),
                    "harvest_date": str(pd.Timestamp(w["window_end"]).date()),
                    "area_mu": area, "total_cost": round(total_cost, 2),
                    "cost_per_mu": cost, "expected_yield_per_mu": yld,
                    "cost_level": r["cost_level"], "yield_level": r["yield_level"],
                    "cost_is_proxy": bool(r["cost_is_proxy"]), "yield_is_proxy": bool(r["yield_is_proxy"]),
                    "reference_warning": r["warning"],
                    "planting_date_source": w["planting_date_source"],
                    "constraint_strength": w["constraint_strength"],
                    "agro_warnings": w["warnings"], "agro_violations": w["violations"],
                    "calendar_confidence_penalty": w["confidence_penalty"],
                    "risk_preference": risk_preference,
                })

    # 数量控制：按 (crop, month) 均匀截断，避免只保留少数作物
    if len(candidates) > max_candidates:
        df = pd.DataFrame(candidates)
        df["_m"] = pd.to_datetime(df["harvest_date"]).dt.month
        keep = (df.groupby(["crop", "_m"], group_keys=False)
                .apply(lambda g: g.head(max(1, int(np.ceil(max_candidates / df.groupby(['crop','_m']).ngroups))))))
        candidates = keep.drop(columns=["_m"]).to_dict("records")

    dupes = len(candidates) - len({c["candidate_id"] for c in candidates})
    return {
        "status": "ok" if candidates else "no_feasible_candidate",
        "city": city,
        "request": {"available_area_mu": available_area_mu, "budget": budget,
                    "earliest_plant_date": earliest_plant_date, "latest_harvest_date": latest_harvest_date,
                    "risk_preference": risk_preference,
                    "allowed_crops": allowed_crops, "excluded_crops": excluded_crops},
        "candidates": candidates,
        "meta": {"crop_pool": crops_pool, "n_crops_pool": len(crops_pool),
                 "n_candidates": len(candidates), "duplicate_ids": int(dupes),
                 "area_step_mu": step, "harvest_window_days": harvest_window_days,
                 "rejected": rejected,
                 "proxy_crops": sorted({c["crop"] for c in candidates if c["cost_is_proxy"] or c["yield_is_proxy"]}),
                 "note": "候选仅覆盖同季单茬（不做复种）；面积不代表市场供给影响（无该因果模型）"},
    }