"""PersistenceConsumer 单元测试

测试策略：
- 用 MagicMock 模拟 ConversationState 和 ConversationPersistence
- 验证 ConversationStateUpdateEvent 触发 save_snapshot
- 验证 AgentStateUpdateEvent 只在匹配 main_agent 时触发 save_snapshot
- 验证不匹配的 AgentStateUpdateEvent 被忽略
"""

from unittest.mock import MagicMock

import pytest

from sdk.agent.agent_state import AgentState
from sdk.conversation.persistence_manager import PersistenceConsumer
from sdk.conversation.state import ConversationState
from sdk.event.agent_state import AgentStateUpdateEvent
from sdk.event.conversation_state import ConversationStateUpdateEvent


def _make_consumer() -> tuple[PersistenceConsumer, MagicMock, MagicMock]:
    """构造 PersistenceConsumer 及其 mock 依赖。"""
    agent_state = AgentState(agent_id="main-agent", agent_type="Agent", conversation_id="conv-1")
    agent_state._events = []

    conversation_state = MagicMock(spec=ConversationState)
    conversation_state.main_agent_state = agent_state
    conversation_state.id = "conv-1"

    persistence = MagicMock()

    consumer = PersistenceConsumer(
        conversation_state=conversation_state,
        persistence_service=persistence,
        conversation_id="conv-1",
    )
    return consumer, conversation_state, persistence


# =====================================================================
# ConversationStateUpdateEvent
# =====================================================================


class TestOnConversationStateUpdateEvent:

    def test_saves_snapshot_on_conversation_state_change(self):
        consumer, conv_state, persistence = _make_consumer()

        event = ConversationStateUpdateEvent(
            key="confirmation_policy", value="never"
        )
        consumer.on_event(event)

        persistence.save_snapshot.assert_called_once()
        snapshot = persistence.save_snapshot.call_args.args[0]
        assert snapshot is conv_state.to_snapshot.return_value

    def test_saves_snapshot_on_execution_status_change(self):
        consumer, conv_state, persistence = _make_consumer()

        event = ConversationStateUpdateEvent(
            key="execution_status", value="error"
        )
        consumer.on_event(event)

        persistence.save_snapshot.assert_called_once()


# =====================================================================
# AgentStateUpdateEvent - main agent match
# =====================================================================


class TestOnAgentStateUpdateEventMatched:

    def test_saves_snapshot_for_main_agent_event(self):
        consumer, conv_state, persistence = _make_consumer()
        conv_state._notify_state_change = MagicMock()

        event = AgentStateUpdateEvent(
            agent_id="main-agent",
            key="execution_status",
            value="running",
        )
        consumer.on_event(event)

        conv_state._notify_state_change.assert_called_once_with(
            "execution_status", conv_state.main_agent_state.execution_status
        )
        persistence.save_snapshot.assert_called_once()

# =====================================================================
# AgentStateUpdateEvent - sub-agent mismatch
# =====================================================================


class TestOnAgentStateUpdateEventMismatched:

    def test_ignores_subagent_event(self):
        consumer, conv_state, persistence = _make_consumer()

        event = AgentStateUpdateEvent(
            agent_id="sub-agent-1",
            key="execution_status",
            value="running",
        )
        consumer.on_event(event)

        persistence.save_snapshot.assert_not_called()

    def test_ignores_when_no_main_agent_state(self):
        consumer, conv_state, persistence = _make_consumer()
        conv_state.main_agent_state = None

        event = AgentStateUpdateEvent(
            agent_id="main-agent",
            key="execution_status",
            value="running",
        )
        consumer.on_event(event)

        persistence.save_snapshot.assert_not_called()


# =====================================================================
# Default event_types
# =====================================================================


class TestDefaultEventTypes:

    def test_subscribes_to_both_event_types(self):
        consumer, _, _ = _make_consumer()

        assert ConversationStateUpdateEvent in consumer.event_types
        assert AgentStateUpdateEvent in consumer.event_types
        assert len(consumer.event_types) == 2
