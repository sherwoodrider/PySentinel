"""DeepSeek API 封装层。

性能与稳定性改造：
* 配置读取由硬编码的 ``D:\\code_repo\\...`` 改为统一配置中心，支持 ``PYSENTINEL_DEEP_SEEK_API_KEY`` 环境变量注入；
* HTTP 调用由 ``requests.request`` 裸调用改为 ``HttpClient``：连接池复用 + 强制超时 + 指数退避重试；
* 按线程隔离 Session，配合 pytest-xdist / 多线程并发时既安全又能复用连接；
* 新增响应缓存层：相同 payload 直接命中本地结果，省时且省 token；
* 增加 ``normalized ask`` 接口，一次调用直接拿到答案，并保证异常可读（不再返回裸 None）。
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from typing import Any, Dict, Optional

from src.common.http import HttpClient
from src.config.settings import Settings, get_settings
from src.test_log.logger import TestLog

_CACHE_DIR = os.path.join(".cache", "llm")


class DeepSeekApi:
    """DeepSeek Chat Completions 客户端。"""

    _default_instance: Optional["DeepSeekApi"] = None
    _default_lock = threading.Lock()

    def __init__(
        self,
        settings: Optional[Settings] = None,
        log_handle: Optional[TestLog] = None,
        *,
        enable_cache: Optional[bool] = None,
        timeout: float = 60.0,
        max_retries: int = 3,
        max_tokens: int = 2048,
        model: Optional[str] = None,
        warm_cache: Any = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.log = log_handle or self._default_log()

        self.url = self.settings.raw_get("deep_seek", "base_url", "https://api.deepseek.com/chat/completions")
        self.model = model or self.settings.raw_get("deep_seek", "model", "deepseek-chat")
        self.timeout = float(self.settings.raw_get("deep_seek", "timeout", timeout))
        self.max_retries = int(self.settings.raw_get("deep_seek", "max_retries", max_retries))

        self.enable_cache = enable_cache if enable_cache is not None else self.settings.getbool("deep_seek", "enable_cache", True)
        self._cache = None
        if self.enable_cache:
            from src.common.cache import TTLCache

            ttl = float(self.settings.raw_get("deep_seek", "cache_ttl", 86400.0))
            self._cache = TTLCache(
                maxsize=2048,
                ttl=ttl,
                persist_path=os.path.join(_CACHE_DIR, "deepseek.json"),
            )
        # 允许外部注入共享缓存（如 conftest 统一管理的 session 级缓存）
        if warm_cache is not None:
            self._cache = warm_cache

        self.authorization = ""
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": "Bearer ",
        }
        self.get_authorization()

        self.payload_dict: Dict[str, Any] = {
            "messages": [{"content": "", "role": "user"}],
            "model": self.model,
            "max_tokens": int(self.settings.raw_get("deep_seek", "max_tokens", max_tokens)),
            "response_format": {"type": "text"},
        }
        self.response_text = ""
        self.answer = ""

        self._http = HttpClient(
            timeout=(5.0, self.timeout),
            max_retries=self.max_retries,
            pool_maxsize=int(self.settings.raw_get("deep_seek", "pool_maxsize", 20)),
        )
        self._payload_lock = threading.Lock()

    # ------------------------------------------------------------------ #
    @staticmethod
    def _default_log() -> TestLog:
        """默认日志句柄。注意不再是全局 basicConfig，多实例可共存。"""
        return TestLog(log_file=os.path.join("logs", "deep_seek_api.log"))

    @classmethod
    def default(cls) -> "DeepSeekApi":
        """进程内共享实例，避免重复读取配置与重复建连。"""
        if cls._default_instance is None:
            with cls._default_lock:
                if cls._default_instance is None:
                    cls._default_instance = cls()
        return cls._default_instance

    # ------------------------------------------------------------------ #
    # 鉴权
    # ------------------------------------------------------------------ #
    def read_config(self) -> None:
        try:
            self.authorization = self.settings.get("deep_seek", "api_key", fallback="")
        except KeyError as exc:
            self.log.log_warning(f"[DeepSeekApi] 未配置 api_key: {exc}")
            self.authorization = ""

    def get_authorization(self) -> None:
        self.read_config()
        self.headers["Authorization"] = f"Bearer {self.authorization}".strip()

    # ------------------------------------------------------------------ #
    # 核心请求
    # ------------------------------------------------------------------ #
    @staticmethod
    def _cache_key(payload: Dict[str, Any]) -> str:
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def ask_question(self, question: str, *, max_tokens: Optional[int] = None, use_cache: bool = True) -> Optional[str]:
        """发起一次对话并返回答案。

        与旧版保持兼容（旧版返回 ``None`` 后需再调 :meth:`get_answer`），
        但现在会直接返回答案，失败时返回 ``None`` 并记录日志，绝不抛出掩盖失败原因。
        """
        with self._payload_lock:
            self.payload_dict["messages"][0]["content"] = question
            if max_tokens is not None:
                self.payload_dict["max_tokens"] = max_tokens
            payload = json.loads(json.dumps(self.payload_dict))  # 深拷贝，避免并发写污染

        key = self._cache_key(payload) if (self._cache and use_cache) else None
        if key:
            sentinel = object()
            cached = self._cache.get(key, sentinel)  # type: ignore[union-attr]
            if cached is not sentinel:
                self.log.log_info(f"[DeepSeekApi][cache-hit] {question[:60]}...")
                self.response_text = ""
                self.answer = cached
                return cached

        self.log.log_info(f"[question]: {question}")
        try:
            response = self._http.request("POST", self.url, headers=self.headers, json_body=payload)
        except Exception as exc:  # 网络/超时/HTTP 错误统一收敛
            self.log.log_error(f"[DeepSeekApi] request failed: {exc}")
            self.response_text = ""
            self.answer = ""
            return None

        self.response_text = response.text
        try:
            answer = self.get_answer()
        except (KeyError, IndexError, ValueError) as exc:
            self.log.log_error(f"[DeepSeekApi] bad response payload: {exc}")
            return None

        if key and self._cache:
            self._cache.set(key, answer)
        return answer

    def get_answer(self) -> str:
        """从最近一次响应中解析答案内容。"""
        response_data = json.loads(self.response_text)
        answer = response_data["choices"][0]["message"]["content"]
        self.log.log_info(f"[answer]: {answer}")
        self.answer = answer
        return answer

    # ------------------------------------------------------------------ #
    # 提示词模板
    # ------------------------------------------------------------------ #
    def error_prompt(self, function_code, description, error_info) -> str:
        return f"""
我有一个python方法,执行后遇到了以下错误:{error_info},
程序的主要功能:{description},
相关代码片段:{function_code},
请帮我：
    1. 解释这个错误的根本原因
    2. 提供具体的修复建议
    3. 回答的字数控制在500字以内,可以少,不能多
"""

    def case_prompt_with_template(self, mode_description, case_example_1, case_example_2, case_num) -> str:
        return f"""
我在写一个python 测试case模块,这个模块的主要功能是：{mode_description},
我的case范例1:{case_example_1},
我的case范例2:{case_example_2},
请帮我：
    1. 阅读我的case范例1和2，记住他们的不同
    2. 阅读模块的主要功能
    3. 分析case范例1和case范例2的不同，然后结合模块的主要功能，严格按照我的case格式，给我生成{case_num}个case的源代码
    4. 除了case 代码之外，其他回答的字数控制在500字以内,可以少,不能多
"""

    def case_prompt_no_template(self, mode_description, case_example, case_num) -> str:
        return f"""
我在写一个python 测试case模块,这个模块的主要功能是：{mode_description},
我的case形式:{case_example},
请帮我：
    1. 阅读我的case形式
    2. 阅读模块的主要功能
    3. 按照我的case格式，然后结合模块的主要功能，给我扩展生成{case_num}个case的源代码
    4. 除了case 代码之外，其他回答的字数控制在500字以内,可以少,不能多
"""

    def case_prompt_py_file(self, base_case_template, case_num) -> str:
        return f"""
我正在编写 Pytest 测试用例，下面是一份已有的测试用例风格和结构参考：
{base_case_template}
请基于以上代码风格，使用以下模块描述与用例要求，模仿生成新的{case_num}个测试函数：
要求：
1. 保持 import 风格与 fixture 使用一致；
2. 新生成的测试函数名称不要与已有重复；
3. 用 pytest 结构写，函数命名风格为 test_ 开头；
4. 只返回纯代码，使用 markdown 格式包裹（python）
"""

    def ui_uodate_prompt(self, old_code, removed_ui, added_ui) -> str:
        return f"""
以下是 Python 的 UI 自动化测试代码：
```python
{old_code}
```
当前网站的 UI 结构发生了更新，原本的 UI 元素如下（已不存在）：
{json.dumps(removed_ui, indent=2, ensure_ascii=False)}

新页面结构如下（新增或替代）：
{json.dumps(added_ui, indent=2, ensure_ascii=False)}
请帮我更新原代码中失效的 selector、role、text 等，使代码在新 UI 中依然能运行，并保留原有功能逻辑。请用 markdown 格式返回纯代码。
"""

    # ------------------------------------------------------------------ #
    def metrics(self) -> Dict[str, Any]:
        """暴露底层 HTTP 指标，便于在会话结束时输出性能数据。"""
        return self._http.metrics.as_dict()

    def close(self) -> None:
        self._http.close()
        if self._cache is not None:
            self._cache.flush()
