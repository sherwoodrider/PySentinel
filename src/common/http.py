"""带连接池 / 重试 / 超时的 HTTP 客户端基类。

原有实现直接用 ``requests.request(...)`` 裸调用，每条请求都重新握手，
且**没有 timeout** —— 服务端一旦挂起会永久阻塞整个测试会话。

本实现：
* 按线程复用 ``Session``（``requests.Session`` 非线程安全 → 用 thread-local 隔离）；
* 底层 ``HTTPAdapter`` 带连接池 + ``urllib3.Retry`` 指数退避；
* 强制超时，避免无限等待；
* 内置轻量指标，便于定位慢请求。
"""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class HttpMetrics:
    """极简请求指标，线程安全。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.request_count = 0
        self.retry_count = 0
        self.failure_count = 0
        self.total_seconds = 0.0

    def record(self, seconds: float, ok: bool) -> None:
        with self._lock:
            self.request_count += 1
            self.total_seconds += seconds
            if not ok:
                self.failure_count += 1

    def as_dict(self) -> Dict[str, Any]:
        with self._lock:
            avg = self.total_seconds / self.request_count if self.request_count else 0.0
            return {
                "requests": self.request_count,
                "failures": self.failure_count,
                "total_seconds": round(self.total_seconds, 3),
                "avg_seconds": round(avg, 3),
            }


class HttpClient:
    """可复用的 HTTP 客户端。

    :param timeout: ``(connect, read)`` 秒；必须为有限值
    :param max_retries: 连接/读错误与幂等状态码的最大重试次数
    :param pool_connections: 连接池中保持的 host 数
    :param pool_maxsize: 单 host 最大连接数，建议 >= 并发 worker 数
    :param backoff_factor: 指数退避基数
    """

    def __init__(
        self,
        timeout: Tuple[float, float] = (5.0, 60.0),
        max_retries: int = 3,
        pool_connections: int = 10,
        pool_maxsize: int = 20,
        backoff_factor: float = 0.5,
        retry_status: Tuple[int, ...] = (408, 429, 500, 502, 503, 504),
    ) -> None:
        self.timeout = timeout
        self.max_retries = max_retries
        self.metrics = HttpMetrics()
        self._local = threading.local()

        self._retry = Retry(
            total=max_retries,
            connect=max_retries,
            read=max_retries,
            status=max_retries,
            backoff_factor=backoff_factor,
            status_forcelist=list(retry_status),
            allowed_methods=frozenset(["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]),
            raise_on_status=False,
            respect_retry_after_header=True,
        )
        self._adapter = HTTPAdapter(
            pool_connections=pool_connections,
            pool_maxsize=pool_maxsize,
            max_retries=self._retry,
        )

    # ------------------------------------------------------------------ #
    @property
    def session(self) -> requests.Session:
        """当前线程专属 Session，首次访问时创建并挂载连接池。"""
        session = getattr(self._local, "session", None)
        if session is None:
            session = requests.Session()
            session.mount("https://", self._adapter)
            session.mount("http://", self._adapter)
            self._local.session = session
        return session

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        data: Optional[Any] = None,
        timeout: Optional[Tuple[float, float]] = None,
    ) -> requests.Response:
        started = time.perf_counter()
        try:
            response = self.session.request(
                method,
                url,
                headers=headers,
                json=json_body,
                data=data,
                timeout=timeout or self.timeout,
            )
            response.raise_for_status()
            return response
        finally:
            self.metrics.record(time.perf_counter() - started, True)

    def close(self) -> None:
        """关闭当前线程的 Session。"""
        session = getattr(self._local, "session", None)
        if session is not None:
            session.close()
            self._local.session = None

    def __enter__(self) -> "HttpClient":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()
