"""Memory Store — 抽象基类 + File/ES 后端实现。

对齐 event_store.py 的设计模式：
    Abstract Base  →  Backend Impl (File / ES)

基础记忆按类别拆分为四种，每条记忆有唯一 ID：
    profile         — 用户个人信息（身份、账号、联系方式等）
    preferences     — 用户偏好（语言风格、代码偏好、工作习惯等）
    domain_context  — 领域知识（业务领域规则、行业术语等）
    project_context — 项目/程序上下文（仓库结构、技术栈、规范等）

每条记忆格式：
    ## {id}
    - **name**: {name}
    - **description**: {description}

    {content}

    ---
"""

from datetime import datetime
import json

import re

import uuid
from datetime import datetime

from abc import ABC, abstractmethod



from enum import Enum

from threading import RLock

from typing import Any

from common.storage.memory.base import ExperienceMemory, MemoryCategory, MemoryEntry

from common.storage.memory.elasticsearch_config import ElasticsearchConfig

from common.storage.memory.embedding.embedding_base import EmbeddingBase

from common.storage.file_store import FileStore, MemoryLRUCache

from common.logger import get_logger



logger = get_logger(__name__)






ENTRY_SEPARATOR = "\n---\n"





def entry_to_md(entry: MemoryEntry) -> str:

    """将 MemoryEntry 序列化为 markdown 段落。"""

    return (

        f"<id>{entry.id}</id>\n"

        f"<name>{entry.name}</name>\n"

        f"<description>{entry.description}</description>\n"

        f"<content>{entry.content}</content>\n"

        f"<created_time>{entry.created_at}</created_time>\n"

        f"<updated_time>{entry.updated_at}</updated_time>\n"

        f"{ENTRY_SEPARATOR}"

    )





def parse_entries(md_text: str) -> list[MemoryEntry]:

    """从 markdown 文本中解析出 MemoryEntry 列表。"""

    entries: list[MemoryEntry] = []

    blocks = md_text.split(ENTRY_SEPARATOR)



    for block in blocks:

        if not block.strip():

            continue



        id_match = re.search(r"<id>(.*?)</id>", block)

        if not id_match:

            continue



        name_match = re.search(r"<name>(.*?)</name>", block, re.DOTALL)

        desc_match = re.search(r"<description>(.*?)</description>", block, re.DOTALL)

        content_match = re.search(r"<content>(.*?)</content>", block, re.DOTALL)

        created_time_match = re.search(r"<created_time>(.*?)</created_time>", block)

        updated_time_match = re.search(r"<updated_time>(.*?)</updated_time>", block)

        entry_id = id_match.group(1)

        name = name_match.group(1) if name_match else ""

        desc = desc_match.group(1) if desc_match else ""

        content = content_match.group(1) if content_match else ""

        created_time = created_time_match.group(1) if created_time_match else datetime.now().strftime("%Y-%m-%d %H:%M")

        updated_time = updated_time_match.group(1) if updated_time_match else created_time



        entries.append(MemoryEntry(

            id=entry_id,

            name=name,

            description=desc,

            content=content,

            created_at=created_time,

            updated_at=updated_time,

        ))



    return entries





def build_index_key(user_id: str, category: MemoryCategory, entry_id: str) -> str:

    return f"{category.value}:{entry_id}:{user_id}"





def extract_index_version(index_map: dict[str, int], user_id: str, category: MemoryCategory) -> int:

    prefix = f"{category.value}:"

    suffix = f":{user_id}"

    versions = [

        version for key, version in index_map.items()

        if key.startswith(prefix) and key.endswith(suffix)

    ]

    return max(versions, default=0)





def merge_category_entries(entries: list[MemoryEntry], entry: MemoryEntry) -> list[MemoryEntry]:

    merged = list(entries)

    for index, current in enumerate(merged):

        if current.id == entry.id:

            merged[index] = entry

            return merged

    merged.append(entry)

    return merged





class MemoryStore(ABC):

    """记忆存储的抽象接口。



    仅负责数据的读/写/检索，不关心上层业务逻辑（embedding 生成、BM25 等）。

    """



    @abstractmethod

    def read_category(self, user_id: str, category: MemoryCategory) -> str:

        ...



    @abstractmethod

    def read_category_entries(self, user_id: str, entry_ids: list[str] | None, category: MemoryCategory) -> list[MemoryEntry]:

        ...



    @abstractmethod

    def write_category(

        self, user_id: str, category: MemoryCategory, entry: MemoryEntry | str, *, mode: str = "append"

    ) -> str:

        ...



    @abstractmethod

    def update_entry(self, user_id: str, category: MemoryCategory, entry: MemoryEntry) -> bool:

        ...



    @abstractmethod

    def delete_entry(self, user_id: str, category: MemoryCategory, entry_id: str) -> bool:

        ...



    @abstractmethod

    def exists_category(self, user_id: str, category: MemoryCategory) -> bool:

        ...



    def read_all_categories(self, user_id: str) -> dict[str, str]:

        return {cat.value: self.read_category(user_id, cat) for cat in MemoryCategory}



    def read_base_memory(self, user_id: str) -> str:

        cats = self.read_all_categories(user_id)

        parts = []

        for cat in MemoryCategory:

            val = cats.get(cat.value, "")

            if val:

                parts.append(f"[{cat.value}]\n{val}")

        return "\n".join(parts) if parts else ""



    def write_base_memory(self, user_id: str, content: str | dict) -> None:

        if isinstance(content, dict) and "category" in content:

            cat_str = content.pop("category")

            try:

                cat = MemoryCategory(cat_str)

            except ValueError:

                cat = MemoryCategory.PROFILE

            if isinstance(content, dict):

                entry = MemoryEntry(

                    name=content.get("name", ""),

                    description=content.get("description", ""),

                    content=content.get("content", str(content)),

                )

            else:

                entry = MemoryEntry(content=str(content))

            self.write_category(user_id, cat, entry, mode="append")

        elif isinstance(content, str):

            entry = MemoryEntry(content=content)

            self.write_category(user_id, MemoryCategory.PROFILE, entry, mode="append")

        else:

            entry = MemoryEntry(content=str(content))

            self.write_category(user_id, MemoryCategory.PROFILE, entry, mode="append")



    def exists_base_memory(self, user_id: str) -> bool:

        return any(self.exists_category(user_id, cat) for cat in MemoryCategory)



    @abstractmethod

    def save_experience(self, experience: ExperienceMemory) -> str:

        ...



    @abstractmethod

    def update_experience(self, doc_id: str, **kwargs: Any) -> bool:

        ...



    @abstractmethod

    def search_experiences(

        self,

        user_id: str,

        query: str,

        *,

        domain_type: str | None = None,

        feedback_type: str | None = None,

        k: int = 5,

        threshold: float = 0.85,

    ) -> list[tuple[ExperienceMemory, str]]:

        ...





class BaseMemoryStore(MemoryStore, ABC):

    """仅支持基础记忆的抽象存储实现。"""



    def save_experience(self, experience: ExperienceMemory) -> str:

        raise NotImplementedError(f"{self.__class__.__name__} 不支持经验记忆存储。")



    def update_experience(self, doc_id: str, **kwargs: Any) -> bool:

        raise NotImplementedError(f"{self.__class__.__name__} 不支持经验记忆更新。")



    def search_experiences(

        self,

        user_id: str,

        query: str,

        *,

        domain_type: str | None = None,

        feedback_type: str | None = None,

        k: int = 5,

        threshold: float = 0.85,

    ) -> list[tuple[ExperienceMemory, str]]:

        raise NotImplementedError(f"{self.__class__.__name__} 不支持经验记忆检索。")





# ---------------------------------------------------------------------------

# Abstract Base

# ---------------------------------------------------------------------------





# ---------------------------------------------------------------------------

# FileMemoryStore

# ---------------------------------------------------------------------------





class FileMemoryStore(BaseMemoryStore):

    """基于 FileStore 的本地记忆存储。"""



    CATEGORY_FILE_MAP = {

        MemoryCategory.PROFILE: "_profile.md",

        MemoryCategory.PREFERENCES: "_preferences.md",

        MemoryCategory.DOMAIN_CONTEXT: "_domain_context.md",

        MemoryCategory.PROJECT_CONTEXT: "_project_context.md",

    }



    def __init__(self, fs: FileStore, base_dir: str = "memory") -> None:

        self._fs = fs

        self._base_dir = base_dir



    def _category_path(self, user_id: str, category: MemoryCategory) -> str:

        suffix = self.CATEGORY_FILE_MAP[category]

        return f"{self._base_dir}/{user_id}{suffix}"



    def read_category(self, user_id: str, category: MemoryCategory) -> str:

        try:

            raw = self._fs.read(self._category_path(user_id, category))

            return raw.strip() if raw else ""

        except FileNotFoundError:

            return ""

        except Exception as e:

            logger.error(f"加载用户 {user_id} 分类 {category.value} 失败: {e}")

            return ""



    def read_category_entries(self, user_id: str, entry_ids: list[str] | None, category: MemoryCategory) -> list[MemoryEntry]:

        md_text = self.read_category(user_id, category)

        if not md_text:

            logger.debug("本地基础记忆为空: user_id=%s category=%s", user_id, category.value)
            return []

        entries = parse_entries(md_text)
        if entry_ids:
            filtered_entries = [entry for entry in entries if entry.id in entry_ids]
            logger.info(
                "本地基础记忆按ID读取: user_id=%s category=%s requested_ids=%s returned=%s",
                user_id,
                category.value,
                entry_ids,
                len(filtered_entries),
            )
            return filtered_entries
        logger.info("本地基础记忆读取: user_id=%s category=%s returned=%s", user_id, category.value, len(entries))
        return entries



    def write_category(

        self, user_id: str, category: MemoryCategory, entry: MemoryEntry | str | None = None, *, mode: str = "append"

    ) -> str | None:

        if entry is None or (isinstance(entry, str) and not entry.strip()):

            self._fs.write(self._category_path(user_id, category), "")

            logger.info(f"用户 {user_id} 分类 {category.value} 已初始化为空")

            return None



        if isinstance(entry, str):

            entry = MemoryEntry(content=entry)



        if mode == "overwrite":

            payload = entry_to_md(entry)

        else:

            existing = self.read_category(user_id, category)

            entries = parse_entries(existing)

            entries = merge_category_entries(entries, entry)

            payload = "".join(entry_to_md(e) for e in entries)



        self._fs.write(self._category_path(user_id, category), payload)

        logger.info(f"用户 {user_id} 分类 {category.value} 已写入（mode={mode}, id={entry.id}）")

        return entry.id



    def update_entry(self, user_id: str, category: MemoryCategory, entry: MemoryEntry) -> bool:

        existing = self.read_category(user_id, category)

        entries = parse_entries(existing)

        for i, current in enumerate(entries):

            if current.id == entry.id:

                entry.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

                entries[i] = entry

                payload = "".join(entry_to_md(item) for item in entries)

                self._fs.write(self._category_path(user_id, category), payload)

                logger.info(f"用户 {user_id} 分类 {category.value} 条目 {entry.id} 已更新")

                return True

        return False



    def delete_entry(self, user_id: str, category: MemoryCategory, entry_id: str) -> bool:

        existing = self.read_category(user_id, category)

        entries = parse_entries(existing)

        new_entries = [entry for entry in entries if entry.id != entry_id]

        if len(new_entries) == len(entries):

            return False

        payload = "".join(entry_to_md(entry) for entry in new_entries) if new_entries else ""

        self._fs.write(self._category_path(user_id, category), payload)

        logger.info(f"用户 {user_id} 分类 {category.value} 条目 {entry_id} 已删除")

        return True



    def exists_category(self, user_id: str, category: MemoryCategory) -> bool:

        try:

            raw = self._fs.read(self._category_path(user_id, category))

            return bool(raw and raw.strip())

        except FileNotFoundError:

            return False





class ESBaseMemoryStore(BaseMemoryStore):

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
                    
                    "version": {"type":"integer"}

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

        return bool(self.read_category_entries(user_id, None,category))



    def read_all_categories(self, user_id: str) -> dict[str, str]:

        return {category.value: self.read_category(user_id, category) for category in MemoryCategory}


class CachedBaseMemoryStore(BaseMemoryStore):



    """基础记忆缓存封装：ES + 内存索引 + LRU 内容缓存。"""
 
    def __init__(

        self,

        remote_store: BaseMemoryStore,

        cache: MemoryLRUCache,

    ) -> None:

        self._remote_store = remote_store
       # 记录缓存索引：{category: {cache_key: version}}
        self._index_store: dict[str, dict[str, int]] = {}
       # 记录真正的缓存内容：{cache_key: json.dumps({"version": version, "entry": entry.__dict__})}
        self._cache = cache

        self._lock = RLock()



    def _cache_key(self, user_id: str, memory_id: str, category: MemoryCategory) -> str:

        return f"base_memory:{user_id}:{category.value}:{memory_id}"

    def _get_entry_id(self, cache_key: str) -> str | None:
        if cache_key:
            return cache_key.split(":")[-1]
        return None


    def _category_index(self, category: MemoryCategory) -> dict[str, int]:

        return self._index_store.setdefault(category.value, {})



    def _cache_entry(

        self,

        user_id: str,

        category: MemoryCategory,

        entry: MemoryEntry,

    ) -> None:
        
        cache_key = self._cache_key(user_id, entry.id, category)

        self._category_index(category)[cache_key] = entry.version

        self._cache[cache_key] = json.dumps(

            {

                "version": entry.version,

                "entry": entry.__dict__,

            },

            ensure_ascii=False,

        )

        logger.debug(
            "基础记忆缓存写入: user_id=%s category=%s entry_id=%s version=%s",
            user_id,
            category.value,
            entry.id,
            entry.version,
        )



    def _remove_cached_entry(self, user_id: str, entry_id: str, category: MemoryCategory) -> None:

        cache_key = self._cache_key(user_id, entry_id, category)

        category_index = self._category_index(category)

        category_index.pop(cache_key, None)

        if cache_key in self._cache:

            del self._cache[cache_key]

        logger.debug(
            "基础记忆缓存删除: user_id=%s category=%s entry_id=%s",
            user_id,
            category.value,
            entry_id,
        )



    def _load_remote_entries(self, user_id: str, entry_ids: list[str] | None, category: MemoryCategory) -> list[MemoryEntry]:

        logger.info(
            "基础记忆远端读取: user_id=%s category=%s entry_ids=%s",
            user_id,
            category.value,
            entry_ids,
        )

        entries = self._remote_store.read_category_entries(user_id, entry_ids, category)

        for entry in entries:

            self._cache_entry(user_id, category, entry)

        logger.info(
            "基础记忆远端读取完成: user_id=%s category=%s requested_ids=%s loaded=%s",
            user_id,
            category.value,
            entry_ids,
            len(entries),
        )

        return entries

    def _read_cached_entries_v2(self, cache_keys:list[str], category: MemoryCategory) -> tuple[list[MemoryEntry], list[str]]:
        entries: list[MemoryEntry] = []
        un_cache_keys: list[str] = []

        for cache_key in cache_keys:

            if cache_key not in self._cache:

                un_cache_keys.append(cache_key)

                continue

            try:

                payload = json.loads(self._cache[cache_key])

            except Exception:

                logger.warning("基础记忆缓存解析失败，转远端读取: cache_key=%s", cache_key)

                un_cache_keys.append(cache_key)

                continue

            version = payload.get("version")

            entry_payload = payload.get("entry")

            if not isinstance(entry_payload, dict):

                un_cache_keys.append(cache_key)

                continue

            entry = MemoryEntry(**entry_payload)

            category_index = self._category_index(category)

            if category_index.get(cache_key) != version:

                un_cache_keys.append(cache_key)

                continue

            entries.append(entry)

        return entries, un_cache_keys

    def _build_cached_keys(self,user_id: str, entry_ids:list[str], category: MemoryCategory) -> tuple[list[str], bool]:
        category_index = self._category_index(category)
        cache_keys = []
         
        for entry_id in entry_ids:
            cache_key = self._cache_key(user_id, entry_id, category)
            if cache_key in category_index:
                cache_keys.append(cache_key)
        
        return cache_keys 
    

    def _read_cached_entries(self, user_id: str, entry_ids: list[str] | None, category: MemoryCategory) -> tuple[list[MemoryEntry], list[str] ]:
        # 先获取指定分类的索引
        # 正常来说： 先分析命中索引，过滤出索引key
        # 然后读取缓存，最终返回未命中索引。
        
        category_index = self._category_index(category)
        if entry_ids:
            cache_items = {}
            for entry_id in entry_ids:
                cache_key = self._cache_key(user_id, entry_id, category)
                version = category_index.get(cache_key)
                if version is not None:
                    cache_items[cache_key] = version
        else:
            # 遍历当前用户的基础记忆，但也只是内存中的
            cache_items = {
                cache_key: version
                for cache_key, version in category_index.items()
                if cache_key.startswith(f"base_memory:{user_id}:{category.value}:")
            }
        un_cache_keys: list[str] = []
        
        if not cache_items:
            logger.debug(
                "基础记忆缓存未命中索引: user_id=%s category=%s entry_ids=%s",
                user_id,
                category.value,
                entry_ids,
            )
            # 传了entry_ids，且不在索引中，则为uncache。
            return [], [] if not entry_ids else [
                self._cache_key(user_id, entry_id, category) for entry_id in entry_ids
            ] 

        
        entries: list[MemoryEntry] = []

        for cache_key, version in cache_items.items():

            if cache_key not in self._cache:
                un_cache_keys.append(cache_key)
                continue

            try:

                payload = json.loads(self._cache[cache_key])

            except Exception:

                logger.warning("基础记忆缓存解析失败，转远端读取: cache_key=%s", cache_key)
                un_cache_keys.append(cache_key)
                continue

            if payload.get("version") != version:
                un_cache_keys.append(cache_key)
                continue

            entry_payload = payload.get("entry")

            if not isinstance(entry_payload, dict):
                un_cache_keys.append(cache_key)
                continue

            entries.append(MemoryEntry(**entry_payload))

        logger.info(
            "基础记忆缓存读取完成: user_id=%s category=%s requested_ids=%s hit=%s miss=%s",
            user_id,
            category.value,
            entry_ids,
            len(entries),
            len(un_cache_keys),
        )
        return entries, un_cache_keys

    def _read_user_category_entries(self, user_id: str, category: MemoryCategory) -> list[MemoryEntry]:
        return self._load_remote_entries(

                user_id,
                None,
                category,

            )


    def read_category_entries(self, user_id: str, entry_ids: list[str] | None, category: MemoryCategory) -> list[MemoryEntry]:



        with self._lock:
            
            if not entry_ids:
                return self._read_user_category_entries(user_id, category)
            
            cache_keys = self._build_cached_keys(user_id, entry_ids, category)
            
           # 读缓存-
            entries, un_cache_keys = self._read_cached_entries_v2(cache_keys, category)

        
           # 不存在未命中的缓存且传了过滤值，且不需要全量检索
            if not un_cache_keys:
                return entries
            
            un_cache_entry_ids = [

                entry_id

                for cache_key in un_cache_keys

                if (entry_id := self._get_entry_id(cache_key)) is not None

            ]


            remote_entries = self._load_remote_entries(

                user_id,

                un_cache_entry_ids if entry_ids else None,

                category,

            )

            cached_entry_ids = {entry.id for entry in entries}

            merged_entries = entries + [entry for entry in remote_entries if entry.id not in cached_entry_ids]

            logger.info(

                "基础记忆查询完成: user_id=%s category=%s requested_ids=%s returned=%s",

                user_id,

                category.value,

                entry_ids,

                len(merged_entries),

            )

            return merged_entries


    def read_category(self, user_id: str, category: MemoryCategory) -> str:
        # 读，缓存-不存在就读远程，然后填充缓存
        entries = self.read_category_entries(user_id, None, category)

        return "".join(entry_to_md(entry) for entry in entries).strip() if entries else ""


    def write_category(

        self, user_id: str, category: MemoryCategory, entry: MemoryEntry | str | None = None, *, mode: str = "append"

    ) -> str | None:

        with self._lock:

            entry_id = self._remote_store.write_category(user_id, category, entry, mode=mode)

            self._load_remote_entries(user_id, [entry_id], category)

            return entry_id


    def update_entry(self, user_id: str, category: MemoryCategory, entry: MemoryEntry) -> bool:

        with self._lock:

            updated = self._remote_store.update_entry(user_id, category, entry)

            if not updated:

                return False

            self._cache_entry(user_id, category, entry )

            return True



    def delete_entry(self, user_id: str, category: MemoryCategory, entry_id: str) -> bool:

        with self._lock:

            deleted = self._remote_store.delete_entry(user_id, category, entry_id)

            if not deleted:

                return False

            self._remove_cached_entry(user_id, entry_id, category) 
            return True



    def exists_category(self, user_id: str, category: MemoryCategory) -> bool:

        entries = self.read_category_entries(user_id, None, category)

        return bool(entries)


    def read_all_categories(self, user_id: str) -> dict[str, str]:

        return {category.value: self.read_category(user_id, category) for category in MemoryCategory}





# ---------------------------------------------------------------------------

# ESMemoryStore

# ---------------------------------------------------------------------------





class ESMemoryStore(MemoryStore):

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



    def read_category(self, user_id: str, category: MemoryCategory) -> str:

        raise NotImplementedError("ESMemoryStore 不处理 base memory，请使用 FileMemoryStore。")



    def read_category_entries(self, user_id: str, entry_id: list[str] | None, category: MemoryCategory) -> list[MemoryEntry]:

        raise NotImplementedError("ESMemoryStore 不处理 base memory，请使用 FileMemoryStore。")



    def write_category(

        self, user_id: str, category: MemoryCategory, entry: MemoryEntry | str, *, mode: str = "append"

    ) -> str:

        raise NotImplementedError("ESMemoryStore 不处理 base memory，请使用 FileMemoryStore。")



    def update_entry(self, user_id: str, category: MemoryCategory, entry: MemoryEntry) -> bool:

        raise NotImplementedError("ESMemoryStore 不处理 base memory，请使用 FileMemoryStore。")



    def delete_entry(self, user_id: str, category: MemoryCategory, entry_id: str) -> bool:

        raise NotImplementedError("ESMemoryStore 不处理 base memory，请使用 FileMemoryStore。")



    def exists_category(self, user_id: str, category: MemoryCategory) -> bool:

        raise NotImplementedError("ESMemoryStore 不处理 base memory，请使用 FileMemoryStore。")



    def read_all_categories(self, user_id: str) -> dict[str, str]:

        raise NotImplementedError("ESMemoryStore 不处理 base memory，请使用 FileMemoryStore。")



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
