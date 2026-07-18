from types import SimpleNamespace
from unittest.mock import MagicMock

from common.utils.common import ExecutionStatus
from sdk.agent.agent_state import AgentState
from sdk.conversation.impl.conversation_impl import LocalConversation
from sdk.event.llm_convertible.action import ActionEvent
from sdk.event.llm_convertible.observation import UserRejectObservation
from sdk.llm import MessageToolCall, TextContent


def _make_action_event(action_id: str = "action-1") -> ActionEvent:
    return ActionEvent(
        id=action_id,
        source="agent",
        thought=[TextContent(text="need approval")],
        action=None,
        tool_name="test_tool",
        tool_call_id="tool-call-1",
        tool_call=MessageToolCall(
            id="tool-call-1",
            name="test_tool",
            arguments='{"path": "demo.txt"}',
            origin="completion",
        ),
        llm_response_id="response-1",
    )


def _make_state(main_agent_state: AgentState) -> MagicMock:
    state = MagicMock()
    state.__enter__.return_value = state
    state.__exit__.return_value = None
    state.get_main_agent_state.return_value = main_agent_state
    return state


def test_reject_pending_actions_restores_idle_and_emits_rejections():
    main_agent_state = AgentState(
        agent_id="main-agent",
        agent_type="Agent",
        conversation_id="conv-1",
        execution_status=ExecutionStatus.WAITING_FOR_CONFIRMATION,
    )
    main_agent_state._events = []

    pending_action = _make_action_event()
    fake_conversation = SimpleNamespace(
        events=[pending_action],
        _state=_make_state(main_agent_state),
        _event_center=MagicMock(),
        agent=SimpleNamespace(id="main-agent"),
    )

    LocalConversation.reject_pending_actions(
        fake_conversation, reason="User rejected the action"
    )

    assert main_agent_state.execution_status == ExecutionStatus.IDLE
    fake_conversation._event_center.publish.assert_called_once()
    published_event = fake_conversation._event_center.publish.call_args.kwargs["event"]
    assert isinstance(published_event, UserRejectObservation)
    assert published_event.action_id == pending_action.id
    assert published_event.rejection_reason == "User rejected the action"


def test_reject_pending_actions_without_pending_actions_only_clears_waiting_state():
    main_agent_state = AgentState(
        agent_id="main-agent",
        agent_type="Agent",
        conversation_id="conv-1",
        execution_status=ExecutionStatus.WAITING_FOR_CONFIRMATION,
    )
    main_agent_state._events = []

    fake_conversation = SimpleNamespace(
        events=[],
        _state=_make_state(main_agent_state),
        _event_center=MagicMock(),
        agent=SimpleNamespace(id="main-agent"),
    )

    LocalConversation.reject_pending_actions(fake_conversation, reason="nothing to do")

    assert main_agent_state.execution_status == ExecutionStatus.IDLE
    fake_conversation._event_center.publish.assert_not_called()
