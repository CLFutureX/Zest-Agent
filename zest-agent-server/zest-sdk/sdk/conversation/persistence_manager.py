from common.utils.common import AgentID, ConversationID
from sdk.conversation.persistence import ConversationPersistence
from sdk.conversation.state import ConversationState
from sdk.event.agent_state import AgentStateUpdateEvent
from sdk.event.conversation_state import ConversationStateUpdateEvent
from sdk.event.event_center import EventConsumer


class PersistenceConsumer(EventConsumer):
    def __init__(
        self,
        conversation_state: ConversationState,
        persistence_service: ConversationPersistence,
        conversation_id: ConversationID | None,
        agent_id: AgentID | None = None,
        event_types: list[type] | None = None,
    ):
        super().__init__(
            conversation_id,
            agent_id,
            event_types or [ConversationStateUpdateEvent, AgentStateUpdateEvent],
        )
        self._conversation_state = conversation_state
        self._persistence_service = persistence_service

    def on_event(self, event: ConversationStateUpdateEvent | AgentStateUpdateEvent):
        if isinstance(event, AgentStateUpdateEvent):
            main_agent_state = self._conversation_state.main_agent_state
            if main_agent_state is None or event.agent_id != main_agent_state.agent_id:
                return
            if event.key == "execution_status":
                self._conversation_state._notify_state_change(
                    "execution_status",
                    main_agent_state.execution_status,
                )

        self._persistence_service.save_snapshot(self._conversation_state.to_snapshot())
