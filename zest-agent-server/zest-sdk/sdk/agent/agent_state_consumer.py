import uuid

from pydantic import Field

from sdk.agent.agent_state import AgentExecutionStatus, AgentState
from sdk.event.base import Event
from sdk.event.event_center import EventConsumer
from common.logger import get_logger
from common.utils.common import AgentID, ConversationID
logger = get_logger(__name__)

class AgentStateEvent(Event):
    """Agent状态变更事件

    当Agent状态发生变化时发布此事件，用于通知订阅者更新状态

    Attributes:
        agent_state: Agent状态快照
        change_type: 变更类型（created/status_changed/completed/failed）
        previous_status: 之前的状态（如果是状态变更）
    """

    agent_state: AgentState = Field(..., description="Agent状态快照")
    change_type: str = Field(
        ..., description="变更类型: created/status_changed/completed/failed/cancelled"
    )
    previous_status: AgentExecutionStatus | None = Field(
        default=None, description="之前的执行状态"
    )

    class Config:
        arbitrary_types_allowed = True

    @property
    def visualize(self):
        """可视化表示"""
        from rich.text import Text

        content = Text()
        content.append(f"AgentStateEvent: {self.change_type}\n", style="bold cyan")
        content.append(f"Agent ID: {self.agent_state.agent_id}\n")
        content.append(f"Status: {self.agent_state.execution_status.value}\n")
        if self.previous_status:
            content.append(f"Previous Status: {self.previous_status.value}\n")
        return content



class AgentEventPersistentConsumer(EventConsumer):
    def __init__(
        self,
        agent_state: AgentState,
        conversation_id: ConversationID | None = None,
        agent_id: AgentID | None = None,
        event_types: list[type] | None = [Event],
        agent_type: str | None = "main"
    ):
        super().__init__(conversation_id, agent_id, event_types)
        self.agent_state = agent_state
        self.agent_type = agent_type

    def on_event(self, event):
        assert self.agent_state.events is not None
       
        logger.info(f"AgentEventPersistentConsumer event {self.agent_type}")
        return self.agent_state.events.append(event)
