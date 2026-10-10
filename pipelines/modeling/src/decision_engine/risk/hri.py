# -*- coding: utf-8 -*-
"""Phase 4: Herding Risk Index (HRI) v1 —— 透明、可解释、可回测的复合指数。

科学边界（写死）：
  - HRI 不是「农民一定会扩种」的概率，而是「可观测市场信号形成的扩种诱因强度」；
  - 没有监督标签，不做分类器；
  - 权重方案对比（Equal / Conceptual / Entropy）+ 敏感性分析；
  - 阈值来自自身历史分布（past-only expanding 分位），不使用人为 30/60/80。
"""
from __future__ import annotations
from typing import Dict, List

import numpy as np
import pandas as pd
from scipy import stats

MIN_PERIODS = 60

COMPONENTS = ["price_level", "momentum", "rise", "volatility", "volume", "area"]

CONCEPTUAL_W = {"price_level": 0.30, "momentum": 0.25, "rise": 0.15,
                "volatility": 0.15, "volume": 0.10, "area": 0.05}


def _expanding_pct(s: pd.Series, min_periods: int = MIN_PERIODS) -> pd.Series:
    return s.expanding(min_periods=min_periods).rank(pct=True)


def build_component_scores(ds: pd.DataFrame, area_yoy: Dict | None = None) -> pd.DataFrame:
    """组件 0-100 分（全部 past-only expanding 分位）。"""
    d = ds.sort_values(["crop", "date"]).copy()
    g = d.groupby("crop", sort=False)

    # 1) 价格位置：same_season → same_month → expanding 依次回退
    lvl = d["same_season_price_percentile"].fillna(d["same_month_price_percentile"])
    lvl = lvl.fillna(d["expanding_price_percentile"])
    d["c_price_level"] = lvl * 100

    # 2) 动能：momentum_30 的历史分位
    d["c_momentum"] = g["price_momentum_30"].transform(_expanding_pct) * 100

    # 3) 连续上涨
    d["c_rise"] = g["continuous_rise_days"].transform(_expanding_pct) * 100

    # 4) 波动率（不稳定 → 风险）
    d["c_volatility"] = g["volatility_30"].transform(_expanding_pct) * 100

    # 5) 成交量相对活跃度（仅沈阳；单位未知，仅相对口径）
    if "volume_percentile" in d.columns:
        d["c_volume"] = d["volume_percentile"] * 100
    else:
        d["c_volume"] = np.nan

    # 6) 面积增速（年度，仅当 city×crop 有真实匹配数据；蔬菜无 → NaN）
    if area_yoy is not None:
        key = list(zip(d["crop"], d["year"]))
        d["c_area"] = [area_yoy.get(k, np.nan) for k in key]
    else:
        d["c_area"] = np.nan
    return d


def _entropy_weights(scores: pd.DataFrame, cols: List[str]) -> Dict[str, float]:
    """熵权法（在训练窗口上计算，之后固定）。"""
    w = {}
    for c in cols:
        x = scores[c].dropna()
        if len(x) < 30:
            w[c] = np.nan
            continue
        v = (x - x.min()) / (x.max() - x.min() + 1e-12) + 1e-6
        p = v / v.sum()
        h = -(p * np.log(p)).sum()
        w[c] = max(0.0, 1 - h / np.log(len(p)))
    tot = np.nansum(list(w.values()))
    return {k: (v / tot if tot > 0 else np.nan) for k, v in w.items()}


def combine_hri(d: pd.DataFrame, weights: Dict[str, float] | None, scheme_name: str,
                entropy_w: Dict | None = None, train_end: str = "2023-12-31") -> pd.DataFrame:
    """按可用组件重新归一化权重求和（缺失组件不填 0）。"""
    cols = [f"c_{c}" for c in COMPONENTS]
    avail = d[cols].notna()
    if scheme_name == "equal":
        w = {f"c_{c}": 1.0 for c in COMPONENTS}
    elif scheme_name == "conceptual":
        w = {f"c_{c}": CONCEPTUAL_W[c] for c in COMPONENTS}
    elif scheme_name == "entropy":
        if entropy_w is None:
            tr = d[pd.to_datetime(d["date"]) <= pd.Timestamp(train_end)]
            entropy_w = _entropy_weights(tr, cols)
        w = {k: (v if v and np.isfinite(v) else 0.0) for k, v in
             {f"c_{c}": entropy_w.get(f"c_{c}", 0.0) for c in COMPONENTS}.items()}
    else:
        raise ValueError(scheme_name)
    num = np.zeros(len(d))
    den = np.zeros(len(d))
    for c in cols:
        wv = w.get(c, 0.0)
        if not np.isfinite(wv) or wv == 0:
            continue
        v = d[c].fillna(0).values
        m = avail[c].values
        num += np.where(m, v * wv, 0.0)
        den += np.where(m, wv, 0.0)
    out = d.copy()
    out[f"hri_{scheme_name}"] = np.where(den > 0, num / den, np.nan)
    out[f"hri_{scheme_name}_component_count"] = avail.sum(axis=1).values
    out[f"hri_{scheme_name}_coverage"] = [
        float(np.nansum([w.get(f"c_{c}", 0) for c in COMPONENTS if pd.notna(row[f"c_{c}"])]) /
              np.nansum([w.get(f"c_{c}", 0) for c in COMPONENTS]))
        for _, row in d[cols].iterrows()]
    return out


def add_levels(d: pd.DataFrame, hri_col: str, min_periods: int = 120) -> pd.DataFrame:
    """风险等级：阈值 = 自身历史（past-only expanding）P50/P75/P90。"""
    out = d.sort_values(["crop", "date"]).copy()
    pct = out.groupby("crop", sort=False)[hri_col].transform(
        lambda s: s.expanding(min_periods=min_periods).rank(pct=True))
    out[f"{hri_col}_percentile"] = pct * 100
    lvl = pd.Series(index=out.index, dtype=object)
    lvl[pct < 0.50] = "low"
    lvl[(pct >= 0.50) & (pct < 0.75)] = "medium"
    lvl[(pct >= 0.75) & (pct < 0.90)] = "high"
    lvl[pct >= 0.90] = "very_high"
    out[f"{hri_col}_level"] = lvl
    return out


def build_hri(ds: pd.DataFrame, area_yoy: Dict | None = None) -> pd.DataFrame:
    d = build_component_scores(ds, area_yoy)
    d = combine_hri(d, None, "equal")
    d = combine_hri(d, None, "conceptual")
    d = combine_hri(d, None, "entropy")
    for s in ["equal", "conceptual", "entropy"]:
        d = add_levels(d, f"hri_{s}")
    return d


def sensitivity(d: pd.DataFrame, seed: int = 42) -> pd.DataFrame:
    """权重方案敏感性：Spearman 相关 + 等级一致率 + ±20% 扰动排名稳定率。"""
    rows = []
    combos = [("equal", "conceptual"), ("equal", "entropy"), ("conceptual", "entropy")]
    for a, b in combos:
        s = d[[f"hri_{a}", f"hri_{b}"]].dropna()
        if len(s) < 30:
            continue
        rho = stats.spearmanr(s[f"hri_{a}"], s[f"hri_{b}"])[0]
        la = d[f"hri_{a}_level"].fillna("na")
        lb = d[f"hri_{b}_level"].fillna("na")
        agree = float((la == lb)[la != "na"].mean())
        rows.append({"comparison": f"{a}_vs_{b}", "spearman": float(rho),
                     "level_agreement": agree, "n": int(len(s))})
    # 单方案权重扰动 ±20%
    rng = np.random.RandomState(seed)
    base = d["hri_conceptual"].values
    mask = np.isfinite(base)
    stab = []
    for _ in range(50):
        w = {k: v * (1 + rng.uniform(-0.2, 0.2)) for k, v in CONCEPTUAL_W.items()}
        num = np.zeros(len(d)); den = np.zeros(len(d))
        for c in COMPONENTS:
            col = f"c_{c}"
            v = d[col].fillna(0).values
            m = d[col].notna().values
            num += np.where(m, v * w[c], 0)
            den += np.where(m, w[c], 0)
        pert = np.where(den > 0, num / den, np.nan)
        ok = mask & np.isfinite(pert)
        rho = stats.spearmanr(base[ok], pert[ok])[0]
        stab.append(float(rho))
    rows.append({"comparison": "conceptual_weight_jitter_20pct", "spearman": float(np.mean(stab)),
                 "level_agreement": np.nan, "n": int(mask.sum())})
    return pd.DataFrame(rows)


def forward_returns(ds: pd.DataFrame, windows: List[int] = [30, 60, 90]) -> pd.DataFrame:
    """未来 k 天价格变化与窗口内最差回撤（仅用未来真实值做验证）。"""
    d = ds.sort_values(["crop", "date"]).reset_index(drop=True).copy()
    dts = pd.to_datetime(d["date"])
    last = dts.max()
    for k in windows:
        fwd = np.full(len(d), np.nan)
        worst = np.full(len(d), np.nan)
        for crop, sub in d.groupby("crop", sort=False):
            idx = sub.index.values
            sd = pd.to_datetime(sub["date"]).values.astype("datetime64[D]")
            p = sub["price_per_kg"].values
            for j, t in enumerate(sd):
                if t + np.timedelta64(k, "D") > np.datetime64(last, "D"):
                    continue
                lo = np.searchsorted(sd, t, side="right")
                hi = np.searchsorted(sd, t + np.timedelta64(k, "D"), side="right")
                if hi <= lo:
                    continue
                w = p[lo:hi]
                fwd[idx[j]] = w[-1] / p[j] - 1
                worst[idx[j]] = w.min() / p[j] - 1
        d[f"fwd_return_{k}d"] = fwd
        d[f"fwd_worst_{k}d"] = worst
    return d


def validate(d: pd.DataFrame, hri_col: str = "hri_conceptual") -> pd.DataFrame:
    """高 HRI（Top5%）vs 低 HRI（Bottom 50%）之后的价格表现。"""
    rows = []
    d = d.copy()
    d = d[d[hri_col].notna()]
    hi_mask = d.groupby("crop")[hri_col].transform(lambda s: s >= s.quantile(0.95))
    lo_mask = d.groupby("crop")[hri_col].transform(lambda s: s <= s.quantile(0.50))
    for k in [30, 60, 90]:
        f, w = f"fwd_return_{k}d", f"fwd_worst_{k}d"
        hi, lo = d.loc[hi_mask, f].dropna(), d.loc[lo_mask, f].dropna()
        if len(hi) < 20 or len(lo) < 20:
            continue
        u, pval = stats.mannwhitneyu(hi, lo, alternative="two-sided")
        rows.append({
            "window_days": k,
            "n_high": len(hi), "n_low": len(lo),
            "high_mean_fwd_return": float(hi.mean()), "low_mean_fwd_return": float(lo.mean()),
            "high_median_fwd_return": float(hi.median()), "low_median_fwd_return": float(lo.median()),
            "high_p_down": float((hi < 0).mean()), "low_p_down": float((lo < 0).mean()),
            "high_mean_worst": float(d.loc[hi_mask, w].dropna().mean()),
            "low_mean_worst": float(d.loc[lo_mask, w].dropna().mean()),
            "mannwhitney_p": float(pval),
        })
        # 分等级
        for lv in ["low", "medium", "high", "very_high"]:
            m = d[f"{hri_col}_level"] == lv
            if m.sum() > 10:
                rows.append({"window_days": k, "level": lv, "n": int(m.sum()),
                             "level_mean_fwd_return": float(d.loc[m, f].dropna().mean()),
                             "level_p_down": float((d.loc[m, f].dropna() < 0).mean()),
                             "level_mean_worst": float(d.loc[m, w].dropna().mean())})
    return pd.DataFrame(rows)