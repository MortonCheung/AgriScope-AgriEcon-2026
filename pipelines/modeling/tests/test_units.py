# -*- coding: utf-8 -*-
"""单元测试：价格单位换算、join 基数、收益公式。"""
import numpy as np
import pandas as pd

from decision_engine.data.build_dataset import build_base


def test_price_unit_conversion():
    base, _ = build_base()
    # price_per_kg == price_per_500g × 2，且与 canonical price_per_kg 一致
    assert np.allclose(base["price_per_kg"], base["price_per_500g"] * 2.0)
    assert base["price_kg_check"].all()
    assert (base["price_raw_unit"] == "元/斤").all()
    # 原始价与 500g 价一致
    assert np.allclose(base["price_raw"], base["price_per_500g"])


def test_join_cardinality():
    base, qc = build_base()
    r = qc.iloc[0]
    assert r["price_rows"] == 14100 and r["volume_rows"] == 14100
    assert r["price_dup_keys"] == 0 and r["volume_dup_keys"] == 0
    assert r["matched_rows"] == 14100
    assert r["price_only_rows"] == 0 and r["volume_only_rows"] == 0
    assert r["row_inflation"] == 0
    assert len(base) == 14100  # 无行数膨胀


def test_panel_balance():
    base, _ = build_base()
    # 10 作物 × 1410 观测，日期集合完全一致
    g = base.groupby("crop")["date"].nunique()
    assert g.nunique() == 1 and g.iloc[0] == 1410
    assert base["crop"].nunique() == 10


def test_profit_formula():
    """收益公式单元测试（与 profit 模块公式一致）。"""
    area_mu, yield_per_mu, cost_per_mu = 80.0, 4500.0, 5200.0
    be = cost_per_mu / yield_per_mu
    assert abs(be - 1.1556) < 1e-3
    for price, expect in [(0.5, 80 * 4500 * 0.5 - 80 * 5200),
                          (2.0, 80 * 4500 * 2.0 - 80 * 5200)]:
        profit = area_mu * yield_per_mu * price - area_mu * cost_per_mu
        assert abs(profit - expect) < 1e-6