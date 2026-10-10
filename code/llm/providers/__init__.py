# -*- coding: utf-8 -*-
"""LLM Provider 选择：有 key 用真实 provider，无 key 用确定性 stub（不阻塞）。"""
from __future__ import annotations
from typing import Optional

from .base import LLMProvider, LLMUnavailable
from .stub import StubProvider
from .openai_compat import OpenAICompatProvider


def get_provider(prefer_real: bool = True, **kwargs) -> LLMProvider:
    if prefer_real:
        p = OpenAICompatProvider(**kwargs)
        if p.is_available():
            return p
    return StubProvider()


__all__ = ["LLMProvider", "LLMUnavailable", "StubProvider", "OpenAICompatProvider", "get_provider"]