import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
import time
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.model.check_relevance import ResponseJudger
from src.mysql.sql_class import DatabaseManager
from src.test_result.result import TestResult
from selenium.webdriver.support import expected_conditions as EC

@pytest.mark.usefixtures("driver", "test_log_handle")
class BaseTest:
    @pytest.fixture(autouse=True)
    def init_fixture(self, driver,test_log_handle,data_base):
        self.driver = driver  # 将 driver 注入到类中
        self.test_log = test_log_handle
        self.db_manager = data_base

    def check_keyword_relevance(self, question, answer):
        try:
            rj = ResponseJudger(question,answer)
            result = rj.second_examine()
            return  result
        except Exception as e:
            print(e)
            self.test_log.log_critical(e)

    def ask_question(self,question, timeout=40):
        try:
            if self.driver is None:
                error_info = "self.driver is None"
                self.test_log.log_error(error_info)
                raise ValueError(error_info)
            question_input = self.driver.find_element(By.ID, "chat-input")
            question_input.send_keys(question)
            time.sleep(10)

            send_button = self.driver.find_element(By.XPATH, '//div[@role="button" and @aria-disabled="false"]')
            send_button.click()

            # regen_button_locator = (By.XPATH, '//rect[@id="重新生成"]')
            # WebDriverWait(self.driver, timeout).until(
            #     EC.presence_of_element_located(regen_button_locator)
            # )
            time.sleep(30)
            answers = self.driver.find_elements(By.CLASS_NAME, "ds-markdown--block")
            answer = answers[-1].text
            if "服务器繁忙" in answer or "系统错误" in answer:
                raise Exception(f"Server error or busy: {answer}")
            return answer  # 返回有效的回答
        except Exception as e:
            self.test_log.log_error(f"Attempt failed: {e}")

