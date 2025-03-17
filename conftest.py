import configparser
import os
import datetime
import pytest
from selenium.webdriver.common.by import By
from src.test_log.logger import TestLog
from src.test_result.result import TestResult


@pytest.fixture(scope="session")
def config_file():
    config = configparser.ConfigParser()
    current_dir = os.getcwd()
    config_file_path = os.path.join(current_dir, "src", "config", "test_config.ini")
    if not os.path.exists(config_file_path):
        raise FileNotFoundError(f"Config file not found: {config_file_path}")
    print(config_file_path)
    config.read(config_file_path)

    if not config.has_section("ssh"):
        raise ValueError("Missing 'ssh' section in config.ini")
    yield config

@pytest.fixture(scope="session")
def log_folder():
        now = datetime.datetime.now()
        str_now = now.strftime('%Y_%m_%d_%H_%M_%S')
        log_folder_name = "pysentinel_" + str_now
        test_path = os.getcwd()
        save_log_folder = os.path.join(test_path, "logs")
        test_log_folder = os.path.join(save_log_folder, log_folder_name)
        if not os.path.exists(test_log_folder):
            os.mkdir(test_log_folder)
            print(f"Created log folder: {test_log_folder}")
        # 返回 log 文件夹路径
        yield test_log_folder
         # 测试会话结束后清理 log 文件夹
        # print(f"Cleaning up log folder: {test_log_folder}")
        # import shutil
        # shutil.rmtree(test_log_folder)

@pytest.fixture(scope="session")
def test_log_handle(log_folder):
    now = datetime.datetime.now()
    str_now = now.strftime('%Y_%m_%d_%H_%M_%S')
    log_folder_name = "pysentinel_" + str_now + ".log"
    test_log_file = os.path.join(log_folder, log_folder_name)
    test_log = TestLog(test_log_file)
    yield test_log


@pytest.fixture(scope="session")
def test_result_handle(log_folder):
    test_result = TestResult(log_folder)
    yield test_result


