# -*- coding: utf-8 -*-
"""引擎 / 风险 / 置信度 / 对比 的自动测试（artifacts 缺失时自动跳过）。"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from decision_engine.common import de_path


def _exists(p) -> bool:
    return Path(p).exists()


@pytest.mark.skipif(not _exists(de_path("data", "features", "hri_v1.parquet")),
                    reason="HRI 未构建")
def test_hri_range():
    h = pd.read_parquet(de_path("data", "features", "hri_v1.parquet"))
    v = h["hri_conceptual"].dropna()
    assert v.min() >= 0 and v.max() <= 100
    lv = h["hri_conceptual_level"].dropna().unique()
    assert set(lv) <= {"low", "medium", "high", "very_high"}
    # HRI 有效行必须至少有一个可用组件；HRI 为 NA 的行（历史不足 60 观测）允许 component_count=0
    valid = h["hri_conceptual"].notna()
    assert (h.loc[valid, "hri_conceptual_component_count"] >= 1).all()
    assert h.loc[~valid, "hri_conceptual"].isna().all()
    # 组件得分范围（全空组件，如沈阳蔬菜无匹配面积数据 c_area，跳过）
    for c in [c for c in h.columns if c.startswith("c_")]:
        s = h[c].dropna()
        if len(s) == 0:
            continue
        assert s.min() >= -1e-6 and s.max() <= 100 + 1e-6


@pytest.mark.skipif(not _exists(de_path("data", "features", "market_risk_v1.parquet")),
                    reason="Market risk 未构建")
def test_market_risk_range():
    m = pd.read_parquet(de_path("data", "features", "market_risk_v1.parquet"))
    v = m["market_risk"].dropna()
    assert v.min() >= 0 and v.max() <= 100
    assert set(m["market_risk_level"].dropna().unique()) <= {"low", "medium", "high", "very_high"}


@pytest.mark.skipif(not _exists(de_path("evaluation", "metrics", "model_selection.csv")),
                    reason="模型未训练")
def test_engine_schema_and_ranges():
    from decision_engine.engine.engine import DecisionEngine
    eng = DecisionEngine()
    r = eng.evaluate_plan({"city": "沈阳", "crop": "西红柿", "plant_date": "2026-10-10",
                           "harvest_date": "2027-01-10", "area_mu": 80, "cost_per_mu": 5200,
                           "expected_yield_per_mu": 4500, "risk_preference": "balanced"})
    for k in ["city", "crop", "price", "profit", "risk", "decision", "confidence",
              "reasons", "evidence", "limitations"]:
        assert k in r, k
    assert r["status"] == "ok"
    assert 0 <= r["confidence"]["score"] <= 100
    assert r["confidence"]["grade"] in list("ABCD")
    assert 0 <= r["decision"]["score"] <= 100
    assert r["decision"]["grade"] in list("ABCD")
    assert r["price"]["low"] <= r["price"]["mid"] <= r["price"]["high"]
    # 盈亏平衡 = 成本/亩产（引擎输出保留 4 位小数）
    assert abs(r["profit"]["break_even_price"] - 5200 / 4500) < 1e-3
    assert len(r["reasons"]) >= 3


def test_no_price_city_degradation():
    from decision_engine.engine.engine import DecisionEngine
    eng = DecisionEngine()
    r = eng.evaluate_plan({"city": "大连", "crop": "西红柿", "plant_date": "2026-10-10",
                           "harvest_date": "2027-06-10", "area_mu": 80, "cost_per_mu": 5200,
                           "expected_yield_per_mu": 4500, "risk_preference": "balanced"})
    assert r["status"] == "insufficient_market_data"
    assert r["price"]["mid"] is None
    assert r["confidence"]["grade"] in list("ABCD")
    assert r["risk"]["climate"]["is_weather_forecast"] is False


def test_scenario_comparison():
    from decision_engine.engine.engine import DecisionEngine
    eng = DecisionEngine()
    plans = [
        {"city": "沈阳", "crop": "西红柿", "plant_date": "2026-10-10", "harvest_date": "2027-01-10",
         "area_mu": 80, "cost_per_mu": 5200, "expected_yield_per_mu": 4500, "risk_preference": "balanced"},
        {"city": "沈阳", "crop": "黄瓜", "plant_date": "2027-03-01", "harvest_date": "2027-06-10",
         "area_mu": 120, "cost_per_mu": 4800, "expected_yield_per_mu": 6000, "risk_preference": "balanced"},
    ]
    res = eng.compare_plans(plans)
    assert "ranking" in res and len(res["ranking"]) == 2
    scores = [r.get("score") for r in res["ranking"]]
    assert all(s is None or 0 <= s <= 100 for s in scores)
    assert res["rank_std_by_preference"] is not None


def test_interval_reported_honestly():
    p = de_path("models", "registry", "interval_selection.json")
    if not _exists(p):
        pytest.skip("interval 未构建")
    sel = json.loads(p.read_text())
    assert 0 <= sel["coverage"] <= 1
    assert sel["is_calibrated_interval"] in (True, False)
    if abs(sel["coverage"] - 0.8) > 0.05:
        assert sel["is_calibrated_interval"] is False, "coverage 不达标时不允许标记 calibrated"


def test_replay_not_cherry_picked():
    p = de_path("evaluation", "cases", "replay_cases.json")
    if not _exists(p):
        pytest.skip("replay 未运行")
    cases = json.loads(p.read_text())["cases"]
    types = {c["case_type"] for c in cases}
    assert "failure" in types, "必须包含失败案例"
    assert len(cases) >= 6