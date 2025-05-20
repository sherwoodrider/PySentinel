import json
import os
from datetime import date

import pandas as pd
import re

from src.deep_seek_api.api import DeepSeekApi
from playwright.sync_api import Playwright, sync_playwright,expect, Page

from src.deep_seek_api.check_error import ai_analyze_error


class UiChecker:
    def __init__(self,old_code_path, url="https://chat.deepseek.com/sign_in", output_path="snapshot"):
        self.url = url
        self.api = DeepSeekApi()
        self.old_code_path = old_code_path
        self.update_folder_path = os.path.dirname(old_code_path)
        self.output_path = output_path
        os.makedirs(self.output_path, exist_ok=True)
    @ai_analyze_error
    def snapshot_ui_structure(self):
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(self.url)
            page.wait_for_timeout(3000)

            dom = page.evaluate("""() => {
                const elements = Array.from(document.querySelectorAll('*'));
                return elements.map(el => {
                    return {
                        tag: el.tagName,
                        role: el.getAttribute('role'),
                        name: el.getAttribute('name'),
                        id: el.id,
                        text: el.innerText ? el.innerText.slice(0, 30) : '',
                        class: el.className
                    };
                });
            }""")

            with open(f"{self.output_path}/dom_{date.today()}.json", "w", encoding="utf-8") as f:
                json.dump(dom, f, indent=2, ensure_ascii=False)
            browser.close()

    @ai_analyze_error
    def compare_ui_snapshots(self,old_file, new_file):
        with open(old_file, "r", encoding="utf-8") as f1, open(new_file, "r", encoding="utf-8") as f2:
            old_dom = json.load(f1)
            new_dom = json.load(f2)
        old_set = set(json.dumps(x, sort_keys=True) for x in old_dom)
        new_set = set(json.dumps(x, sort_keys=True) for x in new_dom)
        added = new_set - old_set
        removed = old_set - new_set
        return [json.loads(x) for x in removed], [json.loads(x) for x in added]

    @ai_analyze_error
    def get_code_from_answer(self, answer: str) -> str:
        match = re.search(r"```(?:python)?\n(.*?)```", answer, re.DOTALL)
        return match.group(1).strip() if match else answer.strip()
    def write_py_file(self, full_file_path, code_text):
        with open(full_file_path, 'w', encoding='utf-8') as f:
            f.write(code_text)
        print(f"[generate success] {full_file_path}")
    def update_case_code_with_ai(self, removed_ui, added_ui):
        if (len(removed_ui) == 0) and (len(added_ui) == 0):
            print("The page elements have not changed and are returned directly")
            return
        with open(self.old_code_path, 'r', encoding='utf-8') as f:
            old_code = f.read()
        prompt = self.api.ui_uodate_prompt(old_code, removed_ui, added_ui)
        self.api.ask_question(prompt)
        answer = self.api.get_answer()
        new_code = self.get_code_from_answer(answer)
        # os.makedirs(self.update_folder_path, exist_ok=True)
        file_name = os.path.basename(self.old_code_path).replace(".py", "_updated.py")
        update_folder_path = os.path.dirname(self.old_code_path)
        new_code_path = os.path.join(update_folder_path,file_name)
        self.write_py_file(new_code_path,new_code)
        print(f"code is already saved in : {new_code_path}")

if __name__ == "__main__":
    old_code_path = r"D:\code_repo\PySentinel\test_cases\conftest.py"
    url = "https://chat.deepseek.com/sign_in"
    output_path = r"D:\code_repo\PySentinel\src\deep_seek_api\snapshot"
    u_c  = UiChecker(old_code_path)
    u_c.snapshot_ui_structure()
    snapshots = sorted(os.listdir(output_path))
    if len(snapshots) < 2:
        print("There should be at least two files")
    else:
        new_snapshot = os.path.join(output_path, snapshots[-1])
        old_snapshot = os.path.join(output_path, snapshots[-2])
        removed_ui, added_ui = u_c.compare_ui_snapshots(old_snapshot, new_snapshot)
        u_c.update_case_code_with_ai(removed_ui=removed_ui,added_ui=added_ui)