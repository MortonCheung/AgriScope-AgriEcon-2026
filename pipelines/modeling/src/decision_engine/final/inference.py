# -*- coding: utf-8 -*-
"""C10: 唯一 Final 生产推理入口（§44/§45/§46/§47/§50）。

FinalDecisionEngine.evaluate(request) → 统一 Final Output Contract。

数据来源严格限定：`models/data/snapshots/final_v1` + `models/reports/final/tables/*`
（**不读取** snapshots/v1、archive、旧 supplements、decision_dataset_v1、model_selection.csv）。

诚实性：
  - horizon 能力分级：7/14/30 = model；60/90 = scenario_only（接口调用者不得当精确预测）
  - 价格区间：逐 crop×horizon 校准状态，极差时降级为 unreliable/no_range
  - Profit：用户真实成本/亩产优先（source=user_input, weight=1.0）；proxy 按 confidence 降权；
    完全缺失 → USER_INPUT_REQUIRED，且不输出虚假精度
  - 风险缺失 ≠ 0：缺失 → 降 confidence / 标记 unavailable
"""
from __future__ import annotations
import uuid
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from decision_engine.final.fcommon import (SNAPSHOT_DIR, REPORTS_DIR, SHENYANG_CROPS,
                                           MODEL_VERSION, DATA_VERSION, now_stamp)
from decision_engine.final import capabilities as CAP
from decision_engine.final import artifacts as ART
from decision_engine.final.risk import (daily_prices, weekly_prices, hri_components,
                                        combine, market_risk)
from decision_engine.final.score import cost_reference_table, profit_grading, decision_score

METHOD_H = CAP.MODEL_HORIZONS


# ---------------------------------------------------------------- 数据装载（final-only）
class _Data:
    _ds: Dict[str, pd.DataFrame] = {}
    _hri: Dict[str, pd.DataFrame] = {}
    _mr: Dict[str, pd.DataFrame] = {}
    _clim: Optional[pd.DataFrame] = None
    _ct: Optional[pd.DataFrame] = None
    _sel: Optional[pd.DataFrame] = None
    _rng: Optional[pd.DataFrame] = None

    @classmethod
    def dataset(cls, city: str) -> pd.DataFrame:
        if city not in cls._ds:
            p = SNAPSHOT_DIR / "datasets" / f"decision_dataset_{city}.parquet"
            d = pd.read_parquet(p)
            d["date"] = pd.to_datetime(d["date"])
            cls._ds[city] = d
        return cls._ds[city]

    @classmethod
    def hri(cls, city: str) -> pd.DataFrame:
        if city not in cls._hri:
            w = weekly_prices(city)
            h = combine(hri_components(w))
            h["date_ref"] = h["iso_year"] * 100 + h["iso_week"]
            cls._hri[city] = h
        return cls._hri[city]

    @classmethod
    def mr(cls, city: str) -> pd.DataFrame:
        if city not in cls._mr:
            cls._mr[city] = market_risk(daily_prices(city))
        return cls._mr[city]

    @classmethod
    def clim(cls) -> pd.DataFrame:
        if cls._clim is None:
            cl = pd.read_parquet(SNAPSHOT_DIR / "model_ready/climate/climate_daily.parquet")
            for c in ["temperature_2m_max", "precipitation_sum"]:
                cl[c] = pd.to_numeric(cl[c], errors="coerce")
            cl["date"] = pd.to_datetime(cl["date"])
            cl["month"] = cl["date"].dt.month
            cl["heat"] = (cl["temperature_2m_max"] > 32).astype(float)
            cl["rain"] = (cl["precipitation_sum"] > 25).astype(float)
            rows = []
            for (city, month), g in cl.groupby(["city", "month"]):
                rows.append({"city": city, "month": month,
                             "heat_days_mean": float(g["heat"].mean() * 30),
                             "heavy_rain_days_mean": float(g["rain"].mean() * 30),
                             "n_years": int(g["date"].dt.year.nunique())})
            d = pd.DataFrame(rows)
            d["heat_exposure"] = d.groupby("city")["heat_days_mean"].rank(pct=True) * 100
            d["rain_exposure"] = d.groupby("city")["heavy_rain_days_mean"].rank(pct=True) * 100
            d["climate_exposure_score"] = (0.5 * d["heat_exposure"] + 0.5 * d["rain_exposure"]).round(1)
            cls._clim = d
        return cls._clim

    @classmethod
    def cost(cls) -> pd.DataFrame:
        if cls._ct is None:
            cls._ct = cost_reference_table()
        return cls._ct

    @classmethod
    def selection(cls) -> pd.DataFrame:
        if cls._sel is None:
            try:
                cls._sel = pd.read_csv(REPORTS_DIR / "tables" / "price_model_selection.csv")
            except Exception:
                cls._sel = pd.DataFrame()
        return cls._sel

    @classmethod
    def ranges(cls) -> pd.DataFrame:
        if cls._rng is None:
            try:
                cls._rng = pd.read_csv(REPORTS_DIR / "tables" / "scenario_range_by_crop_horizon.csv")
            except Exception:
                cls._rng = pd.DataFrame()
        return cls._rng


# ---------------------------------------------------------------- 各模块
def _price_block(city: str, crop: str, horizon: int, as_of: pd.Timestamp) -> Dict:
    hcap = CAP.horizon_capability(city, horizon)
    ds = _Data.dataset(city)
    sub = ds[(ds["crop"] == crop) & (ds["date"] <= as_of)].sort_values("date")
    if not len(sub) or sub["price_per_kg"].notna().sum() < 20:
        return {"available": False, "reason": "no_price_history", "price_level": CAP.city_capability(city).get("price_level")}
    level = CAP.city_capability(city).get("price_level")
    latest = sub.iloc[-1]
    cur_price = float(latest["price_per_kg"])

    # 历史同月「未来 h 天窗口均价」分布（strictly past-only）
    tgt = f"target_mean_price_next_{horizon}d"
    month = int(pd.Timestamp(as_of).month)
    hist = sub[(sub["month"] == month)]
    if tgt in hist.columns:
        hv = hist[tgt].dropna().values
    else:
        hv = np.array([])
    if len(hv) >= 20:
        p10, p50, p90 = np.percentile(hv, [10, 50, 90])
        base_stat = "historical_same_month_window_quantile"
        n_obs, n_years = len(hv), int(hist["year"].nunique())
    else:
        dv = sub["price_per_kg"].dropna().values
        if len(dv) < 20:
            return {"available": False, "reason": "insufficient_history", "price_level": level}
        p10, p50, p90 = np.percentile(dv, [10, 50, 90])
        base_stat = "daily_price_fallback"
        n_obs, n_years = len(dv), int(sub["year"].nunique())

    # 模型点预测（仅 model horizon，且 artifact 可用）
    mid = float(p50)
    method = "scenario_quantile"
    scenario_only = bool(hcap.get("scenario_only"))
    if hcap["mode"] == "model":
        try:
            # 用最新可得特征行做预测（生产：data_end 时点）
            feat_row = sub.iloc[-1]
            pred = ART.predict(city, crop, horizon, feat_row)
            if pred is not None and np.isfinite(pred) and pred > 0:
                mid = float(pred)
                method = f"model_forecast({_selected_algo(city, crop, horizon)})"
                scenario_only = False
        except Exception:
            pass

    # 逐 crop×horizon 校准状态 + 加宽
    rng = _Data.ranges()
    rstatus, k = "scenario_range", 1.0
    if len(rng):
        r = rng[(rng["city"] == city) & (rng["crop"] == crop) & (rng["horizon"] == horizon)]
        if len(r):
            rstatus = str(r.iloc[0]["status"])
            k = float(r.iloc[0]["widen_factor"] or 1.0)
    half_lo = (mid - p10) * k
    half_hi = (p90 - mid) * k
    low, high = mid - half_lo, mid + half_hi

    trend = {"price_latest": round(cur_price, 4),
             "date_latest": str(pd.Timestamp(latest["date"]).date()),
             "momentum_30": None if pd.isna(latest.get("price_momentum_30")) else round(float(latest["price_momentum_30"]), 4)}
    return {
        "available": True, "price_level": level,
        "mid": round(mid, 3), "low": round(low, 3), "high": round(high, 3), "unit": "CNY/kg",
        "horizon_days": int(horizon),
        "method": method, "statistic": base_stat,
        "range_status": rstatus, "widen_factor": round(k, 3),
        "scenario_only": scenario_only,
        "sample": {"n_obs": int(n_obs), "n_years": int(n_years)},
        "trend": trend,
    }


def _selected_algo(city: str, crop: str, horizon: int) -> str:
    sel = _Data.selection()
    r = sel[(sel["city"] == city) & (sel["crop"] == crop) & (sel["horizon"] == horizon)]
    return str(r.iloc[0]["model"]) if len(r) else "unknown"


def _hri_block(city: str, crop: str, as_of: pd.Timestamp) -> Dict:
    h = _Data.hri(city)
    wk = pd.Timestamp(as_of).isocalendar().year * 100 + pd.Timestamp(as_of).isocalendar().week
    sub = h[(h["crop"] == crop) & (h["date_ref"] <= wk)].sort_values("date_ref")
    if not len(sub) or pd.isna(sub.iloc[-1]["HRI"]):
        return {"value": None, "level": None, "available": False,
                "note": "HRI 不可用（缺失不视为 0 风险）"}
    r = sub.iloc[-1]
    return {"value": round(float(r["HRI"]), 1),
            "level": str(r.get("HRI_level")),
            "percentile": None if pd.isna(r.get("hri_pct")) else round(float(r["hri_pct"]), 1),
            "component_count": int(r.get("hri_component_count", 0)),
            "available": True,
            "interpretation": "扩种诱因/跟风环境强度（非扩种概率，非独立因果预测）"}


def _mr_block(city: str, crop: str, as_of: pd.Timestamp) -> Dict:
    m = _Data.mr(city)
    sub = m[(m["crop"] == crop) & (m["date"] <= as_of)].sort_values("date")
    if not len(sub) or pd.isna(sub.iloc[-1]["market_risk"]):
        return {"value": None, "available": False, "note": "Market Risk 不可用"}
    r = sub.iloc[-1]
    return {"value": round(float(r["market_risk"]), 1), "available": True,
            "components": {c: (None if pd.isna(r.get(c)) else round(float(r[c]), 1))
                           for c in ["mr_vol", "mr_dd", "mr_abn", "mr_downvol"] if c in m.columns}}


def _climate_block(city: str, harvest_date: pd.Timestamp) -> Dict:
    cl = _Data.clim()
    month = int(pd.Timestamp(harvest_date).month)
    r = cl[(cl["city"] == city) & (cl["month"] == month)]
    if not len(r):
        return {"value": None, "available": False, "note": "无气候暴露数据"}
    r = r.iloc[0]
    return {"value": float(r["climate_exposure_score"]), "n_years": int(r["n_years"]),
            "available": True,
            "note": "历史季节性气候暴露（非天气预报）；NDVI 月度，异常≠减产"}


def _profit_block(crop: str, price_mid: float, area_mu: float,
                  cost_per_mu: Optional[float], yld: Optional[float]) -> Dict:
    pg = profit_grading()
    ref_row = pg[pg["crop"] == crop]
    cost_class = "NOT_FOUND"
    cost_ref = None
    if len(ref_row) and bool(ref_row.iloc[0]["cost_available"]):
        cost_class = str(ref_row.iloc[0]["best_class"])
        ct = _Data.cost()
        cs = ct[ct["crop_standard"].astype(str).str.contains(crop, na=False)]["cost_per_mu_ref"].dropna()
        cost_ref = float(cs.median()) if len(cs) else None
    user_input = cost_per_mu is not None and yld is not None
    cost = float(cost_per_mu) if user_input else cost_ref
    yield_v = float(yld) if user_input else None

    if cost is None:
        return {"available": False, "reason": "no_cost_reference",
                "status": "USER_INPUT_REQUIRED",
                "cost_source_class": "NOT_FOUND", "yield_source_class": "NOT_FOUND"}
    if yield_v is None:
        # 无真实亩产 → 只给盈亏平衡价（不假装利润）
        be_price = cost / 1.0  # 未定义亩产时无法给 break-even price，返回成本与提示
        return {"available": False, "reason": "no_yield_reference",
                "status": "USER_INPUT_REQUIRED",
                "cost_per_mu": round(cost, 1), "cost_source_class": "user_input" if user_input else _src(cost_class),
                "yield_source_class": "missing",
                "note": "缺少亩产（用户输入或权威参考）→ 不输出利润点估计，仅提供成本"}

    revenue = area_mu * yield_v * price_mid
    total_cost = area_mu * cost
    profit = revenue - total_cost
    roi = profit / total_cost if total_cost else np.nan
    be_price = cost / yield_v
    src = "user_input" if user_input else _src(cost_class)
    reliability = 1.0 if user_input else {  # 与 §30 分级一致
        "LOCAL": 0.85, "RESEARCH_REFERENCE": 0.55, "REGIONAL_PROXY": 0.40, "NOT_FOUND": 0.0,
    }.get(cost_class, 0.3)
    return {
        "available": True,
        "revenue": round(revenue, 0), "total_cost": round(total_cost, 0),
        "profit": round(profit, 0), "roi": round(roi, 4),
        "break_even_price": round(be_price, 4),
        "cost_per_mu": round(cost, 1), "expected_yield_per_mu": round(yield_v, 1),
        "cost_source_class": src, "yield_source_class": "user_input" if user_input else "assumption",
        "reliability": reliability,
        "scenario_semantics": "情景值（面积为用户输入；亩产为假设或用户输入）；非保证利润",
    }


def _src(cost_class: str) -> str:
    return {"LOCAL": "real", "RESEARCH_REFERENCE": "local_reference",
            "REGIONAL_PROXY": "regional_proxy", "SECTOR_PROXY": "regional_proxy"}.get(
        str(cost_class).upper(), "local_reference")


def _confidence_block(price, hri, mr, clim, profit, n_obs, sel_row) -> Dict:
    sample = min(1.0, n_obs / 1000) if n_obs else 0.0
    model_stab = 0.6
    beats = 0.7
    if sel_row is not None:
        w = float(sel_row["mean_WAPE"]); b = float(sel_row["baseline_WAPE"])
        model_stab = float(np.clip(1 - (float(sel_row.get("std_WAPE") or 0) / max(w, 1e-6)), 0, 1))
        beats = 1.0 if bool(sel_row["beats_baseline"]) else 0.7
    calib = 0.6
    price_c = 100 * (0.35 * sample + 0.35 * model_stab + 0.20 * calib + 0.10 * beats)
    # 风险置信：HRI/MR 可用性
    risk_avail = (1 if hri.get("available") else 0) + (1 if mr.get("available") else 0)
    risk_c = 100 * (0.5 * (risk_avail / 2) + 0.3 * sample + 0.2 * model_stab)
    profit_c = 100 * (profit.get("reliability", 0.0) if profit.get("available") else 0.0)
    overall = 0.5 * price_c + 0.25 * profit_c + 0.25 * risk_c
    return {"price_confidence": round(price_c, 1), "profit_confidence": round(profit_c, 1),
            "risk_confidence": round(risk_c, 1), "overall_confidence": round(overall, 1),
            "components": {"sample": round(sample, 3), "model_stability": round(model_stab, 3),
                           "calibration": round(calib, 3), "beats_baseline": beats,
                           "risk_availability": risk_avail / 2}}


# ---------------------------------------------------------------- 引擎
class FinalDecisionEngine:
    """唯一 Final 生产推理入口。不读取任何 v1 / archive / legacy 数据。"""

    def evaluate(self, request: Dict) -> Dict:
        rid = request.get("request_id") or str(uuid.uuid4())[:12]
        city = CAP.normalize_city(request.get("city"))
        crop = request.get("crop")
        area = float(request.get("area_mu") or request.get("area") or 0.0)
        budget = request.get("budget")
        plant_date = pd.Timestamp(request.get("plant_date") or request.get("planting_date") or now_stamp())
        horizon = int(request.get("horizon_days") or 30)
        harvest_date = pd.Timestamp(request.get("harvest_date") or (plant_date + pd.Timedelta(days=horizon)))
        pref = request.get("risk_preference", "balanced")
        cost_in = request.get("actual_cost_per_mu", request.get("cost_per_mu"))
        yld_in = request.get("actual_yield_per_mu", request.get("expected_yield_per_mu"))

        base = {"request_id": rid, "model_version": MODEL_VERSION, "data_version": DATA_VERSION,
                "city": city, "crop": crop, "area_mu": area, "budget": budget,
                "plant_date": str(pd.Timestamp(plant_date).date()),
                "harvest_date": str(pd.Timestamp(harvest_date).date()),
                "horizon_days": horizon, "risk_preference": pref,
                "generated_at": now_stamp()}

        cap = CAP.city_capability(city)
        warnings: List[str] = []
        proxy_flags: List[str] = []

        # ---- 城市能力：不支持 → 明确拒绝（不 fallback）
        if not cap.get("has_price_model"):
            return {**base, "status": "INSUFFICIENT_MARKET_DATA",
                    "price": None, "scenario_range": None, "profit": None,
                    "hri": None, "market_risk": None, "climate_exposure": None,
                    "confidence": {"overall_confidence": 0.0},
                    "recommendation": None, "rank": None, "strategy": None,
                    "stress_scenarios": [],
                    "reasons": [cap.get("basis") or cap.get("limitation") or f"{city} 无连续官方价格序列"],
                    "warnings": ["不做跨城 fallback（无 Shenyang 代理）"],
                    "data_quality": {"city_tier": cap.get("tier")},
                    "proxy_flags": [], "capability": {"city": cap.get("tier")}}

        hcap = CAP.horizon_capability(city, horizon)
        as_of = pd.Timestamp(request.get("as_of")) if request.get("as_of") else _Data.dataset(city)["date"].max()

        price = _price_block(city, crop, horizon, as_of)
        if not price.get("available"):
            return {**base, "status": "INSUFFICIENT_MARKET_DATA", "price": None,
                    "scenario_range": None, "profit": None, "hri": None, "market_risk": None,
                    "climate_exposure": None, "confidence": {"overall_confidence": 0.0},
                    "recommendation": None, "rank": None, "strategy": None,
                    "stress_scenarios": [],
                    "reasons": [f"{city}×{crop} 无足够历史价格样本（{price.get('reason')}）"],
                    "warnings": [], "data_quality": {"price_reason": price.get("reason")},
                    "proxy_flags": [], "capability": {"city": cap.get("tier"), "horizon": hcap}}

        hri = _hri_block(city, crop, as_of)
        mr = _mr_block(city, crop, as_of)
        clim = _climate_block(city, harvest_date)
        profit = _profit_block(crop, price["mid"], area or 60.0, cost_in, yld_in)

        ds = _Data.dataset(city)
        n_obs = int(((ds["crop"] == crop) & (ds["date"] <= as_of)).sum())
        sel = _Data.selection()
        sel_row = None
        s = sel[(sel["city"] == city) & (sel["crop"] == crop) & (sel["horizon"] == horizon)]
        if len(s):
            sel_row = s.iloc[0]
        conf = _confidence_block(price, hri, mr, clim, profit, n_obs, sel_row)

        # 决策评分：Profit 权重按 reliability 降权（§30/§33/§55/§56）
        pool = pd.DataFrame([{
            "profit": profit.get("profit", np.nan) if profit.get("available") else np.nan,
            "degree_downside": profit.get("roi", np.nan) if profit.get("available") else np.nan,
            "fc_low": price["low"], "forecast": price["mid"],
            "HRI": hri.get("value"), "market_risk": mr.get("value"),
            "climate_risk": clim.get("value"), "overall_confidence": conf["overall_confidence"],
        }])
        score = float(decision_score(pool).iloc[0])
        prof_rel = profit.get("reliability", 0.0) if profit.get("available") else 0.0
        if prof_rel < 0.5:
            warnings.append("Profit 来源可信度低（proxy/缺失）→ 已降权，仅作情景参考")

        # 状态判定
        status = "OK"
        if price.get("scenario_only") or hcap.get("scenario_only"):
            status = "SCENARIO_ONLY"
        if not profit.get("available"):
            status = "USER_INPUT_REQUIRED" if profit.get("status") == "USER_INPUT_REQUIRED" else "PARTIAL"
            warnings.append(profit.get("note") or "缺少成本/亩产 → 不输出利润点估计")
        if price.get("range_status") in ("scenario_range_unreliable", "no_range_available"):
            warnings.append(f"区间校准状态={price['range_status']}，不可作为概率区间使用")
        if conf["overall_confidence"] < 40 and status == "OK":
            status = "LOW_CONFIDENCE"
        if not hri.get("available") or not mr.get("available"):
            warnings.append("部分风险指标缺失（缺失未按 0 处理）")

        # proxy flags
        if profit.get("available") and profit.get("cost_source_class") != "user_input":
            proxy_flags.append(f"cost_source_class={profit.get('cost_source_class')}")
        if profit.get("available") and profit.get("yield_source_class") != "user_input":
            proxy_flags.append(f"yield_source_class={profit.get('yield_source_class')}")

        reasons = [
            f"{city}×{crop} {horizon}d：价格 {price['mid']} 元/kg（区间 {price['low']}~{price['high']}，"
            f"{price['range_status']}，加宽×{price['widen_factor']}）",
            f"价格统计口径 {price['statistic']}，方法 {price['method']}"
            + ("（长期 horizon → scenario_only）" if price.get("scenario_only") else ""),
        ]
        if hri.get("available"):
            reasons.append(f"HRI={hri['value']}（{hri['level']}，{hri['component_count']} 组件）")
        if mr.get("available"):
            reasons.append(f"Market Risk={mr['value']}")
        if clim.get("available"):
            reasons.append(f"历史同期气候暴露={clim['value']}（{clim['n_years']} 年，非天气预报）")
        if profit.get("available"):
            reasons.append(f"情景利润≈{profit['profit']:.0f} 元（ROI {profit['roi']*100:.1f}%，"
                           f"成本来源 {profit['cost_source_class']}）")
        reasons.append(f"决策评分 {score}（{pref}）；置信度 {conf['overall_confidence']}")

        return {
            **base, "status": status,
            "price": {"mid": price["mid"], "low": price["low"], "high": price["high"],
                      "unit": price["unit"], "horizon_days": horizon,
                      "method": price["method"], "statistic": price["statistic"],
                      "scenario_only": price["scenario_only"], "sample": price["sample"],
                      "trend": price["trend"], "price_level": price["price_level"]},
            "scenario_range": {"low": price["low"], "high": price["high"],
                               "status": price["range_status"], "widen_factor": price["widen_factor"],
                               "nominal": 0.80,
                               "note": "情景区间（未达 80% 校准标准，非 prediction interval）"},
            "profit": profit,
            "hri": hri, "market_risk": mr, "climate_exposure": clim,
            "confidence": conf,
            "recommendation": {"crop": crop, "decision_score": score,
                               "profit_weight": round(prof_rel, 3)},
            "rank": 1, "strategy": pref,
            "stress_scenarios": [],
            "reasons": reasons, "warnings": warnings,
            "data_quality": {"city_tier": cap.get("tier"), "price_level": price["price_level"],
                             "horizon_mode": hcap["mode"], "n_obs": n_obs},
            "proxy_flags": proxy_flags,
            "capability": {"city": cap.get("tier"), "horizon": hcap},
        }

    def evaluate_many(self, requests: List[Dict]) -> Dict:
        """批量评估 + 排序（NO_CLEAR_WINNER 判定）。"""
        results = [self.evaluate(r) for r in requests]
        ok = [r for r in results if r["status"] in ("OK", "SCENARIO_ONLY", "LOW_CONFIDENCE", "PARTIAL")]
        ok.sort(key=lambda r: r["recommendation"]["decision_score"], reverse=True)
        for i, r in enumerate(ok, 1):
            r["rank"] = i
        status = "OK"
        if not ok:
            status = "NO_FEASIBLE_PLAN"
        elif len(ok) >= 2:
            top = ok[0]["recommendation"]["decision_score"]
            second = ok[1]["recommendation"]["decision_score"]
            if abs(top - second) < 1e-6:
                status = "NO_CLEAR_WINNER"
        return {"status": status, "n": len(results), "n_evaluable": len(ok),
                "ranking": ok, "all": results}


_ENGINE: Optional[FinalDecisionEngine] = None


def get_engine() -> FinalDecisionEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = FinalDecisionEngine()
    return _ENGINE


def evaluate(request: Dict) -> Dict:
    return get_engine().evaluate(request)


if __name__ == "__main__":
    import json
    e = FinalDecisionEngine()
    demo = [
        {"request_id": "demo1", "city": "沈阳", "crop": "西红柿", "area_mu": 60, "budget": 300000,
         "horizon_days": 30, "risk_preference": "balanced"},
        {"request_id": "demo2", "city": "沈阳", "crop": "黄瓜", "area_mu": 60,
         "horizon_days": 90, "actual_cost_per_mu": 20000, "actual_yield_per_mu": 4000},
        {"request_id": "demo3", "city": "大连", "crop": "西红柿", "area_mu": 60, "horizon_days": 30},
    ]
    for d in demo:
        r = e.evaluate(d)
        print(json.dumps({k: r[k] for k in ["request_id", "city", "crop", "status",
                                            "scenario_range", "confidence"]},
                         ensure_ascii=False, indent=1))