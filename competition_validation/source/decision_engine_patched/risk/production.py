# -*- coding: utf-8 -*-
"""Phase 7: Production Context（结构性生产背景，不做产量预测）。

来源：
  - city_data/<city>/data/production_yearly.csv（五城，2017-2025）
  - city_data/reference/decision_engine_supplement/planting_area_yearly.csv / production_yearly_extended.csv
规则：
  - 只保留有真实数值的城市×作物；单位显式换算；
  - 计算 area/yield/production 的 yoy 与 5 年变异系数（CV）；
  - 蔬菜类（沈阳 10 品种）在现有数据中无匹配亩产/面积 → 不伪造，标记 missing。
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from decision_engine.common import de_path

CITY_SLUG = {"沈阳": "shenyang", "朝阳": "chaoyang", "锦州": "jinzhou",
             "大连": "dalian", "铁岭": "tieling", "丹东": "dandong"}
BAD_CROP = ["(2017年)", "(2018年)", "(2019年)", "(2020年)", "(2021年)", "(2022年)",
            "(2023年)", "(2024年)", "(2025年)", "农作物总播种面积", "其他作物"]


def _canonical_production(city_cn: str) -> pd.DataFrame:
    slug = CITY_SLUG[city_cn]
    p = de_path("data", "snapshots", "v1", f"city_data/{slug}/data/production_yearly.csv")
    if not p.exists():
        # 沈阳 canonical 无 production_yearly（审计已确认；沈阳为区县级数据在 processed/）
        print(f"[production] {city_cn}: 无 canonical production_yearly.csv（跳过，未用其他口径替代）")
        return pd.DataFrame(columns=["year", "city", "crop", "planting_area_kha",
                                     "production_ton", "yield_kg_per_ha", "source"])
    df = pd.read_csv(p, low_memory=False)
    df = df[~df["crop"].astype(str).isin(BAD_CROP)].copy()
    df["crop"] = df["crop"].astype(str).str.strip()
    area = pd.to_numeric(df["planting_area"], errors="coerce")
    prod = pd.to_numeric(df["production"], errors="coerce")
    yld = pd.to_numeric(df["yield_per_area"], errors="coerce")
    unit_a = df.get("unit_planting_area", pd.Series("", index=df.index)).astype(str)
    unit_p = df.get("unit_production", pd.Series("", index=df.index)).astype(str)
    unit_y = df.get("unit_yield", pd.Series("", index=df.index)).astype(str)
    kha = np.where(unit_a.str.contains("千公顷"), area, np.nan)
    ton = np.where(unit_p.str.contains("万吨"), prod * 1e4,
                   np.where(unit_p.str.contains("吨"), prod, np.nan))
    kg_ha = np.where(unit_y.str.contains("公斤/公顷"), yld,
                     np.where(unit_y.str.contains("吨/公顷"), yld * 1000, np.nan))
    out = pd.DataFrame({
        "year": pd.to_numeric(df["year"], errors="coerce").astype("Int64"),
        "city": city_cn, "crop": df["crop"],
        "planting_area_kha": kha, "production_ton": ton, "yield_kg_per_ha": kg_ha,
        "source": "canonical_production_yearly",
    })
    out = out.dropna(subset=["planting_area_kha", "production_ton", "yield_kg_per_ha"], how="all")
    return out


def build_production_context() -> pd.DataFrame:
    frames = [_canonical_production(c) for c in CITY_SLUG]
    df = pd.concat(frames, ignore_index=True)

    # supplement 扩展（沈阳/朝阳/锦州等新增年度记录）
    for f in ["planting_area_yearly.csv", "production_yearly_extended.csv"]:
        try:
            s = pd.read_csv(de_path("data", "snapshots", "v1",
                                    "city_data/reference/decision_engine_supplement", f), low_memory=False)
            if "planting_area_mu" in s.columns:
                add = pd.DataFrame({
                    "year": pd.to_numeric(s["year"], errors="coerce").astype("Int64"),
                    "city": s["city"], "crop": s["crop"],
                    "planting_area_kha": pd.to_numeric(s["planting_area_mu"], errors="coerce") / 15000.0,
                    "production_ton": np.nan, "yield_kg_per_ha": np.nan,
                    "source": f"supplement_{f}", })
                df = pd.concat([df, add], ignore_index=True)
            if "production_ton" in s.columns:
                add = pd.DataFrame({
                    "year": pd.to_numeric(s["year"], errors="coerce").astype("Int64"),
                    "city": s["city"], "crop": s["crop"],
                    "planting_area_kha": np.nan,
                    "production_ton": pd.to_numeric(s["production_ton"], errors="coerce"),
                    "yield_kg_per_ha": np.nan,
                    "source": f"supplement_{f}", })
                df = pd.concat([df, add], ignore_index=True)
        except Exception as e:
            print(f"[production] supplement {f} skipped: {e}")

    df = (df.groupby(["city", "crop", "year"], as_index=False)
          .agg(planting_area_kha=("planting_area_kha", "max"),
               production_ton=("production_ton", "max"),
               yield_kg_per_ha=("yield_kg_per_ha", "max"),
               source=("source", "first")))
    df = df.sort_values(["city", "crop", "year"])

    g = df.groupby(["city", "crop"])
    df["area_yoy"] = g["planting_area_kha"].pct_change()
    df["yield_yoy"] = g["yield_kg_per_ha"].pct_change()
    df["production_yoy"] = g["production_ton"].pct_change()
    df["area_cv_5y"] = g["planting_area_kha"].transform(
        lambda s: s.rolling(5, min_periods=3).std() / s.rolling(5, min_periods=3).mean())
    df["yield_cv_5y"] = g["yield_kg_per_ha"].transform(
        lambda s: s.rolling(5, min_periods=3).std() / s.rolling(5, min_periods=3).mean())
    df["production_cv_5y"] = g["production_ton"].transform(
        lambda s: s.rolling(5, min_periods=3).std() / s.rolling(5, min_periods=3).mean())
    return df


_PC_CACHE = None


def _context_df() -> pd.DataFrame:
    global _PC_CACHE
    if _PC_CACHE is None:
        p = de_path("data", "features", "production_context.csv")
        _PC_CACHE = pd.read_csv(p) if p.exists() else pd.DataFrame()
    return _PC_CACHE


def context_for(city: str, crop: str) -> dict:
    """单城市×作物的生产背景（用于 Decision Engine；无数据时返回 missing）。"""
    df = _context_df()
    if df.empty:
        return {"available": False, "reason": "production_context.csv 未构建"}
    sub = df[(df["city"] == city)]
    # 精确匹配作物；蔬菜类没有匹配 → missing（禁止用蔬菜总量冒充）
    exact = sub[sub["crop"] == crop]
    if len(exact) == 0:
        return {"available": False, "reason": f"{city}×{crop} 无匹配生产数据（未用其他口径替代）"}
    exact = exact.sort_values("year")
    last = exact.iloc[-1]
    return {
        "available": True,
        "year": int(last["year"]),
        "planting_area_kha": None if pd.isna(last["planting_area_kha"]) else float(last["planting_area_kha"]),
        "production_ton": None if pd.isna(last["production_ton"]) else float(last["production_ton"]),
        "yield_kg_per_ha": None if pd.isna(last["yield_kg_per_ha"]) else float(last["yield_kg_per_ha"]),
        "area_yoy": None if pd.isna(last["area_yoy"]) else float(last["area_yoy"]),
        "yield_yoy": None if pd.isna(last["yield_yoy"]) else float(last["yield_yoy"]),
        "area_cv_5y": None if pd.isna(last["area_cv_5y"]) else float(last["area_cv_5y"]),
        "yield_cv_5y": None if pd.isna(last["yield_cv_5y"]) else float(last["yield_cv_5y"]),
        "source": last["source"],
        "note": "结构性背景，不是产量预测",
    }