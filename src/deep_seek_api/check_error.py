from conftest import config_file
from src.deep_seek_api.api import DeepSeekApi

import traceback
import inspect

def ai_analyze_error(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            func_code = inspect.getsource(func)
            description = inspect.getdoc(func) or "无描述"
            error_info = traceback.format_exc()
            api = DeepSeekApi()
            question = api.error_prompt(func_code, description, error_info)
            api.ask_question(question)
            answer = api.get_answer()
            raise e  # 抛出原始异常

    return wrapper