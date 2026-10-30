"""数据库 fixture。

改进点：
* 使用统一配置中心，缺失配置不再抛裸异常；
* **连接池**：``mysql.connector.pooling`` 复用连接，避免每个会话重复握手；
* **优雅降级**：数据库不可用时 ``pytest.skip`` 而非让整个会话崩溃；
* 建库建表只做一次，并为高频查询字段加索引。
"""
from __future__ import annotations

import pytest

from src.config.settings import settings

_POOL = None
_POOL_LOCK = None


def _pool_config() -> dict:
    try:
        settings.require("mysql", "host", "user", "password")
    except ValueError as exc:
        pytest.skip(f"MySQL 未配置，跳过数据库相关测试：{exc}")
    return {
        "host": settings.get("mysql", "host"),
        "port": settings.getint("mysql", "port", 3306),
        "user": settings.get("mysql", "user"),
        "password": settings.get("mysql", "password"),
        "database": settings.raw_get("mysql", "database", "test_results_db"),
        "charset": "utf8mb4",
    }


def get_pool():
    """进程共享的只读连接池（建库由 :func:`bootstrap_schema` 负责）。"""
    global _POOL, _POOL_LOCK
    import threading

    if _POOL_LOCK is None:
        _POOL_LOCK = threading.Lock()
    if _POOL is None:
        with _POOL_LOCK:
            if _POOL is None:
                from mysql.connector.pooling import MySQLConnectionPool

                base = _pool_config()
                # 先不带 database 连一次，确保库存在
                bootstrap_schema({k: v for k, v in base.items() if k != "database"})
                try:
                    _POOL = MySQLConnectionPool(
                        pool_name="pysentinel",
                        pool_size=settings.getint("mysql", "pool_size", 5),
                        **base,
                    )
                except Exception as exc:
                    pytest.skip(f"MySQL 连接池创建失败：{exc}")
    return _POOL


def bootstrap_schema(cfg: dict) -> None:
    """幂等地创建库与表，仅在首次调用时执行。"""
    import mysql.connector

    conn = None
    try:
        conn = mysql.connector.connect(**cfg)
        cursor = conn.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{cfg['database']}`")
        cursor.execute(f"USE `{cfg['database']}`")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS test_results (
                id INT AUTO_INCREMENT PRIMARY KEY,
                test_case_name VARCHAR(255) NOT NULL,
                question VARCHAR(500) NOT NULL DEFAULT '',
                answer TEXT NOT NULL,
                result VARCHAR(50) NOT NULL DEFAULT '',
                crash INT DEFAULT 0,
                fail_info VARCHAR(1000) NOT NULL DEFAULT '',
                duration DECIMAL(10,3) DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_case_name (test_case_name),
                INDEX idx_created_at (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        conn.commit()
        cursor.close()
    except Exception as exc:
        pytest.skip(f"MySQL 初始化失败：{exc}")
    finally:
        if conn is not None and conn.is_connected():
            conn.close()


@pytest.fixture(scope="session")
def db_pool():
    """暴露连接池，供需要并发写入的模块使用。"""
    return get_pool()


@pytest.fixture(scope="session")
def db_connection():
    conn = None
    try:
        conn = get_pool().get_connection()
        yield conn
    finally:
        if conn is not None:
            conn.close()  # 归还连接池而非真正关闭


@pytest.fixture(scope="session")
def db_cursor(db_connection):
    cursor = db_connection.cursor()
    try:
        yield cursor
    finally:
        cursor.close()
