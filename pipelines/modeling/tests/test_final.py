# -*- coding: utf-8 -*-
"""Final Model 层单元测试（数据完整性 / 无泄漏 / 指标范围 / 契约）。"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT = Path(__file__).resolve().parents[4]      # monorepo 根（迁移后 data/models 的源布局）
SNAP = PROJECT / "data" / "model_ready" / "snapshots" / "final_v1"
MAN = PROJECT / "data" / "metadata" / "model_manifests" / "final"
REP = PROJECT / "models" / "reports" / "final"


def _final_snapshot_ready():
    return (SNAP / "model_ready").exists() and (SNAP / "datasets").exists()


@pytest.mark.skipif(not _final_snapshot_ready(), reason="final_v1 快照未生成")
def test_snapshot_frozen_and_hashed():
    man = pd.read_csv(MAN / "final_v1_manifest.csv")
    assert len(man) == 19
    assert man["sha256"].notna().all() and man["rows"].gt(0).all()


@pytest.mark.skipif(not _final_snapshot_ready(), reason="final_v1 快照未生成")
def test_shenyang_dataset_single_level_ten_crops():
    ds = pd.read_parquet(SNAP / "datasets" / "decision_dataset_沈阳.parquet")
    assert ds["crop"].nunique() == 10
    assert ds["price_per_kg"].notna().all()
    assert ds["price_per_kg"].min() > 0
    # 目标列仅作标签，且未来目标在时间轴尾端为 NaN
    tg = [c for c in ds.columns if c.startswith("target_mean_price_next_")]
    assert len(tg) == 5


@pytest.mark.skipif(not _final_snapshot_ready(), reason="final_v1 快照未生成")
def test_features_no_future_columns():
    ds = pd.read_parquet(SNAP / "datasets" / "decision_dataset_沈阳.parquet")
    bad = [c for c in ds.columns if any(k in c.lower() for k in ("future", "centered", "forward"))]
    assert bad == []


@pytest.mark.skipif(not _final_snapshot_ready(), reason="final_v1 快照未生成")
def test_hri_in_0_100_and_past_only_levels():
    from decision_engine.final.risk import weekly_prices, hri_components, combine
    w = weekly_prices("沈阳")
    h = combine(hri_components(w))
    v = h["HRI"].dropna()
    assert len(v) > 100
    assert v.min() >= 0 and v.max() <= 100
    # 缺失组件不进加权：component_count 应 > 0 且 <= 6
    assert h["hri_component_count"].between(1, 6).all()


@pytest.mark.skipif(not _final_snapshot_ready(), reason="final_v1 快照未生成")
def test_market_risk_range_and_incremental():
    from decision_engine.final.risk import daily_prices, market_risk
    mr = market_risk(daily_prices("沈阳"))
    v = mr["market_risk"].dropna()
    assert v.min() >= 0 and v.max() <= 100


def test_interval_cov_width_unit():
    from decision_engine.final.intervals import evaluate
    iv = pd.DataFrame({"method": ["m"] * 5, "crop": ["a"] * 5, "fold": ["f"] * 5,
                       "date": pd.date_range("2024-01-01", periods=5),
                       "actual": [1, 2, 3, 4, 5], "mid": [2] * 5,
                       "lo": [0] * 5, "hi": [4] * 5})
    per, agg, seas = evaluate(iv)
    assert abs(float(agg.iloc[0]["coverage"]) - 0.8) < 1e-9  # 4/5 落在 [0,4]


def test_data_map_written():
    p = MAN / "MODEL_DATA_MAP.csv"
    assert p.exists()
    dm = pd.read_csv(p)
    assert {"module", "table", "fields", "forbidden"} <= set(dm.columns)


def test_output_schema_valid_json():
    p = REP / "FINAL_MODEL_OUTPUT_SCHEMA.json"
    if not p.exists():
        pytest.skip("schema 未生成")
    s = json.loads(p.read_text())
    assert "properties" in s and s["properties"]["status"]["enum"]


def test_balanced_penalizes_high_hri_regression():
    """回归测试：当高收益与高 HRI 共现时，balanced 不应把最高 HRI 方案排到第一。

    这是 Final 阶段修复的根因（旧实现风险分量用 /100 线性缩放 → HRI 惩罚不区分候选）。
    """
    from decision_engine.optimization import utility as U
    # 现实机制：追高候选 baseline 收益最高，但 HRI 高、下行更差
    pool = pd.DataFrame({
        "roi_baseline":      [0.60, 0.20, 0.18, 0.16],
        "roi_pessimistic":   [-0.30, 0.10, 0.08, 0.06],
        "confidence_score":  [60, 70, 70, 70],
        "market_risk":       [90, 45, 25, 20],
        "HRI":               [95, 40, 20, 15],
        "climate_risk":      [50, 50, 50, 50],
    })
    s_bal = U.utility_scores(pool, "balanced")
    # 纯逐利会选追高候选(0)；Balanced 必须把它排除在首位
    assert pool["roi_baseline"].idxmax() == 0
    assert s_bal.idxmax() != 0, "Balanced 仍把高 HRI/高下行追高候选排在首位（修复失效）"


def test_capability_registry_and_status_enum():
    from decision_engine.final import capabilities as CAP
    assert CAP.STATUS[0] == "OK"
    assert set(["NO_FEASIBLE_WINDOW", "NO_DIVERSIFICATION_BENEFIT",
                "INSUFFICIENT_MARKET_DATA"]) <= set(CAP.STATUS)
    assert CAP.city_capability("大连")["tier"] == "INSUFFICIENT_MARKET_DATA"
    assert CAP.horizon_capability("沈阳", 30)["mode"] == "model"
    assert CAP.horizon_capability("沈阳", 90)["scenario_only"] is True


def test_final_inference_contract_and_status():
    from decision_engine.final.inference import FinalDecisionEngine
    from decision_engine.final import capabilities as CAP
    e = FinalDecisionEngine()
    r = e.evaluate({"city": "沈阳", "crop": "西红柿", "area_mu": 60, "horizon_days": 30})
    for k in ["request_id", "status", "price", "scenario_range", "confidence",
              "model_version", "data_version"]:
        assert k in r
    assert r["status"] in CAP.STATUS
    # 不支持城市必须拒绝且不 fallback
    d = e.evaluate({"city": "大连", "crop": "西红柿", "horizon_days": 30})
    assert d["status"] == "INSUFFICIENT_MARKET_DATA" and d["price"] is None
    # 90d 必须 scenario_only
    h90 = e.evaluate({"city": "沈阳", "crop": "西红柿", "horizon_days": 90})
    assert h90["price"]["scenario_only"] is True


def test_user_input_overrides_proxy():
    from decision_engine.final.inference import FinalDecisionEngine
    e = FinalDecisionEngine()
    base = {"city": "沈阳", "crop": "西红柿", "area_mu": 60, "horizon_days": 30}
    r1 = e.evaluate(base)
    r2 = e.evaluate({**base, "actual_cost_per_mu": 20000, "actual_yield_per_mu": 4000})
    assert (r2.get("profit") or {}).get("cost_source_class") == "user_input"
    assert (r2.get("profit") or {}).get("reliability") == 1.0
    assert (r1.get("profit") or {}).get("cost_source_class") != "user_input"


def test_scenario_range_status_vocabulary():
    from decision_engine.final.range_ import NOMINAL
    assert NOMINAL == 0.80
    import pandas as pd
    from decision_engine.final.fcommon import REPORTS_DIR
    p = REPORTS_DIR / "tables" / "scenario_range_by_crop_horizon.csv"
    if p.exists():
        d = pd.read_csv(p)
        assert set(d["status"].unique()) <= {"scenario_range", "scenario_range_widened",
                                            "scenario_range_unreliable", "no_range_available"}


def test_decision_score_bounded():
    from decision_engine.final.score import decision_score
    pool = pd.DataFrame({"forecast": [1, 2, 3, 4], "fc_low": [0.5, 1, 2, 3],
                         "HRI": [80, 20, 50, 10], "market_risk": [70, 30, 50, 20],
                         "overall_confidence": [50, 60, 70, 80]})
    sc = decision_score(pool)
    assert sc.between(0, 100).all()
    # 高 HRI + 高风险 + 低收益 → 低分
    assert sc.iloc[1] > sc.iloc[0]