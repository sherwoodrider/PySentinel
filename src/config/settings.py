"""PySentinel 统一配置中心。

解决原有问题：
1. ``os.getcwd()`` 拼接路径 —— 换个目录执行就找不到配置；
2. ``D:\\code_repo\\...`` 硬编码 Windows 路径 —— 跨平台必然失败；
3. 每处都 new 一个 ``ConfigParser`` 重复读盘 —— 无谓 IO；
4. 缺少环境变量覆盖 —— CI / 多环境切换必须改文件。

设计：
* **进程级单例**：ini 只解析一次；
* **mtime 热更新**：配置文件被修改后自动重载，无需重启；
* **环境变量优先**：``PYSENTINEL_<SECTION>_<KEY>`` 覆盖任意项（含密钥，避免明文入库）；
* **类型化读取**：``get / getint / getfloat / getbool / getlist``，缺失时返回默认值而非抛裸异常。
"""
from __future__ import annotations

import configparser
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "src" / "config" / "test_config.ini"

ENV_PREFIX = "PYSENTINEL_"
_TRUE_SET = {"1", "true", "yes", "on", "y"}
_FALSE_SET = {"0", "false", "no", "off", "n"}

# 需要保密的 key 片段，打印时自动脱敏
_SENSITIVE_HINTS = ("password", "api_key", "secret", "token", "passwd")


class Settings:
    """线程安全的配置单例。"""

    _instance: Optional["Settings"] = None
    _class_lock = threading.Lock()

    def __new__(cls, config_path: Optional[str] = None) -> "Settings":
        if cls._instance is None:
            with cls._class_lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._bootstrap(config_path)
                    cls._instance = inst
        return cls._instance

    # ------------------------------------------------------------------ #
    # 初始化 / 加载
    # ------------------------------------------------------------------ #
    def _bootstrap(self, config_path: Optional[str]) -> None:
        self._lock = threading.RLock()
        path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        # 支持从命令行或 CI 指定外部配置文件位置
        path = Path(os.getenv(f"{ENV_PREFIX}CONFIG_FILE", path)).expanduser()
        self.config_path = path

        self.auto_reload = self._env_bool("AUTO_RELOAD", default=True)
        self.check_interval = 1.0  # mtime 检查节流，避免每条都 stat
        self._data: Dict[str, Dict[str, str]] = {}
        self._mtime: float = 0.0
        self._checked_at: float = 0.0
        self._loaded = False
        self._load()

    def _load(self) -> None:
        parser = configparser.ConfigParser()
        if self.config_path.exists():
            # 显式 utf-8-sig 兼容 Windows 记事本写入的 BOM 文件
            parser.read(self.config_path, encoding="utf-8-sig")
            self._mtime = self.config_path.stat().st_mtime
        self._data = {
            section: dict(parser.items(section)) for section in parser.sections()
        }
        self._loaded = True

    def _maybe_refresh(self) -> None:
        """按节流间隔检查文件变更，实现热更新。"""
        if not self.auto_reload or not self.config_path.exists():
            return
        now = time.time()
        if now - self._checked_at < self.check_interval:
            return
        self._checked_at = now
        with self._lock:
            try:
                mtime = self.config_path.stat().st_mtime
            except OSError:
                return
            if mtime != self._mtime:
                self._load()

    def reload(self) -> None:
        """强制重载配置。"""
        with self._lock:
            self._load()

    # ------------------------------------------------------------------ #
    # 环境变量
    # ------------------------------------------------------------------ #
    @staticmethod
    def _env_key(section: str, key: str) -> str:
        return f"{ENV_PREFIX}{section.upper()}_{key.upper()}"

    def _env(self, section: str, key: str) -> Optional[str]:
        val = os.getenv(self._env_key(section, key))
        return val if val not in (None, "") else None

    def _env_bool(self, key: str, default: bool) -> bool:
        raw = os.getenv(f"{ENV_PREFIX}{key}")
        if raw is None or raw == "":
            return default
        return raw.strip().lower() in _TRUE_SET

    # ------------------------------------------------------------------ #
    # 读取接口
    # ------------------------------------------------------------------ #
    def raw_get(self, section: str, key: str, fallback: Any = None) -> Any:
        """环境变量 > ini > fallback。"""
        self._maybe_refresh()
        env_val = self._env(section, key)
        if env_val is not None:
            return env_val
        with self._lock:
            return self._data.get(section, {}).get(key, fallback)

    def get(self, section: str, key: str, fallback: Any = None) -> str:
        value = self.raw_get(section, key, fallback)
        if value is None:
            raise KeyError(f"配置项缺失: [{section}] {key}（可用 {self._env_key(section, key)} 环境变量注入）")
        return str(value)

    def getint(self, section: str, key: str, fallback: int = 0) -> int:
        return int(float(self.raw_get(section, key, fallback)))

    def getfloat(self, section: str, key: str, fallback: float = 0.0) -> float:
        return float(self.raw_get(section, key, fallback))

    def getbool(self, section: str, key: str, fallback: bool = False) -> bool:
        value = self.raw_get(section, key, None)
        if value is None:
            return fallback
        if isinstance(value, bool):
            return value
        token = str(value).strip().lower()
        if token in _TRUE_SET:
            return True
        if token in _FALSE_SET:
            return False
        return fallback

    def getlist(self, section: str, key: str, fallback: Optional[List[str]] = None) -> List[str]:
        value = self.raw_get(section, key, None)
        if value is None:
            return list(fallback or [])
        return [item.strip() for item in str(value).split(",") if item.strip()]

    # ------------------------------------------------------------------ #
    # 便捷接口
    # ------------------------------------------------------------------ #
    def has_section(self, section: str) -> bool:
        self._maybe_refresh()
        with self._lock:
            return section in self._data

    def options(self, section: str) -> Dict[str, str]:
        self._maybe_refresh()
        with self._lock:
            return dict(self._data.get(section, {}))

    def sections(self) -> list:
        self._maybe_refresh()
        with self._lock:
            return list(self._data.keys())

    def getboolean(self, section: str, key: str, fallback: bool = False) -> bool:
        """``ConfigParser`` 风格别名，保证旧代码无需改动即可迁移。"""
        return self.getbool(section, key, fallback)

    def __getitem__(self, section: str) -> "SectionView":
        return SectionView(self, section)

    def require(self, section: str, *keys: str) -> None:
        """前置校验：缺项时快速失败并给出清晰提示，避免跑到一半才炸。"""
        missing = [k for k in keys if self.raw_get(section, k) is None]
        if missing:
            raise ValueError(f"配置段 [{section}] 缺少必要项: {', '.join(missing)}")

    def as_dict(self, mask: bool = True) -> Dict[str, Dict[str, str]]:
        """导出全部配置，`mask=True` 时对敏感项脱敏，便于安全地打印到日志。"""
        self._maybe_refresh()
        with self._lock:
            snapshot = {s: dict(v) for s, v in self._data.items()}
        if not mask:
            return snapshot
        for section, items in snapshot.items():
            for key, value in items.items():
                lower = key.lower()
                if any(hint in lower for hint in _SENSITIVE_HINTS):
                    items[key] = "***" if value else ""
        return snapshot

    # 兼容 dict 风格访问：`"deep_seek" in settings`
    def __contains__(self, section: object) -> bool:
        return isinstance(section, str) and self.has_section(section)

    def __repr__(self) -> str:
        return f"<Settings path={self.config_path} sections={sorted(self._data)}>"


class SectionView:
    """``settings["section"]`` 的只读视图，让旧代码的 dict 风格访问继续可用。"""

    __slots__ = ("_settings", "_section")

    def __init__(self, settings: "Settings", section: str) -> None:
        self._settings = settings
        self._section = section

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and self._settings.raw_get(self._section, key) is not None

    def __getitem__(self, key: str) -> str:
        return self._settings.get(self._section, key)

    def get(self, key: str, fallback: Any = None) -> Any:
        return self._settings.raw_get(self._section, key, fallback)

    def __iter__(self):
        return iter(self._settings.options(self._section))

    def __repr__(self) -> str:
        return f"<SectionView {self._section}>"


def get_settings(config_path: Optional[str] = None) -> Settings:
    """获取全局配置单例。"""
    return Settings(config_path)


settings = get_settings()
