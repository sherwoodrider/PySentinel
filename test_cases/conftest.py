"""用例层 fixtures —— 浏览器会话复用与显式等待。

性能对比（改造前 → 改造后）::

    改造前:  N 个用例 × (chromium 冷启动 3~8s + 完整登录 + 关闭浏览器)
    改造后:  1 次冷启动 + 1 次登录 + N × (new_context ≈ 0.1s)

关键手法：
* ``browser`` 提为 **session 级**，进程内只启动一次 Chromium；
* 登录态用 Playwright 原生 ``storage_state`` **落盘复用**，每个用例新建独立 context 注入，
  既免登录，又保证用例间 Cookie / localStorage 完全隔离；
* 所有 ``time.sleep`` 替换为**显式等待 / 稳定性轮询**；
* 清理掉未使用的 ``sklearn`` 等重量 import；``torch`` / ``transformers`` 也不再在收集期被间接拉取。
"""
from __future__ import annotations

import os
import time
from typing import Any, Dict, Generator

import pytest
import pytest_asyncio
from playwright.async_api import Page as AsyncPage
from playwright.async_api import async_playwright
from playwright.sync_api import Browser, Page, sync_playwright

from src.common.artifacts import register_page, unregister_page
from src.config.settings import PROJECT_ROOT, Settings, get_settings

# --------------------------------------------------------------------------- #
# 选择器常量集中管理：UI 变了只改这里，配合 UiChecker 可自动修复
# --------------------------------------------------------------------------- #
HOME_URL = "https://chat.deepseek.com"
LOGIN_URL = f"{HOME_URL}/sign_in"
CHAT_INPUT = "[role='textbox'][name='给 DeepSeek 发送消息']"
ANSWER_BLOCK = ".ds-markdown--block"
STABLE_ROUNDS = 3          # 文本连续 N 次不变即认定生成结束
POLL_INTERVAL = 400        # ms

_STATE_DIR = str(PROJECT_ROOT / ".cache" / "auth")
os.makedirs(_STATE_DIR, exist_ok=True)


# --------------------------------------------------------------------------- #
# 等待策略
# --------------------------------------------------------------------------- #
def _wait_for_answer(page: Page, timeout: float = 60_000) -> str:
    """等待回答流式输出结束。

    相比固定 ``sleep(30)``：快问答立刻返回，慢问答也不会中途截断。
    """
    page.wait_for_selector(ANSWER_BLOCK, timeout=timeout)
    deadline = time.time() + timeout / 1000
    stable = 0
    previous = ""
    while time.time() < deadline:
        current = page.locator(ANSWER_BLOCK).last.text_content() or ""
        stable = stable + 1 if current == previous else 0
        previous = current
        if stable >= STABLE_ROUNDS and current.strip():
            return current
        page.wait_for_timeout(POLL_INTERVAL)
    return previous


async def _wait_for_answer_async(page: AsyncPage, timeout: float = 60_000) -> str:
    await page.wait_for_selector(ANSWER_BLOCK, timeout=timeout)
    deadline = time.time() + timeout / 1000
    stable = 0
    previous = ""
    while time.time() < deadline:
        current = await page.locator(ANSWER_BLOCK).last.text_content() or ""
        stable = stable + 1 if current == previous else 0
        previous = current
        if stable >= STABLE_ROUNDS and current.strip():
            return current
        await page.wait_for_timeout(POLL_INTERVAL)
    return previous


# --------------------------------------------------------------------------- #
# 同步 Playwright
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def browser_context_args() -> Dict[str, Any]:
    return {"viewport": {"width": 1440, "height": 900}}


@pytest.fixture(scope="session")
def browser_launcher() -> Generator[Any, None, None]:
    """session 级 Playwright 运行时。"""
    with sync_playwright() as playwright:
        yield playwright


@pytest.fixture(scope="session")
def browser(browser_launcher, pytestconfig: pytest.Config) -> Generator[Browser, None, None]:
    """session 级浏览器 —— 整个会话只启动一次 Chromium。"""
    headed = getattr(pytestconfig, "pysentinel", {}).get("headed") or get_settings().getbool("runtime", "headed", False)
    instance = browser_launcher.chromium.launch(
        headless=not headed,
        args=["--disable-dev-shm-usage", "--no-sandbox", "--disable-gpu"],
    )
    yield instance
    instance.close()


def _login_and_dump_state(context_kwargs: Dict[str, Any], browser_page_factory, settings: Settings, path: str) -> None:
    """登录一次并把 ``storage_state`` 落盘给后续所有 context 复用。"""
    context = browser_page_factory(context_kwargs)
    try:
        page = context.new_page()
        page.goto(LOGIN_URL, wait_until="domcontentloaded")
        page.get_by_text("密码登录").click()
        page.get_by_role("textbox", name="请输入手机号/邮箱地址").fill(settings.get("deep_seek", "login_name"))
        page.get_by_role("textbox", name="请输入密码").fill(settings.get("deep_seek", "password"))
        page.get_by_role("button", name="登录").click()
        # 显式等待聊天输入框出现 —— 替代原先的 time.sleep(5)
        if page.locator(CHAT_INPUT).count() == 0:
            page.wait_for_selector(CHAT_INPUT, timeout=60_000)
        context.storage_state(path=path)
    finally:
        context.close()


@pytest.fixture(scope="session")
def storage_state(browser: Browser, browser_context_args: Dict[str, Any]) -> str:
    """登录态文件；未过期则直接复用，跳过整段登录流程。"""
    path = os.path.join(_STATE_DIR, "deepseek_state.json")
    ttl = float(get_settings().raw_get("runtime", "state_ttl", 7200.0))
    if os.path.exists(path) and (time.time() - os.path.getmtime(path)) < ttl:
        return path
    settings = get_settings()
    settings.require("deep_seek", "login_name", "password")
    _login_and_dump_state(browser_context_args, browser.new_context, settings, path)
    return path


@pytest.fixture
def browser_page(
    request: pytest.FixtureRequest,
    browser: Browser,
    storage_state: str,
    browser_context_args: Dict[str, Any],
) -> Generator[Page, None, None]:
    """function 级页面：**免冷启动、免登录**的全新上下文。

    隔离性由 ``new_context`` 保证（独立 Cookie / localStorage / 缓存），
    关闭的是 context 而非浏览器，开销可忽略。
    """
    unregister_page(request.node.nodeid)
    context = browser.new_context(storage_state=storage_state, **browser_context_args)
    page = context.new_page()
    page.set_default_timeout(30_000)
    # 注册给根 conftest，供失败时自动截图留证
    register_page(request.node.nodeid, page)
    try:
        yield page
    finally:
        unregister_page(request.node.nodeid)
        context.close()


# --------------------------------------------------------------------------- #
# 异步 Playwright
# --------------------------------------------------------------------------- #
@pytest_asyncio.fixture(scope="session")
async def async_browser(pytestconfig: pytest.Config):
    headed = getattr(pytestconfig, "pysentinel", {}).get("headed") or get_settings().getbool("runtime", "headed", False)
    async with async_playwright() as playwright:
        instance = await playwright.chromium.launch(
            headless=not headed,
            args=["--disable-dev-shm-usage", "--no-sandbox", "--disable-gpu"],
        )
        try:
            yield instance
        finally:
            await instance.close()


@pytest_asyncio.fixture(scope="session")
async def async_storage_state(async_browser, browser_context_args: Dict[str, Any]) -> str:
    path = os.path.join(_STATE_DIR, "deepseek_async_state.json")
    ttl = float(get_settings().raw_get("runtime", "state_ttl", 7200.0))
    if os.path.exists(path) and (time.time() - os.path.getmtime(path)) < ttl:
        return path

    settings = get_settings()
    settings.require("deep_seek", "login_name", "password")
    context = await async_browser.new_context(**browser_context_args)
    page = await context.new_page()
    try:
        await page.goto(LOGIN_URL, wait_until="domcontentloaded")
        await page.get_by_text("密码登录").click()
        await page.get_by_role("textbox", name="请输入手机号/邮箱地址").fill(settings.get("deep_seek", "login_name"))
        await page.get_by_role("textbox", name="请输入密码").fill(settings.get("deep_seek", "password"))
        await page.get_by_role("button", name="登录").click()
        await page.wait_for_selector(CHAT_INPUT, timeout=60_000)
        await context.storage_state(path=path)
    finally:
        await context.close()
    return path


@pytest_asyncio.fixture
async def logged_in_page(
    request: pytest.FixtureRequest,
    async_browser,
    async_storage_state: str,
    browser_context_args: Dict[str, Any],
):
    context = await async_browser.new_context(storage_state=async_storage_state, **browser_context_args)
    page = await context.new_page()
    page.set_default_timeout(30_000)
    register_page(request.node.nodeid, page)
    try:
        yield page
    finally:
        unregister_page(request.node.nodeid)
        await context.close()


# --------------------------------------------------------------------------- #
# Selenium（保留原 driver，改为模块级 + 显式等待）
# --------------------------------------------------------------------------- #
def login(driver, test_log_handle, settings) -> None:
    """Selenium 登录流程：所有 sleep 换成条件等待。"""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    try:
        wait = WebDriverWait(driver, 20)
        driver.get(LOGIN_URL)
        wait.until(EC.element_to_be_clickable((By.XPATH, "//div[text()='密码登录']"))).click()
        username = wait.until(
            EC.presence_of_element_located((By.XPATH, "//input[@placeholder='请输入手机号/邮箱地址']"))
        )
        username.send_keys(settings.get("deep_seek", "login_name"))
        driver.find_element(By.XPATH, "//input[@placeholder='请输入密码']").send_keys(
            settings.get("deep_seek", "password")
        )
        driver.find_element(By.XPATH, "//div[text()='登录']").click()
        wait.until(EC.presence_of_element_located((By.ID, "chat-input")))
    except Exception as exc:
        test_log_handle.log_critical(f"[login] {exc}")


@pytest.fixture(scope="module")
def driver(test_log_handle, run_settings):
    """模块级 Selenium driver —— 同一模块内复用浏览器实例。"""
    from selenium import webdriver

    instance = None
    if not run_settings.has_section("deep_seek") or not all(
        run_settings.raw_get("deep_seek", k) for k in ("login_name", "password")
    ):
        pytest.fail("there is no DeepSeek info in config")
    try:
        instance = webdriver.Chrome()
        instance.set_page_load_timeout(60)
        instance.implicitly_wait(10)
        login(instance, test_log_handle, run_settings)
        yield instance
    except Exception as exc:
        test_log_handle.log_critical(f"WebDriver init or login fail: {exc}")
        pytest.fail(f"WebDriver init or login fail: {exc}")
    finally:
        if instance:
            instance.quit()


# --------------------------------------------------------------------------- #
# 业务辅助
# --------------------------------------------------------------------------- #
def _open_chat(page: Page) -> None:
    if page.locator(CHAT_INPUT).count() == 0:
        page.goto(HOME_URL, wait_until="domcontentloaded")
        page.wait_for_selector(CHAT_INPUT, timeout=30_000)


def ask_question(page: Page, question: str, timeout: float = 60_000) -> str:
    """提问并取回答。等待采用"文本稳定"判定，而非固定 sleep。"""
    _open_chat(page)
    input_box = page.locator(CHAT_INPUT).first
    input_box.click()
    input_box.fill(question)
    page.keyboard.press("Enter")
    return _wait_for_answer(page, timeout)


async def ask_question_async(page: AsyncPage, question: str, timeout: float = 60_000) -> str:
    if await page.locator(CHAT_INPUT).count() == 0:
        await page.goto(HOME_URL, wait_until="domcontentloaded")
        await page.wait_for_selector(CHAT_INPUT, timeout=30_000)
    input_box = page.locator(CHAT_INPUT).first
    await input_box.click()
    await input_box.fill(question)
    await page.keyboard.press("Enter")
    return await _wait_for_answer_async(page, timeout)


def check_relevance(question: str, answer: str, strategy: str = "balanced", detail: bool = False, **kwargs):
    """判定答案相关性。

    底层 embedding 模型是**进程级单例**，会话内最多加载一次；
    LLM 判定结果有持久化缓存；命中高/低相似度区间时**完全不调用 LLM**。

    :param detail: 为 ``True`` 时返回 :class:`JudgeResult`（含判定原因与相似度），
                   便于把失败原因直接写进断言信息。
    """
    from src.model.check_relevance import ResponseJudger

    result = ResponseJudger(question, answer, strategy=strategy, **kwargs).judge()
    return result if detail else result.passed
