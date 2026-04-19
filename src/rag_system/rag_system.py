"""RAG 系统主模块"""
from typing import Dict
from langchain_classic.chains import RetrievalQA
from langchain_core.prompts import PromptTemplate

from src.rag_system.config import RAGConfig
from src.rag_system.document_loader import DocumentLoader
from src.rag_system.embeddings import LMStudioEmbeddings
from src.rag_system.vector_store import VectorStoreBuilder
from src.rag_system.llm import LMStudioLLM, LocalLLMWrapper


class RAGSystem:
    def __init__(self):
        self.vector_store = None
        self.llm = None
        self.embeddings = None
        self.qa_chain = None
        self.retriever = None

    def initialize(self, rebuild_db: bool = False):
        """初始化整个系统"""
        print("=" * 50)
        print("初始化 RAG 系统...")
        print("=" * 50)

        # 1. 测试 LM Studio 连接
        print("\n1. 测试 LM Studio 连接...")
        print(f"   LLM 模型: {RAGConfig.LLM_MODEL_NAME}")
        print(f"   Embedding 模型: {RAGConfig.EMBEDDING_MODEL_NAME}")

        # 初始化 LLM
        self.llm = LMStudioLLM(RAGConfig.LM_STUDIO_URL, RAGConfig.LLM_MODEL_NAME)

        # 初始化 Embeddings
        self.embeddings = LMStudioEmbeddings(RAGConfig.LM_STUDIO_URL, RAGConfig.EMBEDDING_MODEL_NAME)

        # 测试连接
        try:
            test_embedding = self.embeddings.embed_query("测试")
            print("   ✅ LM Studio 连接成功")
            print(f"   Embedding 维度: {len(test_embedding)}")
        except Exception as e:
            print(f"   ❌ LM Studio 连接失败: {e}")
            print("   请确保 LM Studio 正在运行，并且两个模型都已加载")
            return

        # 2. 构建或加载向量数据库
        print("\n2. 初始化向量数据库...")
        builder = VectorStoreBuilder(RAGConfig.VECTOR_DB_DIR, self.embeddings)

        if rebuild_db or not RAGConfig.VECTOR_DB_DIR.exists():
            print("   构建新的向量数据库...")
            documents = DocumentLoader.load_all_documents(RAGConfig.DOCS_DIR)
            if not documents:
                print("   ❌ 没有找到任何文档！请检查 DOCS_DIR 路径")
                return
            self.vector_store = builder.create_vector_store(documents)
        else:
            print("   加载已有向量数据库...")
            self.vector_store = builder.load_existing_vector_store()
            print("   ✅ 加载成功")

        # 3. 创建检索器
        print("\n3. 创建检索器...")
        self.retriever = self.vector_store.as_retriever(
            search_kwargs={"k": RAGConfig.RETRIEVAL_K}
        )

        # 4. 自定义 Prompt
        prompt_template = """你是一个专业的知识助手。请基于以下【参考内容】回答问题。

【参考内容】
{context}

【问题】
{question}

要求：
1. 如果参考内容中有相关信息，请详细回答
2. 如果参考内容不足，请诚实说明
3. 回答要结构化、条理清晰

回答："""

        PROMPT = PromptTemplate(
            template=prompt_template,
            input_variables=["context", "question"]
        )

        # 5. 创建问答链
        print("4. 创建问答链...")
        wrapped_llm = LocalLLMWrapper(llm_instance=self.llm)

        self.qa_chain = RetrievalQA.from_chain_type(
            llm=wrapped_llm,
            chain_type="stuff",
            retriever=self.retriever,
            chain_type_kwargs={"prompt": PROMPT},
            return_source_documents=True
        )

        print("\n✅ RAG 系统初始化完成！\n")

    def ask(self, question: str) -> Dict:
        """提问并获取答案"""
        if not self.qa_chain:
            raise ValueError("请先调用 initialize()")

        print("   检索相关文档...")
        result = self.qa_chain({"query": question})

        return {
            "question": question,
            "answer": result["result"],
            "sources": list(set([doc.metadata.get("filename", "unknown")
                                 for doc in result.get("source_documents", [])]))
        }

    def interactive_chat(self):
        """交互式命令行问答"""
        print("=" * 60)
        print("📚 RAG 问答系统已启动")
        print(f"🤖 LLM 模型: {RAGConfig.LLM_MODEL_NAME}")
        print(f"🔢 Embedding 模型: {RAGConfig.EMBEDDING_MODEL_NAME}")
        print(f"📁 文档目录: {RAGConfig.DOCS_DIR}")
        print("💡 输入 'quit' 退出")
        print("=" * 60)

        while True:
            question = input("\n❓ 你: ").strip()
            if question.lower() in ['quit', 'exit', 'q']:
                print("再见！")
                break

            if not question:
                continue

            print("🤔 思考中...")
            try:
                result = self.ask(question)
                print(f"\n🤖 助手: {result['answer']}")
                if result['sources']:
                    print(f"\n📚 参考来源: {', '.join(result['sources'])}")
            except Exception as e:
                print(f"\n❌ 出错了: {e}")