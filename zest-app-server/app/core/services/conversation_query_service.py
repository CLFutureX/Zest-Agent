from atexit import register

from common.query.conversation_read_facade import ConversationReadFacade
from common.query.query_models import (
    ConversationEventPage,
    ConversationMemoryRecord,
    ConversationStateView,
)
from app.core.services.task_service import TaskService
from app.core.services.scheduler import Dispatcher
from app.core.registry.base import AgentRegistryServer



class ConversationQueryService:

    def __init__(
        self,
        read_facade: ConversationReadFacade,
        task_service:TaskService,
        dispatcher: Dispatcher, 
    ) -> None:
        self._read_facade = read_facade
        self._dispatcher = dispatcher
        self._task_service = task_service
    def get_events(

        self,

        conversation_id: str,

        cursor: str | None = None,

        limit: int = 20,

        user_id: str | None = None,

    ) -> ConversationEventPage:

        return self._read_facade.get_events(

            conversation_id,

            cursor=cursor,

            limit=limit,

            user_id=user_id,

        )



    def get_base_memories(

        self,

        user_id: str | None = None,

    ) -> list[ConversationMemoryRecord]:

        if not user_id:

            return []

        return self._read_facade.get_base_memories(user_id=user_id)



    def get_experience_memories(

        self,

        user_id: str | None = None,

    ) -> list[ConversationMemoryRecord]:

        if not user_id:

            return []

        return self._read_facade.get_experience_memories(user_id=user_id)
 
         
    def get_base_memories(

        self,

        user_id: str | None = None,

    ) -> list[ConversationMemoryRecord]:

        if not user_id:

            return []

        return self._read_facade.get_base_memories(user_id=user_id)



    def get_experience_memories(

        self,

        user_id: str | None = None,

    ) -> list[ConversationMemoryRecord]:

        if not user_id:

            return []

        return self._read_facade.get_experience_memories(user_id=user_id)

    async def get_state_view(
        self,
        conversation_id: str,
    ) -> ConversationStateView | None:
        """HTTP-call zest-service to get conversation state view.
        Resolves AgentServerInfo from the latest task for this conversation.
        """
      

        task = await self._task_service.get_latest_task_by_conversation(conversation_id)
        if not task or not task.agent_server_id:
            return None
 

        raw = await self._dispatcher.get_conversation_state(conversation_id, task.agent_server_id)
        if not raw:
            return None

        return ConversationStateView(
            conversation_id=raw.get("conversation_id", conversation_id),
            execution_status=raw.get("execution_status", "idle"),
            task_description=raw.get("task_description", ""),
            todos=raw.get("todos", []),
            agent_id=raw.get("agent_id"),
        )