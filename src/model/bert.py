from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import os


class OfflineSentenceBERT:
    def __init__(self, local_model_path=r'D:\hugging_face\models\all-MiniLM-L6-v2'):
        if not os.path.exists(local_model_path):
            raise FileNotFoundError(f"模型路径 {local_model_path} 不存在，请先下载模型")

        self.model = SentenceTransformer(local_model_path)

    def calculate_similarity(self, text1, text2):
        embedding1 = self.model.encode(text1, convert_to_tensor=True)
        embedding2 = self.model.encode(text2, convert_to_tensor=True)
        similarity = cosine_similarity(
            embedding1.reshape(1, -1),
            embedding2.reshape(1, -1)
        )[0][0]

        return similarity

    def is_relevant(self, question, answer, threshold=0.6):
        similarity = self.calculate_similarity(question, answer)
        return similarity >= threshold, similarity

if __name__ == "__main__":
    dir = r'D:\hugging_face\models\all-MiniLM-L6-v2'
    print(type(dir))
    checker = OfflineSentenceBERT(dir)

    questions_answers = [
        ("Python有什么特点？", "Python是一种解释型高级编程语言"),
    ]
    for q, a in questions_answers:
        relevant, score = checker.is_relevant(q, a)
        print(f"问题: {q}")
        print(f"答案: {a}")
        print(f"相关: {relevant}, 相似度: {score:.4f}")