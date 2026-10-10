# -*- coding: utf-8 -*-
"""Phase 9 / §35 §36: 推荐解释器（确定性规则，非 LLM 生成）。

输出每个推荐方案的 reasons（带数字）、tradeoffs、risks、alternatives，
以及"为什么没有推荐另一个"的 comparison_reason。
"""
from __future__ import annotations
from typing import Dict, List, Optional

import numpy as np
import pandas as pd


def explain_plan(row: Dict, ctx: Optional[Dict] = None) -> Dict:
    """对单个方案生成结构化解释（全部由数值规则生成）。"""
    ctx = ctx or {}
    reasons, risks, tradeoffs = [], [], []
    r = row
    # 收益/价格
    reasons.append(f"上市窗口 {r.get('harvest_date')} 的历史同月价格 P50 = {r.get('price_mid'):.2f} 元/kg"
                   f"（P10–P90: {r.get('price_low'):.2f}–{r.get('price_high'):.2f}，情景口径）")
    be = r.get("break_even_price")
    if be:
        rel = (r["price_mid"] / be - 1) * 100
        reasons.append(f"盈亏平衡价 {be:.2f} 元/kg；P50 情景比盈亏平衡{'高' if rel>=0 else '低'} {abs(rel):.1f}%")
    reasons.append(f"基准情景净收益 {r.get('profit_baseline'):,.0f} 元（{r.get('area_mu')} 亩），"
                   f"悲观/乐观情景 {r.get('profit_pessimistic'):,.0f} / {r.get('profit_optimistic'):,.0f} 元")
    # 风险（客观量，不受偏好影响）
    hri, mr, cl = r.get("HRI"), r.get("market_risk"), r.get("climate_risk")
    if hri is not None:
        reasons.append(f"跟风风险 HRI={hri:.1f}（{r.get('HRI_level')}）")
    if mr is not None:
        reasons.append(f"市场风险={mr:.1f}（{r.get('market_risk_level')}）")
    if cl is not None:
        reasons.append(f"历史同期气候暴露={cl:.1f}（非天气预报）")
    reasons.append(f"模型置信度 {r.get('confidence_score'):.1f}（{r.get('confidence_grade')}）；"
                   f"决策评分 {r.get('decision_score'):.1f}（{r.get('decision_grade')}）")
    # 风险提示
    if hri is not None and hri >= 70:
        risks.append(f"HRI={hri:.1f} 处于高位：历史上该水平后 30–90 天价格回落概率明显更高（本项目回测结论）")
    if mr is not None and mr >= 70:
        risks.append(f"市场风险={mr:.1f} 偏高：波动/回撤与区间宽度处于历史高位")
    if cl is not None and cl >= 60:
        risks.append(f"气候暴露={cl:.1f} 偏高：历史同期极端天气概率较高（暴露≠减产）")
    if r.get("cost_is_proxy") or r.get("yield_is_proxy"):
        risks.append("成本/亩产来自参考值或 proxy（非用户实测），利润为参考口径")
    if (r.get("reference_warning") or ""):
        risks.append(str(r["reference_warning"])[:160])
    # tradeoffs（从效用驱动项生成）
    drivers = r.get("utility_drivers") or []
    for d in drivers:
        comp, contrib = d["component"], d["contribution"]
        tradeoffs.append(f"{comp} 贡献 {contrib:+.4f}（风险偏好={ctx.get('risk_preference','balanced')}）")
    return {"crop": r.get("crop"), "harvest_date": str(r.get("harvest_date")),
            "reasons": reasons, "risks": risks, "tradeoffs": tradeoffs}


def comparison_reason(recommended: Dict, alternative: Dict, preference: str = "balanced") -> str:
    """§36 "为什么没有推荐另一个"（对比式解释）。"""
    if not recommended or not alternative:
        return ""
    parts = []
    p_diff = (alternative.get("profit_baseline", 0) - recommended.get("profit_baseline", 0))
    if abs(p_diff) > 0:
        parts.append(f"预测收益：{alternative.get('crop')} {'高' if p_diff>0 else '低'} "
                     f"{abs(p_diff):,.0f} 元")
    d_diff = (alternative.get("profit_pessimistic", 0) - recommended.get("profit_pessimistic", 0))
    parts.append(f"下行情景：{alternative.get('crop')} {'好' if d_diff>0 else '差'} {abs(d_diff):,.0f} 元")
    for k, label in [("HRI", "跟风风险"), ("market_risk", "市场风险"), ("climate_risk", "气候暴露")]:
        a, b = alternative.get(k), recommended.get(k)
        if a is not None and b is not None:
            parts.append(f"{label}：{alternative.get('crop')} {a:.1f} vs {recommended.get('crop')} {b:.1f}")
    u_diff = (alternative.get("utility_score", 0) - recommended.get("utility_score", 0))
    conclusion = (f"在 {preference} 偏好下，综合效用 {recommended.get('crop')} "
                  f"{recommended.get('utility_score'):.4f} > {alternative.get('crop')} "
                  f"{alternative.get('utility_score'):.4f}（差 {abs(u_diff):.4f}）")
    return "；".join(parts) + "；" + conclusion


def plan_label_summary(labeled: Dict[str, Dict]) -> List[Dict]:
    """把 5 个标签整理为可读列表（允许同一方案对应多个标签）。"""
    out = []
    for label, row in labeled.items():
        if row:
            out.append({"label": label, "crop": row.get("crop"),
                        "harvest_date": str(row.get("harvest_date")),
                        "area_mu": row.get("area_mu"),
                        "profit_baseline": row.get("profit_baseline"),
                        "utility_score": row.get("utility_score")})
    return out