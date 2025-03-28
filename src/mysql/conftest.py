import mysql.connector
import pytest

@pytest.fixture(scope="session")
def db_connection(config_file):
    # host=config_file.get("mysql", "host"),
    # port=config_file.get("mysql", "port"),
    # user=config_file.get("mysql", "user"),
    # password=config_file.get("mysql", "password")
    # print("host type: {}".format(type(host)))
    # print("host value: {}".format(str(host)))
    # print("port type: {}".format(type(port)))
    # print("port value: {}".format(str(port)))
    # print("user type: {}".format(type(user)))
    # print("user value: {}".format(str(user)))
    # print("password type: {}".format(type(password)))
    # print("password value: {}".format(str(password)))

    conn = mysql.connector.connect(
        host=config_file.get("mysql", "host"),
        port=config_file.get("mysql", "port"),
        user=config_file.get("mysql", "user"),
        password=config_file.get("mysql", "password")
    )
    # 连接到 MySQL 服务器
    # conn = mysql.connector.connect(
    #     host="localhost",
    #     port="3306",
    #     user="root",
    #     password="123456"
    # )

    cursor = conn.cursor()

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

    yield conn  # 提供数据库连接给测试用例使用

    # 测试结束后清理数据库
    cursor.execute("DROP DATABASE IF EXISTS test_results_db")
    conn.commit()
    cursor.close()
    conn.close()

# Fixture: 获取数据库游标
@pytest.fixture(scope="session")
def db_cursor(db_connection):
    cursor = db_connection.cursor()
    yield cursor
    cursor.close()
