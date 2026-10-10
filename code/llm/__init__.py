# -*- coding: utf-8 -*-
"""AgriScope Long-Horizon LLM 层（Phase 9+）。

定位：**Long-Horizon Forecasting Expert**，不是 chatbot/RAG/文案生成器。
LLM 没有「天然预测权」——必须通过 OOT 回测、校准与消融才允许进入正式数值链路；
本层默认处于 `SCENARIO_ONLY` 实验状态。

结构：
  context/    ForecastContextPacket 构建 + determinism + 泄漏检测
  providers/  LLMProvider 抽象（OpenAI-compatible / stdlib HTTP）+ 确定性 stub
  schemas/    结构化输出 JSON Schema + 数字安全校验
  prompts/    版本化 prompt（forecast_v1 / residual_v1 / scenario_v1 / critic_v1）
  cache/      只缓存「通过校验」的结构化结果
  evaluation/ 评估 harness（blind / context / residual / hybrid）
"""
from __future__ import annotations

__all__ = []