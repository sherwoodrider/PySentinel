import inspect
import pytest
from test_cases.base_case_class import BaseTest


class Test_Fuction(BaseTest):
    def test_simple_chinese_question(self):
        try:
            question =  "今天是星期几"
            answer = "星期六"
            answer = self.ask_question(question)
            test_result = "pass"
            crash = 0
            fail_info = ""
            self.test_log.log_info(f"question: {question}\nanswer: {answer}\n")
            if self.check_keyword_relevance(question, answer):
                test_result = "pass"
                self.test_log.log_info("The answer is related to the question")
            else:
                test_result = "fail"
                fail_info = "The answer is irrelevant to the question"
                self.test_log.log_error(fail_info)
            case_name = str(inspect.currentframe().f_code.co_name)
            self.db_manager.insert(case_name,question,answer,test_result,crash,fail_info)
            self.db_manager.query(case_name)
        except Exception as e:
            self.test_log.log_critical(e)
    @pytest.mark.skip()
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