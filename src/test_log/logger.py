"""日志模块。

原有实现的问题：
* 每次实例化都调用 ``logging.basicConfig(force=True)`` —— 会**清空 root logger 的所有 handler**，
  导致先创建的日志文件被静默丢弃；多个实例互相踩踏，属于典型的全局副作用；
* logger 名直接用文件路径，重复创建同名 logger 时会叠加 handler，日志重复打印；
* 日志无大小上限，长期运行会把磁盘写满。

新实现：
* 具名 logger + handler 幂等绑定，天然支持多实例共存与 xdist 多进程隔离；
* ``RotatingFileHandler`` 自动切分，杜绝无限增长；
* 输出格式带进程/线程标识，方便并行排障；
* 零全局副作用（不再触碰 root logger 的 handler）。
"""
from __future__ import annotations

import logging
import os
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional, Union

DEFAULT_FORMAT = "%(asctime)s [%(levelname)s] [p%(process)d/t%(thread)d] %(name)s - %(message)s"

_registry_lock = threading.Lock()
# key: (logger_name, abs_log_file) -> 已绑定文件 handler，避免重复叠加
_bound: set = set()

_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "warn": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
}


def resolve_level(level: Union[int, str, None]) -> int:
    """把字符串级别名归一化为 ``logging`` 常量，便于用环境变量控制日志级别。"""
    if level is None:
        return logging.INFO
    if isinstance(level, int):
        return level
    return _LEVELS.get(str(level).strip().lower(), logging.INFO)


class TestLog:
    """轻量日志句柄，接口与原实现保持一致，内部改为具名 logger。"""

    def __init__(
        self,
        log_file: str = "main.log",
        level: Union[int, str, None] = logging.INFO,
        *,
        name: Optional[str] = None,
        console: bool = False,
        max_bytes: int = 20 * 1024 * 1024,
        backup_count: int = 5,
        fmt: str = DEFAULT_FORMAT,
    ) -> None:
        self.log_file = str(log_file)
        self.level = resolve_level(level)
        self.logger_name = name or f"pysentinel.{Path(self.log_file).stem}"
        self.logger = logging.getLogger(self.logger_name)
        self.logger.setLevel(self.level)
        # 禁止向 root 传播，避免重复输出 + 与其他实例互相干扰
        self.logger.propagate = False

        self._ensure_file_handler(max_bytes, backup_count, fmt)
        if console:
            self._ensure_console_handler(fmt)

    # ------------------------------------------------------------------ #
    def _ensure_file_handler(self, max_bytes: int, backup_count: int, fmt: str) -> None:
        abs_path = os.path.abspath(self.log_file)
        parent = os.path.dirname(abs_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        with _registry_lock:
            key = (self.logger_name, abs_path)
            if key in _bound:
                return
            handler = RotatingFileHandler(
                abs_path,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            handler.setLevel(self.level)
            handler.setFormatter(logging.Formatter(fmt))
            self.logger.addHandler(handler)
            _bound.add(key)

    def _ensure_console_handler(self, fmt: str) -> None:
        with _registry_lock:
            for h in self.logger.handlers:
                if getattr(h, "_pysentinel_console", False):
                    return
            handler = logging.StreamHandler()
            handler.setLevel(self.level)
            handler.setFormatter(logging.Formatter(fmt))
            handler._pysentinel_console = True  # type: ignore[attr-defined]
            self.logger.addHandler(handler)

    # ------------------------------------------------------------------ #
    # 兼容原接口
    # ------------------------------------------------------------------ #
    def log_debug(self, message) -> None:
        self.logger.debug(message)

    def log_info(self, message) -> None:
        self.logger.info(message)

    def log_warning(self, message) -> None:
        self.logger.warning(message)

    def log_error(self, message, exc_info=False) -> None:
        self.logger.error(message, exc_info=exc_info)

    def log_critical(self, message) -> None:
        self.logger.critical(message)

    # ------------------------------------------------------------------ #
    def set_level(self, level: Union[int, str]) -> None:
        """运行时动态调整级别，方便按阶段降噪。"""
        self.level = resolve_level(level)
        self.logger.setLevel(self.level)
        for handler in self.logger.handlers:
            handler.setLevel(self.level)

    def close(self) -> None:
        for handler in list(self.logger.handlers):
            self.logger.removeHandler(handler)
            try:
                handler.close()
            except Exception:  # pragma: no cover - 关闭失败无需中断
                pass

    # 允许 TestLog 实例直接当 logger 用：`log("msg")`
    __call__ = log_info
