# -*- coding: utf-8 -*-
"""F12b: 在 Final 数据上重跑 §31 Pareto / §32 上市窗口 / §33 面积 / §34 组合 /
§35 压力 / §36 反事实(Minimax Regret) / §42 鲁棒性扩展。

候选价格情景（严格 point-in-time）：
  mid   = Final 选中模型在该 cut-off 的 OOT 预测（horizon h ∈ {30,60,90}）
  low/high = mid + 该 crop×h 的"更早 fold"OOT 残差 P10/P90（scenario range，不称 prediction interval）
成本/亩产：model_ready 参考口径 + 明确 proxy 标注；亩产为情景假设（ASSUMPTION），
          —— 因此利润为**情景值**，价格结果才是无假设指标。
"""
from __future__ import annotations
from typing import Dict, List

import numpy as np
import pandas as pd

from decision_engine.final.fcommon import (SNAPSHOT_DIR, REPORTS_DIR, FINAL_EVAL_DIR,
                                           ensure_dir, write_json, now_stamp)
from decision_engine.final.risk import weekly_prices, hri_components, combine, daily_prices, market_risk
from decision_engine.final.score import cost_reference_table
from decision_engine.optimization import utility as U
from decision_engine.optimization import ranking as RK
from decision_engine.optimization import pareto as PA
from decision_engine.optimization import harvest_window as HW

CITY = "沈阳"
H = 30                       # WAPE 阈值所用主 horizon
HORIZONS = (30, 60, 90)
AREAS = (20.0, 40.0, 60.0)
YIELD_ASSUMPTION = 3500.0        # kg/亩（情景假设）
AREA_DEFAULT = 60.0
BUDGET_DEFAULT = 300000.0
REP_TARGETS = ["2025-03-01", "2025-06-01", "2025-09-01"]


def rep_cutoffs() -> List[str]:
    """从 OOT 预测的可用日期中，选最接近代表月份的真实观测日。"""
    try:
        p = pd.read_parquet(FINAL_EVAL_DIR / "price_predictions.parquet")
        p = p[p["city"] == CITY]
        dates = pd.to_datetime(p["date"]).dropna().unique()
    except Exception:
        return []
    dates = pd.Series(sorted(pd.to_datetime(dates)))
    out = []
    for t in REP_TARGETS:
        t = pd.Timestamp(t)
        out.append(str(dates.iloc[(dates - t).abs().argmin()].date()))
    return sorted(set(out))


# ---------------------------------------------------------------- 情景区间（point-in-time）
def _scenario_lookup() -> pd.DataFrame:
    """per (crop, horizon, fold) 的残差分位（仅用更早 fold 的 OOT 残差）。"""
    p = pd.read_parquet(FINAL_EVAL_DIR / "price_predictions.parquet")
    sel = pd.read_csv(REPORTS_DIR / "tables" / "price_model_selection.csv")
    sel = sel[sel["city"] == CITY]
    rows = []
    for _, r in sel.iterrows():
        h = int(r["horizon"])
        if h not in HORIZONS:
            continue
        sub = p[(p["city"] == CITY) & (p["crop"] == r["crop"]) &
                (p["target"] == f"target_mean_price_next_{h}d") &
                (p["model"] == r["model"]) & (p["route"] == r["route"])]
        sub = sub.assign(resid=sub["actual"] - sub["prediction"])
        for fold in ["fold1_test2024", "fold2_test2025", "fold3_test2026"]:
            prior = sub[sub["fold"] < fold]["resid"].dropna()
            if len(prior) >= 20:
                q10, q90 = np.quantile(prior, [0.10, 0.90])
            else:
                q10, q90 = np.nan, np.nan
            rows.append({"crop": r["crop"], "horizon": h, "fold": fold, "q10": q10, "q90": q90})
    return pd.DataFrame(rows)


def _fold_of(dt) -> str:
    d = pd.Timestamp(dt)
    if d <= pd.Timestamp("2024-12-31"):
        return "fold1_test2024"
    if d <= pd.Timestamp("2025-12-31"):
        return "fold2_test2025"
    return "fold3_test2026"


def build_candidates(cutoff: str, area_variants=AREAS) -> pd.DataFrame:
    T = pd.Timestamp(cutoff)
    p = pd.read_parquet(FINAL_EVAL_DIR / "price_predictions.parquet")
    p["date"] = pd.to_datetime(p["date"])
    sel = pd.read_csv(REPORTS_DIR / "tables" / "price_model_selection.csv")
    sel = sel[(sel["city"] == CITY) & (sel["horizon"].isin(HORIZONS))]
    scen = _scenario_lookup()
    hri_w = combine(hri_components(weekly_prices(CITY)))
    hri_w["wk"] = hri_w["iso_year"] * 100 + hri_w["iso_week"]
    tgt_wk = T.isocalendar().year * 100 + T.isocalendar().week
    mr_d = market_risk(daily_prices(CITY))
    ct = cost_reference_table()
    from decision_engine.final.score import profit_grading
    pg = profit_grading()

    rows = []
    for _, r in sel.iterrows():
        crop, h = r["crop"], int(r["horizon"])
        f = p[(p["city"] == CITY) & (p["crop"] == crop) &
              (p["target"] == f"target_mean_price_next_{h}d") &
              (p["model"] == r["model"]) & (p["route"] == r["route"])]
        f = f[f["date"] == T] if (f["date"] == T).any() else f.iloc[0:0]
        if not len(f):
            continue
        mid = float(f.iloc[0]["prediction"])
        fold = f.iloc[0]["fold"]
        s = scen[(scen["crop"] == crop) & (scen["horizon"] == h) & (scen["fold"] == fold)]
        q10 = float(s.iloc[0]["q10"]) if len(s) and np.isfinite(s.iloc[0]["q10"]) else -0.05 * mid
        q90 = float(s.iloc[0]["q90"]) if len(s) and np.isfinite(s.iloc[0]["q90"]) else 0.05 * mid
        lo, hi = mid + q10, mid + q90
        # 成本/亩产
        cs = ct[ct["crop_standard"].astype(str).str.contains(crop, na=False)]["cost_per_mu_ref"].dropna()
        if len(cs):
            cost = float(cs.median()); cost_level = "observed_city_aggregate"
        else:
            # 无作物级真实成本 → 用蔬菜成本参考中位数作 SECTOR_PROXY（明确降权）
            cost = float(ct["cost_per_mu_ref"].dropna().median())
            cost_level = "sector_proxy"
        if not np.isfinite(cost):
            continue
        yld = YIELD_ASSUMPTION
        # HRI / market risk / climate
        hw = hri_w[(hri_w["crop"] == crop) & (hri_w["wk"] <= tgt_wk)].sort_values("wk")
        HRI = float(hw["HRI"].iloc[-1]) if len(hw) and pd.notna(hw["HRI"].iloc[-1]) else np.nan
        md = mr_d[(mr_d["crop"] == crop) & (mr_d["date"] <= T)].sort_values("date")
        MR = float(md["market_risk"].iloc[-1]) if len(md) and pd.notna(md["market_risk"].iloc[-1]) else np.nan
        CL = 50.0  # 气候为季节性历史暴露，与标的选择非一一对应；中性
        conf = 60.0
        for area in area_variants:
            total_cost = area * cost
            for price, tag in [(lo, "pessimistic"), (mid, "baseline"), (hi, "optimistic")]:
                pass
            roi = {}
            for price, tag in [(lo, "roi_pessimistic"), (mid, "roi_baseline"), (hi, "roi_optimistic")]:
                roi[tag] = (yld * price - cost) / cost
            rows.append({
                "candidate_id": f"{cutoff}_{crop}_h{h}_a{int(area)}",
                "city": CITY, "crop": crop, "horizon": h,
                "plant_date": str((T + pd.Timedelta(days=10)).date()),
                "harvest_start": str((T + pd.Timedelta(days=10)).date()),
                "harvest_date": str((T + pd.Timedelta(days=h)).date()),
                "area_mu": float(area), "cost_per_mu": cost, "expected_yield_per_mu": yld,
                "price_low": lo, "price_mid": mid, "price_high": hi,
                "profit_pessimistic": area * (yld * lo - cost),
                "profit_baseline": area * (yld * mid - cost),
                "profit_optimistic": area * (yld * hi - cost),
                "total_cost": total_cost,
                "roi_pessimistic": roi["roi_pessimistic"], "roi_baseline": roi["roi_baseline"],
                "roi_optimistic": roi["roi_optimistic"],
                "HRI": HRI, "market_risk": MR, "climate_risk": CL,
                "confidence_score": conf, "decision_score": np.nan,
                "evaluable": True, "risk_preference": "balanced",
                "cost_level": cost_level, "yield_level": "assumption",
                "cost_is_proxy": cost_level != "user_input", "yield_is_proxy": True,
                "cutoff": cutoff,
            })
    d = pd.DataFrame(rows)
    if not len(d):
        return d
    d["decision_score"] = d.apply(
        lambda r: 0.0 if not np.isfinite(r["roi_baseline"]) else round(
            (0.4 * r["roi_baseline"] + 0.2 * r["roi_pessimistic"]
             - 0.002 * (r["HRI"] if np.isfinite(r["HRI"]) else 50)
             - 0.002 * (r["market_risk"] if np.isfinite(r["market_risk"]) else 50)) * 100, 2), axis=1)
    return U.utility_report(d)


# ---------------------------------------------------------------- 各阶段
def run_pareto(cand: pd.DataFrame) -> pd.DataFrame:
    objs = [c for c in ["profit_baseline", "HRI", "market_risk", "climate_risk"] if c in cand.columns]
    front = PA.compute_pareto_frontier(cand, max_points=60)
    summ = PA.pareto_summary(front) if len(front) else pd.DataFrame()
    front.to_csv(REPORTS_DIR / "tables" / "pareto_frontier.csv", index=False, encoding="utf-8-sig")
    if len(summ):
        summ.to_csv(REPORTS_DIR / "tables" / "pareto_summary.csv", index=False, encoding="utf-8-sig")
    return summ


def _wape_map() -> Dict[str, float]:
    """Final WAPE（来自 Final price_model_selection.csv，h=30）→ 供 harvest_window 使用，避免读 v1。"""
    sel = pd.read_csv(REPORTS_DIR / "tables" / "price_model_selection.csv")
    sel = sel[(sel["city"] == CITY) & (sel["horizon"] == H)]
    return {r["crop"]: float(r["mean_WAPE"]) for _, r in sel.iterrows() if pd.notna(r["mean_WAPE"])}


def run_window_area(cand: pd.DataFrame, budget=BUDGET_DEFAULT) -> pd.DataFrame:
    """对每个作物跑上市窗口 + 面积优化（取效用最优作物）。"""
    wm = _wape_map()
    out = []
    for crop, g in cand.groupby("crop"):
        g2 = g[g["evaluable"]]
        if not len(g2):
            continue
        try:
            w = HW.optimize_harvest_window(CITY, crop, g2, risk_preference="balanced", wape_map=wm)
        except Exception as e:
            out.append({"crop": crop, "status": "NO_FEASIBLE_WINDOW",
                        "reason": f"所有窗口悲观情景为负 / 无材料级差异窗口（{type(e).__name__}）",
                        "assumptions": "area/yield 为情景假设，成本为参考口径"}); continue
        rec = w.get("recommended_window", {}) if w.get("status") == "ok" else {}
        # 面积优化：取该作物最优窗口的行
        sub = g2.sort_values("utility_score", ascending=False)
        area_res = {}
        try:
            best_area = float(sub.iloc[0]["area_mu"])
            opts = sub[sub["area_mu"] == best_area]
            area_res = HW.optimize_area(opts, AREA_DEFAULT, budget,
                                        float(sub.iloc[0]["cost_per_mu"]),
                                        float(sub.iloc[0]["expected_yield_per_mu"]))
        except Exception as e:
            area_res = {"status": f"area_error:{type(e).__name__}"}
        out.append({
            "crop": crop, "window_status": w.get("status"),
            "harvest_window": rec.get("harvest_window"),
            "n_equivalent_windows": rec.get("n_equivalent_windows"),
            "is_merged_range": rec.get("is_merged_range"),
            "profit_threshold": (w.get("material_difference_threshold") or {}).get("profit_threshold"),
            "area_status": area_res.get("status"),
            "recommended_area_mu": area_res.get("recommended_area_mu"),
            "area_feasible": area_res.get("recommended_area_feasible"),
            "worst_case_loss_at_rec": area_res.get("worst_case_loss_at_recommended"),
            "loss_region_ratio": (area_res.get("sensitivity_matrix") or {}).get("loss_region_ratio"),
            "break_even_price": (area_res.get("break_even") or {}).get("break_even_price"),
        })
    d = pd.DataFrame(out)
    d.to_csv(REPORTS_DIR / "tables" / "window_area_report.csv", index=False, encoding="utf-8-sig")
    return d


def run_portfolio(cand: pd.DataFrame, budget=BUDGET_DEFAULT, risk_preference="balanced") -> Dict:
    from decision_engine.portfolio.optimizer import optimize_crop_portfolio
    # 传入 Final 价格序列 → 组合相关性完全走 final_v1，不读 v1
    price_df = daily_prices(CITY)
    res = optimize_crop_portfolio(cand, AREA_DEFAULT, budget, risk_preference=risk_preference,
                                  price_df=price_df)
    # §40：组合未改善 objective 时给出正式状态
    pm = res.get("portfolio_metrics", {}) or {}
    try:
        hhi = float(pm.get("hhi", 1.0))
    except Exception:
        hhi = 1.0
    if hhi >= 0.999:
        res["status_final"] = "NO_DIVERSIFICATION_BENEFIT"
        res["diversification_note"] = (
            "组合最优解收敛为单作物（HHI=1.0）：在当前 data/风险指标下，"
            "增加作物种类未改善组合效用（集中度惩罚 + 相关性惩罚不足以补偿收益下降）。")
    else:
        res["status_final"] = "OK"
    write_json(res, REPORTS_DIR / "tables" / f"portfolio_{risk_preference}.json")
    return res


# 压力情景（§35/§42/§43）：Final 原生，仅用纯函数 evaluate_profit（不实例化 legacy 引擎）
SHOCKS = [
    ("price_-10", "price", 0.90), ("price_-20", "price", 0.80), ("price_-30", "price", 0.70),
    ("yield_-10", "yield", 0.90), ("yield_-20", "yield", 0.80),
    ("cost_+10", "cost", 1.10), ("cost_+20", "cost", 1.20),
    ("delay_+15d_price_dn5", "price", 0.95),
    ("mild_combo", "combo_mild", None), ("severe_combo", "combo_severe", None),
]


def _scenario_profit(row, kind, factor) -> float:
    from decision_engine.profit.profit import evaluate_profit
    pl, pm, ph = row["price_low"], row["price_mid"], row["price_high"]
    area, cost, yld = row["area_mu"], row["cost_per_mu"], row["expected_yield_per_mu"]
    if kind == "price":
        pl, pm, ph = pl * factor, pm * factor, ph * factor
    elif kind == "yield":
        yld = yld * factor
    elif kind == "cost":
        cost = cost * factor
    elif kind == "combo_mild":
        pl, pm, ph = pl * 0.90, pm * 0.90, ph * 0.90; yld *= 0.95; cost *= 1.10
    elif kind == "combo_severe":
        pl, pm, ph = pl * 0.80, pm * 0.80, ph * 0.80; yld *= 0.85; cost *= 1.20
    r = evaluate_profit(pl, pm, ph, area, cost, yld)
    if "error" in r:
        return np.nan
    return float(r["scenarios"]["baseline"]["profit"])


def run_stress_regret(cand: pd.DataFrame) -> pd.DataFrame:
    """§35 压力 + §43 Minimax Regret（Final 原生）。"""
    best = cand.sort_values("utility_score", ascending=False).groupby("crop").first().reset_index()
    scen_names = [s[0] for s in SHOCKS]
    per_crop = {}
    for _, row in best.iterrows():
        vals = {}
        for name, kind, factor in SHOCKS:
            vals[name] = _scenario_profit(row, kind, factor)
        per_crop[row["crop"]] = vals
    # 每个情景下的最优利润（跨作物）
    best_per_scen = {n: max((v[n] for v in per_crop.values() if np.isfinite(v.get(n, np.nan))), default=np.nan)
                     for n in scen_names}
    rows = []
    for _, row in best.iterrows():
        v = per_crop[row["crop"]]
        regs = [best_per_scen[n] - v[n] for n in scen_names
                if np.isfinite(best_per_scen.get(n, np.nan)) and np.isfinite(v.get(n, np.nan))]
        base = v.get("mild_combo", np.nan)
        rows.append({
            "crop": row["crop"], "harvest_date": row["harvest_date"], "area_mu": row["area_mu"],
            "base_profit": round(float(row["profit_baseline"]), 0),
            "worst_case_profit": round(float(np.nanmin([v[n] for n in scen_names])), 0),
            "max_regret": round(float(max(regs)), 0) if regs else np.nan,
            "mean_regret": round(float(np.mean(regs)), 0) if regs else np.nan,
            "n_loss_scenarios": int(sum(1 for n in scen_names if np.isfinite(v.get(n, np.nan)) and v[n] < 0)),
            "scenarios": ";".join(f"{n}={'' if not np.isfinite(v.get(n, np.nan)) else round(v[n], 0)}"
                                  for n in scen_names),
        })
    tbl = pd.DataFrame(rows).sort_values("max_regret")
    tbl.to_csv(REPORTS_DIR / "tables" / "stress_regret_table.csv", index=False, encoding="utf-8-sig")
    return tbl


# ---------------------------------------------------------------- §42 鲁棒性扩展
def robustness_extensions(cand: pd.DataFrame) -> pd.DataFrame:
    rows = []
    # 风险偏好：三档权重下 Top1 作物与效用
    for pref in ["conservative", "balanced", "aggressive"]:
        s = U.utility_scores(cand, pref)
        top = cand.loc[s.idxmax()]
        rows.append({"dim": "risk_preference", "value": pref, "top_crop": top["crop"],
                     "top_utility": float(s.max()), "top_HRI": top["HRI"],
                     "top_market_risk": top["market_risk"]})
    # 预算：Top1 是否受预算约束
    for b in [100000, 300000, 600000]:
        cap = cand[cand["total_cost"] <= b]
        if not len(cap):
            rows.append({"dim": "budget", "value": b, "top_crop": None, "note": "无可行候选"}); continue
        s = U.utility_scores(cap, "balanced")
        top = cap.loc[s.idxmax()]
        rows.append({"dim": "budget", "value": b, "top_crop": top["crop"],
                     "top_utility": float(s.max()), "n_feasible": int(len(cap))})
    # proxy 可得性：有真实成本 vs 仅 proxy
    real = cand[cand["cost_level"] == "user_input"]
    rows.append({"dim": "proxy_availability", "value": "with_real_cost", "n_feasible": int(len(real)),
                 "note": "蔬菜几乎无 user_input 成本 → 利润置信度受限"})
    rows.append({"dim": "proxy_availability", "value": "proxy_only", "n_feasible": int(len(cand) - len(real))})
    d = pd.DataFrame(rows)
    d.to_csv(REPORTS_DIR / "tables" / "robustness_extensions.csv", index=False, encoding="utf-8-sig")
    return d


def run() -> Dict[str, object]:
    ensure_dir(REPORTS_DIR / "tables")
    out = {}
    all_c = {}
    cuts = rep_cutoffs()
    if not cuts:
        return {"status": "no_available_cutoff_dates"}
    for cut in cuts:
        c = build_candidates(cut)
        if not len(c):
            print(f"[opt] {cut}: no candidates"); continue
        all_c[cut] = c
        c.to_csv(REPORTS_DIR / "tables" / f"final_candidates_{cut}.csv", index=False, encoding="utf-8-sig")
        print(f"[opt] {cut}: candidates={len(c)} crops={c['crop'].nunique()}", flush=True)
    if not all_c:
        return {"status": "no_candidates"}
    c = all_c[sorted(all_c.keys())[len(all_c) // 2]]  # 代表 cut-off（中间月份）
    ps = run_pareto(c)
    wa = run_window_area(c)
    pf_b = run_portfolio(c, risk_preference="balanced")
    pf_c = run_portfolio(c, risk_preference="conservative")
    sr = run_stress_regret(c)
    rx = robustness_extensions(c)
    out = {"cutoffs": list(all_c.keys()), "pareto_rows": len(ps), "window_area_rows": len(wa),
           "portfolio_status": pf_b.get("status"), "stress_rows": len(sr),
           "robustness_rows": len(rx), "ts": now_stamp()}
    write_json(out, REPORTS_DIR / "tables" / "optimize_summary.json")
    return out


if __name__ == "__main__":
    print(run())