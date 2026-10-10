# -*- coding: utf-8 -*-
"""F15: 消融 / 鲁棒性 / 组合 / 压力测试 / 反事实(Minimax Regret)。

全部基于 Final 数据与 Final 价格模型 OOT 预测 + Final HRI / Market Risk。
诚实性：成本/亩产为参考口径（蔬菜多为 RESEARCH_REFERENCE/缺口），
        利润相关压力测试明确标注为「情景假设」，价格结果类指标不含假设。
"""
from __future__ import annotations
from typing import Dict, List

import numpy as np
import pandas as pd
from scipy import stats

from decision_engine.final.fcommon import (SNAPSHOT_DIR, REPORTS_DIR, FINAL_EVAL_DIR,
                                           ensure_dir, write_json, now_stamp)
from decision_engine.final.backtest import build_panel, strategy_scores, _seasonal_pick
from decision_engine.final.risk import daily_prices

H = 30


def _metrics(s: pd.Series) -> Dict[str, float]:
    s = pd.to_numeric(s, errors="coerce").dropna()
    if not len(s):
        return {}
    return {"n": int(len(s)), "mean": float(s.mean()), "median": float(s.median()),
            "downside": float(s[s < 0].mean()) if (s < 0).any() else 0.0,
            "worst": float(s.min()), "p_down": float((s < 0).mean()), "std": float(s.std())}


# ---------------------------------------------------------------- 消融
ABLATIONS = {
    "Price_only":      lambda d: d["fc_n"],
    "Price+HRI":       lambda d: d["fc_n"] - 0.30 * d["hri_n"],
    "Price+Market":    lambda d: d["fc_n"] - 0.20 * d["mr_n"],
    "Price+Climate":   lambda d: d["fc_n"] - 0.10 * d["cl_n"],
    "Price+Profit":    lambda d: 0.5 * d["fc_n"] + 0.5 * d["low_n"],
    "Full":            lambda d: d["s_balanced_fix"],
}


def ablation(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for t, g in panel.groupby("date"):
        if len(g) < 4:
            continue
        sc = strategy_scores(g).copy()
        sc["cl_n"] = 0.5  # 气候为历史暴露、与池内标的无关 → 中性；消融时保持常量以隔离
        for name, fn in ABLATIONS.items():
            score = fn(sc)
            idx = score.idxmax()
            r = g.loc[idx]
            rows.append({"ablation": name, "date": str(pd.Timestamp(t).date()),
                         "realized_return": float(r["realized_return"]),
                         "realized_worst": float(r["realized_worst"]),
                         "HRI": float(r["HRI"]) if pd.notna(r["HRI"]) else np.nan})
    d = pd.DataFrame(rows)
    out = []
    for name, g in d.groupby("ablation"):
        m = _metrics(g["realized_return"])
        out.append({"ablation": name, **m,
                    "mean_worst": float(g["realized_worst"].mean()),
                    "high_hri_rate": float((g["HRI"] >= g["HRI"].quantile(0.9)).mean()),
                    "mean_HRI": float(g["HRI"].mean())})
    return pd.DataFrame(out).sort_values("mean", ascending=False)


# ---------------------------------------------------------------- 天气消融（价格模型）
def weather_ablation() -> pd.DataFrame:
    """with/without weather（h=30，elasticnet/extra_trees，逐折 WAPE 对比）。"""
    from decision_engine.final.models import FINAL_FEATURE_COLS, _factories
    from decision_engine.models.backtest import FOLDS, fold_mask, metrics_table
    from decision_engine.final.fcommon import SNAPSHOT_DIR as SD

    ds = pd.read_parquet(SD / "datasets" / "decision_dataset_沈阳.parquet")
    cl = pd.read_parquet(SD / "model_ready/climate/climate_daily.parquet")
    cl = cl[cl["city"] == "沈阳"][["date", "temperature_2m_max", "temperature_2m_min",
                                   "temperature_2m_mean", "precipitation_sum",
                                   "shortwave_radiation_sum", "et0_fao_evapotranspiration"]].copy()
    cl["date"] = pd.to_datetime(cl["date"]).dt.date
    for c in ["temperature_2m_max", "temperature_2m_min", "temperature_2m_mean",
              "precipitation_sum", "shortwave_radiation_sum", "et0_fao_evapotranspiration"]:
        cl[c] = pd.to_numeric(cl[c], errors="coerce")
    cl = cl.sort_values("date")
    for w in [7, 14, 30]:
        cl[f"precip_{w}"] = cl["precipitation_sum"].rolling(w, min_periods=w).sum()
        cl[f"tmean_anom_{w}"] = cl["temperature_2m_mean"] - cl["temperature_2m_mean"].rolling(w, min_periods=w).mean()
    cl["heavy_rain_flag"] = (cl["precipitation_sum"] > 25).astype(float)
    cl["heat_flag"] = (cl["temperature_2m_max"] > 32).astype(float)
    cl["heat_days_7"] = cl["heat_flag"].rolling(7, min_periods=7).sum()
    wcols = ["temperature_2m_mean", "temperature_2m_max", "temperature_2m_min", "precipitation_sum",
             "precip_7", "precip_14", "precip_30", "tmean_anom_7", "tmean_anom_14",
             "heavy_rain_flag", "heat_days_7"]
    ds["date"] = pd.to_datetime(ds["date"]).dt.date
    d = ds.merge(cl[["date"] + wcols], on="date", how="left")

    tgt = "target_mean_price_next_30d"
    facs = _factories()
    chosen = ["elasticnet", "extra_trees"]
    rows = []
    for crop, sub in d.groupby("crop"):
        for mod in chosen:
            for fold in FOLDS:
                tr_all, te_all = fold_mask(sub.assign(date=pd.to_datetime(sub["date"])), fold)
                tr = sub[tr_all.loc[sub.index] & sub[tgt].notna()]
                te = sub[te_all.loc[sub.index] & sub[tgt].notna()]
                if len(tr) < 200 or not len(te):
                    continue
                for tag, cols in [("without_weather", FINAL_FEATURE_COLS),
                                  ("with_weather", FINAL_FEATURE_COLS + wcols)]:
                    m = facs[mod](); m.fit(tr[cols], tr[tgt])
                    mm = metrics_table(te[tgt].values, m.predict(te[cols]))
                    rows.append({"crop": crop, "model": mod, "fold": fold["name"],
                                 "variant": tag, "WAPE": mm["WAPE"], "MAE": mm["MAE"]})
    w = pd.DataFrame(rows)
    if len(w):
        piv = w.pivot_table(index=["crop", "model", "fold"], columns="variant", values="WAPE").reset_index()
        piv["delta_WAPE"] = piv["with_weather"] - piv["without_weather"]
        piv.to_csv(REPORTS_DIR / "tables" / "weather_ablation_by_fold.csv", index=False, encoding="utf-8-sig")
        summ = piv.groupby("model").agg(mean_with=("with_weather", "mean"),
                                         mean_without=("without_weather", "mean"),
                                         mean_delta=("delta_WAPE", "mean"),
                                         n_improved=("delta_WAPE", lambda s: int((s < 0).sum())),
                                         n=("delta_WAPE", "size")).reset_index()
        summ.to_csv(REPORTS_DIR / "tables" / "weather_ablation_summary.csv", index=False, encoding="utf-8-sig")
        return summ
    return pd.DataFrame()


# ---------------------------------------------------------------- 鲁棒性
def robustness(panel: pd.DataFrame) -> pd.DataFrame:
    panel = panel.copy()
    panel["month"] = pd.to_datetime(panel["date"]).dt.month
    panel["season"] = panel["month"].map({12: "winter", 1: "winter", 2: "winter",
                                          3: "spring", 4: "spring", 5: "spring",
                                          6: "summer", 7: "summer", 8: "summer",
                                          9: "autumn", 10: "autumn", 11: "autumn"})
    rows = []
    for t, g in panel.groupby("date"):
        if len(g) < 4:
            continue
        sc = strategy_scores(g)
        picks = {
            "Balanced_fix": sc["s_balanced_fix"].idxmax(),
            "Profit_only": sc["s_profit"].idxmax(),
            "Risk_only": sc["s_lowrisk"].idxmax(),
        }
        for pol, idx in picks.items():
            rows.append({"policy": pol, "date": str(pd.Timestamp(t).date()), "year": pd.Timestamp(t).year,
                         "season": g.loc[idx, "season"] if "season" in g.columns else panel.loc[idx, "season"],
                         "horizon": H, "realized_return": float(g.loc[idx, "realized_return"]),
                         "HRI": float(g.loc[idx, "HRI"]) if pd.notna(g.loc[idx, "HRI"]) else np.nan})
    d = pd.DataFrame(rows)
    out = []
    for (pol, year), g in d.groupby(["policy", "year"]):
        m = _metrics(g["realized_return"]); out.append({"policy": pol, "dim": "year", "value": year, **m})
    for (pol, season), g in d.groupby(["policy", "season"]):
        m = _metrics(g["realized_return"]); out.append({"policy": pol, "dim": "season", "value": season, **m})
    return pd.DataFrame(out)


# ---------------------------------------------------------------- 组合
def portfolio(panel: pd.DataFrame, topk=3) -> pd.DataFrame:
    rows = []
    for t, g in panel.groupby("date"):
        if len(g) < topk:
            continue
        sc = strategy_scores(g)
        order = sc["s_balanced_fix"].sort_values(ascending=False)
        top = g.loc[order.index[:topk]]
        single = g.loc[order.index[0]]
        weights = pd.Series(1.0 / topk, index=top["crop"])
        hhi = float((weights ** 2).sum())
        rows.append({"date": str(pd.Timestamp(t).date()),
                     "single_return": float(single["realized_return"]),
                     "portfolio_return": float((top["realized_return"] * (1.0 / topk)).sum()),
                     "portfolio_downside": float(top["realized_return"].min()),
                     "hhi": hhi, "n_crops": len(top)})
    d = pd.DataFrame(rows)
    out = pd.DataFrame([{
        "single_mean": d["single_return"].mean(), "portfolio_mean": d["portfolio_return"].mean(),
        "single_downside": d["single_return"][d["single_return"] < 0].mean() if (d["single_return"] < 0).any() else 0,
        "portfolio_worst_mean": d["portfolio_downside"].mean(),
        "single_worst": d["single_return"].min(), "portfolio_worst": d["portfolio_downside"].min(),
        "mean_HHI": d["hhi"].mean(), "n_cutoffs": len(d)}])
    return out


# ---------------------------------------------------------------- 压力测试（利润情景）
def stress(price_shocks=(-0.10, -0.20, -0.30), yield_shocks=(-0.10, -0.20),
           cost_shocks=(0.10, 0.20)) -> pd.DataFrame:
    """情景利润（明确假设 area=60mu, cost/yield 参考口径），产出 base/mild/severe。"""
    from decision_engine.final.score import cost_reference_table
    # 参考价格（元/kg）用沈阳 10 蔬菜近期均价
    dp = daily_prices("沈阳")
    recent = dp[dp["date"] >= dp["date"].max() - pd.Timedelta(days=30)].groupby("crop")["price_per_kg"].mean()
    ct = cost_reference_table()
    AREA = 60.0
    YIELD = 3500.0  # kg/mu 情景假设（蔬菜设施，标注为假设）
    rows = []
    for crop, price in recent.items():
        sub = ct[ct["crop_standard"].astype(str).str.contains(crop, na=False)]
        cost = float(sub["cost_per_mu_ref"].dropna().median()) if len(sub) and sub["cost_per_mu_ref"].notna().any() else np.nan
        if not np.isfinite(cost):
            continue
        scenarios = {"base": (1.0, 1.0, 1.0)}
        for i, ps in enumerate(price_shocks):
            scenarios[f"price{int(ps*100)}"] = (1 + ps, 1.0, 1.0)
        for i, ys in enumerate(yield_shocks):
            scenarios[f"yield{int(ys*100)}"] = (1.0, 1 + ys, 1.0)
        for i, cs in enumerate(cost_shocks):
            scenarios[f"cost+{int(cs*100)}"] = (1.0, 1.0, 1 + cs)
        # 合理组合
        scenarios["severe_combo"] = (0.8, 0.85, 1.2)
        scenarios["mild_combo"] = (0.9, 0.95, 1.1)
        for sc, (pf, yf, cf) in scenarios.items():
            rev = AREA * (YIELD * yf) * (price * pf)
            cost_tot = AREA * (cost * cf)
            rows.append({"crop": crop, "scenario": sc, "price": price, "cost_per_mu": cost,
                         "revenue": rev, "cost": cost_tot, "profit": rev - cost_tot,
                         "roi": (rev - cost_tot) / cost_tot if cost_tot else np.nan,
                         "assumption": "area=60mu, yield=3500kg/mu(假设), cost=参考口径"})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 反事实 / Minimax Regret
def minimax_regret(bt: pd.DataFrame) -> pd.DataFrame:
    piv = bt.pivot_table(index="date", columns="strategy", values="realized_return")
    regret = piv.max(axis=1).values[:, None] - piv.values
    reg = pd.DataFrame(regret, index=piv.index, columns=piv.columns)
    out = pd.DataFrame({"strategy": reg.columns,
                        "mean_regret": reg.mean().values,
                        "worst_regret": reg.max().values,
                        "p95_regret": reg.quantile(0.95).values}).sort_values("worst_regret")
    return out.reset_index(drop=True)


def run() -> Dict[str, object]:
    ensure_dir(REPORTS_DIR / "tables")
    panel = build_panel()
    # 附 season
    panel["month"] = pd.to_datetime(panel["date"]).dt.month
    panel["season"] = panel["month"].map({12: "winter", 1: "winter", 2: "winter", 3: "spring",
                                          4: "spring", 5: "spring", 6: "summer", 7: "summer",
                                          8: "summer", 9: "autumn", 10: "autumn", 11: "autumn"})
    ab = ablation(panel); ab.to_csv(REPORTS_DIR / "tables" / "ablation.csv", index=False, encoding="utf-8-sig")
    rb = robustness(panel); rb.to_csv(REPORTS_DIR / "tables" / "robustness.csv", index=False, encoding="utf-8-sig")
    pf = portfolio(panel); pf.to_csv(REPORTS_DIR / "tables" / "portfolio.csv", index=False, encoding="utf-8-sig")
    st = stress(); st.to_csv(REPORTS_DIR / "tables" / "stress_scenarios.csv", index=False, encoding="utf-8-sig")
    bt = pd.read_parquet(FINAL_EVAL_DIR / "strategy_backtest.parquet")
    mm = minimax_regret(bt); mm.to_csv(REPORTS_DIR / "tables" / "minimax_regret.csv", index=False, encoding="utf-8-sig")
    wa = weather_ablation()
    return {"ablation_rows": len(ab), "robustness_rows": len(rb),
            "weather_ablation_models": int(len(wa)), "ts": now_stamp()}


if __name__ == "__main__":
    print(run())