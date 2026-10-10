# -*- coding: utf-8 -*-
"""F9b: Profit Engine 完整化（§26）+ Decision Score 实际应用（§28）。

§26 要求：
  Revenue = Area × Yield × Price
  Cost    = Area × Cost_per_mu
  Profit  = Revenue − Cost
  ROI / break-even price / break-even yield / break-even cost
  必须区分 real / local_reference / regional_proxy / user_input，不输出虚假精准值。

§28 要求：Decision Score 用 winsorize + 稳健百分位，避免量纲支配与极端值改变排序，
          并保留可解释性。
"""
from __future__ import annotations
from typing import Dict

import numpy as np
import pandas as pd

from decision_engine.final.fcommon import (SNAPSHOT_DIR, REPORTS_DIR, FINAL_EVAL_DIR,
                                           SHENYANG_CROPS, ensure_dir, write_json, now_stamp)
from decision_engine.final.risk import daily_prices
from decision_engine.final.score import cost_reference_table, decision_score

AREA_DEFAULT = 60.0
YIELD_ASSUMPTION = 3500.0     # kg/亩（情景假设，非真实观测）
SOURCE_ORDER = ["user_input", "LOCAL", "local_reference", "RESEARCH_REFERENCE",
                "REGIONAL_PROXY", "NEIGHBORING_PROXY", "SECTOR_PROXY", "NOT_FOUND"]


def _source_class(row) -> str:
    """把成本来源映射到 §26 的四类语义。"""
    c = str(row.get("cost_source_class", "")).upper()
    if c == "LOCAL":
        return "real"                    # 本地实测（沈阳成本调查）
    if c in ("RESEARCH_REFERENCE",):
        return "local_reference"
    if c in ("REGIONAL_PROXY", "NEIGHBORING_PROXY"):
        return "regional_proxy"
    if c in ("SECTOR_PROXY",):
        return "regional_proxy"
    if c == "USER_INPUT":
        return "user_input"
    if c == "NOT_FOUND":
        return "missing"
    return "local_reference"


def profit_engine_table(area: float = AREA_DEFAULT,
                        yield_per_mu: float = YIELD_ASSUMPTION) -> pd.DataFrame:
    """10 蔬菜的 Revenue/Cost/Profit/ROI/盈亏平衡 + 来源分级（明确假设标注）。"""
    ct = cost_reference_table()
    recent = (daily_prices("沈阳").pipe(lambda d: d[d["date"] >= d["date"].max() - pd.Timedelta(days=30)])
              .groupby("crop")["price_per_kg"].mean())
    rows = []
    for crop in SHENYANG_CROPS:
        price = float(recent.get(crop, np.nan))
        sub = ct[ct["crop_standard"].astype(str).str.contains(crop, na=False)]
        if len(sub) and sub["cost_per_mu_ref"].notna().any():
            cost = float(sub["cost_per_mu_ref"].dropna().median())
            src = _source_class(sub.sort_values("cost_reliability", ascending=False).iloc[0])
            n_ref = int(len(sub))
            cost_range = f"{sub['cost_per_mu_ref'].min():.0f}~{sub['cost_per_mu_ref'].max():.0f}"
        else:
            others = ct["cost_per_mu_ref"].dropna()
            cost = float(others.median()) if len(others) else np.nan
            src = "regional_proxy"
            n_ref = 0
            cost_range = "NA(sector median)"
        if not np.isfinite(price) or not np.isfinite(cost):
            rows.append({"crop": crop, "status": "missing_input"}); continue
        revenue = area * yield_per_mu * price
        total_cost = area * cost
        profit = revenue - total_cost
        roi = profit / total_cost if total_cost else np.nan
        be_price = cost / yield_per_mu
        be_yield = cost / price
        be_cost = price * yield_per_mu
        rows.append({
            "crop": crop, "status": "ok",
            "price_ref": round(price, 3), "cost_per_mu": round(cost, 1),
            "area_mu": area, "yield_per_mu": yield_per_mu,
            "revenue": round(revenue, 1), "cost_total": round(total_cost, 1),
            "profit": round(profit, 1), "roi": round(roi, 4),
            "break_even_price": round(be_price, 4),
            "break_even_yield": round(be_yield, 1),
            "break_even_cost": round(be_cost, 1),
            "cost_source_class": src, "cost_n_refs": n_ref, "cost_range": cost_range,
            "yield_source_class": "assumption",
            "note": "利润为情景值（面积/亩产为假设）；盈亏平衡三式与成本来源可追溯",
        })
    return pd.DataFrame(rows)


def apply_decision_score() -> pd.DataFrame:
    """把 §28 Decision Score 实际应用到 Final 候选池（代表 cut-off）。"""
    import glob
    files = sorted(glob.glob(str(REPORTS_DIR / "tables" / "final_candidates_*.csv")))
    if not files:
        return pd.DataFrame()
    out = []
    for f in files:
        d = pd.read_csv(f)
        if not len(d):
            continue
        cutoff = d["cutoff"].iloc[0]
        d = d.copy()
        d["profit"] = d["profit_baseline"]
        d["degree_downside"] = d["roi_pessimistic"]
        if "overall_confidence" not in d.columns:
            d["overall_confidence"] = d.get("confidence_score", 60.0)
        d["decision_score_final"] = decision_score(d)
        d = d.sort_values("decision_score_final", ascending=False)
        d["rank"] = range(1, len(d) + 1)
        out.append(d[["candidate_id", "cutoff", "crop", "horizon", "area_mu", "profit",
                      "degree_downside", "HRI", "market_risk", "climate_risk",
                      "overall_confidence", "utility_score", "decision_score_final", "rank"]])
    res = pd.concat(out, ignore_index=True)
    res.to_csv(REPORTS_DIR / "tables" / "decision_score_ranking.csv", index=False, encoding="utf-8-sig")
    return res


def run() -> Dict[str, object]:
    ensure_dir(REPORTS_DIR / "tables")
    pe = profit_engine_table()
    pe.to_csv(REPORTS_DIR / "tables" / "profit_engine.csv", index=False, encoding="utf-8-sig")
    ds = apply_decision_score()
    out = {
        "profit_crops_ok": int((pe["status"] == "ok").sum()),
        "source_class_distribution": pe["cost_source_class"].value_counts().to_dict() if "cost_source_class" in pe else {},
        "decision_score_rows": int(len(ds)),
        "top3_by_decision_score": ds.sort_values("decision_score_final", ascending=False)
                                   .head(3)[["crop", "horizon", "decision_score_final"]].to_dict("records")
                                   if len(ds) else [],
        "ts": now_stamp(),
    }
    write_json(out, REPORTS_DIR / "tables" / "profit_score_summary.json")
    return out


if __name__ == "__main__":
    print(run())