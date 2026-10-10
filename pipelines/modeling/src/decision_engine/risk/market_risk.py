# -*- coding: utf-8 -*-
"""Phase 5: Market Risk Index（市场本身的不稳定与收益不确定性）。

与 HRI 的区别：
  HRI   = 价格诱导扩种的风险（herding）
  Market Risk = 市场波动/回撤/预测不确定性/下行空间（自身不稳定）

组件：volatility / drawdown / interval_width / downside_risk / abnormality(PyOD 可选)
全部 past-only 分位转 0-100；缺失组件自动重新归一化。
说明：interval_width 与 downside_risk 在回测期优先使用所选区间方法；
      其余期间使用历史季节分位区间（同为 past-only 口径），保证组件可比的连续性。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

MIN_PERIODS = 60


def _exp_pct(s: pd.Series) -> pd.Series:
    return s.expanding(min_periods=MIN_PERIODS).rank(pct=True)


def build_market_risk(ds: pd.DataFrame, interval_preds: pd.DataFrame | None = None,
                      use_pyod: bool = True) -> pd.DataFrame:
    d = ds.sort_values(["crop", "date"]).copy()

    # 1) 波动率
    d["mr_volatility"] = d.groupby("crop", sort=False)["volatility_30"].transform(_exp_pct) * 100
    # 2) 回撤深度（回撤越深风险越高）
    d["mr_drawdown"] = d.groupby("crop", sort=False)["drawdown_30"].transform(
        lambda s: _exp_pct(-s)) * 100

    # 3) 区间宽度（相对价格）：模型区间优先，缺失回退季节分位区间
    d["_rel_width"] = np.nan
    d["_downside_gap"] = np.nan
    if interval_preds is not None and len(interval_preds):
        ivr = interval_preds.groupby(["crop", "date"], as_index=False).agg(
            lo_min=("lo", "min"), hi_max=("hi", "max"))
        # 注：不同方法口径混用会引入方法差异；统一只使用所选主方法
        main = interval_preds.copy()
        main["rel_width_tmp"] = (main["hi"] - main["lo"]) / main["mid"].replace(0, np.nan)
        best_method = main.groupby("method")["rel_width_tmp"].mean().sort_values().index[0]
        main = main[main["method"] == best_method].groupby(["crop", "date"], as_index=False).agg(
            rel_width=("rel_width_tmp", "mean"), lo_=("lo", "min"))
        d = d.merge(main, on=["crop", "date"], how="left")
        d["_rel_width"] = d.get("rel_width")
        d["_downside_gap"] = (d["price_per_kg"] - d.get("lo_")) / d["price_per_kg"].replace(0, np.nan)

    # 季节分位回退（所有行都可用；past-only）
    seas_w = (d["seasonal_p90"] - d["seasonal_p10"]) / d["seasonal_p50"].replace(0, np.nan)
    seas_d = (d["price_per_kg"] - d["seasonal_p10"]) / d["price_per_kg"].replace(0, np.nan)
    d["_rel_width"] = d["_rel_width"].fillna(seas_w)
    d["_downside_gap"] = d["_downside_gap"].fillna(seas_d)
    d["mr_interval_width"] = d.groupby("crop", sort=False)["_rel_width"].transform(_exp_pct) * 100
    d["mr_downside_risk"] = d.groupby("crop", sort=False)["_downside_gap"].transform(_exp_pct) * 100

    # 4) 异常度（PyOD IsolationForest，训练窗口拟合 → 其余 OOS 打分）
    d["mr_abnormality"] = np.nan
    if use_pyod:
        try:
            from pyod.models.iforest import IForest
            feats = [f for f in ["price_return_30", "volatility_30", "drawdown_30", "volume_zscore"]
                     if f in d.columns]
            tr_mask = pd.to_datetime(d["date"]) <= pd.Timestamp("2023-12-31")
            med = d.loc[tr_mask, feats].median()
            clf = IForest(random_state=42, contamination=0.05)
            clf.fit(d.loc[tr_mask, feats].fillna(med).values)
            score = pd.Series(clf.decision_function(d[feats].fillna(med).values), index=d.index)
            d["mr_abnormality"] = score.groupby(d["crop"]).transform(_exp_pct) * 100
        except Exception as e:
            print(f"[market_risk] pyod unavailable: {e}")

    comps = ["mr_volatility", "mr_drawdown", "mr_interval_width", "mr_downside_risk", "mr_abnormality"]
    avail = d[comps].notna()
    d["market_risk"] = d[comps].fillna(0).sum(axis=1) / avail.sum(axis=1).replace(0, np.nan)
    d["market_risk_component_count"] = avail.sum(axis=1)
    d["market_risk_coverage"] = avail.mean(axis=1)
    pct = d.groupby("crop", sort=False)["market_risk"].transform(
        lambda s: s.expanding(min_periods=120).rank(pct=True)) * 100
    d["market_risk_percentile"] = pct
    lvl = pd.Series(index=d.index, dtype=object)
    lvl[pct < 50] = "low"; lvl[(pct >= 50) & (pct < 75)] = "medium"
    lvl[(pct >= 75) & (pct < 90)] = "high"; lvl[pct >= 90] = "very_high"
    d["market_risk_level"] = lvl
    return d.drop(columns=[c for c in ["rel_width", "lo_", "_rel_width", "_downside_gap"]
                           if c in d.columns])


def validate(d: pd.DataFrame, hri_like_col: str = "market_risk") -> pd.DataFrame:
    """高市场风险期 → 未来实现回撤是否更深（验证而非因果）。"""
    from decision_engine.risk.hri import forward_returns
    from scipy import stats
    dd = forward_returns(d)
    dd = dd[dd[hri_like_col].notna()]
    hi = dd.groupby("crop")[hri_like_col].transform(lambda s: s >= s.quantile(0.95))
    lo = dd.groupby("crop")[hri_like_col].transform(lambda s: s <= s.quantile(0.50))
    rows = []
    for k in [30, 90]:
        col = f"fwd_worst_{k}d"
        h, l = dd.loc[hi, col].dropna(), dd.loc[lo, col].dropna()
        if len(h) < 20 or len(l) < 20:
            continue
        u, p = stats.mannwhitneyu(h, l, alternative="two-sided")
        rows.append({"window_days": k, "n_high": len(h), "n_low": len(l),
                     "high_mean_worst_drawdown": float(h.mean()),
                     "low_mean_worst_drawdown": float(l.mean()),
                     "mannwhitney_p": float(p)})
    return pd.DataFrame(rows)