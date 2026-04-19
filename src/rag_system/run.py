"""主程序入口"""
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rag_system import RAGSystem


def main():
    # 检查是否需要安装 requests
    try:
        import requests
    except ImportError:
        print("请先安装 requests: pip install requests")
        exit(1)

    rag = RAGSystem()
    rag.initialize(rebuild_db=False)  # 第一次运行设为 True
    rag.interactive_chat()


if __name__ == "__main__":
    main()