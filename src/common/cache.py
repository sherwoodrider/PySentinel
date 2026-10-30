"""通用缓存组件。

用途：缓存昂贵的外部调用结果（尤其是 LLM 判定、HTTP 响应），
让"重复问同一个问题"从秒级降到微秒级，并直接省掉 token 费用。
"""
from __future__ import annotations

import atexit
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, Optional, Tuple


class TTLCache:
    """线程安全、支持 TTL + LRU + 可选磁盘持久化的缓存。

    :param maxsize: 最大条目数，超出按 LRU 淘汰
    :param ttl: 过期秒数，``None`` 表示永不过期
    :param persist_path: 落盘路径；跨进程（pytest-xdist 各 worker）复用同一文件
    :param autosave_every: 累积多少次写入后自动刷盘
    """

    def __init__(
        self,
        maxsize: int = 512,
        ttl: Optional[float] = 3600.0,
        persist_path: Optional[str] = None,
        autosave_every: int = 20,
    ) -> None:
        self.maxsize = maxsize
        self.ttl = ttl
        self.persist_path = Path(persist_path) if persist_path else None
        self.autosave_every = autosave_every

        self._lock = threading.RLock()
        self._data: Dict[str, Tuple[float, Any]] = {}
        self._hits = 0
        self._misses = 0
        self._dirty = 0

        self._load_from_disk()
        atexit.register(self.flush)

    # ------------------------------------------------------------------ #
    # 基础读写
    # ------------------------------------------------------------------ #
    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            item = self._data.get(key)
            if item is None:
                self._misses += 1
                return default
            expire_at, value = item
            if self.ttl is not None and expire_at < time.time():
                self._data.pop(key, None)
                self._misses += 1
                return default
            # 命中后移到末尾，维持 LRU 顺序
            self._data[key] = self._data.pop(key)
            self._hits += 1
            return value

    def set(self, key: str, value: Any) -> None:
        expire_at = time.time() + self.ttl if self.ttl is not None else float("inf")
        with self._lock:
            self._data.pop(key, None)
            self._data[key] = (expire_at, value)
            while len(self._data) > self.maxsize:
                self._data.pop(next(iter(self._data)))
            self._dirty += 1
            if self.persist_path and self._dirty >= self.autosave_every:
                self.flush()

    def __contains__(self, key: str) -> bool:
        sentinel = object()
        return self.get(key, sentinel) is not sentinel

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)

    def purge_expired(self) -> int:
        """清理已过期条目，返回清理数量。"""
        if self.ttl is None:
            return 0
        now = time.time()
        with self._lock:
            expired = [k for k, (expire_at, _) in self._data.items() if expire_at < now]
            for k in expired:
                self._data.pop(k, None)
            return len(expired)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def stats(self) -> Dict[str, int]:
        with self._lock:
            total = self._hits + self._misses
            return {
                "hits": self._hits,
                "misses": self._misses,
                "size": len(self._data),
                "hit_rate": int(self._hits * 100 / total) if total else 0,
            }

    # ------------------------------------------------------------------ #
    # 持久化
    # ------------------------------------------------------------------ #
    def flush(self) -> None:
        """写入磁盘。多进程并发时可能因同时写导致文件损坏，故做原子替换 + 静默降级。"""
        if not self.persist_path:
            return
        with self._lock:
            self._dirty = 0
            if self.ttl is not None:
                now = time.time()
                alive = {k: v for k, v in self._data.items() if v[0] >= now}
            else:
                alive = dict(self._data)
            payload = {"version": 1, "entries": {k: {"expire_at": v[0], "value": v[1]} for k, v in alive.items()}}
            try:
                self.persist_path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.persist_path.with_suffix(self.persist_path.suffix + ".tmp")
                with open(tmp, "w", encoding="utf-8") as fp:
                    json.dump(payload, fp, ensure_ascii=False)
                os.replace(tmp, self.persist_path)
            except (OSError, TypeError, ValueError):
                # 缓存不可写不应影响主流程
                pass

    def _load_from_disk(self) -> None:
        if not self.persist_path or not self.persist_path.exists():
            return
        try:
            with open(self.persist_path, "r", encoding="utf-8") as fp:
                payload = json.load(fp)
            now = time.time()
            for key, entry in payload.get("entries", {}).items():
                expire_at = entry.get("expire_at", float("inf"))
                if self.ttl is not None and expire_at < now:
                    continue
                self._data[key] = (expire_at, entry.get("value"))
        except (OSError, ValueError):
            # 文件损坏时丢弃重建，不阻塞测试
            pass


def memoize_with(cache: TTLCache, key_func: Optional[Callable[..., str]] = None) -> Callable:
    """装饰器：把函数结果接入 :class:`TTLCache`。

    典型用法::

        judge_cache = TTLCache(ttl=86400, persist_path=".cache/llm.json")

        @memoize_with(judge_cache)
        def ask_llm(question: str) -> str: ...
    """

    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            if key_func is not None:
                key = key_func(*args, **kwargs)
            else:
                key = repr((args, tuple(sorted(kwargs.items()))))
            sentinel = object()
            cached = cache.get(key, sentinel)
            if cached is not sentinel:
                return cached
            result = func(*args, **kwargs)
            cache.set(key, result)
            return result

        wrapper.__wrapped__ = func  # type: ignore[attr-defined]
        wrapper.cache = cache  # type: ignore[attr-defined]
        return wrapper

    return decorator


def iter_cache_keys(cache: TTLCache) -> Iterator[str]:  # pragma: no cover - 调试辅助
    yield from list(cache._data.keys())
