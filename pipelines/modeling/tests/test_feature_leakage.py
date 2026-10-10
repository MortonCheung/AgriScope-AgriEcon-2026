# -*- coding: utf-8 -*-
"""泄漏验证测试。

覆盖：
  1. rolling 不含未来（与手工重算一致）
  2. expanding 分位仅用 <=t
  3. 季节分位仅用历史年份（同月、year<t.year）
  4. 目标列不得出现在模型特征中
  5. 禁止列（STL/loo/extremum 等）不得出现
  6. Cutoff reproducibility：cutoff=2024-12-31 独立重建 == 全量流水线的 <=cutoff 部分
"""
from datetime import date

import numpy as np
import pandas as pd
import pytest

from decision_engine.data.build_dataset import build_base
from decision_engine.features.build_features import add_price_features, add_targets


@pytest.fixture(scope="module")
def base():
    b, _ = build_base()
    return b


@pytest.fixture(scope="module")
def feats(base):
    return add_price_features(base)


def test_rolling_no_future(feats):
    sub = feats[feats["crop"] == "土豆"].sort_values("date").reset_index(drop=True)
    i = 500
    expect = sub["price_per_kg"].iloc[i - 6:i + 1].mean()
    assert abs(sub["price_ma7"].iloc[i] - expect) < 1e-9
    expect30 = sub["price_per_kg"].iloc[i - 29:i + 1].mean()
    assert abs(sub["price_ma30"].iloc[i] - expect30) < 1e-9


def test_expanding_percentile_past_only(feats):
    sub = feats[feats["crop"] == "西红柿"].sort_values("date").reset_index(drop=True)
    i = 300
    hist = sub["price_per_kg"].iloc[:i + 1]
    expect = (hist <= sub["price_per_kg"].iloc[i]).mean()
    assert abs(sub["expanding_price_percentile"].iloc[i] - expect) < 1e-9


def test_seasonal_quantile_uses_prior_years_only(feats, base):
    # 取 2023-06 的样本，期望 = 2021、2022 同月观测的 P10/50/90
    sub = feats[(feats["crop"] == "黄瓜") & (feats["month"] == 6) & (feats["year"] == 2023)]
    row = sub.iloc[0]
    hist = base[(base["crop"] == "黄瓜") & (base["month"] == 6) & (base["year"] < 2023)]["price_per_kg"]
    assert len(hist) >= 20
    p10, p50, p90 = np.percentile(hist, [10, 50, 90])
    assert abs(row["seasonal_p10"] - p10) < 1e-9
    assert abs(row["seasonal_p50"] - p50) < 1e-9
    assert abs(row["seasonal_p90"] - p90) < 1e-9
    assert row["seasonal_year_count"] == 2
    # 2021 年（首年）不可用
    y21 = feats[(feats["crop"] == "黄瓜") & (feats["year"] == 2021)]
    assert not y21["seasonal_feature_available"].any()


def test_targets_not_in_features(base):
    from decision_engine.models.train_price import FEATURE_COLS, TARGET_COLS
    assert not set(FEATURE_COLS) & set(TARGET_COLS)
    assert not any(c.startswith("target_") for c in FEATURE_COLS)
    banned = ["stl", "loo", "extremum", "seasonal_index_a01"]
    for c in FEATURE_COLS:
        assert not any(b in c.lower() for b in banned), c


def test_cutoff_reproducibility(base):
    """cutoff=2024-12-31 独立重建的特征必须与全量流水线完全一致。"""
    cutoff = date(2024, 12, 31)
    full = add_price_features(base)
    trunc = add_price_features(base[base["date"] <= cutoff])
    fc = full[full["date"] <= cutoff]
    keys = ["date", "crop"]
    cols = [c for c in trunc.columns if c not in keys]
    m = fc[keys + cols].merge(trunc[keys + cols], on=keys, suffixes=("_full", "_cut"))
    assert len(m) == len(fc) == len(trunc)
    bad = []
    for c in cols:
        a, b = m[f"{c}_full"], m[f"{c}_cut"]
        if a.dtype == object or str(a.dtype).startswith("bool"):
            same = (a.fillna("__NA__") == b.fillna("__NA__")).all()
        else:
            same = np.allclose(a.astype(float), b.astype(float), equal_nan=True, rtol=0, atol=1e-12)
        if not same:
            bad.append(c)
    assert not bad, f"cutoff 重建不一致（存在泄漏或状态依赖）: {bad[:10]}"


def test_targets_cutoff_consistency(base):
    """target 在未来窗口不完整时必须为 NA（不允许截断窗口强行计算）。"""
    ds = add_targets(add_price_features(base))
    last = max(ds["date"])
    tail = ds[pd.to_datetime(ds["date"]) > pd.Timestamp(last) - pd.Timedelta(days=30)]
    # 距末端不足 30 天的样本 target 必须 NA
    n_should_na = (pd.to_datetime(last) - pd.to_datetime(tail["date"])).dt.days < 30
    assert tail.loc[n_should_na, "target_mean_price_next_30d"].isna().all()