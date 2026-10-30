"""失败根因 AI 分析装饰器。

改进点：
* 移除模块级 ``from conftest import config_file`` —— conftest 不是普通模块，
  在非 pytest 上下文（如脚本直接运行）导入会直接失败；
* AI 分析失败时**静默降级**，绝不掩盖原始异常（原实现若 LLM 报错会替换掉真实异常）；
* 复用共享 DeepSeekApi 实例，避免反复读配置/建连；
* 支持 ``functools.wraps`` 保留原函数元信息，便于 pytest 正确收集 parametrize 的用例名；
* 支持同步与异步函数。
"""
from __future__ import annotations

import functools
import inspect
import traceback
from typing import Callable

from src.config.settings import get_settings


def _ai_enabled() -> bool:
    return get_settings().getbool("deep_seek", "ai_analysis", fallback=True)


def _analyze(func: Callable, error: BaseException) -> str:
    """向 LLM 投递分析请求，任何异常都被吞掉并降级为提示文本。"""
    if not _ai_enabled():
        return "[AI 分析已关闭]"
    try:
        try:
            func_code = inspect.getsource(func)
        except OSError:
            func_code = "<源码不可用>"
        description = inspect.getdoc(func) or "无描述"
        error_info = traceback.format_exc()

        from src.deep_seek_api.api import DeepSeekApi

        api = DeepSeekApi.default()
        answer = api.ask_question(api.error_prompt(func_code, description, error_info))
        return answer or "[AI 分析未返回内容]"
    except Exception as exc:  # AI 分析是"锦上添花"，绝不能影响主流程
        return f"[AI 分析失败，请查看原始堆栈] {exc}"


def ai_analyze_error(func: Callable) -> Callable:
    """在被测函数抛异常后，自动用 LLM 分析根因并附加到异常消息里。"""

    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as exc:
                exc.ai_analysis = _analyze(func, exc)  # type: ignore[attr-defined]
                raise

        return async_wrapper

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            exc.ai_analysis = _analyze(func, exc)  # type: ignore[attr-defined]
            raise

    return wrapper


def analyze_exception(func: Callable, exc: BaseException) -> str:
    """非装饰器形式：pytest hook 里可直接调用（推荐在 makereport 阶段使用）。"""
    return _analyze(func, exc)


def extract_exception(exc: BaseException) -> dict:
    """把异常整理成结构化信息，便于写进报告 / 落库。"""
    tb = exc.__traceback__
    frames: list[dict] = []
    while tb is not None:
        frames.append(
            {
                "file": tb.tb_frame.f_code.co_filename,
                "line": tb.tb_lineno,
                "function": tb.tb_frame.f_code.co_name,
            }
        )
        tb = tb.tb_next
    return {
        "type": type(exc).__name__,
        "message": str(exc),
        "last_frame": frames[-1] if frames else None,
    }


__all__: list[str] = ["ai_analyze_error", "analyze_exception", "extract_exception"]
