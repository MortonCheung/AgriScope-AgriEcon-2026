# -*- coding: utf-8 -*-
"""F8-F11: Climate 边界 / Profit 分级 / Confidence 重设计 / Decision Score 重标准化。

科学边界：
  - Climate：历史季节性气候暴露（非天气预报）；NDVI 月度，不得日频化；异常≠减产；
  - Profit：Revenue=Area×Yield×Price，Cost=Area×Cost_per_mu；strict source_class 分级
            （user_input > local_real > local_reference > regional_proxy > missing）；
  - Confidence：独立于 recommendation score；考虑 coverage/sample/model stability/
            interval calibration/cost&yield source class/proxy share/OOD；
  - Decision Score：winsorize + 池内百分位（robust），避免量纲支配与极端值改变排序。
"""
from __future__ import annotations
from typing import Dict, List

import numpy as np
import pandas as pd

from decision_engine.final.fcommon import (SNAPSHOT_DIR, REPORTS_DIR, FINAL_EVAL_DIR,
                                           ensure_dir, write_json, now_stamp)

# ---------------------------------------------------------------- 成本/亩产分级
COST_CLASS_RANK = {"user_input": 1.0, "LOCAL": 0.85, "local_reference": 0.75,
                   "RESEARCH_REFERENCE": 0.55, "REGIONAL_PROXY": 0.40,
                   "NEIGHBORING_PROXY": 0.35, "SECTOR_PROXY": 0.30, "NOT_FOUND": 0.0}
YIELD_CLASS_RANK = {"user_input": 1.0, "LOCAL": 0.85, "local_reference": 0.70,
                    "RESEARCH_REFERENCE": 0.50, "REGIONAL_PROXY": 0.40, "NOT_FOUND": 0.0}


def cost_reference_table() -> pd.DataFrame:
    """汇总成本参考，标注 source_class（不做虚假精准点估计）。"""
    rows = []
    cc = pd.read_parquet(SNAPSHOT_DIR / "model_ready/profit/cost_components.parquet")
    for _, r in cc.iterrows():
        rows.append({"crop_standard": r.get("crop_standard"), "city": r.get("city"),
                     "cost_per_mu_ref": r.get("total_cost"), "cost_basis": r.get("cost_basis"),
                     "cost_source_class": r.get("cost_source_class"), "year": r.get("year"),
                     "source_name": str(r.get("source_name"))[:80]})
    cp = pd.read_parquet(SNAPSHOT_DIR / "model_ready/profit/crop_cost.parquet")
    for _, r in cp.iterrows():
        rows.append({"crop_standard": r.get("crop_standard"), "city": r.get("city"),
                     "cost_per_mu_ref": r.get("total_cost_per_mu"), "cost_basis": "per_mu",
                     "cost_source_class": r.get("cost_source_class"), "year": r.get("year"),
                     "source_name": str(r.get("source_name"))[:80]})
    df = pd.DataFrame(rows)
    df["cost_per_mu_ref"] = pd.to_numeric(df["cost_per_mu_ref"], errors="coerce")
    df["cost_reliability"] = df["cost_source_class"].map(COST_CLASS_RANK).fillna(0.3)
    return df


def profit_grading() -> pd.DataFrame:
    """报告 10 蔬菜成本/亩产可得性分级（诚实标注缺口）。"""
    from decision_engine.final.fcommon import SHENYANG_CROPS
    ct = cost_reference_table()
    rows = []
    for c in SHENYANG_CROPS:
        sub = ct[ct["crop_standard"].astype(str).str.contains(c, na=False)]
        if len(sub):
            best = sub.sort_values("cost_reliability", ascending=False).iloc[0]
            rows.append({"crop": c, "cost_available": True, "n_refs": int(len(sub)),
                         "best_class": best["cost_source_class"],
                         "cost_reliability": float(best["cost_reliability"]),
                         "cost_range": f"{sub['cost_per_mu_ref'].min()}~{sub['cost_per_mu_ref'].max()}"})
        else:
            rows.append({"crop": c, "cost_available": False, "n_refs": 0,
                         "best_class": "NOT_FOUND", "cost_reliability": 0.0, "cost_range": "NA"})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- Climate
def climate_exposure() -> pd.DataFrame:
    cl = pd.read_parquet(SNAPSHOT_DIR / "model_ready/climate/climate_daily.parquet")
    cl = cl[["city", "date", "temperature_2m_max", "precipitation_sum", "ndvi_anomaly_z",
             "source_frequency_ndvi"]].copy()
    cl["date"] = pd.to_datetime(cl["date"])
    for c in ["temperature_2m_max", "precipitation_sum", "ndvi_anomaly_z"]:
        cl[c] = pd.to_numeric(cl[c], errors="coerce")
    cl["month"] = cl["date"].dt.month
    cl["heat"] = (cl["temperature_2m_max"] > 32).astype(float)
    cl["heavy_rain"] = (cl["precipitation_sum"] > 25).astype(float)
    rows = []
    for (city, month), g in cl.groupby(["city", "month"]):
        rows.append({"city": city, "month": month, "n_years": int(g["date"].dt.year.nunique()),
                     "heat_days_mean": float(g["heat"].mean() * 30),
                     "heavy_rain_days_mean": float(g["heavy_rain"].mean() * 30),
                     "ndvi_anomaly_mean": float(g["ndvi_anomaly_z"].mean()) if g["ndvi_anomaly_z"].notna().any() else np.nan,
                     "ndvi_is_monthly": True,
                     "note": "历史季节性气候暴露（非天气预报）；NDVI 为月度，异常≠减产"})
    df = pd.DataFrame(rows)
    # 与同城其他月份比较的百分位 → 暴露分 0-100
    df["heat_exposure"] = df.groupby("city")["heat_days_mean"].rank(pct=True) * 100
    df["rain_exposure"] = df.groupby("city")["heavy_rain_days_mean"].rank(pct=True) * 100
    df["climate_exposure_score"] = (0.5 * df["heat_exposure"] + 0.5 * df["rain_exposure"]).round(1)
    return df


# ---------------------------------------------------------------- Confidence
def confidence_table() -> pd.DataFrame:
    """每作物 confidence 分量（独立于 recommendation score）。"""
    sel = pd.read_csv(REPORTS_DIR / "tables" / "price_model_selection.csv")
    s30 = sel[(sel["city"] == "沈阳") & (sel["horizon"] == 30)]
    try:
        agg = pd.read_csv(REPORTS_DIR / "tables" / "interval_calibration_summary.csv")
        best_cov = float(agg.iloc[0]["coverage"]) if len(agg) else 0.7
    except Exception:
        best_cov = 0.7
    calib = max(0.0, 1 - abs(best_cov - 0.8) / 0.2)
    ds = pd.read_parquet(SNAPSHOT_DIR / "datasets" / "decision_dataset_沈阳.parquet")
    n_obs = ds.groupby("crop").size()
    pg = profit_grading()
    rows = []
    for _, r in s30.iterrows():
        crop = r["crop"]
        sample_c = float(min(1.0, n_obs.get(crop, 0) / 1000))
        stab = float(np.clip(1 - (r["std_WAPE"] or 0) / max(r["mean_WAPE"], 1e-6), 0, 1))
        beats = 1.0 if r["beats_baseline"] else 0.7
        cost_rel = float(pg[pg["crop"] == crop]["cost_reliability"].iloc[0]) if (pg["crop"] == crop).any() else 0.0
        yield_rel = 0.0  # 蔬菜亩产无可靠来源
        proxy_share = 1 - cost_rel
        price_conf = 100 * (0.35 * sample_c + 0.35 * stab + 0.20 * calib + 0.10 * beats)
        profit_conf = 100 * (0.5 * cost_rel + 0.5 * yield_rel)
        risk_conf = 100 * (0.5 * sample_c + 0.3 * calib + 0.2 * stab)
        overall = 0.5 * price_conf + 0.25 * profit_conf + 0.25 * risk_conf
        rows.append({"crop": crop, "price_confidence": round(price_conf, 1),
                     "profit_confidence": round(profit_conf, 1),
                     "risk_confidence": round(risk_conf, 1),
                     "overall_confidence": round(overall, 1),
                     "sample_score": round(sample_c, 3), "stability_score": round(stab, 3),
                     "calibration_score": round(calib, 3), "cost_reliability": cost_rel,
                     "yield_reliability": yield_rel, "proxy_share": round(proxy_share, 3),
                     "model": r["model"], "route": r["route"],
                     "beats_baseline": bool(r["beats_baseline"])})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- Decision Score
def decision_score(pool: pd.DataFrame, winsor=(0.05, 0.95)) -> pd.Series:
    """robust 决策评分：各分量 winsorize + 池内百分位，避免量纲支配。"""
    def w(s):
        v = pd.to_numeric(s, errors="coerce")
        lo, hi = v.quantile(winsor[0]), v.quantile(winsor[1])
        return v.clip(lo, hi).rank(pct=True, na_option="bottom").fillna(0.5)
    prof = w(pool["profit"] if "profit" in pool else pool["forecast"])
    low = w(pool["degree_downside"] if "degree_downside" in pool else pool.get("fc_low", pool["forecast"]))
    hri = w(pool["HRI"]).rsub(1)          # 低 HRI 更好
    mr = w(pool["market_risk"]).rsub(1)
    cl = w(pool["climate_risk"]).rsub(1) if "climate_risk" in pool else 0.5
    conf = (pd.to_numeric(pool.get("overall_confidence", 50), errors="coerce") / 100).fillna(0.5)
    score = (0.30 * prof + 0.20 * low + 0.15 * hri + 0.15 * mr + 0.10 * cl + 0.10 * conf) * 100
    return score.round(1)


def run() -> Dict[str, object]:
    ensure_dir(REPORTS_DIR / "tables")
    ce = climate_exposure(); ce.to_csv(REPORTS_DIR / "tables" / "climate_exposure.csv", index=False, encoding="utf-8-sig")
    pg = profit_grading(); pg.to_csv(REPORTS_DIR / "tables" / "profit_grading.csv", index=False, encoding="utf-8-sig")
    ct = cost_reference_table(); ct.to_csv(REPORTS_DIR / "tables" / "cost_reference_graded.csv", index=False, encoding="utf-8-sig")
    cf = confidence_table(); cf.to_csv(REPORTS_DIR / "tables" / "confidence_by_crop.csv", index=False, encoding="utf-8-sig")
    out = {
        "climate_months": len(ce),
        "profit_crops_with_reliable_cost": int((pg["cost_reliability"] >= 0.5).sum()),
        "profit_crops_not_found": int((~pg["cost_available"]).sum()),
        "mean_price_confidence": float(cf["price_confidence"].mean()),
        "mean_profit_confidence": float(cf["profit_confidence"].mean()),
        "ts": now_stamp(),
    }
    write_json(out, REPORTS_DIR / "tables" / "score_confidence_summary.json")
    return out


if __name__ == "__main__":
    print(run())