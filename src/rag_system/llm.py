"""LLM 模块 - LM Studio API 封装"""
from typing import Optional, List, Any, Mapping
from langchain_core.language_models.llms import LLM


class LMStudioLLM:
    """封装 LM Studio 的 API 调用，兼容 LangChain"""

    def __init__(self, base_url: str, model_name: str):
        self.base_url = base_url
        self.model_name = model_name
        self.client = None

    def _get_client(self):
        if self.client is None:
            from openai import OpenAI
            self.client = OpenAI(
                base_url=f"{self.base_url}/v1",
                api_key="not-needed",
                timeout=60.0
            )
        return self.client

    def _call(self, prompt: str, **kwargs) -> str:
        client = self._get_client()
        try:
            response = client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=kwargs.get("temperature", 0.3),
                max_tokens=kwargs.get("max_tokens", 4096),
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"LLM 调用错误: {e}")
            return f"调用出错: {str(e)}"

    def __call__(self, prompt: str, **kwargs) -> str:
        return self._call(prompt, **kwargs)


class LocalLLMWrapper(LLM):
    """LangChain 的 LLM 包装器"""
    llm_instance: LMStudioLLM = None

    @property
    def _llm_type(self) -> str:
        return "lm_studio"

    def _call(self, prompt: str, stop: Optional[List[str]] = None, **kwargs) -> str:
        return self.llm_instance(prompt, **kwargs)

    @property
    def _identifying_params(self) -> Mapping[str, Any]:
        from .config import RAGConfig
        return {"model": RAGConfig.LLM_MODEL_NAME}