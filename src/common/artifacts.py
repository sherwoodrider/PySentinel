"""失败留证用的 page 注册表。

放在独立模块里，避免 ``conftest`` 之间通过 ``import conftest`` 互相引用
（这种做法依赖 pytest 的 sys.path 注入，在不同运行方式下并不稳定）。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

_active_pages: Dict[str, Any] = {}


def register_page(nodeid: str, page: Any) -> None:
    _active_pages[nodeid] = page


def unregister_page(nodeid: str) -> None:
    _active_pages.pop(nodeid, None)


def get_page(nodeid: str) -> Optional[Any]:
    return _active_pages.get(nodeid)


def clear() -> None:
    _active_pages.clear()
