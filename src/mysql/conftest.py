import mysql.connector
import pytest

@pytest.fixture(scope="session")
def db_connection(config_file):
    conn = mysql.connector.connect(
        host=config_file.get("mysql", "host"),
        port=config_file.get("mysql", "port"),
        user=config_file.get("mysql", "user"),
        password=config_file.get("mysql", "password")
    )
    if conn.is_connected():
        print("成功连接到MySQL服务器")
    else:
        print("连接失败")
    cursor = conn.cursor()
    # cursor.execute("SHOW DATABASES")
    # print("现有数据库:", cursor.fetchall())
    # print(type(cursor))

    # 创建数据库
    cursor.execute("CREATE DATABASE IF NOT EXISTS test_results_db")
    cursor.execute("USE test_results_db")
    # 创建表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS test_results (
        id INT AUTO_INCREMENT PRIMARY KEY,
        test_case_name VARCHAR(255) NOT NULL,
        question VARCHAR(500) NOT NULL,
        answer TEXT NOT NULL,
        result VARCHAR(50) NOT NULL,
        crash INT,
        fail_info VARCHAR(255) NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()

    yield conn

    conn.commit()
    cursor.close()
    conn.close()

#数据库游标
@pytest.fixture(scope="session")
def db_cursor(db_connection):
    cursor = db_connection.cursor()
    yield cursor
    cursor.close()
