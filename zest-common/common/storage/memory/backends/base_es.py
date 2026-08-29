"""Layer 3 实现 — Elasticsearch 基础记忆后端 (ESBaseMemoryStore)。

类名保留为 ESBaseMemoryStore 以向后兼容。机制层：结构化文档的 ES CRUD。
"""

from datetime import datetime
from typing import Any

from common.storage.memory.backend import BaseMemoryBackend
from common.storage.memory.base import MemoryCategory, MemoryEntry
from common.storage.memory.elasticsearch_config import ElasticsearchConfig
from common.storage.memory.utils import entry_to_md
from common.logger import get_logger

logger = get_logger(__name__)


class ESBaseMemoryStore(BaseMemoryBackend):
    """基础记忆 ES 存储。"""

    def __init__(self, es_config: ElasticsearchConfig) -> None:
        from elasticsearch import Elasticsearch, exceptions as es_exceptions

        self._collection_name = f"{es_config.collection_name}_base"

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

        self._create_index_if_not_exists()
        logger.info(f"ESBaseMemoryStore 初始化成功，索引: {self._collection_name}")

    def _create_index_if_not_exists(self) -> None:
        if self._es_client.indices.exists(index=self._collection_name):
            return
        mapping = {
            "mappings": {
                "properties": {
                    "user_id": {"type": "keyword"},
                    "category": {"type": "keyword"},
                    "entry_id": {"type": "keyword"},
                    "name": {"type": "text"},
                    "description": {"type": "text"},
                    "content": {"type": "text"},
                    "created_at": {"type": "keyword"},
                    "updated_at": {"type": "keyword"},
                    "version": {"type": "integer"}
                }
            },
            "settings": {"number_of_shards": 1, "number_of_replicas": 0},
        }
        self._es_client.indices.create(index=self._collection_name, body=mapping)

    def _doc_id(self, user_id: str, category: MemoryCategory, entry_id: str) -> str:
        return f"{user_id}:{category.value}:{entry_id}"

    def _entry_from_source(self, source: dict[str, Any]) -> MemoryEntry:
        return MemoryEntry(
            id=source.get("entry_id", ""),
            name=source.get("name", ""),
            description=source.get("description", ""),
            content=source.get("content", ""),
            created_at=source.get("created_at", datetime.now().strftime("%Y-%m-%d %H:%M")),
            updated_at=source.get("updated_at", datetime.now().strftime("%Y-%m-%d %H:%M")),
        )

    def read_category_entries(self, user_id: str, entry_ids: list[str] | None, category: MemoryCategory) -> list[MemoryEntry]:
        if entry_ids:
            entry_ids = [entry for entry in entry_ids if entry]
        filters = [
            {"term": {"user_id": user_id}},
            {"term": {"category": category.value}},
        ]
        if entry_ids:
            filters.append({"terms": {"entry_id": entry_ids}})

        logger.info(
            "ES基础记忆查询: user_id=%s category=%s entry_ids=%s",
            user_id,
            category.value,
            entry_ids,
        )

        query = {
            "query": {
                "bool": {
                    "filter": filters
                }
            },
            "size": 1000,
            "sort": [{"updated_at": {"order": "asc"}}, {"entry_id": {"order": "asc"}}],
        }
        entries: list[MemoryEntry] = []
        try:
            response = self._es_client.search(index=self._collection_name, body=query)
            entries = [self._entry_from_source(hit.get("_source", {})) for hit in response.get("hits", {}).get("hits", [])]
        except Exception as e:
            logger.error(f"read_category_entries error:{e} ")
        logger.info(
            "ES基础记忆查询完成: user_id=%s category=%s entry_ids=%s returned=%s",
            user_id,
            category.value,
            entry_ids,
            len(entries),
        )
        return entries

    def read_category(self, user_id: str, category: MemoryCategory) -> str:
        entries = self.read_category_entries(user_id, None, category)
        return "".join(entry_to_md(entry) for entry in entries).strip() if entries else ""

    def write_category(
        self, user_id: str, category: MemoryCategory, entry: MemoryEntry | str | None = None, *, mode: str = "append"
    ) -> str | None:
        if entry is None or (isinstance(entry, str) and not entry.strip()):
            return None
        if isinstance(entry, str):
            entry = MemoryEntry(content=entry)

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        if not entry.created_at:
            entry.created_at = current_time
        entry.updated_at = current_time

        if mode == "overwrite":
            existing_entries = self.read_category_entries(user_id, None, category)
            for existing in existing_entries:
                self.delete_entry(user_id, category, existing.id)

        document = {
            "user_id": user_id,
            "category": category.value,
            "entry_id": entry.id,
            "name": entry.name,
            "description": entry.description,
            "content": entry.content,
            "created_at": entry.created_at,
            "updated_at": entry.updated_at,
        }

        self._es_client.index(
            index=self._collection_name,
            id=self._doc_id(user_id, category, entry.id),
            document=document,
            refresh="wait_for",
        )
        return entry.id

    def update_entry(self, user_id: str, category: MemoryCategory, entry: MemoryEntry) -> bool:
        entry.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.write_category(user_id, category, entry, mode="append")
        return True

    def delete_entry(self, user_id: str, category: MemoryCategory, entry_id: str) -> bool:
        try:
            self._es_client.delete(
                index=self._collection_name,
                id=self._doc_id(user_id, category, entry_id),
                refresh="wait_for",
            )
            return True
        except Exception:
            return False

    def exists_category(self, user_id: str, category: MemoryCategory) -> bool:
        return bool(self.read_category_entries(user_id, None, category))

    def read_all_categories(self, user_id: str) -> dict[str, str]:
        return {category.value: self.read_category(user_id, category) for category in MemoryCategory}
