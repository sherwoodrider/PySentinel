"""配置模块"""
from pathlib import Path


class RAGConfig:
    # 文档目录
    DOCS_DIR = Path("/Users/jasperjiang/code_repo/infinite_library")

    # 向量数据库存储目录
    VECTOR_DB_DIR = Path("/Users/jasperjiang/code_repo/.rag_vector_db")

    # LM Studio 配置
    LM_STUDIO_URL = "http://localhost:1234"
    LLM_MODEL_NAME = "deepseek/deepseek-r1-0528-qwen3-8b"
    EMBEDDING_MODEL_NAME = "text-embedding-nomic-embed-text-v1.5"

    # 分块参数
    CHUNK_SIZE = 1000
    CHUNK_OVERLAP = 200

    # 检索参数
    RETRIEVAL_K = 4