"""用例基类。

原先是"孤儿基类"（没有任何用例继承），且内部存在 ``sleep(10)`` / ``sleep(30)``
两处硬等待 —— 单用例至少 40 秒纯空转；更糟的是异常分支**隐式 return None**，
会把真实的 error 伪装成 assert 失败，掩盖真正的故障原因。

现在：
* 等待改为轮询「回答文本连续稳定」，生成完毕即刻返回；
* 失败时抛出可读异常，而不是静默返回 ``None``；
* 判定复用 ``process 级单例``模型，不再每个实例重载一次 embedding 模型。
"""
from __future__ import annotations

import time

import pytest
from selenium.webdriver.common.by import By

ANSWER_BLOCK = "ds-markdown--block"
CHAT_INPUT_ID = "chat-input"
SERVER_BUSY_HINTS = ("服务器繁忙", "系统错误", "网络异常")


@pytest.mark.usefixtures("test_log_handle")
class BaseTest:
    @pytest.fixture(autouse=True)
    def init_fixture(self, test_log_handle):
        self.test_log = test_log_handle

    # ------------------------------------------------------------------ #
    def check_relevance(self, question: str, answer: str, strategy: str = "balanced") -> bool:
        """相关性判定；异常向上抛，不再返回 None 掩盖错误。"""
        from src.model.check_relevance import ResponseJudger

        result = ResponseJudger(question, answer, strategy=strategy).judge()
        self.test_log.log_info(f"[judge] {result!r}")
        return result.passed

    # ------------------------------------------------------------------ #
    def ask_question(self, question: str, timeout: int = 60, poll_interval: float = 0.5) -> str:
        """提问并返回回答。

        :raises RuntimeError: driver 未就绪或服务端返回异常内容（不再静默返回 None）
        """
        if getattr(self, "driver", None) is None:
            raise RuntimeError("driver 未初始化，请确认 BaseTest 已声明 driver fixture")

        question_input = self.driver.find_element(By.ID, CHAT_INPUT_ID)
        question_input.send_keys(question)
        # 等发送按钮可点击 —— 替代原来的 sleep(10)
        self._wait_until(
            lambda: len(
                self.driver.find_elements(By.XPATH, '//div[@role="button" and @aria-disabled="false"]')
            )
            > 0,
            timeout=15,
            interval=0.3,
            desc="等待发送按钮可用",
        )
        self.driver.find_element(By.XPATH, '//div[@role="button" and @aria-disabled="false"]').click()

        answer = self._wait_answer_stable(timeout=timeout, poll_interval=poll_interval)
        if any(hint in answer for hint in SERVER_BUSY_HINTS):
            raise RuntimeError(f"服务端返回异常内容: {answer[:120]}")
        return answer

    # ------------------------------------------------------------------ #
    def _wait_answer_stable(self, timeout: int = 60, poll_interval: float = 0.5, stable_rounds: int = 3) -> str:
        """轮询直到回答文本连续 N 次不变。替代原来的 sleep(30)。"""
        deadline = time.time() + timeout
        previous = ""
        stable = 0
        while time.time() < deadline:
            blocks = self.driver.find_elements(By.CLASS_NAME, ANSWER_BLOCK)
            current = blocks[-1].text if blocks else ""
            if current.strip():
                stable = stable + 1 if current == previous else 0
                previous = current
                if stable >= stable_rounds:
                    return current
            time.sleep(poll_interval)
        raise RuntimeError(f"等待回答超时（{timeout}s），最后一次内容: {previous[:120]}")

    @staticmethod
    def _wait_until(predicate, timeout: int = 15, interval: float = 0.3, desc: str = "") -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if predicate():
                    return
            except Exception:
                pass
            time.sleep(interval)
        raise RuntimeError(f"等待条件超时（{timeout}s）: {desc or 'unknown'}")
