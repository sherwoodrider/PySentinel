"""健壮性用例（数据驱动）。

原版只有一个硬编码的噪声问题；现在从数据集里取 ``category=robustness`` 的全部语料，
新增噪声场景只需在 JSON 里追加一条。
"""
from __future__ import annotations

import pytest

from test_cases.conftest import ask_question, check_relevance
from test_cases.data_loader import case_ids, get_cases

_ROBUST_CASES = get_cases("questions", category="robustness")


@pytest.mark.ai
@pytest.mark.flaky
@pytest.mark.parametrize("case", _ROBUST_CASES, ids=case_ids(_ROBUST_CASES))
def test_noise_robustness(browser_page, test_log_handle, case):
    """输入含噪声（错别字 / 特殊符号）时仍能给出相关回答。"""
    question = case["question"]
    answer = ask_question(browser_page, question)
    test_log_handle.log_info(f"question: {question}\nanswer: {answer}")

    assert answer and answer.strip(), "未取到回答内容"

    result = check_relevance(question, answer, detail=True)
    assert result, f"噪声鲁棒性判定未通过 | reason={result.reason} detail={result.detail}"
