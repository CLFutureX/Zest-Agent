# state.py
from abc import abstractmethod
import operator
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, SupportsIndex, overload

from common.storage.event_log.events_list_base import EventsListBase
from common.storage.event_log.persistence_const import (
    BASE_STATE,
    EVENT_FILE_PATTERN,
    EVENT_NAME_RE,
    EVENTS_DIR,
)
from common.event.event import Event
from common.event.types import EventID
from common.storage.file_store import FileStore
from common.storage.file_store.cache import MemoryLRUCache
from common.storage.file_store.local import LocalFileStore
from common.storage.file_store.memory import InMemoryFileStore
from common.storage.storage_settings import (
    StorageSettings,
    load_storage_settings_from_env,
    resolve_event_local_dir,
    resolve_state_local_file,
)
from common.logger import get_logger
from common.utils.common import AgentID, ConversationID

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorCollection
    from pymongo import MongoClient

logger = get_logger(__name__)

LOCK_FILE_NAME = ".eventlog.lock"
LOCK_TIMEOUT_SECONDS = 30


class EventLog(EventsListBase):

    """事件日志的抽象接口：定义标准行为，不包含实现"""



    @abstractmethod

    def get_index(self, event_id: EventID) -> int:

        """根据 event_id 获取索引"""

        ...



    @abstractmethod

    def get_id(self, idx: int) -> EventID:

        """根据索引获取 event_id"""

        ...



    @overload

    @abstractmethod

    def __getitem__(self, idx: int) -> Event: ...



    @overload

    @abstractmethod

    def __getitem__(self, idx: slice) -> list[Event]: ...



    @abstractmethod

    def __getitem__(self, idx: SupportsIndex | slice) -> Event | list[Event]:

        ...



    @abstractmethod

    def __iter__(self) -> Iterator[Event]:

        ...



    @abstractmethod

    def append(self, event: Event) -> None:

        ...



    @abstractmethod

    def query_events(

        self,

        *,

        cursor: str | None = None,

        limit: int = 20,

        user_id: str | None = None,

    ) -> tuple[list[Event], str | None, bool]:

        """按游标查询事件列表，支持可选 user_id 过滤。"""

        ...



    @abstractmethod

    def __len__(self) -> int:

        ...
class MongoEventLog(EventLog):
    """基于 motor（异步）的 MongoDB 事件日志实现，采用懒加载策略与 LRU 缓存。

    使用 AsyncIOMotorClient，原生兼容 FastAPI / asyncio 上下文。
    同步上下文请使用 SyncMongoEventLog（见 sync_event_store.py）。
    """

    DEFAULT_CACHE_MAX_SIZE = 1000
    DEFAULT_CACHE_MAX_MEMORY = 50 * 1024 * 1024  # 50 MB

    _collection: "AsyncIOMotorCollection"
    _id_to_idx: dict[EventID, int]
    _idx_to_id: dict[int, EventID]
    _event_cache: MemoryLRUCache
    _length: int
    _length_loaded: bool

    def __init__(
        self,
        mongodb_url: str,
        conversation_id: str,
        agent_id: AgentID,
        main_agent: bool = True,
        db_name: str = "agent_events",
        collection_name: str = "event_logs",
        cache_max_size: int = DEFAULT_CACHE_MAX_SIZE,
        cache_max_memory: int = DEFAULT_CACHE_MAX_MEMORY,
    ) -> None:
        from motor.motor_asyncio import AsyncIOMotorClient

        self.conversation_id = conversation_id
        self.agent_id = agent_id
        self.main_agent = main_agent

        client = get_motor_client(mongodb_url)
        self._collection = client[db_name][collection_name]
        self._id_to_idx = {}
        self._idx_to_id = {}
        self._event_cache = MemoryLRUCache(max_memory=cache_max_memory, max_size=cache_max_size)
        self._length = 0
        self._length_loaded = False

    async def ensure_indexes(self) -> None:
        """创建必要的索引（异步，启动时调用一次即可）。"""
        await self._collection.create_index("event_id", unique=True)
        await self._collection.create_index("idx")
        await self._collection.create_index("conversation_id")

    async def _ensure_length_loaded(self) -> None:
        if self._length_loaded:
            return
        try:
            doc = await self._collection.find_one(
                {"conversation_id": self.conversation_id}, sort=[("idx", -1)]
            )
            if doc is not None:
                self._length = doc["idx"] + 1
        except Exception as e:
            logger.warning("Failed to load MongoEventLog length: %s", e)
        self._length_loaded = True

    async def _ensure_id_loaded(self, idx: int) -> EventID | None:
        if idx in self._idx_to_id:
            return self._idx_to_id[idx]
        try:
            doc = await self._collection.find_one(
                {"conversation_id": self.conversation_id, "idx": idx},
                {"event_id": 1, "idx": 1},
            )
            if doc is not None:
                evt_id = doc["event_id"]
                self._idx_to_id[idx] = evt_id
                self._id_to_idx.setdefault(evt_id, idx)
                return evt_id
        except Exception as e:
            logger.warning("Failed to load event ID at index %d: %s", idx, e)
        return None

    async def get_index(self, event_id: EventID) -> int:  # type: ignore[override]
        if event_id in self._id_to_idx:
            return self._id_to_idx[event_id]
        try:
            doc = await self._collection.find_one(
                {"conversation_id": self.conversation_id, "event_id": event_id},
                {"idx": 1, "event_id": 1},
            )
            if doc is not None:
                idx = doc["idx"]
                self._id_to_idx[event_id] = idx
                self._idx_to_id[idx] = event_id
                return idx
        except Exception as e:
            logger.warning("Failed to find index for event_id %s: %s", event_id, e)
        raise KeyError(f"Unknown event_id: {event_id}")

    async def get_id(self, idx: int) -> EventID:  # type: ignore[override]
        if idx < 0:
            await self._ensure_length_loaded()
            idx += self._length
        if idx < 0 or idx >= self._length:
            raise IndexError("Event index out of range")
        evt_id = await self._ensure_id_loaded(idx)
        if evt_id is None:
            raise IndexError(f"Event not found at index {idx}")
        return evt_id

    async def _get_single_item(self, i: int) -> Event:
        if i in self._event_cache:
            return self._event_cache[i]
        evt_id = await self._ensure_id_loaded(i)
        if evt_id is None:
            raise IndexError(f"Event not found at index {i}")
        doc = await self._collection.find_one(
            {"conversation_id": self.conversation_id, "event_id": evt_id}
        )
        if doc is None:
            raise FileNotFoundError(f"Missing event: {evt_id}")
        event = Event.model_validate_json(doc["event_json"])
        self._event_cache[i] = event
        return event

    @overload
    def __getitem__(self, idx: int) -> Event: ...

    @overload
    def __getitem__(self, idx: slice) -> list[Event]: ...

    def __getitem__(self, idx: SupportsIndex | slice) -> Event | list[Event]:
        raise NotImplementedError("MongoEventLog is async-only; use async methods directly")

    def __iter__(self) -> Iterator[Event]:
        raise NotImplementedError("MongoEventLog is async-only; use async methods directly")

    def __len__(self) -> int:
        return self._length

    async def append(self, event: Event) -> None:  # type: ignore[override]
        """异步追加事件。"""
        evt_id = event.id
        if evt_id in self._id_to_idx:
            existing_idx = self._id_to_idx[evt_id]
            raise ValueError(f"Event with ID '{evt_id}' already exists at index {existing_idx}")

        await self._ensure_length_loaded()
        target_idx = self._length
        event_json = event.model_dump_json(exclude_none=True)
        doc = {
            "conversation_id": self.conversation_id,
            "agent_id": str(self.agent_id),
            "is_main": 1 if self.main_agent else 0,
            "event_id": evt_id,
            "idx": target_idx,
            "event_json": event_json,
            "timestamp": event.timestamp,
            "source": event.source,
        }
        try:
            await self._collection.insert_one(doc)
        except Exception as e:
            if "duplicate key" in str(e).lower() or "E11000" in str(e):
                raise ValueError(
                    f"Event with ID '{evt_id}' already exists (duplicate key error)"
                ) from e
            logger.error("Failed to append event to MongoDB: %s", e)
            raise

        self._idx_to_id[target_idx] = evt_id
        self._id_to_idx[evt_id] = target_idx
        self._event_cache[target_idx] = event
        self._length += 1

    async def query_events(  # type: ignore[override]
        self,
        *,
        cursor: str | None = None,
        limit: int = 20,
        user_id: str | None = None,
    ) -> tuple[list[Event], str | None, bool]:
        """异步游标分页查询。"""
        await self._ensure_length_loaded()
        query: dict[str, Any] = {"conversation_id": self.conversation_id}
        if user_id:
            query["user_id"] = user_id
        if cursor is not None:
            query["idx"] = {"$gte": max(int(cursor), 0)}

        cursor_obj = self._collection.find(query).sort("idx", 1).limit(max(limit + 1, 1))
        docs = await cursor_obj.to_list(length=limit + 1)
        has_more = len(docs) > limit
        docs = docs[:limit]
        events = [Event.model_validate_json(doc["event_json"]) for doc in docs]
        next_cursor = str(docs[-1]["idx"] + 1) if has_more and docs else None
        return events, next_cursor, has_more
class LocalEventLog(EventLog):
    """Persistent event log with locking for concurrent writes.

    This class provides thread-safe and process-safe event storage using
    the FileStore's locking mechanism. Events are persisted to disk and
    can be accessed by index or event ID.

    Note:
        For LocalFileStore, file locking via flock() does NOT work reliably
        on NFS mounts or network filesystems. Users deploying with shared
        storage should use alternative coordination mechanisms.
    """

    _fs: FileStore
    _dir: str
    _length: int
    _lock_path: str

    def __init__(self, fs: FileStore, dir_path: str = EVENTS_DIR) -> None:
        self._fs = fs
        self._dir = dir_path
        self._id_to_idx: dict[EventID, int] = {}
        self._idx_to_id: dict[int, EventID] = {}
        self._lock_path = f"{dir_path}/{LOCK_FILE_NAME}"
        self._length = self._scan_and_build_index()

    def get_index(self, event_id: EventID) -> int:
        """Return the integer index for a given event_id."""
        try:
            return self._id_to_idx[event_id]
        except KeyError:
            raise KeyError(f"Unknown event_id: {event_id}")

    def get_id(self, idx: int) -> EventID:
        """Return the event_id for a given index."""
        if idx < 0:
            idx += self._length
        if idx < 0 or idx >= self._length:
            raise IndexError("Event index out of range")
        return self._idx_to_id[idx]

    @overload
    def __getitem__(self, idx: int) -> Event: ...

    @overload
    def __getitem__(self, idx: slice) -> list[Event]: ...

    def __getitem__(self, idx: SupportsIndex | slice) -> Event | list[Event]:
        if isinstance(idx, slice):
            start, stop, step = idx.indices(self._length)
            return [self._get_single_item(i) for i in range(start, stop, step)]
        return self._get_single_item(idx)

    def _get_single_item(self, idx: SupportsIndex) -> Event:
        i = operator.index(idx)
        if i < 0:
            i += self._length
        if i < 0 or i >= self._length:
            raise IndexError("Event index out of range")
        txt = self._fs.read(self._path(i))
        if not txt:
            raise FileNotFoundError(f"Missing event file: {self._path(i)}")
        return Event.model_validate_json(txt)

    def __iter__(self) -> Iterator[Event]:

        for i in range(self._length):

            txt = self._fs.read(self._path(i))

            if not txt:

                continue

            evt = Event.model_validate_json(txt)

            evt_id = evt.id

            if i not in self._idx_to_id:

                self._idx_to_id[i] = evt_id

                self._id_to_idx.setdefault(evt_id, i)

            yield evt



    def append(self, event: Event) -> None:

        """Append an event with locking for thread/process safety.



        Raises:

            TimeoutError: If the lock cannot be acquired within LOCK_TIMEOUT_SECONDS.

            ValueError: If an event with the same ID already exists.

        """

        evt_id = event.id



        try:

            with self._fs.lock(self._lock_path, timeout=LOCK_TIMEOUT_SECONDS):

                disk_length = self._count_events_on_disk()

                if disk_length > self._length:

                    self._sync_from_disk(disk_length)



                if evt_id in self._id_to_idx:

                    existing_idx = self._id_to_idx[evt_id]

                    raise ValueError(

                        f"Event with ID '{evt_id}' already exists at index "

                        f"{existing_idx}"

                    )



                target_path = self._path(self._length, event_id=evt_id)

                self._fs.write(target_path, event.model_dump_json(exclude_none=True))



                self._idx_to_id[self._length] = evt_id

                self._id_to_idx[evt_id] = self._length

                self._length += 1

        except TimeoutError:

            logger.error(

                f"Failed to acquire EventLog lock within {LOCK_TIMEOUT_SECONDS}s "

                f"for event {evt_id}"

            )

            raise



    def query_events(

        self,

        *,

        cursor: str | None = None,

        limit: int = 20,

        user_id: str | None = None,

    ) -> tuple[list[Event], str | None, bool]:

        start = max(int(cursor), 0) if cursor is not None else max(self._length - limit, 0)

        stop = min(start + limit, self._length)

        events = [self._get_single_item(i) for i in range(start, stop)]

        has_more = stop < self._length

        next_cursor = str(stop) if has_more else None

        return events, next_cursor, has_more



    def _count_events_on_disk(self) -> int:

        """Count event files on disk."""

        try:

            paths = self._fs.list(self._dir)

        except FileNotFoundError:

            return 0

        except Exception as e:

            logger.warning("Error listing event directory %s: %s", self._dir, e)

            return 0

        return sum(

            1

            for p in paths

            if p.rsplit("/", 1)[-1].startswith("event-") and p.endswith(".json")

        )



    def _sync_from_disk(self, disk_length: int) -> None:

        """Sync state for events written by other processes."""

        existing_idx_to_id = dict(self._idx_to_id)

        scanned_length = self._scan_and_build_index()



        for idx, evt_id in existing_idx_to_id.items():

            if idx not in self._idx_to_id:

                self._idx_to_id[idx] = evt_id

            if evt_id not in self._id_to_idx:

                self._id_to_idx[evt_id] = idx



        self._length = max(scanned_length, disk_length)



    def __len__(self) -> int:

        return self._length

    def _path(self, idx: int, *, event_id: EventID | None = None) -> str:
        return f"{self._dir}/{
            EVENT_FILE_PATTERN.format(
                idx=idx, event_id=event_id or self._idx_to_id[idx]
            )
        }"

    def _scan_and_build_index(self) -> int:
        try:
            paths = self._fs.list(self._dir)
        except Exception:
            self._id_to_idx.clear()
            self._idx_to_id.clear()
            return 0

        by_idx: dict[int, EventID] = {}
        for p in paths:
            name = p.rsplit("/", 1)[-1]
            m = EVENT_NAME_RE.match(name)
            if m:
                idx = int(m.group("idx"))
                evt_id = m.group("event_id")
                by_idx[idx] = evt_id
            else:
                logger.warning(f"Unrecognized event file name: {name}")

        if not by_idx:
            self._id_to_idx.clear()
            self._idx_to_id.clear()
            return 0

        n = 0
        while True:
            if n not in by_idx:
                if any(i > n for i in by_idx.keys()):
                    logger.warning(
                        "Event index gap detected: "
                        f"expect next index {n} but got {sorted(by_idx.keys())}"
                    )
                break
            n += 1

        self._id_to_idx.clear()
        self._idx_to_id.clear()
        for i in range(n):
            evt_id = by_idx[i]
            self._idx_to_id[i] = evt_id
            if evt_id in self._id_to_idx:
                logger.warning(
                    f"Duplicate event ID '{evt_id}' found during scan. "
                    f"Keeping first occurrence at index {self._id_to_idx[evt_id]}, "
                    f"ignoring duplicate at index {i}"
                )
            else:
                self._id_to_idx[evt_id] = i
        return n


# ---------------------------------------------------------------------------
# Factory: unified entry point for creating EventLog instances
# ---------------------------------------------------------------------------

def create_event_log(

    *,

    conversation_id: ConversationID,

    agent_id: AgentID | None = None,

    cache_limit_size: int=500, 

    main_agent: bool = True,

    mongodb_url: str | None = None,

    db_name: str = "agent_events",

    collection_name: str = "event_logs",

    backend: str | None = None,

    storage_settings: StorageSettings | None = None,

) -> EventLog:

    """统一的事件日志工厂方法。"""

    settings = storage_settings or load_storage_settings_from_env()



    event_settings = settings.event_log



    resolved_backend = (backend or event_settings.backend).lower()



    resolved_cache_limit_size = cache_limit_size or event_settings.cache_limit_size


 


    if resolved_backend == "mongo":



        resolved_url = mongodb_url or (event_settings.mongo.url if event_settings.mongo else None)



        resolved_db_name = db_name or event_settings.db_name



        resolved_collection_name = collection_name or event_settings.collection_name



        if not resolved_url:



            raise ValueError("Mongo 事件日志后端缺少 mongodb_url 配置。")



        return MongoEventLog(



            conversation_id=conversation_id,



            agent_id=agent_id,



            main_agent=main_agent,



            mongodb_url=resolved_url,



            db_name=resolved_db_name,



            collection_name=resolved_collection_name,



        )







    agent_events_dir = resolve_event_local_dir( 
        settings = settings, 
        agent_id = str(agent_id),
        conversation_id=str(conversation_id), 
    )



    fs = get_fs_store(settings.local.root_dir, resolved_cache_limit_size)
 
    return LocalEventLog(fs=fs, dir_path=agent_events_dir)

def get_fs_store(root_path:str, cache_limit_size:int): 
      
    return LocalFileStore(root_path,cache_limit_size=cache_limit_size)

# ---------------------------------------------------------------------------
# StateStore: 会话状态的持久化存储抽象
# ---------------------------------------------------------------------------
# MongoDB client factories
# ---------------------------------------------------------------------------

# --- motor（异步）客户端缓存，供 MongoEventLog 使用 ---
_motor_client_cache: dict[str, Any] = {}


def get_motor_client(mongodb_url: str, namespace: str = "default") -> Any:
    """获取 motor AsyncIOMotorClient 单例，使用 namespace+URL 缓存。"""
    cache_key = f"{namespace}:{mongodb_url}"
    if cache_key not in _motor_client_cache:
        from motor.motor_asyncio import AsyncIOMotorClient
        _motor_client_cache[cache_key] = AsyncIOMotorClient(mongodb_url)
    return _motor_client_cache[cache_key]


# --- pymongo（同步）客户端缓存，供 MongoStateStore 同步访问使用 ---
mongo_client_cache: dict[str, "MongoClient"] = {}


def get_mongo_client(mongodb_url: str, namespace: str = "default") -> "MongoClient":
    """获取 pymongo MongoClient 单例（同步，仅供 StateStore 等同步上下文使用）。"""
    global mongo_client_cache
    cache_key = f"{namespace}:{mongodb_url}"
    if cache_key not in mongo_client_cache:
        from pymongo import MongoClient
        mongo_client_cache[cache_key] = MongoClient(mongodb_url)
    return mongo_client_cache[cache_key]
class StateStore:
    """会话状态持久化存储的极简接口。

    仅负责 base_state 的 read / write / exists，不关心上层业务逻辑。
    """

    @abstractmethod
    def read(self,type:str) -> str | None:
        """读取 state payload；不存在时返回 None。"""
        ...

    @abstractmethod
    def write(self, payload: str,type: str) -> None:
        """写入 state payload。"""
        ...

    @abstractmethod
    def exists(self,type:str) -> bool:
        """检查是否已有持久化数据。"""
        ...


class FileStateStore(StateStore):
    """基于 FileStore 的状态存储。"""

    def __init__(self, fs: FileStore, key: str = BASE_STATE) -> None:
         
        self._fs = fs
        self._key = key

    def read(self, type: str) -> str | None:
        try:
            key = self.get_state_key(type)
            return self._fs.read(key)
        except FileNotFoundError:
            return None

    def write(self, payload: str,type: str) -> None:
        key = self.get_state_key(type)
        self._fs.write(key, payload, cache=False)

    def exists(self,type:str) -> bool:
        
        return self.read(type) is not None

    def get_state_key(self,type: str)-> str:
       return f"{type}_{self._key}"

class MongoStateStore(StateStore):
    """基于 MongoDB 的状态存储。"""

    def __init__(
        self,
        mongodb_url: str,
        conversation_id: ConversationID,
        db_name: str = "agent_data",
        collection_name: str = "conversation_state",
    ) -> None:
        from pymongo import MongoClient

        self._conversation_id = conversation_id
        
        self._collection = get_mongo_client(mongodb_url)[db_name][collection_name]
        self._collection.create_index("conversation_id", unique=True)

    def read(self,type:str) -> str | None:
        doc = self._collection.find_one(
            {"conversation_id": self._conversation_id, "type": type}, {"state_json": 1}
        )
        return doc["state_json"] if doc else None

    def write(self, payload: str,type: str) -> None:
        self._collection.replace_one(
            {"conversation_id": self._conversation_id, "type": type},
            {"conversation_id": self._conversation_id, "state_json": payload, "type": type},
            upsert=True,
        )

    def exists(self,type:str) -> bool:
        return self._collection.count_documents(
            {"conversation_id": self._conversation_id, "type": type}, limit=1
        ) > 0


def create_state_store(

    *,

    conversation_id: ConversationID,

    cache_limit_size: int = 500, 
    mongodb_url: str | None = None, 
    db_name: str = "agent_data", 
    collection_name: str = "conversation_state", 
    backend: str | None = None, 
    storage_settings: StorageSettings | None = None,

) -> StateStore:

    """统一的状态存储工厂方法。"""

    settings = storage_settings or load_storage_settings_from_env()



    state_settings = settings.state_store



    resolved_backend = (backend or state_settings.backend).lower()

    if resolved_backend == "mongo":



        resolved_url = mongodb_url or (state_settings.mongo.url if state_settings.mongo else None)



        resolved_db_name = db_name or state_settings.db_name



        resolved_collection_name = collection_name or state_settings.collection_name



        if not resolved_url:



            raise ValueError("Mongo 状态存储后端缺少 mongodb_url 配置。")



        return MongoStateStore( 

            mongodb_url=resolved_url, 
            db_name=resolved_db_name,
            collection_name=resolved_collection_name,
            conversation_id=conversation_id,



        )
 

    local_state_file = resolve_state_local_file(

        settings=settings,

        conversation_id=str(conversation_id),

    )



    fs = get_fs_store(settings.local.root_dir, cache_limit_size)



    return FileStateStore(fs=fs, key=local_state_file)
         

