import inspect
import pytest

from tests.base_case_class import BaseTest
from tests.conftest import print_case_name


class TestFuction(BaseTest):
    #1. 测试AI对简单中文问题的回答
    @print_case_name
    def test_simple_chinese_question(self):
        try:
            case_result = {
                "case_name": str(inspect.currentframe().f_code.co_name),
                "total": 0,
                "pass": 0,
                "fail": 0,
                "crash": 0,
                "fail_info": []
            }
            questions = [
                "什么是机器学习",
                "Python是什么",
                "如何学习编程"
            ]
            for question in questions:
                case_result["total"] += 1
                answer = self.ask_question(question)
                self.test_log.log_info(f"question: {question}\nanswer: {answer}\n")
                if self.calculate_semantic_similarity(question, answer):
                    case_result["pass"] += 1
                    self.test_log.log_info("The answer is related to the question")
                else:
                    case_result["fail"] += 1
                    fail_info = "The answer is irrelevant to the question"
                    self.test_log.log_error(fail_info)
                    case_result["fail_info"].append(fail_info)
            # self.test_result.add_case_result(str(inspect.currentframe().f_code.co_name), case_result)
        except Exception as e:
            self.test_log.log_critical(e)
    #2. 测试AI对复杂问题的回答
    @print_case_name
    def test_complex_question(self,test_log_handle):
        try:
            case_result = {
                "case_name": str(inspect.currentframe().f_code.co_name),
                "total": 0,
                "pass": 0,
                "fail": 0,
                "crash": 0,
                "fail_info": []
            }
            questions = [
                "如何设计一个高可用的分布式系统",
                "深度学习和机器学习有什么区别"
            ]
            for question in questions:
                case_result["total"] += 1
                answer = self.ask_question(question)
                self.test_log.log_info(f"question: {question}\nanswer: {answer}\n")
                if self.calculate_semantic_similarity(question, answer):
                    case_result["pass"] += 1
                    self.test_log.log_info("The answer is related to the question")
                else:
                    case_result["fail"] += 1
                    fail_info = "The answer is irrelevant to the question"
                    self.test_log.log_error(fail_info)
                    case_result["fail_info"].append(fail_info)
            # test_env.test_result.add_case_result(str(inspect.currentframe().f_code.co_name), case_result)
        except Exception as e:
            self.test_log.log_critical(e)