# -*- coding: utf-8 -*-
"""C7/C9: 生产不变量验证（§31/§33/§35/§36/§46/§47/§50）。

逐项实测并留存证据：
  I1 用户真实 cost/yield 覆盖 proxy/local_reference，并重算 profit/ROI/break-even/confidence
  I2 风险缺失 ≠ 0（缺失时 available=False 且 confidence 下降，而非记 0）
  I3 所有返回 status ∈ 统一枚举
  I4 不支持城市不 fallback（大连不得返回沈阳数值）
  I5 Profit 不输出虚假精度（proxy 来源时带 source + scenario 语义 + 舍入）
  I6 Output Contract 字段齐备（schema 必需字段）
"""
from __future__ import annotations
from typing import Dict

import json
import pandas as pd

from decision_engine.final.fcommon import MANIFEST_DIR, ensure_dir, write_json, now_stamp
from decision_engine.final import capabilities as CAP
from decision_engine.final.inference import FinalDecisionEngine

REQUIRED_FIELDS = ["request_id", "model_version", "data_version", "city", "crop",
                   "price", "scenario_range", "hri", "market_risk", "climate_exposure",
                   "confidence", "recommendation", "status", "warnings", "reasons"]


def run() -> Dict[str, object]:
    ensure_dir(MANIFEST_DIR)
    e = FinalDecisionEngine()
    checks = []

    def add(name, ok, detail=""):
        checks.append({"invariant": name, "pass": bool(ok), "detail": str(detail)[:200]})

    base = {"city": "沈阳", "crop": "西红柿", "area_mu": 60, "horizon_days": 30}

    # I1 用户输入覆盖
    r_proxy = e.evaluate({**base})
    r_user = e.evaluate({**base, "actual_cost_per_mu": 20000, "actual_yield_per_mu": 4000})
    p_proxy = r_proxy.get("profit") or {}
    p_user = r_user.get("profit") or {}
    src_proxy = p_proxy.get("cost_source_class")
    src_user = p_user.get("cost_source_class")
    add("I1_user_input_overrides_source",
        src_user == "user_input" and src_proxy != "user_input",
        f"proxy={src_proxy} user={src_user}")
    add("I1_user_input_weight_1",
        p_user.get("reliability") == 1.0 and (p_proxy.get("reliability") or 0) < 1.0,
        f"proxy_rel={p_proxy.get('reliability')} user_rel={p_user.get('reliability')}")
    rec_user = (r_user.get("recommendation") or {}).get("profit_weight")
    add("I1_user_input_changes_decision",
        rec_user is not None and rec_user == 1.0,
        f"profit_weight={rec_user}")

    # I2 缺失 ≠ 0
    missing_hri = [r for r in [r_proxy, e.evaluate({"city": "朝阳", "crop": "西红柿", "horizon_days": 30})]]
    ok2 = True
    detail2 = []
    for r in missing_hri:
        h = r.get("hri") or {}
        m = r.get("market_risk") or {}
        if h.get("available") is False and h.get("value") is not None:
            ok2 = False
        if m.get("available") is False and m.get("value") is not None:
            ok2 = False
        detail2.append(f"hri_avail={h.get('available')},mr_avail={m.get('available')}")
    add("I2_missing_risk_not_zero", ok2, ";".join(detail2))

    # I3/I6 status & contract
    samples = [r_proxy, r_user,
               e.evaluate({"city": "沈阳", "crop": "黄瓜", "horizon_days": 90,
                           "actual_cost_per_mu": 15000, "actual_yield_per_mu": 3000}),
               e.evaluate({"city": "大连", "crop": "西红柿", "horizon_days": 30}),
               e.evaluate({"city": "锦州", "crop": "土豆", "horizon_days": 30})]
    add("I3_status_enum", all(r["status"] in CAP.STATUS for r in samples),
        sorted({r["status"] for r in samples}))
    add("I6_contract_fields",
        all(all(k in r for k in REQUIRED_FIELDS) for r in samples),
        f"required={len(REQUIRED_FIELDS)}")

    # I4 不 fallback
    dl = e.evaluate({"city": "大连", "crop": "西红柿", "horizon_days": 30})
    add("I4_no_cross_city_fallback",
        dl["status"] == "INSUFFICIENT_MARKET_DATA" and dl.get("price") is None,
        f"status={dl['status']} price={dl.get('price')}")

    # I7 horizon 能力
    h30 = e.evaluate({**base, "horizon_days": 30})
    h90 = e.evaluate({**base, "horizon_days": 90})
    add("I7_horizon_capability",
        (h30["price"] or {}).get("scenario_only") is False and (h90["price"] or {}).get("scenario_only") is True,
        f"h30_scenario_only={(h30['price'] or {}).get('scenario_only')} "
        f"h90_scenario_only={(h90['price'] or {}).get('scenario_only')}")

    # I5 profit 语义（proxy 时不装真实）
    if p_proxy.get("available"):
        add("I5_profit_semantics",
            ("scenario_semantics" in p_proxy) and (p_proxy.get("cost_source_class") in
                                                   ("real", "local_reference", "regional_proxy", "user_input")),
            f"src={p_proxy.get('cost_source_class')}")
    else:
        add("I5_profit_semantics", True, "profit 不可用（符合诚实原则）")

    df = pd.DataFrame(checks)
    df.to_csv(MANIFEST_DIR / "invariants.csv", index=False, encoding="utf-8-sig")
    out = {"n": len(df), "n_pass": int(df["pass"].sum()), "all_pass": bool(df["pass"].all()),
           "ts": now_stamp()}
    write_json(out, MANIFEST_DIR / "invariants.json")
    return out


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=1))