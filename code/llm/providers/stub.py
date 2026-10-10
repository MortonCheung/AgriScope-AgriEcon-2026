# -*- coding: utf-8 -*-
"""Phase 10：确定性 stub provider（无 API key 时跑通 harness 用）。

**重要诚实性声明**：本 provider 不是 LLM，输出由程序确定性派生（种子 = context_hash），
因此**不能**用于评估「LLM 的预测能力」。所有使用它的结果必须标记
`is_real_llm=false` / `HARNESS_SMOKE_ONLY`，且报告中 LLM 数值增益一律写「未评估」。
"""
from __future__ import annotations
from typing import Any, Dict, Optional

from .base import LLMProvider


class StubProvider(LLMProvider):
    name = "stub"
    model = "deterministic-stub-v1"
    is_real_llm = False
    seed_supported = True

    def complete_json(self, *, task: str, system: str, user: str,
                      schema_name: str, context: Optional[Dict[str, Any]] = None,
                      temperature: float = 0.0, seed: Optional[int] = None) -> Dict[str, Any]:
        ctx = context or {}
        h = str(ctx.get("context_hash", ""))
        base = float(ctx.get("baseline_point") or ctx.get("current_price") or 1.0)
        horizon = int(ctx.get("horizon") or 90)
        # 确定性抖动 ∈ [-1.5%, +1.5%]，与 horizon 弱相关；不是预测，只为打通链路
        u = self._stable_unit(task, schema_name, h, str(horizon))
        jitter = (u - 0.5) * 0.03
        point = base * (1.0 + jitter)
        width = max(0.04, 0.03 + 0.0002 * horizon)
        direction = "up" if jitter > 1e-6 else ("down" if jitter < -1e-6 else "flat")

        if schema_name == "forecast":
            return {
                "forecast_horizon": horizon,
                "point_forecast": round(point, 4),
                "range_low": round(point * (1 - width), 4),
                "range_high": round(point * (1 + width), 4),
                "direction": direction,
                "confidence": round(0.5, 4),
                "drivers": ["stub_provider_no_real_llm"],
                "downside_risks": ["stub_output_not_a_forecast"],
                "assumptions": ["deterministic_stub"],
                "uncertainty": "stub：本输出无预测含义，仅用于链路验证",
                "unit": ctx.get("unit", "CNY/kg"),
                "method": ctx.get("method", task), "context_hash": h,
            }
        if schema_name == "residual":
            return {"adjustment_pct": round(jitter * 100, 4), "confidence": 0.5,
                    "method": ctx.get("method", task), "context_hash": h,
                    "rationale": "stub：确定性残差，无预测含义"}
        if schema_name == "critic":
            return {"warnings": ["stub_provider"], "recommendation_strength": "weak",
                    "method": ctx.get("method", task), "context_hash": h,
                    "model_disagreement": round(abs(jitter) * 100, 4)}
        return {}


__all__ = ["StubProvider"]
