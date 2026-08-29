"""Layer 3 实现 — Elasticsearch 经验记忆后端 (ESMemoryStore)。

类名保留为 ESMemoryStore 以向后兼容。机制层：经验的向量存取与 KNN 检索。
仅实现 ExperienceMemoryBackend，不再含 base memory 的 NotImplementedError 桩。
"""

from datetime import datetime
from typing import Any

from common.storage.memory.backend import ExperienceMemoryBackend
from common.storage.memory.base import ExperienceMemory
from common.storage.memory.elasticsearch_config import ElasticsearchConfig
from common.storage.memory.embedding.embedding_base import EmbeddingBase
from common.logger import get_logger

logger = get_logger(__name__)


class ESMemoryStore(ExperienceMemoryBackend):
    """基于 Elasticsearch 的经验记忆存储。"""

    DEFAULT_K: int = 5
    DEFAULT_NUM_CANDIDATES: int = 100
    VALID_FEEDBACK_TYPES: set[str] = {"positive", "negative"}

    def __init__(self, es_config: ElasticsearchConfig, embedding_base: EmbeddingBase) -> None:
        from elasticsearch import Elasticsearch, exceptions as es_exceptions

        self._embedding_base = embedding_base
        self._collection_name = es_config.collection_name
        self._embedding_dims = es_config.embedding_model_dims

        if es_config.cloud_id:
            self._es_client = Elasticsearch(
                cloud_id=es_config.cloud_id,
                api_key=es_config.api_key,
                verify_certs=es_config.verify_certs,
                headers=es_config.headers or {},
            )
        else:
            host_str = f"{es_config.host}" if es_config.port is None else f"{es_config.host}:{es_config.port}"
            self._es_client = Elasticsearch(
                hosts=[host_str],
                basic_auth=(es_config.user, es_config.password) if es_config.user and es_config.password else None,
                verify_certs=es_config.verify_certs,
                headers=es_config.headers or {},
            )

        if not self._es_client.ping():
            raise es_exceptions.ConnectionError("ES连接失败")

        self._create_vector_index_if_not_exists()
        logger.info(f"ESMemoryStore 初始化成功，索引: {self._collection_name}")

    def _create_vector_index_if_not_exists(self) -> None:
        try:
            if self._es_client.indices.exists(index=self._collection_name):
                return

            index_mapping = {
                "mappings": {
                    "properties": {
                        "user_id": {"type": "keyword"},
                        "question": {"type": "text"},
                        "solution": {"type": "text"},
                        "domain_type": {"type": "keyword"},
                        "feedback_type": {"type": "keyword"},
                        "execute_trace": {"type": "nested", "properties": {
                            "tool_name": {"type": "keyword", "ignore_above": 64},
                            "choice_reason": {"type": "text"},
                        }},
                        "ref_count": {"type": "integer"},
                        "created_at": {"type": "date", "format": "yyyy-MM-dd HH:mm:ss"},
                        "updated_at": {"type": "date", "format": "yyyy-MM-dd HH:mm:ss"},
                        "embedding_vector": {
                            "type": "dense_vector", "dims": self._embedding_dims,
                            "index": True, "similarity": "cosine",
                            "index_options": {"type": "hnsw", "m": 16, "ef_construction": 100},
                        },
                    }
                },
                "settings": {"number_of_shards": 1, "number_of_replicas": 0},
            }
            self._es_client.indices.create(index=self._collection_name, body=index_mapping)
            logger.info(f"向量索引 {self._collection_name} 创建成功")
        except Exception as e:
            raise Exception(f"Index check/create failed: {e}")

    def save_experience(self, experience: ExperienceMemory) -> str:
        if not all([experience.user_id, experience.question, experience.solution,
                     experience.domain_type, experience.feedback_type]):
            raise ValueError("经验字段 user_id/question/solution/domain_type/feedback_type 不能为空")

        if experience.feedback_type not in self.VALID_FEEDBACK_TYPES:
            raise ValueError(f"反馈类型必须是 {self.VALID_FEEDBACK_TYPES} 之一")

        embedding_vector = self._embedding_base.get_embedding(experience.question)
        if len(embedding_vector) != self._embedding_dims:
            raise ValueError(f"向量维度不匹配: 生成 {len(embedding_vector)} 维，预期 {self._embedding_dims} 维")

        current_time = datetime.now()
        created_at = experience.created_at if experience.created_at else current_time
        updated_at = experience.updated_at if experience.updated_at else created_at

        doc = {
            "user_id": experience.user_id,
            "question": experience.question,
            "solution": experience.solution,
            "domain_type": experience.domain_type,
            "feedback_type": experience.feedback_type,
            "execute_trace": [t.model_dump() for t in experience.execute_trace],
            "embedding_vector": embedding_vector,
            "ref_count": 0,
            "created_at": created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": updated_at.strftime("%Y-%m-%d %H:%M:%S"),
        }

        response = self._es_client.index(index=self._collection_name, document=doc)
        doc_id = response["_id"]
        logger.info(f"经验保存成功，文档ID: {doc_id}")
        return doc_id

    def update_experience(self, doc_id: str, **kwargs: Any) -> bool:
        update_data: dict[str, Any] = {"updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

        if "solution" in kwargs and kwargs["solution"] is not None:
            update_data["solution"] = kwargs["solution"]

        if "execute_trace" in kwargs and kwargs["execute_trace"] is not None:
            update_data["execute_trace"] = [
                t.model_dump_json() if hasattr(t, "model_dump_json") else t for t in kwargs["execute_trace"]
            ]

        if "question" in kwargs and kwargs["question"] is not None:
            update_data["question"] = kwargs["question"]
            update_data["embedding_vector"] = self._embedding_base.get_embedding(kwargs["question"])

        if "ref_count" in kwargs:
            update_data["ref_count"] = kwargs["ref_count"]

        if "feedback_type" in kwargs and kwargs["feedback_type"] is not None:
            update_data["feedback_type"] = kwargs["feedback_type"]

        self._es_client.update(index=self._collection_name, id=doc_id, body={"doc": update_data})
        logger.info(f"经验文档 {doc_id} 更新成功")
        return True

    def search_experiences(
        self, user_id: str, query: str, *,
        domain_type: str | None = None, feedback_type: str | None = None,
        k: int = 5, threshold: float = 0.85,
    ) -> list[tuple[ExperienceMemory, str]]:
        filter_conditions: list[dict] = [{"term": {"user_id": user_id}}]
        if feedback_type:
            filter_conditions.append({"term": {"feedback_type": feedback_type}})
        if domain_type:
            filter_conditions.append({"term": {"domain_type": domain_type}})

        query_body = {
            "size": k,
            "_source": [
                "user_id", "question", "solution", "domain_type",
                "execute_trace", "feedback_type", "created_at", "updated_at"
            ],
        }
        if query and query.strip():
            query_vector = self._embedding_base.get_embedding(query)
            if len(query_vector) != self._embedding_dims:
                raise ValueError(f"向量维度不匹配: 生成 {len(query_vector)} 维，预期 {self._embedding_dims} 维")
            query_body['knn'] = {"field": "embedding_vector", "query_vector": query_vector,
                     "k": k, "num_candidates": self.DEFAULT_NUM_CANDIDATES,
                     "filter": filter_conditions}
        else:
            query_body["query"] = {
                "bool": {
                    "filter": filter_conditions
                }
            }
            threshold = -1

        try:
            response = self._es_client.search(index=self._collection_name, body=query_body)
        except Exception as e:
            logger.error(f"ES 经验检索异常: {e}", exc_info=True)
            raise

        results: list[tuple[ExperienceMemory, str]] = []
        for hit in response["hits"]["hits"]:
            score = hit.get("_score", 0.0)
            if score < threshold:
                continue
            doc_id = hit.get("_id", "")
            source = hit.get("_source", {})
            results.append((
                ExperienceMemory(
                    id=doc_id, user_id=source.get("user_id", ""),
                    question=source.get("question", ""), solution=source.get("solution", ""),
                    execute_trace=source.get("execute_trace", []),
                    domain_type=source.get("domain_type"),
                    feedback_type=source.get("feedback_type", ""),
                    created_at=datetime.strptime(source.get("created_at", ""), "%Y-%m-%d %H:%M:%S") if source.get("created_at") else None,
                    updated_at=datetime.strptime(source.get("updated_at", ""), "%Y-%m-%d %H:%M:%S") if source.get("updated_at") else None,
                ),
                doc_id,
            ))

        logger.info(f"用户 {user_id} 经验检索完成，召回 {len(results)} 条有效结果")
        return results
