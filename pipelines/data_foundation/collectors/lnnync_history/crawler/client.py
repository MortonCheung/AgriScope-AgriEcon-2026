"""HTTP 客户端：低频限速 + 指数退避重试 + 结构化日志。

设计原则（施工手册第八节）：
- 不对政府网站做高并发暴力抓取，默认请求间隔 0.5~1.5s
- 429/500/502/503/504 与连接超时使用 2/4/8s 指数退避，最多重试 3 次
- 单篇失败只记日志，绝不中断整体采集
"""
from __future__ import annotations

import random
import time
import threading
from dataclasses import dataclass
from typing import Iterable

import httpx
from tenacity import RetryCallState, retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from . import get_logger

log = get_logger("crawler.client")


class FetchError(Exception):
    """不可恢复的抓取失败（重试耗尽，或非重试类状态码如 404）。"""

    def __init__(self, url: str, status: int | None, message: str):
        super().__init__(message)
        self.url = url
        self.status = status
        self.message = message


class _Retryable(Exception):
    """内部信号：本次请求可重试。"""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


@dataclass
class FetchResult:
    url: str
    status: int
    text: str
    elapsed: float


class RateLimiter:
    """线程安全限速器：保证相邻两次请求间隔落在 [min, max] 区间内。"""

    def __init__(self, min_interval: float, max_interval: float):
        self.min_interval = min_interval
        self.max_interval = max_interval
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            target = random.uniform(self.min_interval, self.max_interval)
            if self._last and (now - self._last) < target:
                time.sleep(target - (now - self._last))
            self._last = time.monotonic()


def _log_before_retry(state: RetryCallState) -> None:
    log.warning("[RETRY %d] %s", state.attempt_number, state.outcome.exception())


class HttpClient:
    def __init__(
        self,
        min_interval: float = 0.5,
        max_interval: float = 1.5,
        connect_timeout: float = 10.0,
        read_timeout: float = 30.0,
        max_retries: int = 3,
        backoff: Iterable[float] = (2, 4, 8),
        retry_on_status: Iterable[int] = (429, 500, 502, 503, 504),
        user_agent: str = "liaoning-agri-data/1.0 (+research)",
        verify_ssl: bool = True,
    ):
        self.limiter = RateLimiter(min_interval, max_interval)
        self.max_retries = max_retries
        self.retry_on_status = set(retry_on_status)
        # wait_exponential(multiplier=2) 产生 2,4,8,8... 与手册要求一致
        multiplier = float(list(backoff)[0]) / 2.0 if backoff else 1.0
        self._retry = retry(
            retry=retry_if_exception_type(_Retryable),
            stop=stop_after_attempt(max_retries + 1),
            wait=wait_exponential(multiplier=multiplier, min=float(backoff[0]) if backoff else 2,
                                  max=float(backoff[-1]) if backoff else 8),
            before_sleep=_log_before_retry,
            reraise=True,
        )
        timeout = httpx.Timeout(connect=connect_timeout, read=read_timeout, write=10.0, pool=10.0)
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": user_agent, "Accept-Language": "zh-CN,zh;q=0.9"},
            verify=verify_ssl,
        )

    def get(self, url: str) -> FetchResult:
        """GET 一个 URL。成功返回 FetchResult；失败抛出 FetchError（由调用方决定如何处理）。"""
        started = time.monotonic()
        try:
            return self._get_with_retry(url, started)
        except _Retryable as exc:
            raise FetchError(url, exc.status, str(exc)) from exc

    def _get_with_retry(self, url: str, started: float) -> FetchResult:
        attempt = {"n": 0}

        @self._retry
        def _once() -> FetchResult:
            attempt["n"] += 1
            self.limiter.wait()
            try:
                resp = self._client.get(url)
            except httpx.TimeoutException as exc:
                raise _Retryable(f"timeout: {exc}")
            except httpx.HTTPError as exc:
                raise _Retryable(f"http-error: {exc}")

            if resp.status_code == 200:
                text = self._decode(resp)
                elapsed = time.monotonic() - started
                log.debug("[OK] HTTP 200 %s (%.2fs)", url, elapsed)
                return FetchResult(url, 200, text, elapsed)

            if resp.status_code in self.retry_on_status:
                raise _Retryable(f"HTTP {resp.status_code}", resp.status_code)

            log.warning("[FAIL] HTTP %s %s", resp.status_code, url)
            raise FetchError(url, resp.status_code, f"HTTP {resp.status_code}")

        return _once()

    @staticmethod
    def _decode(resp: httpx.Response) -> str:
        """站点响应头未声明 charset（实测 Content-Type: text/html），按 meta/内容探测解码。"""
        declared = (resp.encoding or "").lower()
        if declared and declared not in ("ascii", "utf-8"):
            try:
                return resp.content.decode(declared, errors="replace")
            except (LookupError, UnicodeDecodeError):
                pass
        for enc in ("utf-8", "gb18030", "gbk"):
            try:
                return resp.content.decode(enc)
            except UnicodeDecodeError:
                continue
        return resp.content.decode("utf-8", errors="replace")

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "HttpClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
