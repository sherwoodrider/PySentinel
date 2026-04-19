"""Embeddings 模块 - LM Studio API 封装"""
from typing import List
import requests


class LMStudioEmbeddings:
    """使用 LM Studio 的 API 来生成 embeddings"""

    def __init__(self, base_url: str, model_name: str):
        self.base_url = base_url
        self.model_name = model_name
        self.embedding_url = f"{base_url}/v1/embeddings"

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """为多个文档生成 embeddings"""
        embeddings = []
        for text in texts:
            embedding = self.embed_query(text)
            embeddings.append(embedding)
        return embeddings

    def embed_query(self, text: str) -> List[float]:
        """为单个查询生成 embedding"""
        try:
            response = requests.post(
                self.embedding_url,
                headers={"Content-Type": "application/json"},
                json={
                    "model": self.model_name,
                    "input": text
                },
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                return result["data"][0]["embedding"]
            else:
                print(f"Embedding API 错误: {response.status_code} - {response.text}")
                return [0.0] * 768
        except Exception as e:
            print(f"生成 embedding 时出错: {e}")
            return [0.0] * 768

    def embed_documents_batch(self, texts: List[str], batch_size: int = 10) -> List[List[float]]:
        """批量生成 embeddings（效率更高）"""
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            try:
                response = requests.post(
                    self.embedding_url,
                    headers={"Content-Type": "application/json"},
                    json={
                        "model": self.model_name,
                        "input": batch
                    },
                    timeout=60
                )

                if response.status_code == 200:
                    result = response.json()
                    batch_embeddings = [item["embedding"] for item in result["data"]]
                    all_embeddings.extend(batch_embeddings)
                else:
                    print(f"批量 embedding 错误: {response.status_code}")
                    for _ in batch:
                        all_embeddings.append([0.0] * 768)
            except Exception as e:
                print(f"批量生成 embedding 时出错: {e}")
                for _ in batch:
                    all_embeddings.append([0.0] * 768)

        return all_embeddings