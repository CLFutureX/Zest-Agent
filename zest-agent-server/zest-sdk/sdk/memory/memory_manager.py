"""Memory Manager — 业务逻辑层。

负责记忆检索编排、去重判断、BM25 相似度计算等业务逻辑。
所有 I/O 操作委托给 MemoryStore 接口。

基础记忆已拆分为四种分类，每条记忆有唯一 ID：
    profile         — 用户个人信息（身份、账号、联系方式等）
    preferences     — 用户偏好（语言风格、代码偏好、工作习惯等）
    domain_context  — 领域知识（业务领域规则、行业术语等）
    project_context — 项目/程序上下文（仓库结构、技术栈、规范等）
"""

import logging
import threading
from datetime import datetime
from typing import Any, ClassVar
 
import jieba
from pydantic import BaseModel, Field, model_validator

from common.storage.memory.base import BaseMemoryEvent, ExecutionTrace, ExperienceMemory
from common.storage.memory.memory_store_factory import (
    create_base_memory_store,
    create_experience_memory_store,
)
from common.storage.memory.store import MemoryCategory, MemoryEntry, MemoryStore
from common.storage.storage_settings import StorageSettings
from sdk.event.event_center import EventConsumer
from sdk.llm.message import Message, TextContent 

logger = logging.getLogger(__name__)


class MemoryManager(BaseModel):
    """记忆管理器 — 业务逻辑层。

    依赖 MemoryStore 接口进行数据读写，自身只负责：
    - base memory (4 categories) + experience memory 的检索编排
    - 经验去重判断（执行轨迹比对 + BM25 相似度）
    - embedding 维度校验
    """

    DEFAULT_K: ClassVar[int] = 5
    DEFAULT_THRESHOLD: ClassVar[float] = 0.55
    DEFAULT_NUM_CANDIDATES: ClassVar[int] = 100
    VALID_FEEDBACK_TYPES: ClassVar[set[str]] = {"positive", "negative", "optimization"}

    # 存储层
    base_store: MemoryStore | None = Field(default=None)
    experience_store: MemoryStore | None = Field(default=None)

    # # 后端配置
    # base_backend: str = Field()
    # experience_backend: str = Field()
 

    # 配置
    storage_settings: StorageSettings | None = Field(default=None)

    # 记忆开关：按用户配置决定是否启用基础记忆 / 经验记忆
    enable_base_memory: bool = Field(default=True)
    enable_experience_memory: bool = Field(default=True)

    class Config:
        arbitrary_types_allowed = True

    @model_validator(mode="after")
    def _initialize_stores(self) -> "MemoryManager":
        """根据开关自动初始化对应 store：仅在开启时初始化。"""
        # 只有开启基础记忆才初始化 store
        if self.enable_base_memory and self.base_store is None:
            self.base_store = create_base_memory_store( 
                storage_settings=self.storage_settings,
            )

        # 只有开启经验记忆才初始化 store
        if self.enable_experience_memory and self.experience_store is None:
            self.experience_store = create_experience_memory_store( 
                storage_settings=self.storage_settings,
            )

        return self

    @classmethod
    def create(
        cls,
        # base_backend: str = "local",
        # experience_backend: str = "es",
        storage_settings: StorageSettings | None = None,  
        enable_base_memory: bool = True,
        enable_experience_memory: bool = True,
    ) -> "MemoryManager":
        """工厂方法：创建 MemoryManager 实例（支持开关）"""
        return cls(
            # base_backend=base_backend,
            # experience_backend=experience_backend,
            storage_settings=storage_settings,  
            enable_base_memory=enable_base_memory,
            enable_experience_memory=enable_experience_memory,
        )

    # ------------------------------------------------------------------
    # 公共 API — 分类记忆
    # ------------------------------------------------------------------

    def get_user_memory(self, user_message: Message) -> dict[str, Any] | None:
        """加载用户记忆（基础记忆 + 经验记忆，受开关控制）"""
        if not user_message.user_id:
            return None

        categorized_memory = {}
        base_memory_str = ""
        experience_memory = []
        doc_ids = []

        # --------------------------
        # 基础记忆开关
        # --------------------------
        if self.enable_base_memory and self.base_store is not None:
            categorized_memory = self._load_categorized_base_memory(user_message.user_id)
            parts = []
            for cat in MemoryCategory:
                val = categorized_memory.get(cat.value, "")
                if val:
                    parts.append(f"[{cat.value}]\n{val}")
            base_memory_str = "\n".join(parts) if parts else ""
     
        # --------------------------
        # 经验记忆开关
        # --------------------------
        if self.enable_experience_memory and self.experience_store is not None:
            content = ""
        if user_message.content and len(user_message.content) > 0:
            if user_message.content and len(user_message.content) > 0:
                content = (
                    user_message.content[0].text
                    if isinstance(user_message.content[0], TextContent)
                    else ""
                )
            experience_memory, doc_ids = self._search_experience_memory(
                user_message.user_id, content
            )
        
        return {
            "base_memory": categorized_memory,
            "base_memory_str": base_memory_str,
            "experience_memory": experience_memory,
            "doc_ids": doc_ids,
        }
     

    def build_base_memory(
        self,
        user_id: str,
        content: str | dict | MemoryEntry,
        category: MemoryCategory | str | None = None,
        *,
        mode: str = "append",
    ) -> str:

        if category is None:
            category = MemoryCategory.PROFILE
        elif isinstance(category, str):
            try:
                category = MemoryCategory(category)
            except ValueError:
                logger.warning(f"无效分类 {category}，使用 profile")
                category = MemoryCategory.PROFILE

        if isinstance(content, MemoryEntry):
            entry = content
        elif isinstance(content, dict):
            entry = MemoryEntry(
                name=content.get("name", ""),
                description=content.get("description", ""),
                content=content.get("content", str(content)),
            )
        else:
            entry = MemoryEntry(content=str(content))

        if not self.enable_base_memory or self.base_store is None:
            logger.info("基础记忆未启用，跳过写入")
            return ""
        return self.base_store.write_category(user_id, category, entry, mode=mode)

    def update_base_memory_entry(
        self, user_id: str, entry: MemoryEntry, category: MemoryCategory | str | None = None
    ) -> bool:
        # if not self.enable_base_memory:
        #     return False
        # ...（逻辑不变）
        if category is None:
            category = MemoryCategory.PROFILE
        elif isinstance(category, str):
            category = MemoryCategory(category)
        return self.base_store.update_entry(user_id, category, entry)

    def delete_base_memory_entry(
        self, user_id: str, entry_id: str, category: MemoryCategory | str | None = None
    ) -> bool:
        # if not self.enable_base_memory:
        #     return False
        if category is None:
            category = MemoryCategory.PROFILE
        elif isinstance(category, str):
            category = MemoryCategory(category)
        return self.base_store.delete_entry(user_id, category, entry_id)

    def build_experience(self, experience: ExperienceMemory) -> str:
        """保存经验记忆：按相似度+轨迹一致性+反馈类型决策。

        决策矩阵（检索阈值 0.7）：
        - 无相似经验 -> new
        - 轨迹完全一致 + 反馈相同 -> skip
        - 轨迹完全一致 + 反馈不同 -> update feedback_type
        - 轨迹部分一致 + positive -> update: 合并 execute_trace
        - 轨迹部分一致 + optimization -> review 队列（待人工审核）
        - 轨迹完全不同 -> new
        """
        if not self.enable_experience_memory or self.experience_store is None:
            logger.info("经验记忆未启用，跳过保存")
            return ""
        if not all([
            experience.user_id,
            experience.question,
            experience.solution,
            experience.domain_type,
            experience.feedback_type,
        ]):
            raise ValueError("必填字段不能为空")

        if experience.feedback_type not in self.VALID_FEEDBACK_TYPES:
            raise ValueError(f"仅支持 {self.VALID_FEEDBACK_TYPES}")

        existing_experiences, existing_ids = self._search_experience_memory(
            experience.user_id,
            query=experience.question,
            domain_type=experience.domain_type,
            threshold=0.7,
        )

        new_tools = [t.tool_name for t in experience.execute_trace]

        for idx, exp in enumerate(existing_experiences):
            old_tools = [t.tool_name for t in exp.execute_trace]
            trace_equal = (old_tools == new_tools)
            trace_overlap = bool(set(old_tools) & set(new_tools)) and not trace_equal

            if trace_equal and exp.feedback_type == experience.feedback_type:
                logger.info(f"轨迹一致且反馈相同，跳过保存：{existing_ids[idx]}")
                return existing_ids[idx]

            if trace_equal and exp.feedback_type != experience.feedback_type:
                self.experience_store.update_experience(
                    existing_ids[idx], feedback_type=experience.feedback_type,
                )
                logger.info(f"轨迹一致但反馈不同，更新 feedback_type：{existing_ids[idx]}")
                return existing_ids[idx]

            if trace_overlap:
                if experience.feedback_type == "optimization":
                    logger.warning(
                        f"optimization 反馈进入待审核队列（暂未持久化）：question={experience.question}"
                    )
                    return ""

                merged_trace = self._merge_execute_trace(exp.execute_trace, experience.execute_trace)
                self.experience_store.update_experience(
                    existing_ids[idx], execute_trace=merged_trace,
                )
                logger.info(f"轨迹部分一致，合并 execute_trace：{existing_ids[idx]}")
                return existing_ids[idx]

        doc_id = self.experience_store.save_experience(experience)
        logger.info(f"经验保存成功：{doc_id}")
        return doc_id

    def _merge_execute_trace(
        self, old: list[ExecutionTrace], new: list[ExecutionTrace]
    ) -> list[ExecutionTrace]:
        """合并两条执行轨迹：以 old 为基底，追加 new 中未出现的工具节点，保序去重。"""
        seen = {t.tool_name for t in old}
        merged = list(old)
        for t in new:
            if t.tool_name not in seen:
                merged.append(t)
                seen.add(t.tool_name)
        return merged

    def update_experience(
        self, doc_id: str, ref_count: int, solution: str | None = None, **kwargs
    ) -> bool:
        # if not self.enable_experience_memory:
        #     return False
        return self.experience_store.update_experience(
            doc_id=doc_id, ref_count=ref_count, solution=solution, **kwargs
        )

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _load_categorized_base_memory(self, user_id: str) -> dict[str, str]:
        if not self.enable_base_memory or self.base_store is None:
            return {}

        result = {}
        for cat in MemoryCategory:
            val = self.base_store.read_category(user_id, cat)
            result[cat.value] = val or ""

        if all(v == "" for v in result.values()):
            for cat in MemoryCategory:
                self.base_store.write_category(user_id, cat, "", mode="overwrite")
            logger.info(f"为 {user_id} 初始化空基础记忆")

        return result

    def _search_experience_memory(
        self, user_id: str, query: str, *, domain_type=None, feedback_type=None, threshold=None
    ) -> tuple[list[ExperienceMemory], list[str]]:
        if not self.enable_experience_memory or self.experience_store is None or not query:
            return [], []

        threshold = threshold or self.DEFAULT_THRESHOLD
        results = self.experience_store.search_experiences(
            user_id=user_id,
            query=query,
            domain_type=domain_type,
            feedback_type=feedback_type,
            k=self.DEFAULT_K,
            threshold=threshold,
        )
        return [exp for exp, _ in results], [did for _, did in results]


# ---------------------------------------------------------------------------
# BM25 工具函数
# ---------------------------------------------------------------------------

def calculate_bm25_score(new_solution: str, existing_solution: str) -> float:
    # 完全不变
    if not new_solution or not existing_solution:
        return 0.0
    try:
        def tokenize(text: str) -> list[str]:
            stop_words = {"的", "了", "是", "我", "你", "他", "在", "有", "就", "都"}
            return [w for w in jieba.cut(text) if w.strip() and w not in stop_words] or ["_empty_"]

        new_tokens = tokenize(new_solution)
        existing_tokens = tokenize(existing_solution)
        freq = {}
        for t in new_tokens:
            freq[t] = freq.get(t, 0) + 1

        k1, b = 1.2, 0.75
        score = 0.0
        for t in set(existing_tokens):
            tf = freq.get(t, 0)
            den = tf + k1 * (1 - b + b * len(new_tokens) / len(new_tokens))
            score += (tf * (k1 + 1)) / den if den else 0
        return max(0.0, score)
    except Exception as e:
        logger.error(f"BM25 计算失败: {e}")
        n = set(jieba.cut(new_solution))
        e = set(jieba.cut(existing_solution))
        return len(n & e) / len(n | e) if n | e else 0.0


# ---------------------------------------------------------------------------
# Event Consumer
# ---------------------------------------------------------------------------

class ExperienceMemoryConsumer(EventConsumer):
    def __init__(self, _memory_manager: MemoryManager, **kwargs):
        super().__init__(event_types=[ExperienceMemory], **kwargs)
        self.__memory_manager = _memory_manager

    def on_event(self, event: ExperienceMemory):
        logger.info(f"收到经验记忆事件: {event.id}")
        try:
            self.__memory_manager.build_experience(event)
            logger.info(f"处理成功: {event.id}")
        except Exception as e:
            logger.error(f"处理失败: {e}")


class BaseMemoryConsumer(EventConsumer):
    def __init__(self, _memory_manager: MemoryManager, **kwargs):
        super().__init__(event_types=[BaseMemoryEvent], **kwargs)
        self.__memory_manager = _memory_manager

    def on_event(self, event: BaseMemoryEvent):
        logger.info(f"收到基础记忆事件: {event.category}")
        try:
            self.__memory_manager.build_base_memory(user_id = event.user_id,
                                                   content = event.content,
                                                   category= event.category,
                                                   mode= event.mode)
            logger.info(f"处理成功: {event.category}")
        except Exception as e:
            logger.error(f"处理失败: {e}")

# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------

__memory_manager: MemoryManager | None = None
_memory_lock = threading.Lock()

def get_memory_manager(
    # base_backend: str = "local",
    # experience_backend: str = "es",
    storage_settings: StorageSettings | None = None, 
    enable_base_memory: bool = True,
    enable_experience_memory: bool = True,
) -> MemoryManager:
    """获取（按开关）记忆管理器全局单例。

    开关语义：取本会话传入开关与已有单例开关的「并集」——若任一会话启用了某记忆，
    则单例保留该记忆能力，避免后启动的会话因更小开关集而关闭已初始化的 store。
    """
    global __memory_manager
    with _memory_lock:
        if __memory_manager is None:
            __memory_manager = MemoryManager.create(
                # base_backend=base_backend,
                # experience_backend=experience_backend,
                storage_settings=storage_settings, 
                enable_base_memory=enable_base_memory,
                enable_experience_memory=enable_experience_memory,
            )
        else:
            # 并集策略：保留更宽的开关
            if enable_base_memory and not __memory_manager.enable_base_memory:
                __memory_manager.enable_base_memory = True
                if __memory_manager.base_store is None:
                    __memory_manager.base_store = create_base_memory_store(
                        storage_settings=__memory_manager.storage_settings,
                    )
            if enable_experience_memory and not __memory_manager.enable_experience_memory:
                __memory_manager.enable_experience_memory = True
                if __memory_manager.experience_store is None:
                    __memory_manager.experience_store = create_experience_memory_store(
                        storage_settings=__memory_manager.storage_settings,
                    )
    return __memory_manager