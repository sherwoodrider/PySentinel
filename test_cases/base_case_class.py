import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
import time
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

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
            keywords = set(question.split())
            relevant = any(keyword in answer for keyword in keywords)
            return relevant
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


    def calculate_semantic_similarity(self, question, answer):
        try:
            # 使用TF-IDF计算语义相似度
            vectorizer = TfidfVectorizer()
            tfidf_matrix = vectorizer.fit_transform([question, answer])
            similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]

            # 设置相似度阈值
            if similarity > 0.5:  # 阈值可根据实际情况调整
                return True
            else:
                return False
        except Exception as e:
            print(e)
            self.test_log.log_critical(e)
            return False

    def check_robustness(self, question, answer):
        try:
            # 使用TF-IDF计算语义相似度
            vectorizer = TfidfVectorizer()
            tfidf_matrix = vectorizer.fit_transform([question, answer])
            similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]

            # 设置较低的相似度阈值以容忍噪声
            if similarity > 0.3:  # 阈值可根据实际情况调整
                return True
            else:
                return False
        except Exception as e:
            print(e)
            self.test_log.log_critical(e)
            return False

    def check_performance(self, response_time, resource_usage):
        try:
            # 定义性能阈值
            max_response_time = 5  # 最大响应时间（秒）
            max_memory_usage = 100 * 1024 * 1024  # 最大内存占用（100MB）

            if response_time <= max_response_time and resource_usage <= max_memory_usage:
                return True  # 性能达标
            else:
                return False  # 性能不达标
        except Exception as e:
            print(e)
            self.test_log.log_critical(e)
            return False