# -*- coding: utf-8 -*-
"""Phase 10：LLMProvider 抽象（OpenAI-compatible，可切换模型）。

约定：provider 只负责「把 prompt 变成**结构化 JSON**」；数字安全与缓存校验由上层负责。
失败（超时/限流/5xx/解析失败）必须抛 `LLMUnavailable`，**不得**返回半成品。
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

import hashlib
import json


class LLMUnavailable(RuntimeError):
    """provider 不可用 / 调用失败 / 输出不可解析（上层据此降级为统计 fallback）。"""


class LLMProvider(ABC):
    name: str = "base"
    model: str = "unknown"
    is_real_llm: bool = False
    seed_supported: bool = False

    def cache_config(self) -> Dict[str, Any]:
        """Non-secret config affecting request behavior; override for provider adapters."""
        return self.describe()

    def call_metadata(self) -> Dict[str, Any]:
        return {"token_usage": "unknown", "estimated_cost_usd": "unknown"}

    @abstractmethod
    def complete_json(self, *, task: str, system: str, user: str,
                      schema_name: str, context: Optional[Dict[str, Any]] = None,
                      temperature: float = 0.0, seed: Optional[int] = None) -> Dict[str, Any]:
        """返回已解析的结构化 dict；失败抛 LLMUnavailable。"""

    def is_available(self) -> bool:
        return True

    def describe(self) -> Dict[str, Any]:
        return {"provider": self.name, "model": self.model,
                "is_real_llm": self.is_real_llm,
                "seed_supported": self.seed_supported}

    # 便于子类复用：稳定地从文本派生一个 [0,1) 的数（确定性，禁用内置 hash）
    @staticmethod
    def _stable_unit(*parts: str) -> float:
        h = hashlib.sha256(("|".join(parts)).encode("utf-8")).hexdigest()
        return int(h[:8], 16) / float(0xFFFFFFFF)


__all__ = ["LLMProvider", "LLMUnavailable"]
