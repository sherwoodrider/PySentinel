import configparser
import json
import logging

import requests
import os

from src.test_log.logger import TestLog


class DeepSeekApi():
    def __init__(self):
        self.test_log = TestLog(log_file="./deep_seek_api.log", level=logging.DEBUG)
        self.url = "https://api.deepseek.com/chat/completions"
        self.headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': 'Bearer'
        }
        self.authorization = ""
        self.get_authorization()
        self.payload_dict = {
                  "messages": [
                    {
                      "content": "",
                      "role": "user" }
                  ],
                  "model": "deepseek-chat",
                  "max_tokens": 2048,
                  "response_format": {
                    "type": "text"},
            }
        self.payload = json.dumps(self.payload_dict)
        self.response_text = ""
        self.answer = ""

    def read_config(self):
        try:
            # current_folder_path = os.getcwd()
            # config_file_path = os.path.join(current_folder_path, "../config/test_config.ini")
            config_file_path = "../config/test_config.ini"
            config = configparser.ConfigParser()
            config.read(config_file_path)
            self.authorization =  config.get("deep_seek","api_key")
        except Exception as e:
            print(e)
    def get_authorization(self):
        self.read_config()
        # authorization =  config_file.get("deep_seek","api_key")
        self.headers['Authorization'] = 'Bearer '+ self.authorization
    def ask_question(self,question):
        self.payload_dict["messages"][0]["content"] = question
        self.payload =  json.dumps(self.payload_dict)
        self.test_log.log_info("[question]: " + str(question))
        response = requests.request("POST", self.url, headers=self.headers, data=self.payload)
        # print(response.text)
        self.response_text =  response.text

    def error_prompt(self,function_code,description,error_info):
        prompt_info = f'''
        我有一个python方法,执行后遇到了以下错误:{error_info},
        程序的主要功能:{description},
        相关代码片段:{function_code},
        请帮我：
            1. 解释这个错误的根本原因
            2. 提供具体的修复建议
            3. 回答的字数控制在500字以内,可以少,不能多

'''
        return prompt_info

    def case_prompt_with_template(self,mode_description,case_example_1,case_example_2,case_num):
        prompt_info = f'''
                我在写一个python 测试case模块,这个模块的主要功能是：{mode_description},
                我的case范例1:{case_example_1},
                我的case范例2:{case_example_2},
                请帮我：
                    1. 阅读我的case范例1和2，记住他们的不同
                    2. 阅读模块的主要功能
                    3. 分析case范例1和case范例2的不同，然后结合模块的主要功能，严格按照我的case格式，给我生成{case_num}个case的源代码
                    4. 除了case 代码之外，其他回答的字数控制在500字以内,可以少,不能多

        '''
        return prompt_info

    def case_prompt_no_template(self,mode_description,case_example,case_num):
        prompt_info = f'''
                我在写一个python 测试case模块,这个模块的主要功能是：{mode_description},
                我的case形式:{case_example},
                请帮我：
                    1. 阅读我的case形式
                    2. 阅读模块的主要功能
                    3. 按照我的case格式，然后结合模块的主要功能，给我扩展生成{case_num}个case的源代码
                    4. 除了case 代码之外，其他回答的字数控制在500字以内,可以少,不能多
        '''
        return prompt_info


    def case_prompt_py_file(self,base_case_template,case_num):
        prompt_info = f"""
    我正在编写 Pytest 测试用例，下面是一份已有的测试用例风格和结构参考：
    {base_case_template}
    请基于以上代码风格，使用以下模块描述与用例要求，模仿生成新的{case_num}个测试函数：
    要求：
    1. 保持 import 风格与 fixture 使用一致；
    2. 新生成的测试函数名称不要与已有重复；
    3. 用 pytest 结构写，函数命名风格为 test_ 开头；
    4. 只返回纯代码，使用 markdown 格式包裹（python）
    """
        return prompt_info

    def ui_uodate_prompt(self,old_code,removed_ui,added_ui):
        prompt_info = f"""
    以下是 Python 的 UI 自动化测试代码：
    ```python{old_code}
    当前网站的 UI 结构发生了更新，原本的 UI 元素如下（已不存在）：
    {json.dumps(removed_ui, indent=2, ensure_ascii=False)}
    
    新页面结构如下（新增或替代）：
    {json.dumps(added_ui, indent=2, ensure_ascii=False)}
    请帮我更新原代码中失效的 selector、role、text 等，使代码在新 UI 中依然能运行，并保留原有功能逻辑。请用 markdown 格式返回纯代码。
    """
        return prompt_info

    def get_answer(self):
        response_data = json.loads(self.response_text)
        answer = response_data["choices"][0]["message"]["content"]
        self.test_log.log_info("[answer]: " + str(answer))
        return answer








