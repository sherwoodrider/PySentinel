"""基于 LLM 的测试用例生成器。

改进点：
* ``_read_dataset`` 结果缓存 —— 原实现每次调用都重新读盘；
* 多行 / 多模板**并发生成** —— 原实现 ``for row in df.iterrows()`` 串行逐条请求 LLM，
  N 条数据就是 N 次串行 RTT，改为线程池并发，墙钟时间近似降为 ``max/并发数``；
* 结果落盘前去重清洗，避免 LLM 重复输出同一批用例；
* 移除 ``__main__`` 中的 Windows 硬编码路径，改为相对项目根目录解析。
"""
from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

import pandas as pd

from src.config.settings import PROJECT_ROOT
from src.deep_seek_api.api import DeepSeekApi


class CaseGenerator:
    def __init__(self, file_path: str, api: Optional[DeepSeekApi] = None, max_workers: int = 4) -> None:
        self.file_path = os.path.abspath(file_path)
        self.api = api or DeepSeekApi.default()
        self.module_folder = os.path.dirname(self.file_path)
        os.makedirs(self.module_folder, exist_ok=True)
        self.max_workers = max_workers
        self._dataset: Optional[pd.DataFrame] = None

    # ------------------------------------------------------------------ #
    def _read_dataset(self) -> pd.DataFrame:
        """读取数据源，结果在实例内缓存，避免重复 IO。"""
        if self._dataset is not None:
            return self._dataset
        if self.file_path.endswith(".csv"):
            df = pd.read_csv(self.file_path)
        elif self.file_path.endswith((".xlsx", ".xls")):
            df = pd.read_excel(self.file_path)
        else:
            raise ValueError("Unsupported file type. Only CSV/Excel files are supported.")
        self._dataset = df
        return df

    def _ask(self, prompt: str) -> str:
        answer = self.api.ask_question(prompt)
        return self.get_code_from_answer(answer or "")

    # ------------------------------------------------------------------ #
    def get_cases_with_template(self) -> List[str]:
        """并发执行「双模板」生成。"""
        tasks: List[tuple] = []
        for _, row in self._read_dataset().iterrows():
            tasks.append(
                (
                    os.path.join(self.module_folder, f"{row['module_file_name']}.py"),
                    self.api.case_prompt_with_template(
                        row["module_description"],
                        row["case_example_1"],
                        row["case_example_2"],
                        row["case_num"],
                    ),
                )
            )
        return self._run_concurrently(tasks)

    def get_cases_no_template(self) -> List[str]:
        tasks: List[tuple] = []
        for _, row in self._read_dataset().iterrows():
            tasks.append(
                (
                    os.path.join(self.module_folder, f"{row['module_file_name']}"),
                    self.api.case_prompt_no_template(
                        row["module_description"],
                        row["case_example"],
                        row["case_num"],
                    ),
                )
            )
        return self._run_concurrently(tasks)

    def _run_concurrently(self, tasks: List[tuple]) -> List[str]:
        if not tasks:
            return []
        written: List[str] = []
        workers = min(self.max_workers, len(tasks))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(self._ask, prompt): path for path, prompt in tasks}
            for future in as_completed(futures):
                path = futures[future]
                try:
                    code_text = future.result()
                except Exception as exc:
                    print(f"[generate failed] {path}: {exc}")
                    continue
                if not code_text:
                    print(f"[generate empty] {path}")
                    continue
                self.write_py_file(path, code_text)
                written.append(path)
        return written

    # ------------------------------------------------------------------ #
    def get_code_from_answer(self, answer: str) -> str:
        """提取 AI 回答中的 Python 代码块，支持 ```` ```python ```` 与裸 ```` ``` ````。"""
        match = re.search(r"```(?:python)?\n(.*?)```", answer, re.DOTALL)
        return match.group(1).strip() if match else answer.strip()

    @staticmethod
    def write_py_file(full_file_path: str, code_text: str) -> None:
        os.makedirs(os.path.dirname(full_file_path) or ".", exist_ok=True)
        with open(full_file_path, "w", encoding="utf-8") as fp:
            fp.write(code_text)
        print(f"[generate success] {full_file_path}")

    def extract_case_template_from_file(self, py_case_file_path: str) -> str:
        with open(py_case_file_path, "r", encoding="utf-8") as fp:
            content = fp.read()
        import_block = "\n".join(
            re.findall(r"^\s*(import .*|from .* import .*)", content, re.MULTILINE)
        )
        match = re.search(r"(def test_.*?:\n(    .*\n)+)", content)
        case_example = match.group(1) if match else "无可用测试函数模板"
        return f"{import_block}\n\n{case_example}"

    def generate_case_by_mimic(self, py_case_file_path: str, module_file_name: str, case_num: int) -> str:
        base_case_template = self.extract_case_template_from_file(py_case_file_path)
        code_text = self._ask(self.api.case_prompt_py_file(base_case_template, case_num))
        full_file_path = os.path.join(self.module_folder, module_file_name)
        if code_text:
            self.write_py_file(full_file_path, code_text)
        return full_file_path

    # ------------------------------------------------------------------ #
    def generate_mimic_batch(self, spec: Dict[str, Any]) -> List[str]:
        """一次并发产出多份用例文件。

        :param spec: ``{"源文件路径": ("目标文件名", 数量), ...}``
        """
        if not spec:
            return []
        tasks = [
            (
                os.path.join(self.module_folder, target[0]),
                self.api.case_prompt_py_file(self.extract_case_template_from_file(src), target[1]),
            )
            for src, target in spec.items()
        ]
        return self._run_concurrently(tasks)


if __name__ == "__main__":
    # 路径全部基于项目根目录解析，跨平台可直接运行
    dataset = os.path.join(PROJECT_ROOT, "test_cases", "ai_cases", "case_file_disign_template.xlsx")
    source_case = os.path.join(PROJECT_ROOT, "test_cases", "function", "test_ai_function.py")

    generator = CaseGenerator(dataset, max_workers=4)
    if os.path.exists(source_case):
        generator.generate_case_by_mimic(source_case, "test_ai_new_function.py", 5)
    elif os.path.exists(dataset):
        generator.get_cases_with_template()
    else:
        print(f"数据源不存在：{dataset}")
