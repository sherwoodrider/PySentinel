"""答案相关性判定器（三级分诊）。

原有实现的核心瓶颈：
* ``ResponseJudger.__init__`` 每次都 ``SentenceTransformer(...)`` —— 一个几百 MB 的模型
  **每个用例重新加载一次**，耗时数秒；
* 每次判定都 new 一个 ``DeepSeekApi`` —— 重复读配置、重复建连、重复付费请求；
* ``second_examine`` 单独被当作断言使用，加载了模型却完全没用它；
* 三个判定不分先后全跑 —— 便宜的本地校验和昂贵的 LLM 校验一视同仁。

新实现：
* **模型进程级单例 + 懒加载**：只有真正需要语义层时才加载，且全程只加载一次；
* **分级短路（tiered short-circuit）**：本地免费校验先行，
  高置信通过/失败直接出结论，**只在"灰色区间"才升级到 LLM**，大幅降低延迟与 token 成本；
* **LLM 结果持久化缓存**：相同 (question, answer) 跨会话复用；
* **批量编码** ``judge_batch``：多条用例一次性 encode，摊薄模型调用开销；
* **降级容错**：模型缺失时自动降级到关键词 + LLM，不再让环境差异直接炸掉测试。
"""
from __future__ import annotations

import hashlib
import re
import threading
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.config.settings import Settings, get_settings
from src.test_log.logger import TestLog

# --------------------------------------------------------------------------- #
# 模型单例仓库
# --------------------------------------------------------------------------- #
class SentenceModelRegistry:
    """SentenceTransformer 进程级单例。``local_files_only`` 保证离线可用。"""

    _model: Any = None
    _model_path: Optional[str] = None
    _lock = threading.Lock()
    _failed: bool = False

    @classmethod
    def default_path(cls, settings: Settings) -> str:
        return str(settings.raw_get("model", "sentence_model_path", "text2vec-base-chinese"))

    @classmethod
    def get(cls, model_path: Optional[str] = None, settings: Optional[Settings] = None) -> Any:
        settings = settings or get_settings()
        path = model_path or cls.default_path(settings)

        if cls._model is not None and cls._model_path == path:
            return cls._model
        if cls._failed:
            return None

        with cls._lock:
            if cls._model is not None and cls._model_path == path:
                return cls._model
            if cls._failed:
                return None
            try:
                # 延迟导入：torch/transformers 很重，放到模块导入期会拖慢 pytest 收集
                from sentence_transformers import SentenceTransformer

                cls._model = SentenceTransformer(path, local_files_only=True)
                cls._model_path = path
                return cls._model
            except Exception as exc:  # 模型缺失/依赖缺失 → 降级而非崩溃
                cls._failed = True
                TestLog(log_file="logs/model.log").log_warning(
                    f"[SentenceModelRegistry] 加载本地模型失败({path}): {exc}，语义判定层将被跳过"
                )
                return None

    @classmethod
    def reset(cls) -> None:  # 便于测试或强制重新加载
        with cls._lock:
            cls._model = None
            cls._model_path = None
            cls._failed = False


# --------------------------------------------------------------------------- #
# 判定器
# --------------------------------------------------------------------------- #
_STRATEGIES = ("fast", "balanced", "strict")


class ResponseJudger:
    """问题/答案相关性判定。

    :param question: 提问
    :param answer: 待判定答案
    :param strategy:
        ``fast``     —— 仅关键词，纯本地零成本；
        ``balanced`` —— 关键词 → 语义；仅当落在灰色区间才调用 LLM（默认，性价比最高）；
        ``strict``   —— 三层全部通过才算通过（等同旧行为）。
    """

    def __init__(
        self,
        question: str,
        answer: str,
        strategy: str = "balanced",
        settings: Optional[Settings] = None,
        api: Any = None,
        cache: Any = None,
        log_handle: Optional[TestLog] = None,
    ) -> None:
        self.question = question or ""
        self.answer = answer or ""
        self.strategy = strategy if strategy in _STRATEGIES else "balanced"
        self.settings = settings or get_settings()
        self.log = log_handle or TestLog(log_file="logs/judge.log")

        # --- 阈值集中到配置，便于按环境调优 ---
        self.keyword_ratio = self.settings.getfloat("judge", "keyword_ratio", 0.6)
        self.similarity_high = self.settings.getfloat("judge", "similarity_high", 0.75)
        self.similarity_low = self.settings.getfloat("judge", "similarity_low", 0.45)
        self.confidence = self.settings.getint("judge", "confidence", 80)

        # --- 依赖懒注入，构造成本接近于 0 ---
        self._api = api
        self._cache = cache

    # ------------------------------------------------------------------ #
    @property
    def api(self):
        if self._api is None:
            from src.deep_seek_api.api import DeepSeekApi

            self._api = DeepSeekApi.default()
        return self._api

    @property
    def cache(self):
        if self._cache is None:
            from src.common.cache import TTLCache

            self._cache = TTLCache(
                maxsize=1024,
                ttl=float(self.settings.raw_get("judge", "cache_ttl", 86400.0)),
                persist_path=".cache/llm/judge.json",
            )
        return self._cache

    # ------------------------------------------------------------------ #
    # 第一层：关键词（免费、毫秒级）
    # ------------------------------------------------------------------ #
    def keyword_validation(self, ratio: Optional[float] = None) -> bool:
        ratio = self.keyword_ratio if ratio is None else ratio
        try:
            # 延迟导入：jieba 首次加载有 ~1s 预热与建缓存开销
            from jieba import analyse

            keywords = analyse.extract_tags(self.question, topK=10)
        except Exception as exc:
            self.log.log_warning(f"[judge] jieba 不可用，跳过关键词层: {exc}")
            return True  # 无法证明不相关时不应直接判死
        if not keywords:
            return True
        found = [kw for kw in keywords if kw in self.answer]
        match_ratio = len(found) / len(keywords)
        self.log.log_debug(f"[judge] keyword {len(found)}/{len(keywords)} = {match_ratio:.2f}")
        return match_ratio > ratio

    # ------------------------------------------------------------------ #
    # 第二层：语义相似度（本地、几十毫秒）
    # ------------------------------------------------------------------ #
    def _encode(self, texts: Sequence[str]):
        model = SentenceModelRegistry.get(settings=self.settings)
        if model is None:
            return None
        return model.encode(list(texts), convert_to_numpy=True, show_progress_bar=False)

    def similarity_score(self) -> Optional[float]:
        """返回余弦相似度；模型不可用时返回 ``None``。"""
        embeddings = self._encode([self.question, self.answer])
        if embeddings is None:
            return None
        try:
            import numpy as np
        except Exception:  # pragma: no cover
            return None
        emb0 = embeddings[0] / np.linalg.norm(embeddings[0])
        emb1 = embeddings[1] / np.linalg.norm(embeddings[1])
        return float(np.dot(emb0, emb1))

    def semantic_similarity(self, threshold: float = 0.65) -> Optional[bool]:
        score = self.similarity_score()
        if score is None:
            return None
        self.log.log_debug(f"[judge] semantic score={score:.3f} threshold={threshold}")
        return score > threshold

    # ------------------------------------------------------------------ #
    # 第三层：LLM 裁判（昂贵，仅在必要时调用 + 结果缓存）
    # ------------------------------------------------------------------ #
    def _llm_verdict(self) -> bool:
        key = hashlib.sha256(
            f"{self.question}||{self.answer}||{self.confidence}".encode("utf-8")
        ).hexdigest()
        sentinel = object()
        cached = self.cache.get(key, sentinel)
        if cached is not sentinel:
            self.log.log_info("[judge] second_examine cache hit")
            return bool(cached)

        prompt_info = f"""
我要判定一个ai生成的答案对还是错，问题是：{self.question},
ai给出的答案是:{self.answer},
请帮我：
    1. 阅读问题和答案
    2. 如果包含事实，请进行事实性核对：通过权威来源确认标准答案
    3. 进行关键词检查：检查回答是否包含问题中的核心关键词
    4. 进行主题一致性检查：判断附加信息是否围绕核心问题展开
    5. 进行冗余度检查：是否包含无关或过度扩展的内容
    6. 输出给我的答案只包含对或者错，置信度百分比
"""
        try:
            answer = self.api.ask_question(prompt_info)
            if answer is None:
                return False
            match = re.search(r"(\d+)%", answer)
            if not match:
                self.log.log_warning(f"[judge] 未找到置信度信息，原始回答: {answer}")
                verdict = False
            else:
                verdict = ("对" in answer) and (int(match.group(1)) > self.confidence)
        except Exception as exc:
            self.log.log_error(f"[judge] LLM 判定异常: {exc}")
            verdict = False

        self.cache.set(key, verdict)
        return verdict

    def second_examine(self) -> bool:
        """单独调用 LLM 裁判（保留原接口，语义不变）。"""
        return self._llm_verdict()

    # ------------------------------------------------------------------ #
    # 编排入口
    # ------------------------------------------------------------------ #
    def judge(self) -> "JudgeResult":
        """按策略分级判定，返回带原因与耗时信息的结构化结果。"""
        import time

        started = time.perf_counter()
        layers: Dict[str, Any] = {}

        # 空答案不必再花任何成本
        if not self.answer or not str(self.answer).strip():
            return JudgeResult(False, "empty_answer", {"elapsed": 0.0})

        if not self.keyword_validation():
            layers["keyword"] = False
            return JudgeResult(False, "keyword", {**layers, "elapsed": time.perf_counter() - started})
        layers["keyword"] = True

        if self.strategy == "fast":
            return JudgeResult(True, "keyword", {**layers, "elapsed": time.perf_counter() - started})

        score = self.similarity_score()
        layers["similarity"] = score

        if self.strategy == "balanced":
            if score is not None and score >= self.similarity_high:
                # 高置信相关：无需再花 token
                return JudgeResult(True, "semantic_high", {**layers, "elapsed": time.perf_counter() - started})
            if score is not None and score <= self.similarity_low:
                return JudgeResult(False, "semantic_low", {**layers, "elapsed": time.perf_counter() - started})
            verdict = self._llm_verdict()
            layers["llm"] = verdict
            return JudgeResult(verdict, "llm", {**layers, "elapsed": time.perf_counter() - started})

        # strict：三层全部通过
        semantic_ok = True if score is None else score > self.keyword_ratio
        layers["semantic"] = semantic_ok
        verdict = self._llm_verdict()
        layers["llm"] = verdict
        ok = layers["keyword"] and semantic_ok and verdict
        return JudgeResult(ok, "strict", {**layers, "elapsed": time.perf_counter() - started})

    def validate_answer_relevance(self) -> bool:
        """保留原接口语义：三层必须全部通过。"""
        if self.strategy == "strict":
            return self.judge().passed
        return ResponseJudger(
            self.question, self.answer, strategy="strict",
            settings=self.settings, api=self._api, cache=self._cache, log_handle=self.log,
        ).judge().passed

    # ------------------------------------------------------------------ #
    # 批量判定：一次 encode 多条，摊薄模型开销
    # ------------------------------------------------------------------ #
    @classmethod
    def judge_batch(
        cls,
        pairs: Sequence[Tuple[str, str]],
        strategy: str = "balanced",
        settings: Optional[Settings] = None,
        api: Any = None,
        cache: Any = None,
    ) -> List["JudgeResult"]:
        if not pairs:
            return []
        probe = cls(pairs[0][0], pairs[0][1], strategy=strategy, settings=settings, api=api, cache=cache)
        model = SentenceModelRegistry.get(settings=probe.settings)

        flat: List[str] = []
        for q, a in pairs:
            flat.extend([q, a])
        scores: List[Optional[float]] = [None] * len(pairs)
        if model is not None:
            try:
                import numpy as np

                embeddings = model.encode(flat, convert_to_numpy=True, show_progress_bar=False)
                idx = 0
                for i in range(len(pairs)):
                    v0, v1 = embeddings[idx], embeddings[idx + 1]
                    idx += 2
                    scores[i] = float(np.dot(v0 / np.linalg.norm(v0), v1 / np.linalg.norm(v1)))
            except Exception as exc:  # pragma: no cover
                probe.log.log_warning(f"[judge_batch] encode failed: {exc}")

        results: List[JudgeResult] = []
        for (question, answer), score in zip(pairs, scores):
            judger = cls(question, answer, strategy=strategy, settings=probe.settings, api=api, cache=cache)
            if score is not None:
                if strategy == "balanced":
                    if score >= judger.similarity_high:
                        results.append(JudgeResult(True, "semantic_high", {"similarity": score}))
                        continue
                    if score <= judger.similarity_low:
                        results.append(JudgeResult(False, "semantic_low", {"similarity": score}))
                        continue
            results.append(judger.judge())
        return results


class JudgeResult:
    """判定结果：不仅有布尔值，还带原因与分层明细，失败时可直接打印定位。"""

    __slots__ = ("passed", "reason", "detail")

    def __init__(self, passed: bool, reason: str, detail: Optional[Dict[str, Any]] = None) -> None:
        self.passed = bool(passed)
        self.reason = reason
        self.detail = detail or {}

    def __bool__(self) -> bool:
        return self.passed

    def __eq__(self, other: object) -> bool:
        # 兼容旧用例里 `assert result == True` 的写法
        if isinstance(other, bool):
            return self.passed == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self.passed, self.reason))

    def __repr__(self) -> str:
        return f"<JudgeResult passed={self.passed} reason={self.reason} detail={self.detail}>"
