"""Unit tests for event_store: LocalEventLog, MongoEventLog, SyncMongoEventLog.

测试策略：
- LocalEventLog：使用 InMemoryFileStore，无外部依赖，直接运行。
- MongoEventLog（异步）：mock motor collection，验证异步逻辑。
- SyncMongoEventLog：mock MongoEventLog 的异步方法，验证同步桥接。
"""
import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from common.event.event import Event
from common.event.types import SourceType
from common.storage.event_log.event_store import (
    LocalEventLog,
    MongoEventLog,
    create_event_log,
)
from common.storage.event_log.sync_event_store import SyncMongoEventLog
from common.storage.file_store.memory import InMemoryFileStore


# ---------------------------------------------------------------------------
# Test fixture: 具体 Event 子类
# ---------------------------------------------------------------------------

class DummyEvent(Event):
    """最小化可实例化的 Event 子类，仅用于测试。"""
    message: str = ""

    @property
    def visualize(self):
        from rich.text import Text
        return Text(self.message)


def make_event(source: SourceType = "user", message: str = "hello") -> DummyEvent:
    return DummyEvent(source=source, message=message)


# ---------------------------------------------------------------------------
# TestLocalEventLog
# ---------------------------------------------------------------------------

class TestLocalEventLog:

    def _make_log(self) -> LocalEventLog:
        return LocalEventLog(fs=InMemoryFileStore(), dir_path="events")

    def test_append_and_len(self):
        log = self._make_log()
        assert len(log) == 0
        log.append(make_event())
        assert len(log) == 1
        log.append(make_event(message="world"))
        assert len(log) == 2

    def test_getitem_by_index(self):
        log = self._make_log()
        e1, e2 = make_event(message="first"), make_event(message="second")
        log.append(e1)
        log.append(e2)
        assert log[0].id == e1.id
        assert log[1].id == e2.id

    def test_getitem_negative_index(self):
        log = self._make_log()
        e = make_event()
        log.append(e)
        assert log[-1].id == e.id

    def test_getitem_slice(self):
        log = self._make_log()
        events = [make_event(message=str(i)) for i in range(5)]
        for e in events:
            log.append(e)
        sliced = log[1:3]
        assert [x.id for x in sliced] == [events[1].id, events[2].id]

    def test_iter(self):
        log = self._make_log()
        events = [make_event(message=str(i)) for i in range(3)]
        for e in events:
            log.append(e)
        assert [e.id for e in log] == [e.id for e in events]

    def test_get_index_and_get_id(self):
        log = self._make_log()
        e = make_event()
        log.append(e)
        assert log.get_index(e.id) == 0
        assert log.get_id(0) == e.id

    def test_duplicate_event_raises(self):
        log = self._make_log()
        e = make_event()
        log.append(e)
        with pytest.raises(ValueError, match="already exists"):
            log.append(e)

    def test_index_out_of_range_raises(self):
        log = self._make_log()
        with pytest.raises(IndexError):
            _ = log[0]

    def test_query_events_no_cursor(self):
        log = self._make_log()
        for i in range(5):
            log.append(make_event(message=str(i)))
        events, next_cursor, has_more = log.query_events(limit=3)
        assert len(events) == 3
        assert has_more is True
        assert next_cursor is not None

    def test_query_events_with_cursor(self):
        log = self._make_log()
        for i in range(5):
            log.append(make_event(message=str(i)))
        _, cursor, _ = log.query_events(limit=3)
        events2, _, has_more2 = log.query_events(cursor=cursor, limit=3)
        assert len(events2) == 2
        assert has_more2 is False

    def test_query_events_exact_limit(self):
        log = self._make_log()
        for i in range(3):
            log.append(make_event(message=str(i)))
        events, next_cursor, has_more = log.query_events(limit=3)
        assert len(events) == 3
        assert has_more is False
        assert next_cursor is None

    def test_create_event_log_local_factory(self):
        log = create_event_log(conversation_id="c1", agent_id="a1", backend="local")
        assert isinstance(log, LocalEventLog)



# ---------------------------------------------------------------------------
# TestMongoEventLog  (async, mock motor collection)
# ---------------------------------------------------------------------------

class TestMongoEventLog:

    def _make_log(self):
        with patch("common.storage.event_log.event_store.get_motor_client") as mc:
            col = MagicMock()
            mc.return_value.__getitem__.return_value.__getitem__.return_value = col
            log = MongoEventLog(
                mongodb_url="mongodb://localhost:27017",
                conversation_id="conv-test",
                agent_id="agent-test",
            )
            log._collection = col
        return log, col

    @pytest.mark.asyncio
    async def test_ensure_indexes(self):
        log, col = self._make_log()
        col.create_index = AsyncMock()
        await log.ensure_indexes()
        assert col.create_index.call_count == 3

    @pytest.mark.asyncio
    async def test_append_increments_length(self):
        log, col = self._make_log()
        col.find_one = AsyncMock(return_value=None)
        col.insert_one = AsyncMock()
        e = make_event()
        await log.append(e)
        assert len(log) == 1
        assert col.insert_one.called

    @pytest.mark.asyncio
    async def test_append_duplicate_raises(self):
        log, col = self._make_log()
        col.find_one = AsyncMock(return_value=None)
        col.insert_one = AsyncMock()
        e = make_event()
        await log.append(e)
        with pytest.raises(ValueError, match="already exists"):
            await log.append(e)

    @pytest.mark.asyncio
    async def test_query_events_returns_events(self):
        log, col = self._make_log()
        e = make_event(message="q-test")
        cur = MagicMock()
        cur.to_list = AsyncMock(return_value=[{"idx": 0, "event_json": e.model_dump_json(exclude_none=True)}])
        col.find.return_value.sort.return_value.limit.return_value = cur
        col.find_one = AsyncMock(return_value=None)
        events, nc, hm = await log.query_events(limit=10)
        assert len(events) == 1 and events[0].id == e.id
        assert hm is False and nc is None

    @pytest.mark.asyncio
    async def test_query_events_has_more(self):
        log, col = self._make_log()
        evts = [make_event(message=str(i)) for i in range(3)]
        docs = [{"idx": i, "event_json": e.model_dump_json(exclude_none=True)} for i, e in enumerate(evts)]
        cur = MagicMock()
        cur.to_list = AsyncMock(return_value=docs)
        col.find.return_value.sort.return_value.limit.return_value = cur
        col.find_one = AsyncMock(return_value=None)
        events, nc, hm = await log.query_events(limit=2)
        assert len(events) == 2 and hm is True and nc == "2"

    @pytest.mark.asyncio
    async def test_get_index_found(self):
        log, col = self._make_log()
        e = make_event()
        col.find_one = AsyncMock(return_value={"idx": 0, "event_id": e.id})
        assert await log.get_index(e.id) == 0

    @pytest.mark.asyncio
    async def test_get_index_missing_raises(self):
        log, col = self._make_log()
        col.find_one = AsyncMock(return_value=None)
        with pytest.raises(KeyError):
            await log.get_index("nonexistent")

    def test_sync_getitem_iter_raise(self):
        """__getitem__ and __iter__ raise NotImplementedError (sync forbidden)."""
        log, _ = self._make_log()
        with pytest.raises(NotImplementedError): _ = log[0]
        with pytest.raises(NotImplementedError): list(log)

    def test_get_index_is_coroutine(self):
        """get_index is async; sync call returns coroutine, not a plain value."""
        import inspect
        log, _ = self._make_log()
        coro = log.get_index("x")
        assert inspect.iscoroutine(coro)
        coro.close()

    def test_get_id_is_coroutine(self):
        """get_id is async; sync call returns coroutine, not a plain value."""
        import inspect
        log, _ = self._make_log()
        coro = log.get_id(0)
        assert inspect.iscoroutine(coro)
        coro.close()

    @pytest.mark.asyncio
    async def test_create_event_log_mongo_factory(self):
        with patch("common.storage.event_log.event_store.get_motor_client"):
            log = create_event_log(conversation_id="c1", agent_id="a1", backend="mongo", mongodb_url="mongodb://localhost:27017")
        assert isinstance(log, MongoEventLog)


# ---------------------------------------------------------------------------
# TestSyncMongoEventLog  (mock MongoEventLog async methods)
# ---------------------------------------------------------------------------

class TestSyncMongoEventLog:

    def _make(self):
        with patch("common.storage.event_log.event_store.get_motor_client"):
            with patch.object(MongoEventLog, "ensure_indexes", new_callable=AsyncMock):
                return SyncMongoEventLog(mongodb_url="mongodb://localhost:27017", conversation_id="c", agent_id="a")

    def test_append_delegates(self):
        log = self._make()
        e = make_event()
        with patch.object(log._async_log, "append", new_callable=AsyncMock) as m:
            log.append(e); m.assert_called_once_with(e)

    def test_query_events_delegates(self):
        log = self._make()
        exp = ([make_event()], None, False)
        with patch.object(log._async_log, "query_events", new_callable=AsyncMock, return_value=exp) as m:
            result = log.query_events(limit=5, user_id="u1")
            m.assert_called_once_with(cursor=None, limit=5, user_id="u1")
            assert result == exp

    def test_get_index_delegates(self):
        log = self._make()
        e = make_event()
        with patch.object(log._async_log, "get_index", new_callable=AsyncMock, return_value=0) as m:
            assert log.get_index(e.id) == 0; m.assert_called_once_with(e.id)

    def test_get_id_delegates(self):
        log = self._make()
        fid = str(uuid.uuid4())
        with patch.object(log._async_log, "get_id", new_callable=AsyncMock, return_value=fid) as m:
            assert log.get_id(0) == fid; m.assert_called_once_with(0)

    def test_len_delegates(self):
        log = self._make(); log._async_log._length = 7; assert len(log) == 7

    def test_iter_single_page(self):
        log = self._make()
        events = [make_event(message=str(i)) for i in range(3)]
        with patch.object(log._async_log, "query_events", new_callable=AsyncMock, return_value=(events, None, False)):
            assert [e.id for e in log] == [e.id for e in events]

    def test_iter_multi_page(self):
        log = self._make()
        p1, p2 = [make_event(message="a")], [make_event(message="b")]
        calls = []
        async def side(*, cursor=None, limit=1000, user_id=None):
            calls.append(cursor); return (p1, "1", True) if cursor is None else (p2, None, False)
        with patch.object(log._async_log, "query_events", side_effect=side):
            result = list(log)
        assert len(result) == 2 and len(calls) == 2

if __name__ == "__main__":
    monogb = TestMongoEventLog()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(monogb.test_ensure_indexes())
    loop.run_until_complete(monogb.test_append_increments_length())
     
    