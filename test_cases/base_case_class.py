import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
import time
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.mysql.sql_class import DatabaseManager
from src.test_result.result import TestResult


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

    def ask_question(self,question, timeout=90):
        try:
            if self.driver is None:
                error_info = "self.driver is None"
                self.test_log.log_error(error_info)
                raise ValueError(error_info)
            # 输入问题
            question_input = self.driver.find_element(By.ID, "chat-input")
            question_input.send_keys(question)
            time.sleep(10)  # 等待输入完成
            # 点击发送按钮
            button = self.driver.find_element(By.CLASS_NAME, "f6d670")
            button.click()

            time.sleep(30)  # 等待答案

            # # 动态等待答案生成
            # try:
            #     # 等待直到新的回答出现
            #     WebDriverWait(self.driver, timeout).until(
            #         lambda driver: len(driver.find_elements(By.CLASS_NAME, "ds-markdown--block")) > 0
            #     )
            #     # 等待回答完全输出完毕
            #     last_answer_length = 0
            #     start_time = time.time()
            #     while True:
            #         answers = self.driver.find_elements(By.CLASS_NAME, "ds-markdown--block")
            #         current_answer = answers[-1].text
            #
            #         # 如果回答长度不再变化，说明回答已完成
            #         if len(current_answer) == last_answer_length:
            #             break
            #         # 如果超时，抛出异常
            #         if time.time() - start_time > timeout:
            #             raise TimeoutError("Answer generation timed out")
            #
            #         last_answer_length = len(current_answer)
            #         time.sleep(1)  # 每隔1秒检查一次
            #
            # except Exception as e:
            #     self.test_log.log_error(f"Timeout while waiting for answer: {e}")
            #     raise TimeoutError("Answer generation timed out")

            # 获取最新的回答
            answers = self.driver.find_elements(By.CLASS_NAME, "ds-markdown--block")
            answer = answers[-1].text

            # 检查回答是否包含服务器繁忙等异常信息
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