"""测试结果持久化 DAO。

修复的既有缺陷：
* ``update()`` SQL 只有 2 个占位符却传入 4 个值 —— 必然报 "not enough arguments"；
* ``query()`` 只 SELECT 一列却断言 ``row[1]`` —— 必然 IndexError；
* ``except AssertionError`` 捕获面太窄，数据库连接异常会被吞掉后悄悄丢失；
* 逐条 ``execute + commit`` —— 批量落库时每条一次网络往返。

新增：``executemany`` 批量写入（一次往返写 N 条），以及自动截断超长字段防止 ``DataError``。
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

MAX_QUESTION = 500
MAX_FAIL_INFO = 1000
MAX_ANSWER = 60000


def _clip(value: Any, limit: int) -> str:
    text = "" if value is None else str(value)
    return text[:limit]


class DatabaseManager:
    def __init__(self, test_log_handle, db_cursor, db_connection, table: str = "test_results") -> None:
        self.test_log = test_log_handle
        self.db_cursor = db_cursor
        self.db_connection = db_connection
        self.table = table

    # ------------------------------------------------------------------ #
    def _safe_execute(self, sql: str, values: Sequence, many: bool = False) -> bool:
        try:
            if many:
                self.db_cursor.executemany(sql, list(values))
            else:
                self.db_cursor.execute(sql, values)
            self.db_connection.commit()
            return True
        except Exception as exc:
            # 落库失败不应影响测试结论的产出
            try:
                self.db_connection.rollback()
            except Exception:  # pragma: no cover
                pass
            self.test_log.log_error(f"[DatabaseManager] SQL 执行失败: {exc}")
            return False

    # ------------------------------------------------------------------ #
    def insert(self, case_name, question, answer, test_result, crash, fail_info, duration: float = 0.0) -> bool:
        self.test_log.log_info("[DatabaseManager]:insert begin")
        sql = (
            f"INSERT INTO {self.table} "
            "(test_case_name, question, answer, result, crash, fail_info, duration) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)"
        )
        values = (
            _clip(case_name, 255),
            _clip(question, MAX_QUESTION),
            _clip(answer, MAX_ANSWER),
            _clip(test_result, 50),
            int(crash or 0),
            _clip(fail_info, MAX_FAIL_INFO),
            round(float(duration or 0.0), 3),
        )
        ok = self._safe_execute(sql, values)
        self.test_log.log_info("[DatabaseManager]:insert end")
        return ok

    def insert_many(self, rows: Iterable[Dict[str, Any]]) -> int:
        """批量写入，把 N 次往返压缩成 1 次。

        rows 每项需包含 ``test_case_name / question / answer / result / crash / fail_info``。
        """
        payload: List[Tuple] = [
            (
                _clip(r.get("test_case_name"), 255),
                _clip(r.get("question"), MAX_QUESTION),
                _clip(r.get("answer"), MAX_ANSWER),
                _clip(r.get("result"), 50),
                int(r.get("crash") or 0),
                _clip(r.get("fail_info"), MAX_FAIL_INFO),
                round(float(r.get("duration") or 0.0), 3),
            )
            for r in rows
        ]
        if not payload:
            return 0
        sql = (
            f"INSERT INTO {self.table} "
            "(test_case_name, question, answer, result, crash, fail_info, duration) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)"
        )
        return len(payload) if self._safe_execute(sql, payload, many=True) else 0

    # ------------------------------------------------------------------ #
    def query(self, case_name) -> Optional[Dict[str, Any]]:
        self.test_log.log_info("[DatabaseManager]:query begin")
        try:
            self.db_cursor.execute(
                f"SELECT result, crash, fail_info FROM {self.table} WHERE test_case_name = %s",
                (case_name,),
            )
            row = self.db_cursor.fetchone()
        except Exception as exc:
            self.test_log.log_error(f"[DatabaseManager] query failed: {exc}")
            return None
        self.test_log.log_info("[DatabaseManager]:query end")
        if row is None:
            return None
        return {"result": row[0], "crash": row[1], "fail_info": row[2]}

    def update(self, case_name, test_result, crash=0, fail_info="") -> Optional[int]:
        sql = f"UPDATE {self.table} SET result = %s, crash = %s, fail_info = %s WHERE test_case_name = %s"
        values = (_clip(test_result, 50), int(crash or 0), _clip(fail_info, MAX_FAIL_INFO), case_name)
        if not self._safe_execute(sql, values):
            return None
        return self.db_cursor.rowcount

    def delete(self, test_case_name) -> Optional[int]:
        sql = f"DELETE FROM {self.table} WHERE test_case_name = %s"
        if not self._safe_execute(sql, (test_case_name,)):
            return None
        return self.db_cursor.rowcount
