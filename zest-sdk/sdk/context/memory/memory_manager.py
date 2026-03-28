import json
import logging
from datetime import datetime
from pathlib import Path
import threading
from typing import Any, ClassVar
import uuid

import jieba
from elasticsearch import Elasticsearch, exceptions as es_exceptions
from pydantic import BaseModel, Field, PrivateAttr

from sdk.context.memory.base import ExperienceMemory
from sdk.context.memory.elasticsearch_config import ElasticsearchConfig
from sdk.context.memory.embedding.embedding_base import EmbeddingBase
from sdk.event.event_center import EventConsumer
from sdk.llm.message import Message, TextContent

# 规范日志器（保留）
logger = logging.getLogger(__name__)


class MemoryManager(BaseModel):
    # 新增：抽离可配置参数，避免硬编码
    # 核心修复：用 ClassVar + 类型注解标记类常量（非模型字段）
    DEFAULT_K: ClassVar[int] = 5
    DEFAULT_THRESHOLD: ClassVar[float] = 0.85
    DEFAULT_NUM_CANDIDATES: ClassVar[int] = 100
    DEFAULT_EF_SEARCH: ClassVar[int] = 50
    VALID_FEEDBACK_TYPES: ClassVar[set[str]] = {"positive", "negative"}
    embedding_base: EmbeddingBase = Field()
    base_memory_dir: str = Field(default="./memory", description=" 记忆目录")
    _es_client: Elasticsearch = PrivateAttr()
    _embedding_dims: int = PrivateAttr()
    _collection_name: str = PrivateAttr()

    def __init__(
        self,
        embedding_base: EmbeddingBase,
        base_memory_dir: str,
        elastic_config: ElasticsearchConfig,
    ):
        super().__init__(embedding_base=embedding_base, base_memory_dir=base_memory_dir)
        # 本地内存目录初始化（保留，逻辑正确）
        Path(self.base_memory_dir).mkdir(parents=True, exist_ok=True)

        # ES客户端初始化（保留，逻辑正确） - 后面应该将这个配置也作为属性，最好了

        if elastic_config.cloud_id:
            self._es_client = Elasticsearch(
                cloud_id=elastic_config.cloud_id,
                api_key=elastic_config.api_key,
                verify_certs=elastic_config.verify_certs,
                headers=elastic_config.headers or {},
            )
        else:
            self._es_client = Elasticsearch(
                hosts=[
                    f"{elastic_config.host}"
                    if elastic_config.port is None
                    else f"{elastic_config.host}:{elastic_config.port}"
                ],
                basic_auth=(elastic_config.user, elastic_config.password)
                if elastic_config.user and elastic_config.password
                else None,
                verify_certs=elastic_config.verify_certs,
                headers=elastic_config.headers or {},
            )
        print("Hosts:", [f"{elastic_config.host}" if elastic_config.port is None else f"{elastic_config.host}:{elastic_config.port}"])
        self._collection_name = elastic_config.collection_name
        self._embedding_dims = elastic_config.embedding_model_dims

        # 新增：校验ES连接
        try:
            if not self._es_client.ping():
                raise es_exceptions.ConnectionError("ES连接失败")
            logger.info(f"ES客户端初始化成功，索引名：{self._collection_name}")

            self._create_vector_index_if_not_exists()

        except Exception as e:
            logger.error(f"ES客户端初始化失败：{str(e)}")
            raise

    def _create_vector_index_if_not_exists(self):
        """检查向量索引是否存在，不存在则创建（含dense_vector字段映射）"""
        try:
            # 1. 检查索引是否已存在
            if self._es_client.indices.exists(index=self._collection_name):
                logger.info(f"索引 {self._collection_name} 已存在，无需创建")
                return

            # 2. 定义向量索引的映射（适配ES 8.8.2）
            index_mapping = {
                "mappings": {
                    "properties": {
                        # 基础字段
                        "user_id": {"type": "keyword"},  # 用户ID（精准过滤）
                        "question": {"type": "text"},  # 问题文本（关键词检索）
                        "solution": {"type": "text"},  # 解决方案文本
                        "domain_type": {"type": "keyword"},  # 领域类型（精准过滤）
                        "feedback_type": {"type": "keyword"},  # 反馈类型（精准过滤）
                        #执行轨迹：对象数组 → 必须用 nested
                        "execute_trace": {
                            "type": "nested",
                            "properties": {
                                "tool_name": { "type": "keyword", "ignore_above": 64 },
                                "choice_reason": { "type": "text" },
                            },
                        },
                        "ref_count": {"type": "integer"},  # 引用计数（可选，后续用于LRU等策略）
                        "created_at": {"type": "date", "format": "yyyy-MM-dd HH:mm:ss"},
                        "updated_at": {"type": "date", "format": "yyyy-MM-dd HH:mm:ss"},  # 更新时间
                        # 核心向量字段（适配你的embedding_dims）
                        "embedding_vector": {
                            "type": "dense_vector",
                            "dims": self._embedding_dims,  # 从配置读取向量维度
                            "index": True,  # 开启索引（支持KNN查询）
                            "similarity": "cosine",  # 余弦相似度（文本Embedding推荐）
                            "index_options": {
                                "type": "hnsw",  # HNSW算法（近似最近邻）
                                "m": 16,  # HNSW参数（默认16）
                                "ef_construction": 100,  # 构建时的ef参数（默认100）
                            },
                        },
                    }
                },
                # 索引设置（可选，优化性能）
                "settings": {
                    "number_of_shards": 1,
                    "number_of_replicas": 0,  # 本地开发无需副本
                    "index.mapping.total_fields.limit": 2000,  # 增加字段限制（防止字段过多报错）
                },
            }

            # 3. 创建索引
            self._es_client.indices.create(
                index=self._collection_name, body=index_mapping
            )
            logger.info(
                f"向量索引 {self._collection_name} 创建成功，向量维度：{self._embedding_dims}"
            )

        except Exception as e:
            logger.error(f"检查/创建索引异常：{str(e)}")
            raise Exception(f"Index check/create failed: {e}")

    def get_user_memory(self, user_message: Message) -> dict[str, Any] | None:
        """
        加载用户记忆（本地基础记忆+ES经验记忆）
        :param user_message: 用户消息对象（含user_id/content）
        :return: 包含base_memory和experience_memory的字典
        """
        # 参数校验（保留，逻辑正确）
        if not user_message.user_id:
            return None

        # 加载本地基础记忆（保留，逻辑正确）
        base_memory = self._load_base_memory(user_message.user_id)

        # 修复：校验content是否为空列表，避免IndexError
        content = ""
        if user_message.content and len(user_message.content) > 0:
            content = (
                user_message.content[0].text
                if isinstance(user_message.content[0], TextContent)
                else ""
            )

        # 修复：参数顺序（user_id在前，content在后）
        experience_memory, doc_ids, _ = self._search_experience_memory(
            user_message.user_id, content
        )

        return {
            "base_memory": base_memory,
            "experience_memory": experience_memory,
            "doc_ids": doc_ids,
        }

    def build_base_memory(self, content: str):
        """ 直接通过文件操作系统，差异覆盖更新"""
        pass


    def _load_base_memory(self, user_id: str) -> str:
        """加载用户本地基础记忆（JSON文件） - 调整，要写入到s3中，
        或者统一的s3路径，通过user_id分离不同用户的记忆地址， 覆盖更新"""
        base_memory_file = Path(
            self.base_memory_dir + "/" + f"{user_id}_base_memory.json"
        )
        base_path_str = f"base_memory_file path: {str(base_memory_file)}"
        base_content_str = f"base_memory_file content: "

        if not base_memory_file.exists():
            base_memory_file.parent.mkdir(parents=True, exist_ok=True)
            with open(base_memory_file, "w", encoding="utf-8") as f:
                json.dump({}, f, ensure_ascii=False, indent=2)
            logger.info(
                f"用户{user_id}无本地基础记忆文件,已新建:{str(base_memory_file)}"
            )
            base_content_str += "内容为空"
            return f"{base_path_str}\n {base_content_str}\n"

        try:
            with open(base_memory_file, encoding="utf-8") as f:
                base_data = json.load(f)
            base_content_str += json.dumps(base_data, ensure_ascii=False)
            return f"{base_path_str}\n {base_content_str}\n"
        except json.JSONDecodeError as e:
            logger.error(f"用户{user_id}基础记忆文件解析失败：{str(e)}")
            return ""
        except Exception as e:
            logger.error(f"加载用户{user_id}基础记忆失败：{str(e)}")
            return ""

    # 修复：参数顺序（user_id在前，content在后），补充完整类型注解
    def _search_experience_memory(
        self,
        user_id: str,
        content: str,
        solution: str | None = None,
        domain_type: str | None = None,
        feedback_type: str | None = None,
        threshold: float = DEFAULT_THRESHOLD,
    ) -> tuple[list, list[str], list[str]]:
        if not content:
            logger.info(f"用户{user_id}查询内容为空，无相关经验记录")
            return [], [], []

        user_query = content
        try:
            # 1. 生成查询向量
            query_vector = self._get_query_embedding(user_query)

            # 2. 构建过滤条件
            filter_conditions = [{"term": {"user_id": user_id}}]
            if feedback_type:
                filter_conditions.append({"term": {"feedback_type": feedback_type}})
            if domain_type:
                filter_conditions.append({"term": {"domain_type": domain_type}})
            if solution:
                filter_conditions.append({"match": {"solution": solution}})

            # 3. ✅ 修复：使用 ES 8.8.x 支持的 KNN 查询格式
            # 注意：ES 8.8.x 的 KNN 查询需要放在顶级，而不是 bool/must 中
            query_body = {
                "knn": {
                    "field": "embedding_vector",
                    "query_vector": query_vector,
                    "k": self.DEFAULT_K,
                    "num_candidates": self.DEFAULT_NUM_CANDIDATES,
                    "filter": filter_conditions,  # 过滤条件放在 knn 内部
                },
                "size": self.DEFAULT_K,
                "_source": [
                    "id",
                    "user_id",
                    "question",
                    "solution",
                    "domain_type",
                    "execute_trace",
                    "feedback_type",
                    "created_at",
                    "updated_at",
                ],
            }

            # 4. 打印查询用于调试
            logger.debug(f"执行查询：{json.dumps(query_body, indent=2)}")

            # 5. 执行查询
            response = self._es_client.search(
                index=self._collection_name, body=query_body
            )

            # 6. 解析结果（修复遍历逻辑）
            experience_lines: list[ExperienceMemory] = []
            doc_ids = []
            solutions = []

            # ✅ 修复：正确遍历 hits
            for hit in response["hits"]["hits"]:
                # 过滤低于阈值的结果
                score = hit.get("_score", 0.0)
                if score < threshold:
                    continue

                doc_id = hit.get("_id", "无ID")
                source = hit.get("_source", {})

                doc_ids.append(doc_id)
                solutions.append(source.get("solution", "无"))
                experience_lines.append(
                    ExperienceMemory(
                        id=doc_id,
                        user_id=source.get("user_id", "无"),
                        question=source.get("question", "无"),
                        solution=source.get("solution", "无"),
                        execute_trace=source.get("execute_trace", []),
                        domain_type=source.get("domain_type", "无"),
                        feedback_type=source.get("feedback_type", "无"),
                        created_at=source.get("created_at"),
                        updated_at=source.get("updated_at"),
                    )
                )

            logger.info(f"用户{user_id}经验检索完成，召回{len(doc_ids)}条有效结果")
            return experience_lines, doc_ids, solutions

        except es_exceptions.NotFoundError:
            logger.warning(f"用户{user_id}的索引不存在")
            return [], [], []
        except es_exceptions.ConnectionError as e:
            logger.error(f"用户{user_id}ES连接异常：{str(e)}")
            raise
        except Exception as e:
            logger.error(f"用户{user_id}经验检索异常：{str(e)}", exc_info=True)
            raise

    def _get_query_embedding(self, query: str) -> list[float]:
        """生成查询文本的embedding向量"""
        try:
            embedding = self.embedding_base.get_embedding(query)
            # 校验向量维度是否匹配
            if len(embedding) != self._embedding_dims:
                raise ValueError(
                    f"向量维度不匹配：生成{len(embedding)}维，预期{self._embedding_dims}维"
                )
            return embedding
        except Exception as e:
            logger.error(f"生成查询向量失败：{str(e)}")
            raise Exception(f"Failed to get query embedding: {e}")

    def build_experience(
        self,   experience: ExperienceMemory
    ) -> str | None:
        """
        保存新的经验数据到ES（先校验重复，再保存）
        :param user_id: 用户ID
        :param question: 经验问题
        :param solution: 经验解决方案
        :param domain_type: 经验适用领域
        :param feedback_type: 反馈类型（positive/negative/neutral）
        :return: 保存成功返回文档ID，失败返回None
        """
        # 新增：参数合法性校验
        if not all([experience.user_id, experience.question, experience.solution, experience.domain_type, experience.feedback_type]):
            logger.error(
                "保存经验失败：user_id/question/solution/domain_type/feedback_type不能为空"
            )
            raise ValueError(
                "All parameters (user_id, question, solution, domain_type, feedback_type) are required."
            )
        if experience.feedback_type not in self.VALID_FEEDBACK_TYPES:
            logger.error(
                f"保存经验失败：反馈类型{experience.feedback_type}不合法（仅支持{self.VALID_FEEDBACK_TYPES}）"
            )
            raise ValueError(
                f"Feedback type must be one of {self.VALID_FEEDBACK_TYPES}"
            )

        try:
            # 修复：重复经验判断逻辑（existing_experiences[1]非空表示有相似经验）
            execute_traces, existing_ids, _ = self._search_experience_memory(
                experience.user_id, content=experience.question, domain_type=experience.domain_type,threshold=0.8
            )
            
            if existing_ids:
                new_traces_tool_names = [trace.tool_name for trace in experience.execute_trace]
                for idx,trace in enumerate(execute_traces):
                    exist_tool_names = [trace.tool_name for trace in trace.execute_trace]
                    if exist_tool_names == new_traces_tool_names:
                        logger.info(f"用户{experience.user_id}新旧经验执行轨迹完全一致，跳过保存")
                        return existing_ids[idx]
                # for exp_id, existing_solution in zip(existing_ids, existing_solutions):
                #     # 计算新solution与已存在solution的TF-IDF得分
                #     # 或者直接判断解决方案链路是否一致？直接使用确定性分析？
                #     # 这样的话，就要求解决方案，按照action链路总结
                #     tfidf_score = self._calculate_solution_bm25_score(
                #         experience.solution, existing_solution
                #     )
                #     logger.info(f"用户{experience.user_id}新旧solution BM25得分：{tfidf_score}")
                #     if tfidf_score > 2.5:  # 若相似度超过阈值，则不保存新经验
                #         logger.info(f"用户{experience.user_id}新旧solution相似度过高，跳过保存")
                #         return None
                # 目前仅更新了最新的一条相似经验的solution，后续可根据需求调整为更新所有相似经验?
                # 不更新也行- 我们继续新增
                # self.update_experience(doc_id=existing_ids[0], solution=experience.solution)
                # return existing_ids[0]

            # 生成向量并保存
            embedding_vector = self.embedding_base.get_embedding(experience.question)
            
            # ====================== 时间修复 1 ======================
            # 统一时间格式：优先使用传入的时间，没有则自动生成当前时间
            current_time = datetime.now()
            created_at = experience.created_at if experience.created_at else current_time
            updated_at = experience.updated_at if experience.updated_at else created_at
            
            # 严格按照 ES 映射格式格式化
            created_at_str = created_at.strftime("%Y-%m-%d %H:%M:%S")
            updated_at_str = updated_at.strftime("%Y-%m-%d %H:%M:%S")
            # =======================================================
            
            execute_trace_dicts = [trace.model_dump() for trace in experience.execute_trace]
            doc = {
                "user_id": experience.user_id,
                "question": experience.question,
                "solution": experience.solution,
                "domain_type": experience.domain_type,
                "feedback_type": experience.feedback_type,
                "execute_trace": execute_trace_dicts,
                "embedding_vector": embedding_vector,
                "ref_count": 0,  # 初始引用计数为0
                "created_at": created_at_str,  # 修复
                "updated_at": updated_at_str   # 修复
            }
            logger.info(f"写入经验{doc}")
            response = self._es_client.index(index=self._collection_name, document=doc)
            doc_id = response["_id"]
            logger.info(f"用户{experience.user_id}经验保存成功，文档ID：{doc_id}")
            return doc_id
        except Exception as e:
            logger.error(f"用户{experience.user_id}经验保存失败：{str(e)}")
            raise Exception(f"Failed to save experience: {e}")

    # 更新经验 - 更新时，是全量覆盖，还是仅覆盖解决方案？ 初步选择仅覆盖解决方案即可，因为 question 需要经过embedding。
    def update_experience(
        self, doc_id: str, ref_count: int,solution: str | None = None,execute_trace: list | None = None,question: str | None = None
    ) -> bool:
        try:
            
            # ====================== 时间修复 2 ======================
            # 修复：ES 不支持 "now"，必须生成标准时间字符串
            current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            update_data: dict[str, Any] = { 
                "ref_count": ref_count,  # 更新引用计数
                
                "updated_at": current_time_str,  # 修复
            }
            if solution:
                update_data["solution"] = solution
            # =======================================================
            if execute_trace is not None:
                execute_trace_str = [trace.model_dump_json() for trace in execute_trace]
                update_data["execute_trace"] = execute_trace_str
            if question:
                update_data["question"] = question
                update_data["embedding_vector"] = self.embedding_base.get_embedding(
                    question
                )
            self._es_client.update(
                index=self._collection_name, id=doc_id, body={"doc": update_data}
            )
            logger.info(f"经验文档{doc_id}更新成功")
            return True
        except Exception as e:
            logger.error(f"经验文档{doc_id}更新失败：{str(e)}")
            raise Exception(f"Failed to update experience: {e}")

        # 新增：计算新solution与召回经验solution的BM25

    def _calculate_solution_bm25_score(
        self, new_solution: str, existing_solution: str
    ) -> float:
        """
        修复版：纯 Python 实现 BM25（解决"请记录"等短文本负分问题）
        :param new_solution: 新经验的解决方案
        :param existing_solution: 已召回经验的解决方案
        :return: BM25 得分（≥0，相同字符串得分>0）
        """
        if not new_solution or not existing_solution:
            return 0.0

        try:
            # 1. 中文分词（保留短文本完整词汇）
            def tokenize(text):
                stop_words = {
                    "的",
                    "了",
                    "是",
                    "我",
                    "你",
                    "他",
                    "在",
                    "有",
                    "就",
                    "都",
                }
                tokens = [
                    word
                    for word in jieba.cut(text)
                    if word.strip() and word not in stop_words
                ]
                # 兜底：短文本分词后为空时返回占位符
                return tokens if tokens else ["_empty_"]

            # 2. 分词处理
            new_tokens = tokenize(new_solution)
            existing_tokens = tokenize(existing_solution)

            # 3. 修复核心：手动计算标准 BM25（不依赖库的IDF）
            # 3.1 统计词频
            doc_freq = {}
            for token in new_tokens:
                doc_freq[token] = doc_freq.get(token, 0) + 1

            # 3.2 BM25 参数（和ES一致）
            k1 = 1.2
            b = 0.75
            doc_len = len(new_tokens)
            avg_doc_len = doc_len  # 单文档场景

            # 3.3 标准 BM25 计算（确保无负数）
            score = 0.0
            for token in set(existing_tokens):  # 去重查询词
                tf = doc_freq.get(token, 0)
                # 手动计算IDF（单文档场景强制为1.0，避免负数）
                idf = 1.0

                # BM25 核心公式
                denominator = tf + k1 * (1 - b + b * (doc_len / avg_doc_len))
                if denominator == 0:
                    term_score = 0.0
                else:
                    term_score = idf * (tf * (k1 + 1)) / denominator

                score += max(0.0, term_score)  # 确保每一项非负

            # 最终兜底：确保得分≥0
            return max(0.0, score)

        except Exception as e:
            logger.error(f"计算 solution BM25 得分失败：{str(e)}")
            # 降级方案：词重叠率（非负）
            new_words = set(jieba.cut(new_solution))
            existing_words = set(jieba.cut(existing_solution))
            intersection = new_words.intersection(existing_words)
            union = new_words.union(existing_words)
            return len(intersection) / len(union) if union else 0.0


class ExperienceMemoryConsumer(EventConsumer):
    def __init__( self,
        conversation_id: uuid.UUID | str | None = None,
        agent_id: uuid.UUID | str | None = None,
        event_types: list[type] | None = None,
        memory_manager: MemoryManager | None = None,):
        event_types = [ExperienceMemory]
        super().__init__(
            conversation_id=conversation_id,
            agent_id=agent_id,
            event_types=event_types,
        )
        self._memory_manager = memory_manager
        
    def consume(self, event: ExperienceMemory) -> None:
        # 这里可以根据事件类型调用 MemoryManager 的方法来更新记忆
        logger.info(f"ExperienceMemoryConsumer 收到事件：{event}")
        if self._memory_manager:
            try:
                self._memory_manager.build_experience(
                    event
                )
                logger.info(f"ExperienceMemoryConsumer 成功处理事件：{event.id}")
            except Exception as e:
                logger.error(f"ExperienceMemoryConsumer 处理事件失败：{str(e)}")
        else:
            logger.warning("ExperienceMemoryConsumer 未配置 MemoryManager，无法处理事件")
        pass


# Global singleton instance
_memory_manager: MemoryManager  
_memory_lock = threading.Lock()  # 全局锁，确保线程安全

def get_memory_manager(embedding_base: EmbeddingBase,
        base_memory_dir: str,
        elastic_config: ElasticsearchConfig) -> MemoryManager:
    """全局单例 MemoryManager 获取函数（保留，逻辑正确）"""
    global _memory_manager
    with _memory_lock:
        if _memory_manager is None:
            _memory_manager = MemoryManager(embedding_base=embedding_base, 
                                           base_memory_dir=base_memory_dir, 
                                           elastic_config=elastic_config)
        return _memory_manager