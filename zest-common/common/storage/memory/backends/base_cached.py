"""Layer 3 实现 — 基础记忆缓存装饰器 (CachedBaseMemoryStore)。

设计要点：缓存是一个「装饰器」，与具体后端实现同一个接口 BaseMemoryBackend，
可透明包裹任意基础记忆后端（Local / ES / ...）。缓存策略与"选哪个后端"解耦。
类名保留为 CachedBaseMemoryStore 以向后兼容。
"""

import json
from threading import RLock

from common.storage.file_store import MemoryLRUCache
from common.storage.memory.backend import BaseMemoryBackend
from common.storage.memory.base import MemoryCategory, MemoryEntry
from common.storage.memory.utils import entry_to_md
from common.logger import get_logger

logger = get_logger(__name__)


class CachedBaseMemoryStore(BaseMemoryBackend):
    """基础记忆缓存封装：远端后端 + 内存索引 + LRU 内容缓存。"""

    def __init__(
        self,
        remote_store: BaseMemoryBackend,
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

    def _read_cached_entries_v2(self, cache_keys: list[str], category: MemoryCategory) -> tuple[list[MemoryEntry], list[str]]:
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

    def _build_cached_keys(self, user_id: str, entry_ids: list[str], category: MemoryCategory) -> list[str]:
        category_index = self._category_index(category)
        cache_keys = []
        for entry_id in entry_ids:
            cache_key = self._cache_key(user_id, entry_id, category)
            if cache_key in category_index:
                cache_keys.append(cache_key)
        return cache_keys

    def _read_cached_entries(self, user_id: str, entry_ids: list[str] | None, category: MemoryCategory) -> tuple[list[MemoryEntry], list[str]]:
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
            self._cache_entry(user_id, category, entry)
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
