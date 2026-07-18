from abc import ABC, abstractmethod

import json

from typing import Any



from common.logger import get_logger

from common.query.query_models import (

    ConversationEventPage,

    ConversationEventRecord,

    ConversationMemoryRecord,

    ConversationStateView,

    TodoItem,

)

from common.storage.event_log.event_store import create_event_log, create_state_store

from common.storage.memory.memory_store_factory import (

    create_base_memory_store,

    create_experience_memory_store,

)

from common.storage.memory.store import (

    ESMemoryStore,

    FileMemoryStore,

    MemoryCategory,

    parse_entries,

)

from common.utils.common import ExecutionStatus



logger = get_logger(__name__)





class ConversationReadFacade(ABC):

 


    @abstractmethod

    def get_events(

        self,

        conversation_id: str,

        cursor: str | None = None,

        limit: int = 20,

        user_id: str | None = None,

    ) -> ConversationEventPage:

        ...



    @abstractmethod

    def get_base_memories(

        self,
  
        user_id: str | None = None,

    ) -> list[ConversationMemoryRecord]:

        ...



    @abstractmethod

    def get_experience_memories(

        self,
 
        user_id: str | None = None,

    ) -> list[ConversationMemoryRecord]:

        ...
 

class ConversationReadFacadeImpl(ConversationReadFacade):

    def __init__(self, *, cache_limit_size: int = 500) -> None:

        self._cache_limit_size = cache_limit_size

 


    def get_events(

        self,

        conversation_id: str,

        cursor: str | None = None,

        limit: int = 20,

        user_id: str | None = None,

    ) -> ConversationEventPage:

        event_log = create_event_log(

            conversation_id=conversation_id,

            cache_limit_size=self._cache_limit_size,

        )

        events, next_cursor, has_more = event_log.query_events(

            cursor=cursor,

            limit=limit,

            user_id=user_id,

        )

        records = [self._to_event_record(conversation_id, event) for event in events]

        return ConversationEventPage(

            items=records,

            next_cursor=next_cursor,

            has_more=has_more,

        )



    def get_base_memories(

        self, 

        user_id: str | None = None,

    ) -> list[ConversationMemoryRecord]:

        if not user_id:

            return []



        memory_store = create_base_memory_store(

            cache_limit_size=self._cache_limit_size,

        )

        memories: list[ConversationMemoryRecord] = []

        for category in MemoryCategory:

            if isinstance(memory_store, FileMemoryStore):

                content = memory_store.read_category(user_id, category)

                entries = parse_entries(content) if content else []

            else:

                entries = memory_store.read_category_entries(user_id, None, category)



            for entry in entries:

                memories.append(

                    ConversationMemoryRecord(

                        id=str(entry.id),

                        memory_type="base",

                        category=category.value,

                        title=entry.name or None,

                        content=entry.content,

                        metadata={

                            "description": entry.description,

                            "created_at": entry.created_at,

                            "updated_at": entry.updated_at,
                        },
                    )
                )

        return memories

    # 经验记忆要优化： 默认查用户的经验记忆，同时支持用户输入问题，检索经验记忆
    def get_experience_memories(
        self,
        user_id: str | None = None,
    ) -> list[ConversationMemoryRecord]:
        if not user_id:
            return []

        memory_store = create_experience_memory_store(
            backend="es",
        )

        if not isinstance(memory_store, ESMemoryStore):
            return []

        records: list[ConversationMemoryRecord] = []
        for memory, doc_id in memory_store.search_experiences(
            user_id=user_id, query=""
        ):
            records.append(
                ConversationMemoryRecord(
                    id=doc_id,
                    memory_type="experience",
                    title=memory.question,
                    content=memory.solution,
                    score=None,
                    metadata={
                        "domain_type": memory.domain_type,
                        "feedback_type": memory.feedback_type,
                        "created_at": memory.created_at.isoformat() if memory.created_at else None,
                        "updated_at": memory.updated_at.isoformat() if memory.updated_at else None,
                        "execute_trace": [
                            trace.model_dump(mode="json") if hasattr(trace, "model_dump") else trace
                            for trace in memory.execute_trace
                        ],
                    },
                )
            )
        return records

    def _to_event_record(
        self, conversation_id: str, event: Any
    ) -> ConversationEventRecord:
        payload = event.model_dump(mode="json") if hasattr(event, "model_dump") else {}
        return ConversationEventRecord(
            event_id=str(getattr(event, "id", "")),
            conversation_id=conversation_id,
            event_type=event.__class__.__name__,
            source=str(getattr(event, "source", "")),
            timestamp=str(getattr(event, "timestamp", "")),
            payload=payload,
        )

    def _extract_latest_message(self, events: list[ConversationEventRecord]) -> str | None:
        for event in reversed(events):
            if event.event_type == "MessageEvent":
                content = event.payload.get("content")
                if isinstance(content, str) and content:
                    return content
        return None

    def _extract_agent_state(self, data: dict[str, Any]) -> str | None:
        agent_state = data.get("main_agent_state")
        if isinstance(agent_state, dict):
            return agent_state.get("state") or agent_state.get("agent_state")
        return None

    def _extract_updated_at(self, data: dict[str, Any]) -> str | None:
        stats = data.get("stats")
        if isinstance(stats, dict):
            return stats.get("updated_at")
        return None

 