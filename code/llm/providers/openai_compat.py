# -*- coding: utf-8 -*-
"""Phase 10：OpenAI-compatible provider（stdlib HTTP，不引入 openai SDK 强依赖）。

secret 只从环境变量读取（`.env` 由 `.gitignore` 忽略，只提交 `.env.example`）：
  AGRISCOPE_LLM_API_KEY / AGRISCOPE_LLM_BASE_URL / AGRISCOPE_LLM_MODEL
无 key 时 `is_available() == False`，RC2 实验报告 Secret 阻塞；不运行 stub 数值实验。
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from typing import Any, Dict, Optional

from .base import LLMProvider, LLMUnavailable


class OpenAICompatProvider(LLMProvider):
    name = "openai_compatible"
    is_real_llm = True
    seed_supported = True

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None,
                 model: Optional[str] = None, timeout: Optional[int] = None,
                 max_completion_tokens: int = 1200, max_attempts: Optional[int] = None):
        self.api_key = api_key or os.environ.get("AGRISCOPE_LLM_API_KEY") \
            or os.environ.get("OPENAI_API_KEY")
        self.base_url = (base_url or os.environ.get("AGRISCOPE_LLM_BASE_URL")
                         or "https://api.deepseek.com/v1").rstrip("/")
        self.model = model or os.environ.get("AGRISCOPE_LLM_MODEL") or "gpt-4o-mini"
        # 真实推理型模型单次延迟实测 35–70s；默认超时必须覆盖，否则会把正常响应判为失败。
        self.timeout = int(timeout or os.environ.get("AGRISCOPE_LLM_TIMEOUT") or 180)
        self.max_attempts = max(1, int(max_attempts or os.environ.get("AGRISCOPE_LLM_MAX_ATTEMPTS") or 3))
        raw_max = os.environ.get("AGRISCOPE_LLM_MAX_TOKENS")
        try:
            self.max_tokens = int(raw_max) if raw_max else None
        except ValueError:
            self.max_tokens = None
        # 仅用于 OpenAI 兼容性的回退字段；DeepSeek 不识别时由上层忽略。
        self.max_completion_tokens = max_completion_tokens
        self._metadata: Dict[str, Any] = {}
        self.seed_supported = os.environ.get("AGRISCOPE_LLM_SEED_SUPPORTED", "false").lower() == "true"
        parsed = urlsplit(self.base_url)
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("LLM base URL must be HTTPS without credentials, query or fragment")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def cache_config(self) -> Dict[str, Any]:
        return {**self.describe(), "base_url": self.base_url, "timeout": self.timeout,
                "response_format": "json_object", "max_tokens": self.max_tokens,
                "max_completion_tokens": self.max_completion_tokens,
                "max_attempts": self.max_attempts, "seed": self.seed_supported}

    def call_metadata(self) -> Dict[str, Any]:
        return dict(self._metadata)

    def complete_json(self, *, task: str, system: str, user: str,
                      schema_name: str, context: Optional[Dict[str, Any]] = None,
                      temperature: float = 0.0, seed: Optional[int] = None) -> Dict[str, Any]:
        self._metadata = {"token_usage": "unknown", "estimated_cost_usd": "unknown"}
        if not self.is_available():
            raise LLMUnavailable("no_api_key")
        last_error: Optional[LLMUnavailable] = None
        # 指数退避重试：仅瞬时故障（超时/5xx/429/网络层）可重试；4xx 与解析失败不重试。
        for attempt in range(1, self.max_attempts + 1):
            if attempt > 1:
                import time as _time  # noqa: PLC0415
                _time.sleep(min(2 ** (attempt - 1), 20))
            try:
                payload: Dict[str, Any] = {
                    "model": self.model,
                    "temperature": temperature,
                    "response_format": {"type": "json_object"},
                    "messages": [{"role": "system", "content": system},
                                 {"role": "user", "content": user}],
                }
                if self.max_tokens is not None:
                    payload["max_tokens"] = self.max_tokens
                if seed is not None and self.seed_supported:
                    payload["seed"] = seed
                req = urllib.request.Request(
                    f"{self.base_url}/chat/completions",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json",
                             "Authorization": f"Bearer {self.api_key}"},
                    method="POST")
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310
                    body = json.loads(resp.read().decode("utf-8"))
                choice = body["choices"][0]
                usage = body.get("usage")
                self._metadata = {"token_usage": usage if isinstance(usage, dict) else "unknown",
                                  "estimated_cost_usd": "unknown",
                                  "response_model": body.get("model", "unknown"),
                                  "response_id": body.get("id", "unknown"),
                                  "system_fingerprint": body.get("system_fingerprint", "unknown")}
                finish = choice.get("finish_reason")
                if choice["message"].get("refusal"):
                    raise LLMUnavailable("refused_response")
                if finish != "stop":
                    # 显式区分：截断（可能是 reasoning token 撑满上限）与意外终止，
                    # 便于上层选择「提高上限」还是「修 prompt」，而不是静默掩盖。
                    raise LLMUnavailable(f"incomplete_response_finish_reason:{finish}")
                content = choice["message"]["content"]
                return json.loads(content)
            except LLMUnavailable:
                raise
            except urllib.error.HTTPError as e:                                  # noqa: PERF203
                if e.code in (408, 429) or 500 <= e.code <= 599:
                    last_error = LLMUnavailable(f"http_{e.code}_attempt_{attempt}")
                    continue
                raise LLMUnavailable(f"http_{e.code}") from e
            except json.JSONDecodeError as e:                                    # noqa: PERF203
                raise LLMUnavailable("unparsable_response") from e
            except Exception as e:                                               # noqa: BLE001
                last_error = LLMUnavailable(f"transport_error:{type(e).__name__}_attempt_{attempt}")
                continue
        raise last_error or LLMUnavailable("retries_exhausted")


__all__ = ["OpenAICompatProvider"]
