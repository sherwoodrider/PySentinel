import pytest
import time

import pytest_asyncio
from playwright.async_api import async_playwright,Page
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from selenium.webdriver.support import expected_conditions as EC
import re
from playwright.sync_api import Playwright, sync_playwright,expect, Page
from typing import AsyncGenerator
def login(driver,test_log_handle,config_file):
    try:
        # 打开 DeepSeek 登录页面
        driver.get("https://chat.deepseek.com/sign_in")
        element = driver.find_element(By.XPATH, "//div[text()='密码登录']")
        element.click()
        time.sleep(5)
        # # 找到用户名和密码输入框（根据实际页面元素修改）
        username_input = driver.find_element(By.XPATH, "//input[@placeholder='请输入手机号/邮箱地址']")
        password_input = driver.find_element(By.XPATH, "//input[@placeholder='请输入密码']")
        # username_input.send_keys(config_file.get["deep_seek"]["login_name"])
        # password_input.send_keys(config_file["deep_seek"]["password"])
        username_input.send_keys(config_file.get("deep_seek","login_name"))
        password_input.send_keys(config_file.get("deep_seek","password"))
        # checkbox = driver.find_element(By.CLASS_NAME, "ds-checkbox")#勾选同意
        # checkbox.click()
        login_input = driver.find_element(By.XPATH, "//div[text()='登录']")  # 点击登录
        login_input.click()
        time.sleep(5)  # 等待登录完成
        # 等待登录完成
        # WebDriverWait(driver, 10).until(EC.url_contains("chat.deepseek.com"))
    except Exception as e:
        print(e)
        test_log_handle.log_critical(e)

@pytest.fixture(scope="module")
def driver(test_log_handle, config_file):
    driver = None
    try:
        if "deep_seek" not in config_file or not all(k in config_file["deep_seek"] for k in ["login_name", "password"]):
            pytest.fail("there is no DeepSeek info in config_file")
        driver = webdriver.Chrome()
        login(driver,test_log_handle, config_file)
        # 提供 driver 给测试使用
        yield driver
    except Exception as e:
        # 记录日志并标记测试失败
        test_log_handle.log_critical(f"WebDriver init or login fail: {e}")
        pytest.fail(f"WebDriver init or login fail: {e}")
    finally:
        # 确保 driver 被正确关闭
        if driver:
            driver.quit()

@pytest.fixture(scope="function")
def browser_page(config_file):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto("https://chat.deepseek.com/sign_in")
        page.get_by_text("密码登录").click()
        page.get_by_role("textbox", name="请输入手机号/邮箱地址").fill(config_file.get("deep_seek","login_name"))
        page.get_by_role("textbox", name="请输入密码").fill(config_file.get("deep_seek","password"))
        page.get_by_role("button", name="登录").click()
        # page.wait_for_selector("[role='textbox'][name='给 DeepSeek 发送消息']")
        yield page
        browser.close()

def ask_question(page: Page, question: str) -> str:
    input_box = page.get_by_role("textbox", name="给 DeepSeek 发送消息")
    input_box.click()
    input_box.fill(question)
    page.get_by_role("button").filter(has_text=re.compile(r"^$")).click()
    page.wait_for_selector(".ds-flex > .ds-flex > div")
    answer = page.locator(".ds-markdown--block").last.text_content()
    return answer
@pytest_asyncio.fixture(scope="function")
async def logged_in_page(config_file):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page()
        await page.goto("https://chat.deepseek.com/sign_in")
        await page.get_by_text("密码登录").click()
        await page.get_by_role("textbox", name="请输入手机号/邮箱地址").fill(config_file.get("deep_seek","login_name"))
        await page.get_by_role("textbox", name="请输入密码").fill(config_file.get("deep_seek","password"))
        await page.get_by_role("button", name="登录").click()
        # await page.wait_for_selector("给 DeepSeek 发送消息",timeout=5000)
        yield page
        await browser.close()

async def ask_question_async(page, question: str) -> str:
    input_box = page.get_by_role("textbox", name="给 DeepSeek 发送消息")
    await input_box.click()
    await input_box.fill(question)
    await page.get_by_role("button").filter(has_text=re.compile(r"^$")).click()
    await page.wait_for_selector(".ds-flex > .ds-flex > div")
    answer = await page.locator(".ds-markdown--block").last.text_content()
    return answer
