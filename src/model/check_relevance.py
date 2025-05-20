import re

from jieba import analyse

from sentence_transformers import SentenceTransformer
import numpy as np

from src.deep_seek_api.api import DeepSeekApi

class ResponseJudger():
    def __init__(self,question,answer):
        self.model = SentenceTransformer('D:/hugging_face/models/text2vec-base-chinese', local_files_only=True)
        self.api = DeepSeekApi()
        self.question = question
        self.answer = answer

    def second_examine(self):
        try:
            prompt_info = f'''
                        我要判定一个ai生成的答案对还是错，问题是：{self.question},
                        ai给出的答案是:{self.answer},
                        请帮我：
                            1. 阅读问题和答案
                            2. 如果包含事实，请进行事实性核对：通过权威来源确认标准答案
                            3. 进行关键词检查：检查回答是否包含问题中的核心关键词
                            4. 进行主题一致性检查：判断附加信息是否围绕核心问题展开
                            5. 进行冗余度检查：是否包含无关或过度扩展的内容
                            6. 输出给我的答案只包含对或者错，置信度百分比
                '''
            self.api.ask_question(prompt_info)
            answer = self.api.get_answer()
            match = re.search(r'(\d+)%', answer)
            if match:
                confidence = int(match.group(1))
                if "对" in answer and (confidence > 80):
                    return True
                else:
                    return False
            else:
                print(f"未找到置信度信息，原始回答: {answer}")
                return False  # 明确返回False而不是隐式返回None
        except Exception as e:
            print(f"second_examine出错: {e}")
            return False

    def semantic_similarity(self,threshold=0.65):
        embeddings = self.model.encode([self.question, self.answer])
        emb0 = embeddings[0] / np.linalg.norm(embeddings[0])
        emb1 = embeddings[1] / np.linalg.norm(embeddings[1])
        similarity = np.dot(emb0, emb1)
        print(f"Similarity score: {similarity:.2f}")
        if similarity > threshold:
            return True
        else:
            return False
    def keyword_validation(self,ratio =0.6):
        keywords = analyse.extract_tags(self.question, topK=10)
        print(keywords)
        found_keywords = [kw for kw in keywords if kw in self.answer]
        match_ratio = len(found_keywords) / len(keywords)
        print(match_ratio)
        if match_ratio > ratio:
            print(f"Matched {len(found_keywords)}/{len(keywords)} keywords")
            return True
        else:
            return False
    def validate_answer_relevance(self):
        keyword_result = self.keyword_validation()
        semantic_result= self.semantic_similarity()
        api_result = self.second_examine()
        if keyword_result and semantic_result and api_result:
            return True
        else:
            return False



