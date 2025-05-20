import re
import pytest
from playwright.async_api import async_playwright, Page

from test_cases.conftest import ask_question, check_relevance, ask_question_async


def test_math_question(browser_page,test_log_handle):
    input_box = browser_page.get_by_role("textbox", name="给 DeepSeek 发送消息")
    input_box.click()
    question = "求解方程x^2 - 4 = 0"
    answer = ask_question(browser_page, question)
    test_log_handle.log_info(f"question: {question}\nanswer: {answer}\n")
    result = check_relevance(question, answer)
    assert result == True

def test_simple_chinese_question(browser_page,test_log_handle):
    input_box = browser_page.get_by_role("textbox", name="给 DeepSeek 发送消息")
    input_box.click()
    question = "什么是机器学习,请用不多于500个字回答"
    answer = ask_question(browser_page, question)
    test_log_handle.log_info(f"question: {question}\nanswer: {answer}\n")
    result = check_relevance(question, answer)
    assert result == True

@pytest.mark.asyncio
async def test_new_with_deepseek(logged_in_page,test_log_handle):
    question = "请用50个字解释人工智能"
    answer  = await ask_question_async(logged_in_page, question)
    test_log_handle.log_info(f"question: {question}\nanswer: {answer}\n")