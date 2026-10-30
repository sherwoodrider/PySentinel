"""轻量数据驱动加载器。

支持 JSON / YAML（YAML 需安装 pyyaml，缺失时自动降级，不会让收集失败）。
数据文件与用例代码解耦：**加用例 = 加数据**，不再需要复制粘贴测试函数。
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any, Dict, List, Optional

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def _load_raw(file_path: str) -> Dict[str, Any]:
    ext = os.path.splitext(file_path)[1].lower()
    with open(file_path, "r", encoding="utf-8") as fp:
        if ext == ".json":
            return json.load(fp)
        if ext in (".yaml", ".yml"):
            try:
                import yaml  # type: ignore
            except ImportError as exc:
                raise RuntimeError(f"读取 {file_path} 需要 pyyaml: pip install pyyaml") from exc
            return yaml.safe_load(fp)
    raise ValueError(f"不支持的数据文件格式: {file_path}")


@lru_cache(maxsize=32)
def load_dataset(name: str = "questions", cache_key: float = 0.0) -> List[Dict[str, Any]]:
    """读取数据集。

    :param cache_key: 传入文件 mtime 可在文件更新时自动失效缓存（热更新）
    """
    for ext in (".json", ".yaml", ".yml"):
        path = os.path.join(DATA_DIR, f"{name}{ext}")
        if os.path.exists(path):
            data = _load_raw(path)
            return data.get("cases", data if isinstance(data, list) else [])
    raise FileNotFoundError(f"数据集不存在: {os.path.join(DATA_DIR, name)}.json|.yaml")


def get_cases(
    name: str = "questions",
    category: Optional[str] = None,
    tag: Optional[str] = None,
    only_ids: bool = False,
) -> List[Dict[str, Any]]:
    """按条件筛选用例数据。"""
    base = os.path.join(DATA_DIR, name)
    candidates = [f"{base}{ext}" for ext in (".json", ".yaml", ".yml")]
    existing = next((p for p in candidates if os.path.exists(p)), None)
    cache_key = os.path.getmtime(existing) if existing else 0.0

    cases = load_dataset(name, cache_key)
    if category:
        cases = [c for c in cases if c.get("category") == category]
    if tag:
        cases = [c for c in cases if tag in (c.get("tags") or [])]
    return [c["id"] for c in cases] if only_ids else cases


def case_ids(cases: List[Dict[str, Any]]) -> List[str]:
    """生成稳定的用例 ID，便于 ``pytest --collect-only`` 与重试定位。"""
    return [str(c.get("id") or c.get("question", "")[:24]) for c in cases]
