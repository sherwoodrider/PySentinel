import os
import pandas as pd
import re

from src.deep_seek_api.api import DeepSeekApi


class CaseGenerator:
    def __init__(self, file_path):
        self.file_path = file_path
        self.api = DeepSeekApi()
        self.module_folder = os.path.dirname(file_path)
        os.makedirs(self.module_folder, exist_ok=True)

    def _read_dataset(self):
        if self.file_path.endswith('.csv'):
            return pd.read_csv(self.file_path)
        elif self.file_path.endswith('.xlsx'):
            return pd.read_excel(self.file_path)
        else:
            raise ValueError("Unsupported file type. Only CSV and Excel files are supported.")

    def get_cases_with_template(self):
        df = self._read_dataset()

        for _, row in df.iterrows():
            module_description = row['module_description']
            case_example_1 = row['case_example_1']
            case_example_2 = row['case_example_2']
            case_num = row['case_num']
            module_file_name = row['module_file_name'] + ".py"

            prompt_info = self.api.case_prompt_with_template(
                module_description, case_example_1, case_example_2, case_num
            )

            self.api.ask_question(prompt_info)
            answer = self.api.get_answer()
            code_text = self.get_code_from_answer(answer)

            full_file_path = os.path.join(self.module_folder, module_file_name)
            self.write_py_file(full_file_path, code_text)

    def get_cases_no_template(self):
        df = self._read_dataset()

        for _, row in df.iterrows():
            module_description = row['module_description']
            case_example = row['case_example']
            case_num = row['case_num']
            module_file_name = row['module_file_name']

            prompt_info = self.api.case_prompt_no_template(
                module_description, case_example, case_num
            )

            self.api.ask_question(prompt_info)
            answer = self.api.get_answer()
            code_text = self.get_code_from_answer(answer)

            full_file_path = os.path.join(self.module_folder, module_file_name)
            self.write_py_file(full_file_path, code_text)

    def get_code_from_answer(self, answer: str) -> str:
        """
        提取 AI 回答中的 Python 代码块。
        支持 ```python 和 ``` 包裹的形式。
        """
        match = re.search(r"```(?:python)?\n(.*?)```", answer, re.DOTALL)
        return match.group(1).strip() if match else answer.strip()

    def write_py_file(self, full_file_path, code_text):
        with open(full_file_path, 'w', encoding='utf-8') as f:
            f.write(code_text)
        print(f"[generate success] {full_file_path}")

    def extract_case_template_from_file(self, py_case_file_path: str) -> str:
        with open(py_case_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        # 提取 import 语句
        import_block = '\n'.join(re.findall(r'^\s*(import .*|from .* import .*)', content, re.MULTILINE))
        # 提取一个函数体作为模板（默认第一个 test_ 开头的函数）
        match = re.search(r'(def test_.*?:\n(    .*\n)+)', content)
        case_example = match.group(1) if match else "无可用测试函数模板"
        return f"{import_block}\n\n{case_example}"

    def generate_case_by_mimic(self, py_case_file_path: str,module_file_name: str,case_num):
        base_case_template = self.extract_case_template_from_file(py_case_file_path)
        prompt = self.api.case_prompt_py_file(base_case_template,case_num)
        self.api.ask_question(prompt)
        answer = self.api.get_answer()
        code_text = self.get_code_from_answer(answer)
        full_file_path = os.path.join(self.module_folder, module_file_name)
        self.write_py_file(full_file_path, code_text)

if __name__ == '__main__':
    file_path = r"D:\code_repo\PySentinel\test_cases\ai_cases\case_file_disign_template.xlsx"
    g_c = CaseGenerator(file_path)
    # g_c.get_cases_with_template()
    # file_path = r"D:\code_repo\PySentinel\test_cases\ai_cases\case_file_disign_no_template.xlsx"
    # g_c.get_cases_with_template()
    py_case_file_path = r"D:\code_repo\PySentinel\test_cases\function\test_ai_function.py"
    g_c.generate_case_by_mimic(py_case_file_path,"test_ai_new_function.py",5)
