"""向量数据库模块"""
from pathlib import Path
from typing import List
from langchain_community.vectorstores import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.rag_system.config import RAGConfig


class VectorStoreBuilder:
    def __init__(self, persist_dir: Path, embeddings):
        self.persist_dir = persist_dir
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.embeddings = embeddings

    def create_vector_store(self, documents: List) -> Chroma:
        """从文档创建向量数据库"""
        print("正在分割文档...")
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=RAGConfig.CHUNK_SIZE,
            chunk_overlap=RAGConfig.CHUNK_OVERLAP,
            separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""]
        )

        chunks = text_splitter.split_documents(documents)
        print(f"文档已分割为 {len(chunks)} 个文本块")

        print("正在生成 embeddings 并创建向量数据库（可能需要几分钟）...")
        vector_store = Chroma.from_documents(
            documents=chunks,
            embedding=self.embeddings,
            persist_directory=str(self.persist_dir)
        )

        print(f"向量数据库已保存到: {self.persist_dir}")
        return vector_store

    def load_existing_vector_store(self) -> Chroma:
        """加载已存在的向量数据库"""
        return Chroma(
            persist_directory=str(self.persist_dir),
            embedding_function=self.embeddings
        )