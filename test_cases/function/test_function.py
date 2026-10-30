"""功能用例（数据驱动版）。

对比原版：原本 4 个用例是 4 个复制粘贴的函数，加一条语料就要再加一个函数。
现在全部由 ``test_cases/data/questions.json`` 驱动 —— **加用例只需加数据**。

同时：
* 断言信息带上判定原因与相似度，失败时一眼看出是"关键词不匹配"还是"LLM 判错"；
* 长度约束用例由 ``max_answer_chars`` 数据驱动，不再硬编码在代码里。
"""
from __future__ import annotations

import pytest

from test_cases.conftest import ask_question, ask_question_async, check_relevance
from test_cases.data_loader import case_ids, get_cases

_CASES = get_cases("questions")
_IDS = case_ids(_CASES)


@pytest.mark.ai
@pytest.mark.parametrize("case", _CASES, ids=_IDS)
def test_answer_relevance(browser_page, test_log_handle, case):
    """同一份问答在不同场景下的相关性判定。"""
    question = case["question"]
    answer = ask_question(browser_page, question)
    test_log_handle.log_info(f"question: {question}\nanswer: {answer}")

    assert answer and answer.strip(), "未取到回答内容"

    result = check_relevance(question, answer)
    assert result, f"相关性判定未通过 | question={question}"


@pytest.mark.ai
@pytest.mark.parametrize(
    "case",
    [c for c in _CASES if c.get("max_answer_chars")],
    ids=case_ids([c for c in _CASES if c.get("max_answer_chars")]),
)
def test_answer_length_limit(browser_page, test_log_handle, case):
    """验证"不超过 N 字"这类约束是否被遵守。"""
    question = case["question"]
    limit = case["max_answer_chars"]
    answer = ask_question(browser_page, question)
    test_log_handle.log_info(f"[length] question={question} limit={limit} actual={len(answer or '')}")

    assert answer, "未取到回答内容"
    assert len(answer.strip()) <= limit, f"回答超长：{len(answer.strip())} > {limit}"


@pytest.mark.asyncio
async def test_async_chat(logged_in_page, test_log_handle):
    """异步 Playwright 通道冒烟。"""
    question = "请用50个字解释人工智能"
    answer = await ask_question_async(logged_in_page, question)
    test_log_handle.log_info(f"question: {question}\nanswer: {answer}")
    assert answer and answer.strip()


def test_super_hero_questions(deep_seek_api, test_log_handle):
    """直连 API 的冒烟用例（不经过浏览器，最快）。"""
    question = "中国有超级英雄么，用不超过50个字回答我"
    answer = deep_seek_api.ask_question(question)
    test_log_handle.log_info(f"question: {question}\nanswer: {answer}")
    assert answer and answer.strip()
