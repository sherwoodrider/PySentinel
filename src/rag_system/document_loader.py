"""文档加载模块"""
from pathlib import Path
from typing import List


class DocumentLoader:
    @staticmethod
    def load_single_document(file_path: Path) -> List:
        from langchain_community.document_loaders import (
            PyPDFLoader,
            Docx2txtLoader,
            UnstructuredExcelLoader,
            UnstructuredEPubLoader,
            TextLoader
        )

        ext = file_path.suffix.lower()
        try:
            if ext == '.pdf':
                loader = PyPDFLoader(str(file_path))
            elif ext == '.docx':
                loader = Docx2txtLoader(str(file_path))
            elif ext == '.xlsx':
                loader = UnstructuredExcelLoader(str(file_path), mode="elements")
            elif ext == '.epub':
                loader = UnstructuredEPubLoader(str(file_path))
            elif ext == '.md':
                loader = TextLoader(str(file_path), encoding='utf-8')
            else:
                print(f"跳过不支持格式: {file_path}")
                return []

            documents = loader.load()
            for doc in documents:
                doc.metadata["source"] = str(file_path)
                doc.metadata["filename"] = file_path.name
                doc.metadata["filetype"] = ext[1:]
            return documents
        except Exception as e:
            print(f"加载失败 {file_path}: {e}")
            return []

    @staticmethod
    def load_all_documents(docs_dir: Path) -> List:
        all_docs = []
        supported_exts = ['.pdf', '.docx', '.xlsx', '.epub', '.md']

        if not docs_dir.exists():
            print(f"错误：目录不存在 {docs_dir}")
            return []

        for file_path in docs_dir.rglob("*"):
            if file_path.suffix.lower() in supported_exts:
                print(f"正在加载: {file_path.name}")
                docs = DocumentLoader.load_single_document(file_path)
                all_docs.extend(docs)
        print(f"\n总计加载 {len(all_docs)} 个文档块")
        return all_docs