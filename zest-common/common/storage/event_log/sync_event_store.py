"""同步包装层：通过 AsyncExecutor 将 MongoEventLog 的异步接口桥接为同步调用。

同步上下文（如 zest-sdk agent 运行时）使用 SyncMongoEventLog；
异步上下文（如 FastAPI）直接使用 MongoEventLog。
"""
from collections.abc import Iterator

from common.event.event import Event
from common.event.types import EventID
from common.storage.event_log.event_store import MongoEventLog
from common.utils.async_executor import AsyncExecutor
from common.utils.common import AgentID, ConversationID

# 模块级单例，所有 SyncMongoEventLog 实例共享同一个后台 event loop portal
_executor = AsyncExecutor()


class SyncMongoEventLog:
    """MongoEventLog 的同步包装，适用于无 asyncio event loop 的同步上下文。

    内部通过模块级 AsyncExecutor 在独立后台 loop 中执行 motor 异步调用。
    不要在已有 asyncio event loop 的上下文（如 FastAPI 路由）中使用——直接使用 MongoEventLog。
    """

    def __init__(
        self,
        mongodb_url: str,
        conversation_id: str,
        agent_id: AgentID,
        main_agent: bool = True,
        db_name: str = "agent_events",
        collection_name: str = "event_logs",
        cache_max_size: int = MongoEventLog.DEFAULT_CACHE_MAX_SIZE,
        cache_max_memory: int = MongoEventLog.DEFAULT_CACHE_MAX_MEMORY,
    ) -> None:
        self._async_log = MongoEventLog(
            mongodb_url=mongodb_url,
            conversation_id=conversation_id,
            agent_id=agent_id,
            main_agent=main_agent,
            db_name=db_name,
            collection_name=collection_name,
            cache_max_size=cache_max_size,
            cache_max_memory=cache_max_memory,
        )
        # 初始化时同步建立索引
        _executor.run_async(self._async_log.ensure_indexes)

    def append(self, event: Event) -> None:
        """同步追加事件。"""
        _executor.run_async(self._async_log.append, event)

    def query_events(
        self,
        *,
        cursor: str | None = None,
        limit: int = 20,
        user_id: str | None = None,
    ) -> tuple[list[Event], str | None, bool]:
        """同步游标分页查询。"""
        return _executor.run_async(
            self._async_log.query_events,
            cursor=cursor,
            limit=limit,
            user_id=user_id,
        )

    def get_index(self, event_id: EventID) -> int:
        """同步获取事件索引。"""
        return _executor.run_async(self._async_log.get_index, event_id)

    def get_id(self, idx: int) -> EventID:
        """同步获取事件 ID。"""
        return _executor.run_async(self._async_log.get_id, idx)

    def __len__(self) -> int:
        return len(self._async_log)

    def __iter__(self) -> Iterator[Event]:
        """同步迭代（全量加载，慎用于大日志）。"""
        events, next_cursor, has_more = self.query_events(limit=1000)
        yield from events
        while has_more and next_cursor is not None:
            events, next_cursor, has_more = self.query_events(cursor=next_cursor, limit=1000)
            yield from events
