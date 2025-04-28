import re
import pytest
from playwright.async_api import async_playwright, Page

from test_cases.conftest import ask_question
def test_chat_with_deepseek(browser_page,test_log_handle):
    # page = browser_page
    input_box = browser_page.get_by_role("textbox", name="给 DeepSeek 发送消息")
    input_box.click()
    question = "如何筛选有用的信息,请用50个字回答"
    answer = ask_question(browser_page, question)
    test_log_handle.log_info(f"question: {question}\nanswer: {answer}\n")
