# -*- coding: utf-8 -*-
"""Phase 13: Decision Engine v1 —— 统一 Python API。

  evaluate_plan({city, crop, plant_date, harvest_date, area_mu,
                 cost_per_mu, expected_yield_per_mu, risk_preference})
  compare_plans([planA, planB, ...])

原则：
  - 所有数字来自模型/规则/公式/历史数据，不由 LLM 生成；
  - 价格层级不混用（沈阳=wholesale；朝阳=market_average；锦州=单一层级）；
  - 区间未校准时明确标注 scenario range；
  - 无价格模型城市返回 insufficient_market_data（科学边界，不是失败）。
"""
from __future__ import annotations
import json
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from decision_engine.common import de_path, read_json
from decision_engine.confidence import confidence as conf
from decision_engine.confidence import drift as drift_mod
from decision_engine.engine.decision import WEIGHTS, decision_score
from decision_engine.profit.profit import evaluate_profit
from decision_engine.risk import climate, production

PRICE_CITIES = {"沈阳": "street", "朝阳": "market_average", "锦州": "single_level"}
NO_PRICE_CITIES = ["大连", "铁岭", "丹东"]
SHENYANG_CROPS = ["土豆", "西红柿", "黄瓜", "韭菜", "青椒", "尖椒", "茄子", "芹菜", "芸豆", "甘蓝"]


class DecisionEngine:
    def __init__(self, as_of: Optional[str] = None):
        self.as_of = pd.Timestamp(as_of) if as_of else None
        self.ds = pd.read_parquet(de_path("data", "processed", "decision_dataset_v1.parquet"))
        self.ds["date"] = pd.to_datetime(self.ds["date"])
        self.data_end = self.ds["date"].max()
        self.hri = pd.read_parquet(de_path("data", "features", "hri_v1.parquet"))
        self.hri["date"] = pd.to_datetime(self.hri["date"])
        self.mr = pd.read_parquet(de_path("data", "features", "market_risk_v1.parquet"))
        self.mr["date"] = pd.to_datetime(self.mr["date"])
        self.interval_sel = read_json(de_path("models", "registry", "interval_selection.json"))
        try:
            self.registry = read_json(de_path("models", "registry", "model_registry.json"))
        except Exception:
            self.registry = {}
        self.sel = pd.read_csv(de_path("evaluation", "metrics", "model_selection.csv")) \
            if de_path("evaluation", "metrics", "model_selection.csv").exists() else None
        self._regional = None

    # ---------------------------------------------------------------- 数据裁剪
    def _cut(self, df: pd.DataFrame) -> pd.DataFrame:
        if self.as_of is not None:
            return df[df["date"] <= self.as_of]
        return df

    def _regional_data(self, city: str) -> Optional[pd.DataFrame]:
        p = de_path("data", "features", f"regional_{city}.parquet")
        if not p.exists():
            return None
        if self._regional is None:
            self._regional = {}
        if city not in self._regional:
            df = pd.read_parquet(p)
            df["date"] = pd.to_datetime(df["date"])
            self._regional[city] = df
        return self._regional[city]

    # ---------------------------------------------------------------- 价格
    def _seasonal_price(self, prices: pd.DataFrame, crop: str, month: int,
                        as_of: Optional[pd.Timestamp]) -> Dict:
        """上市窗口价格分位。

        优先使用与业务口径一致的「未来 30 天窗口均值」历史分布（target_mean_price_next_30d），
        窗口必须完全落在截止日之前（严格 past-only）；样本不足回退日频同月分位。
        """
        tgt = "target_mean_price_next_30d"
        if tgt in prices.columns:
            sub = prices[(prices["crop"] == crop) & (prices["month"] == month)]
            if as_of is not None:
                sub = sub[pd.to_datetime(sub["date"]) + pd.Timedelta(days=30) <= as_of]
            v = sub[tgt].dropna().values
            if len(v) >= 20:
                p10, p50, p90 = np.percentile(v, [10, 50, 90])
                return {"available": True, "low": float(p10), "mid": float(p50), "high": float(p90),
                        "n_obs": int(len(v)), "n_years": int(sub["year"].nunique()),
                        "years": sorted(sub["year"].unique().tolist()),
                        "statistic": "window_mean_30d（与收益情景同口径）"}
        sub = prices[(prices["crop"] == crop) & (prices["month"] == month)]
        if as_of is not None:
            sub = sub[sub["date"] <= as_of]
        v = sub["price_per_kg"].dropna().values
        if len(v) < 20:
            return {"available": False, "n_obs": int(len(v)),
                    "reason": f"历史同月样本不足（n={len(v)} < 20）"}
        p10, p50, p90 = np.percentile(v, [10, 50, 90])
        return {"available": True, "low": float(p10), "mid": float(p50), "high": float(p90),
                "n_obs": int(len(v)), "n_years": int(sub["year"].nunique()),
                "years": sorted(sub["year"].unique().tolist()),
                "statistic": "daily_price_fallback"}

    def _price_block(self, city: str, crop: str, plant_date, harvest_date) -> Dict:
        as_of = self.as_of
        market_month = pd.Timestamp(harvest_date).month
        if city == "沈阳":
            prices = self.ds
            level = "wholesale"
        else:
            prices = self._regional_data(city)
            level = {"朝阳": "market_average", "锦州": "single_selected_level"}.get(city)
        if prices is None:
            return {"available": False, "price_level": level, "market_data": "insufficient"}

        sp = self._seasonal_price(self._cut(prices), crop, market_month, as_of)
        if not sp.get("available"):
            return {"available": False, "price_level": level, "market_data": "insufficient",
                    "reason": sp.get("reason")}

        # 短期趋势（截至数据末/截止日）
        recent = self._cut(prices[prices["crop"] == crop]).sort_values("date")
        trend = {"direction": None, "momentum_30": None, "momentum_60": None,
                 "continuous_rise_days": None, "price_latest": None, "date_latest": None}
        if len(recent) and "price_momentum_30" in recent.columns:
            r = recent.iloc[-1]
            trend.update({
                "direction": ("up" if (r.get("price_momentum_30") or 0) > 0.02 else
                              "down" if (r.get("price_momentum_30") or 0) < -0.02 else "flat"),
                "momentum_30": None if pd.isna(r.get("price_momentum_30")) else round(float(r["price_momentum_30"]), 4),
                "momentum_60": None if pd.isna(r.get("price_momentum_60")) else round(float(r["price_momentum_60"]), 4),
                "continuous_rise_days": int(r.get("continuous_rise_days", 0) or 0),
                "price_latest": round(float(r["price_per_kg"]), 4),
                "date_latest": str(pd.Timestamp(r["date"]).date()),
            })
        return {"available": True, "price_level": level,
                "window_month": int(market_month),
                "low": sp["low"], "mid": sp["mid"], "high": sp["high"],
                "method": "seasonal_quantile(same_month_history)",
                "statistic": sp.get("statistic"),
                "is_calibrated_interval": False,
                "sample": {"n_obs": sp["n_obs"], "n_years": sp["n_years"], "years": sp["years"]},
                "trend": trend,
                "semantics": "历史同月分位（scenario range），不是概率预测区间"}

    # ---------------------------------------------------------------- 风险
    def _risk_block(self, city: str, crop: str, plant_date, harvest_date) -> Dict:
        out = {"market": None, "herding": None, "climate": None, "production": None}
        hri_src = self.hri
        mr_src = self.mr
        if city != "沈阳":
            rp = de_path("data", "features", f"regional_risk_{city}.parquet")
            if rp.exists():
                rr = pd.read_parquet(rp)
                rr["date"] = pd.to_datetime(rr["date"])
                hri_src = rr if "hri_conceptual" in rr.columns else self.hri.iloc[0:0]
                mr_src = rr if "market_risk" in rr.columns else self.mr.iloc[0:0]
            else:
                hri_src = self.hri.iloc[0:0]
                mr_src = self.mr.iloc[0:0]

        h = self._cut(hri_src[hri_src["crop"] == crop])
        if len(h):
            r = h.iloc[-1]
            out["herding"] = {
                "value": round(float(r["hri_conceptual"]), 1),
                "level": str(r.get("hri_conceptual_level")),
                "percentile": None if pd.isna(r.get("hri_conceptual_percentile")) else round(float(r["hri_conceptual_percentile"]), 1),
                "components": {c.replace("c_", ""): (None if pd.isna(r.get(c)) else round(float(r[c]), 1))
                               for c in ["c_price_level", "c_momentum", "c_rise", "c_volatility",
                                         "c_volume", "c_area"] if c in h.columns},
                "component_count": int(r.get("hri_conceptual_component_count", 0)),
                "feature_coverage": round(float(r.get("hri_conceptual_coverage", np.nan)), 2)
                if "hri_conceptual_coverage" in h.columns and pd.notna(r.get("hri_conceptual_coverage")) else None,
                "date": str(pd.Timestamp(r["date"]).date()),
                "interpretation": "可观测市场信号形成的扩种诱因强度（非扩种概率）",
            }
        m = self._cut(mr_src[mr_src["crop"] == crop])
        if len(m):
            r = m.iloc[-1]
            out["market"] = {
                "value": None if pd.isna(r["market_risk"]) else round(float(r["market_risk"]), 1),
                "level": str(r.get("market_risk_level")),
                "percentile": None if pd.isna(r.get("market_risk_percentile")) else round(float(r["market_risk_percentile"]), 1),
                "components": {c.replace("mr_", ""): (None if pd.isna(r.get(c)) else round(float(r[c]), 1))
                               for c in ["mr_volatility", "mr_drawdown", "mr_interval_width",
                                         "mr_downside_risk", "mr_abnormality"] if c in m.columns},
                "date": str(pd.Timestamp(r["date"]).date()),
            }
        out["climate"] = climate.plan_exposure(city, plant_date, harvest_date,
                                               as_of=self.as_of if self.as_of is not None else None)
        out["production"] = production.context_for(city, crop)
        return out

    # ---------------------------------------------------------------- 主入口
    def evaluate_plan(self, plan: Dict) -> Dict:
        city = plan.get("city")
        crop = plan.get("crop")
        plant_date = plan.get("plant_date")
        harvest_date = plan.get("harvest_date")
        area_mu = float(plan.get("area_mu", 0) or 0)
        cost_per_mu = float(plan.get("cost_per_mu", 0) or 0)
        yld = float(plan.get("expected_yield_per_mu", 0) or 0)
        pref = plan.get("risk_preference", "balanced")

        base = {"city": city, "crop": crop, "plant_date": plant_date, "harvest_date": harvest_date,
                "risk_preference": pref, "as_of": str(self.as_of.date()) if self.as_of is not None else str(self.data_end.date())}

        if city in NO_PRICE_CITIES:
            risk = self._risk_block(city, crop, plant_date, harvest_date)
            cparts = self._confidence_parts(city, crop, None, risk, plan)
            res = {**base,
                   "status": "insufficient_market_data",
                   "price": {"low": None, "mid": None, "high": None, "unit": "CNY/kg",
                             "method": None, "is_calibrated_interval": False,
                             "reason": f"{city} 无连续官方价格序列（审计结论），不提供价格模型输出"},
                   "profit": None, "risk": risk,
                   "decision": {"score": None, "grade": None, "risk_preference": pref},
                   "confidence": {"score": cparts["score"], "grade": cparts["grade"],
                                  "data_coverage": None, "components": cparts["components"]},
                   "reasons": [f"{city} 仅有生产/气象/事件数据，无连续官方价格序列",
                               "已返回生产背景与历史同期气候暴露，置信度低"],
                   "evidence": [{"type": "production_context", "value": risk["production"]},
                                {"type": "climate_exposure", "value": risk["climate"]}],
                   "limitations": ["不提供价格/收益/决策评分（数据不支持，不做假）"]}
            return res

        price = self._price_block(city, crop, plant_date, harvest_date)
        risk = self._risk_block(city, crop, plant_date, harvest_date)

        if not price.get("available"):
            cparts = self._confidence_parts(city, crop, None, risk, plan)
            return {**base,
                    "status": "insufficient_market_data",
                    "price": {"low": None, "mid": None, "high": None, "unit": "CNY/kg",
                              "method": None, "is_calibrated_interval": False,
                              "reason": price.get("reason") or "该作物无可用价格序列"},
                    "profit": None, "risk": risk,
                    "decision": {"score": None, "grade": None, "risk_preference": pref},
                    "confidence": {"score": cparts["score"], "grade": cparts["grade"],
                                   "components": cparts["components"]},
                    "reasons": [f"{city}×{crop} 无足够历史价格样本，未做价格建模"],
                    "evidence": [], "limitations": ["不做无数据支撑的价格/收益输出"]}

        profit = evaluate_profit(price["low"], price["mid"], price["high"],
                                 area_mu, cost_per_mu, yld,
                                 is_calibrated_interval=price["is_calibrated_interval"])
        if "error" in profit:
            return {**base, "status": "invalid_input", "error": profit["error"],
                    "price": {k: price.get(k) for k in ["low", "mid", "high"]},
                    "risk": risk, "profit": None,
                    "decision": {"score": None, "grade": None}, "confidence": None,
                    "reasons": ["输入参数不合法"], "evidence": [], "limitations": []}

        hri_v = (risk["herding"] or {}).get("value")
        mr_v = (risk["market"] or {}).get("value")
        cl_v = risk["climate"].get("climate_exposure_score")
        dec = decision_score(
            roi_baseline=profit["scenarios"]["baseline"]["roi"],
            roi_pessimistic=profit["scenarios"]["pessimistic"]["roi"],
            market_risk=mr_v if mr_v is not None else 50.0,
            herding_risk=hri_v if hri_v is not None else 50.0,
            climate_risk=cl_v if cl_v is not None else 50.0,
            risk_preference=pref)

        cparts = self._confidence_parts(city, crop, price, risk, plan)
        conf_block = {"score": cparts["score"], "grade": cparts["grade"],
                      "data_coverage": cparts["details"]["data"]["coverage_score"],
                      "components": cparts["components"], "details": cparts["details"]}

        reasons, evidence, limits = self._narrate(base, price, profit, risk, dec, conf_block)
        return {**base, "status": "ok", "price": price, "profit": {
            "break_even_price": profit["break_even_price"],
            "total_cost": profit["total_cost"],
            "pessimistic": profit["scenarios"]["pessimistic"],
            "baseline": profit["scenarios"]["baseline"],
            "optimistic": profit["scenarios"]["optimistic"],
            "scenario_semantics": profit["scenario_semantics"],
        }, "risk": risk, "decision": dec, "confidence": conf_block,
            "reasons": reasons, "evidence": evidence, "limitations": limits}

    # ---------------------------------------------------------------- 置信度
    def _confidence_parts(self, city, crop, price, risk, plan) -> Dict:
        ds = self._cut(self.ds)
        sub = ds[(ds["city"] == city) & (ds["crop"] == crop)]
        n_obs = len(sub)
        if n_obs and city == "沈阳":
            span = (pd.Timestamp(sub["date"].max()) - pd.Timestamp(sub["date"].min())).days + 1
            bdays = max(1, int(span * 5 / 7))
            coverage = min(1.0, n_obs / bdays)
            missing = float(sub["price_per_kg"].isna().mean())
            sq = "A"
        elif price and price.get("available"):
            coverage = min(1.0, price.get("sample", {}).get("n_obs", 0) / 900)
            missing = 0.0
            sq = "B"
        else:
            coverage, missing, sq = 0.0, 1.0, "C"

        m_wape = b_wape = m_std = None
        if self.sel is not None:
            row = self.sel[self.sel["crop"] == crop]
            if len(row):
                m_wape = float(row.iloc[0]["mean_WAPE"])
                b_wape = float(row.iloc[0]["baseline_mean_WAPE"])
                if "std_WAPE" in row.columns:
                    m_std = None if pd.isna(row.iloc[0]["std_WAPE"]) else float(row.iloc[0]["std_WAPE"])
        iv = self.interval_sel
        hri_cov = (risk.get("herding") or {}).get("feature_coverage")
        clim_cov = (risk["climate"].get("component_count") or 0) / 6.0
        harvest = pd.Timestamp(plan.get("harvest_date"))
        days_beyond = max(0, (harvest - self.data_end).days)
        be = None
        if plan.get("cost_per_mu") and plan.get("expected_yield_per_mu"):
            be = float(plan["cost_per_mu"]) / float(plan["expected_yield_per_mu"])
        hist = sub["price_per_kg"].dropna()
        within = bool(len(hist) and be is not None and hist.min() * 0.8 <= be <= hist.max() * 1.2) \
            if be is not None else True
        parts = {
            "data": conf.data_score(n_obs, coverage, missing, sq),
            "model": conf.model_score(m_wape, b_wape, m_std),
            "interval": conf.interval_score(iv.get("coverage") if price and price.get("available") else None),
            "feature": conf.feature_score(hri_cov, min(1.0, clim_cov)),
            "domain": conf.domain_score(harvest <= self.data_end + pd.Timedelta(days=3650),
                                        days_beyond, within, price is not None and price.get("available")),
        }
        # 漂移（point-in-time：训练期 ≤2023-12-31 vs 截止日前 12 个月）
        as_of_ts = self.as_of if self.as_of is not None else self.data_end
        cur_start = str((as_of_ts - pd.Timedelta(days=365)).date())
        try:
            dsub = self.ds[self.ds["date"] <= as_of_ts]
            parts["drift"] = drift_mod.drift_score(dsub, crop, ref_end="2023-12-31",
                                                   cur_start=cur_start)
        except Exception as e:
            parts["drift"] = {"score": 50.0, "note": f"drift 计算失败: {type(e).__name__}"}
        return conf.confidence_engine(parts)

    # ---------------------------------------------------------------- 叙述层
    def _narrate(self, base, price, profit, risk, dec, confb) -> tuple:
        reasons, evidence, limits = [], [], []
        reasons.append(
            f"上市窗口（{price['window_month']}月）历史同月价格 P10/P50/P90 = "
            f"{price['low']:.2f}/{price['mid']:.2f}/{price['high']:.2f} 元/kg"
            f"（{price['sample']['n_years']} 年 {price['sample']['n_obs']} 个观测，strictly past-only）")
        be = profit["break_even_price"]
        rel = (price["mid"] / be - 1) * 100
        reasons.append(f"盈亏平衡价 {be:.2f} 元/kg；历史 P50 比盈亏平衡{'高' if rel >= 0 else '低'} {abs(rel):.1f}%")
        pos = "亏损" if profit["scenarios"]["baseline"]["profit"] < 0 else "盈利"
        reasons.append(f"基准情景（P50）净收益 {profit['scenarios']['baseline']['profit']:.0f} 元（{pos}），"
                       f"ROI {profit['scenarios']['baseline']['roi']*100:.1f}%")
        if risk.get("herding"):
            h = risk["herding"]
            reasons.append(f"跟风风险 HRI={h['value']}（{h['level']}），"
                           f"主导组件: " + ", ".join(
                               f"{k}={v}" for k, v in sorted(
                                   (h["components"] or {}).items(), key=lambda kv: -(kv[1] or 0))[:2]))
        if risk.get("market"):
            m = risk["market"]
            reasons.append(f"市场风险={m['value']}（{m['level']}）")
        cl = risk["climate"]
        if cl.get("climate_exposure_score") is not None:
            reasons.append(f"历史同期气候暴露={cl['climate_exposure_score']}（{cl['n_years']} 年同窗口概率，非天气预报）")
        reasons.append(f"综合决策评分 {dec['score']}（{dec['grade']}，{base['risk_preference']}）；"
                       f"结果置信度 {confb['score']}（{confb['grade']}）")

        evidence.append({"type": "seasonal_price", "source": "canonical price_observation",
                         "detail": price["sample"], "price_level": price["price_level"]})
        if self.sel is not None:
            row = self.sel[self.sel["crop"] == base["crop"]]
            if len(row):
                r = row.iloc[0]
                evidence.append({"type": "price_model_backtest",
                                 "model": r["model"], "route": r["route"],
                                 "mean_WAPE": round(float(r["mean_WAPE"]), 2),
                                 "best_baseline_WAPE": round(float(r["baseline_mean_WAPE"]), 2),
                                 "folds": 3,
                                 "detail": "expanding window: train≤2023→test2024; ≤2024→2025; ≤2025→2026(1-9月)"})
        evidence.append({"type": "interval_calibration", "detail": self.interval_sel})
        evidence.append({"type": "hri_definition",
                         "detail": "HRI = 价格位置/动能/连涨/波动率/成交量(仅沈阳)/面积(如有) 的历史分位加权；权重方案 equal/conceptual/entropy 已做敏感性"})
        evidence.append({"type": "climate_basis", "detail": cl.get("basis"),
                         "years_used": cl.get("n_years")})
        if risk.get("production", {}).get("available"):
            evidence.append({"type": "production_context", "detail": risk["production"]})
        else:
            evidence.append({"type": "production_context", "detail": "无匹配城市×作物生产数据（未用其他口径替代）"})

        limits.extend([
            "价格区间为历史同月分位（scenario range），不是经过校准的概率预测区间",
            "未来 60/90 天不做精确点预测（数据支持不足，A06：气象无预测增量）",
            "HRI 无跨城市联动维度（跨城重叠窗口覆盖率 <8%，审计结论）",
            "气候暴露≠减产/损失（无分作物灾损标签）",
            "亩均成本为用户输入（项目内无历史蔬菜亩均成本）",
        ])
        if not price["is_calibrated_interval"]:
            limits.append("is_calibrated_interval=false：区间未通过 empirical coverage 校准检验")
        return reasons, evidence, limits

    # ---------------------------------------------------------------- 方案对比
    def compare_plans(self, plans: List[Dict]) -> Dict:
        rows, full = [], []
        for p in plans:
            r = self.evaluate_plan(p)
            full.append(r)
            if r.get("status") != "ok":
                rows.append({"plan": p, "score": None, "status": r.get("status")})
                continue
            d = r["decision"]
            row = {"city": r["city"], "crop": r["crop"],
                   "plant_date": r["plant_date"], "harvest_date": r["harvest_date"],
                   "area_mu": p.get("area_mu"),
                   "price_mid": r["price"]["mid"],
                   "break_even_price": r["profit"]["break_even_price"],
                   "profit_baseline": r["profit"]["baseline"]["profit"],
                   "profit_pessimistic": r["profit"]["pessimistic"]["profit"],
                   "roi_baseline": r["profit"]["baseline"]["roi"],
                   "market_risk": (r["risk"]["market"] or {}).get("value"),
                   "hri": (r["risk"]["herding"] or {}).get("value"),
                   "climate": r["risk"]["climate"].get("climate_exposure_score"),
                   "score": d["score"], "grade": d["grade"],
                   "confidence": r["confidence"]["score"],
                   "score_conservative": d["scores_by_preference"]["conservative"],
                   "score_balanced": d["scores_by_preference"]["balanced"],
                   "score_aggressive": d["scores_by_preference"]["aggressive"]}
            rows.append(row)
        out = pd.DataFrame(rows).sort_values("score", ascending=False, na_position="last").reset_index(drop=True)
        rank_std = None
        if len(out) > 1 and out["score"].notna().all():
            ranks = [out[c].rank(ascending=False) for c in
                     ["score_conservative", "score_balanced", "score_aggressive"]]
            rank_std = float(np.mean([r.std() for r in ranks]))
        return {"ranking": out.to_dict(orient="records"),
                "rank_std_by_preference": rank_std,
                "note": "rank_std 越小排名越稳定（>1 表示结论对风险偏好敏感）",
                "full_results": full}