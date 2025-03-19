import pytest
@pytest.mark.usefixtures("test_log_handle", "db_cursor", "db_connection")
class DatabaseManager():
    @pytest.fixture(autouse=True)
    def init_fixture(self,test_log_handle,db_cursor,db_connection):
        self.test_log = test_log_handle
        self.db_cursor = db_cursor
        self.db_connection = db_connection

    # def __init__(self, test_log_handle, db_cursor, db_connection):
    #     self.test_log = test_log_handle
    #     self.db_cursor = db_cursor
    #     self.db_connection = db_connection
    def insert(self,case_name,question,answer,test_result,crash,fail_info):
        try:
            self.test_log.log_info("[DatabaseManager]:insert begin")
            # 将结果插入数据库
            sql = "INSERT INTO test_results (test_case_name, question,answer,result,crash,fail_info) VALUES (%s, %s)"
            values = (case_name,question,answer, test_result, crash, fail_info)
            self.db_cursor.execute(sql, values)
            self.db_connection.commit()
            self.test_log.log_info("[DatabaseManager]:insert end")
        except AssertionError as e:
            self.test_log.log_critical(e)

    def query(self, case_name):
        try:
            self.test_log.log_info("[DatabaseManager]:query begin")
            self.db_cursor.execute("SELECT result FROM test_results WHERE test_case_name = %s", (case_name,))
            row = self.db_cursor.fetchone()
            assert row is not None  # 查询到了结果
            assert row[1] == case_name
            self.test_log.log_info("[DatabaseManager]:query end")
        except AssertionError as e:
            self.test_log.log_critical(e)
    def update(self, case_name,test_result,crash,fail_info):
        try:
            sql = "UPDATE test_results SET result = %s WHERE test_case_name = %s"
            values = (case_name, test_result, crash, fail_info)
            self.db_cursor.execute(sql, values)
            self.db_connection.commit()
            return self.db_cursor.rowcount  # 返回受影响的行数
        except AssertionError as e:
            self.test_log.log_critical(e)
    def delete(self, test_case_name):
        try:
            sql = "DELETE FROM test_results WHERE test_case_name = %s"
            self.db_cursor.execute(sql, (test_case_name,))
            self.db_connection.commit()
            return self.db_cursor.rowcount
        except AssertionError as e:
            self.test_log.log_critical(e)




