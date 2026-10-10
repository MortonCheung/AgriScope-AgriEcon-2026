# -*- coding: utf-8 -*-
"""F12-F14: Final 推荐策略 + 历史回测 + Balanced 根因诊断与修复。

设计原则（诚实性优先）：
  - 沈阳 10 蔬菜的「成本/亩产」在 model_ready 中只有零散 RESEARCH_REFERENCE/proxy，
    不足以支撑真实利润点估计（§11/§26）→ 主指标改用**真实价格结果**：
        realized_return = 未来 h 天窗口均价 / 建仓时点价 - 1（无成本/亩产假设）
        realized_downside = 未来 h 天窗口最低价 / 建仓时点价 - 1
  - 预测值来自 Final Price Model 的严格 OOT 预测（selected model per crop）；
  - HRI / Market Risk 来自 Final 单层价格派生指标（as_of 时点可得）；
  - 策略：Balanced(原) / Balanced(修) / Profit-only / Risk-only / Chase-price / Seasonal / Random / Most-Robust；
  - 指标：平均/中位收益、downside、worst、max drawdown、high-HRI 选中率、win rate、regret、稳定性。
"""
from __future__ import annotations
from typing import Dict, List

import numpy as np
import pandas as pd
from scipy import stats

from decision_engine.final.fcommon import (SNAPSHOT_DIR, FINAL_EVAL_DIR, REPORTS_DIR,
                                           ensure_dir, write_json, now_stamp)
from decision_engine.final.risk import daily_prices, weekly_prices, hri_components, combine, market_risk

H = 30
P90_HRI_THR_KEY = "hri_pool_p90"


# ---------------------------------------------------------------- 候选池构建
def build_panel() -> pd.DataFrame:
    """每 (date, crop) 一行：预测 / 现价 / 实际 / HRI / market risk。"""
    preds = pd.read_parquet(FINAL_EVAL_DIR / "price_predictions.parquet")
    sel = pd.read_csv(REPORTS_DIR / "tables" / "price_model_selection.csv")
    sel30 = sel[(sel["city"] == "沈阳") & (sel["horizon"] == H)]
    keys = set(zip(sel30["crop"], sel30["model"], sel30["route"]))
    p = preds[(preds["city"] == "沈阳") & (preds["target"] == f"target_mean_price_next_{H}d")].copy()
    p = p[[(c, m, r) in keys for c, m, r in zip(p["crop"], p["model"], p["route"])]]
    p = p.rename(columns={"prediction": "forecast", "actual": "realized_mean"})
    p["date"] = pd.to_datetime(p["date"])
    p = p[["date", "crop", "forecast", "realized_mean", "anchor_price", "fold"]]

    # HRI（周）
    w = weekly_prices("沈阳"); w["wk"] = w["iso_year"] * 100 + w["iso_week"]
    hri = combine(hri_components(w))[["crop", "iso_year", "iso_week", "HRI", "hri_pct"]]
    hri["wk"] = hri["iso_year"] * 100 + hri["iso_week"]
    p["iso_year"] = p["date"].dt.isocalendar().year.astype(int)
    p["iso_week"] = p["date"].dt.isocalendar().week.astype(int)
    p["wk"] = p["iso_year"] * 100 + p["iso_week"]
    p = p.merge(hri[["crop", "wk", "HRI", "hri_pct"]], on=["crop", "wk"], how="left")

    # market risk（日）
    mr = market_risk(daily_prices("沈阳"))[["date", "crop", "market_risk"]]
    p = p.merge(mr, on=["date", "crop"], how="left")

    # 区间 P10/P90（seasonal_window_quantile 或最优）
    try:
        iv = pd.read_parquet(FINAL_EVAL_DIR / "predictions_with_intervals.parquet")
        iv["date"] = pd.to_datetime(iv["date"])
        iv = iv.rename(columns={"p10": "fc_low", "p90": "fc_high"})[["date", "crop", "fc_low", "fc_high"]]
        p = p.merge(iv, on=["date", "crop"], how="left")
    except Exception:
        p["fc_low"] = np.nan; p["fc_high"] = np.nan

    p["realized_return"] = p["realized_mean"] / p["anchor_price"] - 1
    # 未来窗口最低价（downside 真实结果）
    ds = pd.read_parquet(SNAPSHOT_DIR / "datasets" / "decision_dataset_沈阳.parquet",
                         columns=["date", "crop", "target_min_price_next_30d"])
    ds["date"] = pd.to_datetime(ds["date"])
    p = p.merge(ds, on=["date", "crop"], how="left")
    p["realized_worst"] = p["target_min_price_next_30d"] / p["anchor_price"] - 1
    return p.dropna(subset=["forecast", "realized_return", "anchor_price"]).reset_index(drop=True)


# ---------------------------------------------------------------- 策略
def _pool_pct(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").rank(pct=True, na_option="bottom").fillna(0.5)


def strategy_scores(g: pd.DataFrame) -> pd.DataFrame:
    d = g.copy()
    d["hri_n"] = _pool_pct(d["HRI"])                 # 池内百分位
    d["mr_n"] = (pd.to_numeric(d["market_risk"], errors="coerce") / 100).fillna(0.5)
    d["fc_n"] = _pool_pct(d["forecast"])
    d["low_n"] = _pool_pct(d["fc_low"].fillna(d["forecast"]))
    d["cur_n"] = _pool_pct(d["anchor_price"])
    # 原 Balanced（复现旧权重语义：收益 0.35 / 下行 0.20 / 置信 0.10 / 市场 0.15 / 跟风 0.12 / 气候 0.08；无气候→剔除）
    d["s_balanced_old"] = 0.35 * d["fc_n"] + 0.20 * d["low_n"] - 0.15 * d["mr_n"] - 0.12 * d["hri_n"]
    # 修复版 Balanced：HRI 用池内百分位（可区分）+ 提高跟风惩罚 + 风险约束性更强
    d["s_balanced_fix"] = 0.30 * d["fc_n"] + 0.20 * d["low_n"] - 0.20 * d["mr_n"] - 0.30 * d["hri_n"]
    d["s_profit"] = d["forecast"]
    d["s_lowrisk"] = -(d["mr_n"] + d["hri_n"])
    d["s_chase"] = d["anchor_price"]
    d["s_robust"] = d["fc_low"].fillna(d["forecast"]) - 0.5 * d["hri_n"] * d["forecast"]
    return d


STRATS = {
    "AgriScope_Balanced_old": "s_balanced_old",
    "AgriScope_Balanced_fix": "s_balanced_fix",
    "Profit_only": "s_profit",
    "Risk_only": "s_lowrisk",
    "Chase_price": "s_chase",
    "Most_Robust": "s_robust",
}


def _seasonal_pick(g: pd.DataFrame, hist: pd.DataFrame) -> int:
    """历史同月窗口均价最高作物（严格只用 <=t 的同月历史）。"""
    t = g["date"].iloc[0]
    hh = hist[(hist["month"] == t.month) & (hist["date"] < t)]
    if not len(hh):
        return g["forecast"].idxmax()
    best = hh.groupby("crop")["price_per_kg"].mean()
    for c in g.sort_values("crop")["crop"]:
        if c in best.index:
            return g.index[g["crop"] == c][0]
    return g["forecast"].idxmax()


def run_backtest(cutoff_step_days: int = 7) -> Dict[str, object]:
    panel = build_panel()
    daily = daily_prices("沈阳"); daily["month"] = daily["date"].dt.month
    dates = sorted(panel["date"].unique())
    step = pd.Timedelta(days=cutoff_step_days)
    rows = []
    for t in dates:
        g = panel[panel["date"] == t]
        if len(g) < 4:
            continue
        sc = strategy_scores(g)
        thr = g["HRI"].quantile(0.90)
        for name, col in STRATS.items():
            idx = sc[col].idxmax()
            sel = g.loc[[idx]]
            rows.append(_rec(t, name, sel, g, thr))
        # Seasonal 与 Random（同一切点、同池）
        sidx = _seasonal_pick(g, daily)
        rows.append(_rec(t, "Seasonal", g.loc[[sidx]], g, thr))
        rng = np.random.RandomState(abs(hash(str(t))) % (10 ** 6))
        ridx = g.index[rng.permutation(len(g))[0]]
        rows.append(_rec(t, "Random", g.loc[[ridx]], g, thr))
    bt = pd.DataFrame(rows)
    if not len(bt):
        return {"status": "no_results"}
    best = bt.groupby("date")["realized_return"].max().rename("best")
    bt = bt.merge(best, on="date", how="left")
    bt["regret"] = bt["best"] - bt["realized_return"]
    bt.to_parquet(FINAL_EVAL_DIR / "strategy_backtest.parquet", index=False)

    summ = (bt.groupby("strategy")
            .agg(n=("realized_return", "size"),
                 mean_market_return=("realized_return", "mean"),
                 median_market_return=("realized_return", "median"),
                 downside=("realized_return", lambda s: float(s[s < 0].mean()) if (s < 0).any() else 0.0),
                 worst_market_return=("realized_return", "min"),
                 p05=("realized_return", lambda s: float(s.quantile(0.05))),
                 p_down=("realized_return", lambda s: float((s < 0).mean())),
                 mean_worst_path=("realized_worst", "mean"),
                 high_hri_rate=("high_hri", "mean"),
                 mean_HRI=("HRI", "mean"),
                 mean_market_risk=("market_risk", "mean"),
                 win_rate=("win", "mean"),
                 mean_regret=("regret", "mean"),
                 stability=("realized_return", "std"))
            .reset_index())
    # 风险调整：mean/|downside|
    summ["risk_adj"] = summ["mean_market_return"] / summ["downside"].abs().replace(0, np.nan)
    # §16 指标语义修正：本指标是市场价格机会收益，不是农户种植利润
    summ["metric_semantics"] = "market_return = 未来30天窗口均价/建仓价-1（市场机会，非农户利润）"
    summ = summ.sort_values("mean_market_return", ascending=False)
    summ.to_csv(REPORTS_DIR / "tables" / "strategy_benchmark.csv", index=False, encoding="utf-8-sig")
    return {"status": "ok", "n_cutoffs": bt["date"].nunique(), "summary": summ}


def _rec(t, name, sel, pool, thr) -> Dict:
    r = sel.iloc[0]
    return {
        "date": str(pd.Timestamp(t).date()), "strategy": name, "crop": r["crop"],
        "forecast": float(r["forecast"]), "anchor": float(r["anchor_price"]),
        "realized_return": float(r["realized_return"]),
        "realized_worst": float(r["realized_worst"]) if "realized_worst" in r else np.nan,
        "HRI": float(r["HRI"]) if pd.notna(r["HRI"]) else np.nan,
        "high_hri": bool(pd.notna(r["HRI"]) and r["HRI"] >= thr),
        "market_risk": float(r["market_risk"]) if pd.notna(r["market_risk"]) else np.nan,
        "win": bool(r["realized_return"] > 0),
    }


# ---------------------------------------------------------------- Balanced 根因诊断
def diagnosis(panel: pd.DataFrame) -> Dict[str, object]:
    rows = []
    for t, g in panel.groupby("date"):
        if len(g) < 6 or g["HRI"].notna().sum() < 4:
            continue
        sc = strategy_scores(g)
        rows.append({
            "date": str(pd.Timestamp(t).date()),
            "corr_HRI_forecast": stats.spearmanr(g["HRI"], g["forecast"], nan_policy="omit")[0],
            "corr_HRI_anchor": stats.spearmanr(g["HRI"], g["anchor_price"], nan_policy="omit")[0],
            "corr_HRI_realized": stats.spearmanr(g["HRI"], g["realized_return"], nan_policy="omit")[0],
            "pick_old_highhri": bool(g.loc[sc["s_balanced_old"].idxmax(), "HRI"] >= g["HRI"].quantile(0.9)),
            "pick_fix_highhri": bool(g.loc[sc["s_balanced_fix"].idxmax(), "HRI"] >= g["HRI"].quantile(0.9)),
            "pick_profit_highhri": bool(g.loc[sc["s_profit"].idxmax(), "HRI"] >= g["HRI"].quantile(0.9)),
        })
    d = pd.DataFrame(rows)
    out = {
        "n_cutoffs": int(len(d)),
        "mean_corr_HRI_forecast": float(d["corr_HRI_forecast"].mean()),
        "mean_corr_HRI_anchor": float(d["corr_HRI_anchor"].mean()),
        "mean_corr_HRI_realized": float(d["corr_HRI_realized"].mean()),
        "high_hri_rate_old": float(d["pick_old_highhri"].mean()),
        "high_hri_rate_fix": float(d["pick_fix_highhri"].mean()),
        "high_hri_rate_profit": float(d["pick_profit_highhri"].mean()),
    }
    d.to_csv(REPORTS_DIR / "tables" / "balanced_diagnosis_by_cutoff.csv", index=False, encoding="utf-8-sig")
    # 判定 A/B/C
    valid_hri = out["mean_corr_HRI_realized"] < -0.05
    corr_fc = out["mean_corr_HRI_forecast"]
    if valid_hri and abs(corr_fc) > 0.15:
        case = "C (HRI 有效，但与预测收益/价格水平高相关 → 旧 score 未有效惩罚)"
    elif valid_hri:
        case = "A (HRI 有效，推荐层未正确惩罚)"
    else:
        case = "B (HRI 验证失败)"
    out["diagnosis_case"] = case
    write_json(out, REPORTS_DIR / "tables" / "balanced_diagnosis.json")
    return out


if __name__ == "__main__":
    p = build_panel()
    print("panel rows:", len(p), "dates:", p["date"].nunique())
    print("diagnosis:", diagnosis(p))
    print(run_backtest())