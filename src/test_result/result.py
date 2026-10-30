"""测试结果收集与汇总。

原实现的 ``add_case_result`` 没有任何调用方，属于"孤岛代码"。
这里补齐完整闭环：由根 ``conftest.py`` 的 hook 自动落数据，
最终产出结构化 JSON（含耗时、失败原因、AI 分析），供报告与通知消费。
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional


class TestResult:
    """线程安全的会话级结果收集器。"""

    def __init__(self, log_path: str, suite_name: str = "PySentinel") -> None:
        self.log_path = log_path
        self.suite_name = suite_name
        self.started_at = datetime.now()
        self.result_dict: Dict[str, Dict[str, Any]] = {}
        self.final_result_dict: Dict[str, Any] = {}
        self._lock = threading.RLock()
        os.makedirs(self.log_path or ".", exist_ok=True)

    # ------------------------------------------------------------------ #
    # 写入
    # ------------------------------------------------------------------ #
    def add_case_result(self, case_name: str, dict: Dict[str, Any]) -> None:  # noqa: A002 - 保持原签名
        with self._lock:
            self.result_dict[case_name] = dict

    def record(
        self,
        case_name: str,
        outcome: str,
        duration: float = 0.0,
        error: Optional[str] = None,
        nodeid: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        """按 pytest 的 outcome 记录一条结果。

        ``outcome`` 取值：``passed`` / ``failed`` / ``skipped`` / ``error`` / ``xfailed`` / ``xpassed``
        """
        entry = {
            "total": 1,
            "pass": 1 if outcome == "passed" else 0,
            "fail": 1 if outcome == "failed" else 0,
            "skip": 1 if outcome == "skipped" else 0,
            "crash": 1 if outcome == "error" else 0,
            "outcome": outcome,
            "duration": round(float(duration), 3),
            "error": (error or "")[:2000],
            "nodeid": nodeid or case_name,
        }
        if extra:
            entry.update(extra)
        with self._lock:
            # 重试 / 多 phase 场景：保留最新一次结果，累计耗时
            prev = self.result_dict.get(case_name)
            if prev:
                entry["duration"] = round(float(prev.get("duration", 0.0)) + entry["duration"], 3)
                entry["retries"] = int(prev.get("retries", 0)) + 1
            self.result_dict[case_name] = entry

    # ------------------------------------------------------------------ #
    # 汇总
    # ------------------------------------------------------------------ #
    def get_common_dict(self) -> Dict[str, Any]:
        with self._lock:
            total = passed = failed = crash = skipped = 0
            duration = 0.0
            for value in self.result_dict.values():
                total += int(value.get("total", 1))
                passed += int(value.get("pass", 0))
                failed += int(value.get("fail", 0))
                crash += int(value.get("crash", 0))
                skipped += int(value.get("skip", 0))
                duration += float(value.get("duration", 0.0))

            finished_at = datetime.now()
            elapsed = (finished_at - self.started_at).total_seconds()
            common = {
                "suite": self.suite_name,
                "started_at": self.started_at.isoformat(timespec="seconds"),
                "finished_at": finished_at.isoformat(timespec="seconds"),
                "elapsed": round(elapsed, 3),
                "cases_duration": round(duration, 3),
                "total": total,
                "pass": passed,
                "fail": failed,
                "crash": crash,
                "skip": skipped,
                "pass_rate": round(passed * 100 / total, 2) if total else 0.0,
            }

        self.common_dict = common
        self.final_result_dict["common"] = common
        self.final_result_dict["test_result"] = self.result_dict
        return common

    def get_final_dict(self) -> Dict[str, Any]:
        try:
            self.get_common_dict()
        except Exception as exc:  # pragma: no cover - 汇总失败不应中断会话
            print(f"[TestResult] 汇总失败: {exc}")
        return self.final_result_dict

    # ------------------------------------------------------------------ #
    # 输出
    # ------------------------------------------------------------------ #
    @property
    def json_path(self) -> str:
        return os.path.join(self.log_path or ".", "test_result.json")

    def result_to_json(self) -> str:
        """写入 JSON 汇总文件，返回文件路径。"""
        self.get_final_dict()
        path = self.json_path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as fp:
            json.dump(self.final_result_dict, fp, indent=4, ensure_ascii=False)
        return path

    def failed_cases(self) -> List[Dict[str, Any]]:
        """失败明细，供通知/报告直接消费。"""
        with self._lock:
            return [
                {"name": name, **info}
                for name, info in self.result_dict.items()
                if info.get("fail") or info.get("crash")
            ]

    def summary_text(self) -> str:
        """一行式摘要，适合钉钉/企微/终端输出。"""
        common = self.get_common_dict()
        return (
            f"{common['suite']} | total={common['total']} pass={common['pass']} "
            f"fail={common['fail']} crash={common['crash']} skip={common['skip']} "
            f"pass_rate={common['pass_rate']}% elapsed={common['elapsed']}s"
        )
