# -*- coding: utf-8 -*-
"""Phase 1 / §7-§9: 农事约束层（分层推断 + 显式 provenance）。

现实约束（已核实）：项目 `crop_calendar` 只覆盖粮食作物；`crop_calendar_detailed`(v2)
对 P0 蔬菜仅有零散条目（番茄/马铃薯/黄瓜/设施蔬菜组，多为月级/跨城市）。

因此采用 **分层推断**，每一层都记录来源与强度：

  user_window              （用户显式给定）              strength=strong
  observed_calendar        （同城×同作物条目）            strength=strong
  regional_reference       （同省同作物/设施蔬菜组条目）   strength=medium
  inferred_from_price_seasonality（自身历史价格季节低谷）  strength=weak
  assumed_public_reference （公开生育期常识区间，仅用于反推种植窗口）weak + 显式标注

硬拒绝规则只在证据充分（strong/medium）时生效；weak 约束只产生 warning 与 confidence 折扣。
"""
from __future__ import annotations
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from decision_engine.common import de_path

# ---------------------------------------------------------------- 常量
WARM_SEASON_CROPS = ["西红柿", "黄瓜", "青椒", "尖椒", "茄子", "芸豆"]
WINTER_MONTHS = [12, 1, 2]

# 公开生育期常识区间（天，露地/设施合并的大致范围）——**不是项目数据**，
# 仅在完全没有项目农事历时用于反推种植窗口，输出会显式标注。
ASSUMED_GROWING_DAYS = {
    "西红柿": (75, 110), "黄瓜": (60, 95), "芸豆": (55, 85), "茄子": (80, 115),
    "青椒": (80, 115), "尖椒": (80, 115), "土豆": (85, 115), "韭菜": (90, 150),
    "芹菜": (70, 105), "甘蓝": (80, 110),
}

CITY_PRICE_SLUG = {"沈阳": None, "朝阳": "朝阳", "锦州": "锦州"}

# 匹配用同义词（与 reference_inputs 保持一致，此处独立定义避免循环依赖）
MATCH_SYNONYMS = {
    "西红柿": ["西红柿", "番茄"], "土豆": ["土豆", "马铃薯"],
    "黄瓜": ["黄瓜"], "韭菜": ["韭菜"], "青椒": ["青椒", "辣椒"],
    "尖椒": ["尖椒", "辣椒"], "茄子": ["茄子"], "芹菜": ["芹菜"],
    "芸豆": ["芸豆", "菜豆", "豆角"], "甘蓝": ["甘蓝", "卷心菜"],
}

CALENDAR_FILES = [
    ("city_data/reference/decision_engine_supplement_v2/crop_calendar_detailed.csv", "v2_detailed"),
    ("city_data/reference/decision_engine_supplement/crop_calendar.csv", "v1_calendar"),
]
SNAP_DIRS = {"v2_detailed": "v2", "v1_calendar": "v1"}


def _read_calendar() -> pd.DataFrame:
    frames = []
    for rel, tag in CALENDAR_FILES:
        p = de_path("data", "snapshots", SNAP_DIRS[tag], rel)
        if not p.exists():
            continue
        d = pd.read_csv(p, low_memory=False)
        d["_src"] = tag
        frames.append(d)
    if not frames:
        return pd.DataFrame(columns=["city", "crop_standard", "stage_group", "start_date", "end_date", "_src"])
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------- 价格季节性推断
def _monthly_seasonality(city: str) -> Optional[pd.DataFrame]:
    """自身历史月份价格分布（past-only：仅使用历史已发生数据；用于识别本地上市低谷）。"""
    if city == "沈阳":
        ds = pd.read_parquet(de_path("data", "processed", "decision_dataset_v1.parquet"))
        ds["date"] = pd.to_datetime(ds["date"])
    else:
        p = de_path("data", "features", f"regional_{city}.parquet")
        if not p.exists():
            return None
        ds = pd.read_parquet(p)
        ds["date"] = pd.to_datetime(ds["date"])
        if "month" not in ds.columns:
            ds["month"] = ds["date"].dt.month
    g = ds.groupby(["crop", "month"])["price_per_kg"].median().reset_index()
    g["pct_in_crop"] = g.groupby("crop")["price_per_kg"].rank(pct=True)
    return g


def _infer_marketing_months(city: str, crop: str, max_months: int = 4) -> List[int]:
    """价格低位月 = 本地供给高峰（经验推断，弱约束）。"""
    s = _monthly_seasonality(city)
    if s is None:
        return []
    sub = s[s["crop"] == crop].sort_values("pct_in_crop")
    if len(sub) < 6:
        return []
    return sorted(sub.head(max_months)["month"].astype(int).tolist())


# ---------------------------------------------------------------- 构建日历
def _normalize_calendar_rows(cal: pd.DataFrame) -> pd.DataFrame:
    c = cal.copy()
    c["start_ts"] = pd.to_datetime(c["start_date"], errors="coerce")
    c["end_ts"] = pd.to_datetime(c["end_date"], errors="coerce")
    c["start_ts"] = c["start_ts"].fillna(c["end_ts"])
    c["end_ts"] = c["end_ts"].fillna(c["start_ts"])
    c["month_start"] = c["start_ts"].dt.month
    c["month_end"] = c["end_ts"].dt.month
    c["stage_group"] = c["stage_group"].astype(str)
    return c


def _match_calendar(cal: pd.DataFrame, city: str, crop: str) -> Tuple[pd.DataFrame, str]:
    """返回 (匹配行, 匹配层级)。层级：observed_calendar / regional_reference / none

    仅「同城 × 同作物」才记为 observed_calendar（强约束）；
    「同城设施蔬菜组」或「同省他市」一律记为 regional_reference（中等约束，只作提示）。
    """
    names = MATCH_SYNONYMS.get(crop, [crop])
    cs = cal["crop_standard"].astype(str)
    pat = "|".join(names)
    exact_city = cal[(cal["city"] == city) & (cs.str.contains(pat, na=False, regex=True))]
    # 排除泛化蔬菜/粮食组标签（如「水稻,蔬菜,西瓜」）被误认为该作物
    exact_city = exact_city[~exact_city["crop_standard"].astype(str).str.contains("粮食|,", na=False, regex=True)]
    if len(exact_city):
        return exact_city, "observed_calendar"
    other = cal[(cal["city"] != city) & (cs.str.contains(pat, na=False, regex=True))]
    other = other[~other["crop_standard"].astype(str).str.contains("粮食", na=False)]
    if len(other):
        return other, "regional_reference"
    grp = cal[(cal["city"] == city) & (cs.str.contains("设施蔬菜", na=False))]
    if len(grp):
        return grp, "regional_reference"
    grp2 = cal[(cal["city"] != city) & (cs.str.contains("设施蔬菜", na=False))]
    if len(grp2):
        return grp2, "regional_reference"
    return cal.iloc[0:0], "none"


def build_crop_calendar(city: str, crops: List[str]) -> pd.DataFrame:
    cal = _normalize_calendar_rows(_read_calendar())
    rows = []
    for crop in crops:
        matched, level = _match_calendar(cal, city, crop)
        plant_rows = matched[matched["stage_group"].isin(["planting", "transplant", "nursery"])]
        harvest_rows = matched[matched["stage_group"].isin(["harvest", "maturity"])]
        # 价格季节性低谷（弱推断）
        inferred_months = _infer_marketing_months(city, crop)
        if level == "observed_calendar":
            strength = "strong"
        elif level == "regional_reference":
            strength = "medium"
        elif inferred_months:
            level, strength = "inferred_from_price_seasonality", "weak"
        else:
            level, strength = "none", "none"

        def _months(df: pd.DataFrame) -> List[int]:
            if not len(df):
                return []
            out = set(df["month_start"].dropna().astype(int)) | set(df["month_end"].dropna().astype(int))
            return sorted(m for m in out if 1 <= m <= 12)

        plant_months = _months(plant_rows)
        harvest_months_cal = _months(harvest_rows)
        harvest_months = harvest_months_cal or inferred_months
        harvest_months_source = "calendar" if harvest_months_cal else ("price_seasonality" if inferred_months else "none")
        prod_systems = sorted(set(matched["production_system"].dropna().astype(str))) if len(matched) else []
        rows.append({
            "city": city, "crop": crop,
            "calendar_level": level, "constraint_strength": strength,
            "planting_months": plant_months, "harvest_months": harvest_months,
            "harvest_months_source": harvest_months_source,
            "harvest_months_from_price": inferred_months,
            "production_systems": prod_systems,
            "growing_days_assumed": ASSUMED_GROWING_DAYS.get(crop),
            "n_calendar_rows": int(len(matched)),
            "calendar_evidence": (matched[["crop_standard", "stage_group", "start_date", "end_date", "city", "_src"]]
                                  .head(4).to_dict("records")) if len(matched) else [],
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 种植窗口反推
def derive_planting_window(city: str, crop: str, harvest_start, harvest_end,
                           cal_row: Optional[pd.Series] = None) -> Dict:
    """由上市窗口反推种植窗口（只依据已有农事历 / 显式假设表）。"""
    hs, he = pd.Timestamp(harvest_start), pd.Timestamp(harvest_end)
    level = cal_row.get("calendar_level") if cal_row is not None else None
    months = list(cal_row.get("planting_months") or []) if cal_row is not None else []
    if level == "observed_calendar" and months:
        # 仅同城农事历可作为强约束
        year = hs.year if hs.month >= min(months) else hs.year
        starts = [pd.Timestamp(year=year, month=int(m), day=1) for m in months]
        return {"plant_start": str(min(starts).date()),
                "plant_end": str((max(starts) + pd.offsets.MonthEnd(0)).date()),
                "source": "observed_calendar", "constraint_strength": "strong",
                "note": "由同城项目农事历 planting/transplant 月反推",
                "calendar_hint_months": months}
    lo, hi = ASSUMED_GROWING_DAYS.get(crop, (75, 105))
    return {"plant_start": str((hs - pd.Timedelta(days=hi)).date()),
            "plant_end": str((he - pd.Timedelta(days=lo)).date()),
            "source": "inferred_window", "constraint_strength": "weak",
            "note": f"依据公开生育期常识区间 {lo}-{hi} 天反推（非项目实测），已降低约束强度",
            "calendar_hint_months": months or None}


# ---------------------------------------------------------------- 可行性校验
def check_agronomic_feasibility(city: str, crop: str, plant_date, harvest_date,
                                production_system: str = "unknown",
                                cal_row: Optional[pd.Series] = None) -> Dict:
    plant, harv = pd.Timestamp(plant_date), pd.Timestamp(harvest_date)
    violations, warnings, notes = [], [], []

    # 1) 时间顺序与生育期区间（硬）
    if harv <= plant:
        violations.append("harvest_date 必须晚于 plant_date")
    else:
        lo, hi = ASSUMED_GROWING_DAYS.get(crop, (60, 120))
        days = (harv - plant).days
        if days < lo * 0.7:
            violations.append(f"生育期过短（{days} 天 < {int(lo*0.7)} 天下限）")
        elif days > hi * 1.5:
            violations.append(f"生育期过长（{days} 天 > {int(hi*1.5)} 天上限）")
        elif not (lo <= days <= hi):
            warnings.append(f"生育期 {days} 天超出常见区间 {lo}-{hi} 天（弱约束）")

    strength = cal_row.get("constraint_strength") if cal_row is not None and hasattr(cal_row, "get") else "weak"
    harvest_months = list(cal_row.get("harvest_months") or []) if cal_row is not None else []
    harvest_src = (cal_row.get("harvest_months_source") if cal_row is not None else None) or "none"
    plant_months = list(cal_row.get("planting_months") or []) if cal_row is not None else []
    infer_months = list(cal_row.get("harvest_months_from_price") or []) if cal_row is not None else []

    # 2) 上市月是否符合农事历（仅「同城日历 + strong」才硬拒绝；价格季节性推断只警告）
    if harvest_months and harv.month not in harvest_months:
        hard = (strength == "strong" and harvest_src == "calendar")
        msg = f"上市月 {harv.month} 不在可行上市窗口 {harvest_months}（来源={harvest_src}）"
        (violations if hard else warnings).append(msg if hard else msg + "（弱约束）")
    if plant_months and plant.month not in plant_months:
        hard = (strength == "strong")
        msg = f"种植月 {plant.month} 不在可行种植窗口 {plant_months}"
        (violations if hard else warnings).append(msg if hard else msg + "（弱约束）")

    # 3) 露地 × 冬季 × 喜温作物（硬）
    if production_system in ("open_field",) and plant.month in WINTER_MONTHS and crop in WARM_SEASON_CROPS:
        violations.append(f"露地越冬不成立：{crop} 为喜温作物，{plant.month} 月露地种植不可行（需设施）")
    if production_system in ("unknown", "unspecified") and plant.month in WINTER_MONTHS and crop in WARM_SEASON_CROPS:
        warnings.append(f"{plant.month} 月种植 {crop} 依赖设施；系统未取得 production_system 证据（约束强度已降低）")

    if infer_months:
        notes.append(f"上市月候选含价格季节性低谷推断：{infer_months}")

    penalty = {"strong": 0.0, "medium": 0.05, "weak": 0.12, "none": 0.18}.get(strength, 0.12)
    if production_system in ("unknown", "unspecified"):
        penalty += 0.05
    return {
        "feasible": len(violations) == 0,
        "violations": violations, "warnings": warnings, "notes": notes,
        "constraint_strength": strength,
        "confidence_penalty": round(min(penalty, 0.25), 3),
        "calendar_level": cal_row.get("calendar_level") if cal_row is not None else None,
        "evidence": (cal_row.get("calendar_evidence") if cal_row is not None else None) or [],
    }


def calendar_for(city: str, crop: str) -> Dict:
    """单作物日历（带缓存），供候选生成与窗口优化复用。"""
    key = (city, crop)
    if key not in _CAL_CACHE:
        tbl = build_crop_calendar(city, [crop])
        _CAL_CACHE[key] = tbl.iloc[0].to_dict() if len(tbl) else {}
    return _CAL_CACHE[key]


_CAL_CACHE: Dict[Tuple[str, str], Dict] = {}


def feasible_harvest_windows(city: str, crop: str, earliest: pd.Timestamp, latest: pd.Timestamp,
                             window_days: int = 10, start_day: int = 5) -> List[Dict]:
    """在 [earliest, latest] 内离散化上市窗口（默认 10 天窗），仅保留农事可行窗口。"""
    cal_row = pd.Series(calendar_for(city, crop))
    hint_months = list(cal_row.get("planting_months") or [])
    out = []
    cur = pd.Timestamp(earliest)
    while cur <= latest:
        end = cur + pd.Timedelta(days=window_days - 1)
        if end > latest:
            end = pd.Timestamp(latest)
        plant = derive_planting_window(city, crop, cur, end, cal_row)
        feas = check_agronomic_feasibility(city, crop, plant["plant_start"], end,
                                           production_system="unknown", cal_row=cal_row)
        out.append({"window_start": cur, "window_end": end,
                    "plant_start": pd.Timestamp(plant["plant_start"]),
                    "plant_end": pd.Timestamp(plant["plant_end"]),
                    "planting_date_source": plant["source"],
                    "constraint_strength": feas["constraint_strength"],
                    "calendar_hint_months": hint_months or None,
                    "feasible": feas["feasible"],
                    "violations": feas["violations"], "warnings": feas["warnings"],
                    "confidence_penalty": feas["confidence_penalty"]})
        cur = cur + pd.Timedelta(days=window_days)
    return out