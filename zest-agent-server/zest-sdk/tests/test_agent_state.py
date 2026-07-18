"""AgentState 显式 mutation API 单元测试

测试策略：
- 直接构造 AgentState 实例（不走 build 避免依赖 EventLog 基础设施）
- 用 MagicMock 模拟 EventCenter，验证事件发布的 key/value/调用次数
- 验证幂等性：相同值不发布事件
- 验证容器型字段的整体替换语义
"""

from unittest.mock import MagicMock

import pytest

from common.utils.common import ConversationID, ExecutionStatus
from sdk.agent.agent_state import AgentState


def _make_agent_state(agent_id: str = "test-agent") -> AgentState:
    """构造一个最小可用的 AgentState，绕过 build() 的 EventLog 依赖。"""
    state = AgentState(
        agent_id=agent_id,
        agent_type="Agent",
        conversation_id="conv-1",
    )
    state._events = []
    return state


def _bind_event_center(state: AgentState) -> MagicMock:
    """给 AgentState 绑定一个 mock EventCenter，返回 mock 供断言。"""
    ec = MagicMock()
    state.bind_event_center(ec, "conv-1")
    return ec


# =====================================================================
# set_execution_status
# =====================================================================


class TestSetExecutionStatus:

    def test_publishes_event_on_change(self):
        state = _make_agent_state()
        ec = _bind_event_center(state)

        state.set_execution_status(ExecutionStatus.RUNNING)

        assert state.execution_status == ExecutionStatus.RUNNING
        ec.publish.assert_called_once()
        event = ec.publish.call_args.kwargs["event"]
        assert event.key == "execution_status"
        assert event.value == ExecutionStatus.RUNNING
        assert event.agent_id == "test-agent"

    def test_no_event_when_same_status(self):
        state = _make_agent_state()
        state.execution_status = ExecutionStatus.IDLE
        ec = _bind_event_center(state)

        state.set_execution_status(ExecutionStatus.IDLE)

        ec.publish.assert_not_called()

    def test_no_event_without_event_center(self):
        state = _make_agent_state()

        state.set_execution_status(ExecutionStatus.RUNNING)

        assert state.execution_status == ExecutionStatus.RUNNING


# =====================================================================
# activate_knowledge_skills / activate_experiences
# =====================================================================


class TestActivateKnowledgeSkills:

    def test_appends_and_publishes(self):
        state = _make_agent_state()
        ec = _bind_event_center(state)

        state.activate_knowledge_skills(["skill-a", "skill-b"])

        assert state.activated_knowledge_skills == ["skill-a", "skill-b"]
        ec.publish.assert_called_once()
        event = ec.publish.call_args.kwargs["event"]
        assert event.key == "activated_knowledge_skills"

    def test_no_event_on_empty_input(self):
        state = _make_agent_state()
        ec = _bind_event_center(state)

        state.activate_knowledge_skills([])

        ec.publish.assert_not_called()

    def test_accumulates_across_calls(self):
        state = _make_agent_state()
        _bind_event_center(state)

        state.activate_knowledge_skills(["a"])
        state.activate_knowledge_skills(["b"])

        assert state.activated_knowledge_skills == ["a", "b"]


class TestActivateExperiences:

    def test_appends_and_publishes(self):
        state = _make_agent_state()
        ec = _bind_event_center(state)

        state.activate_experiences(["exp-1"])

        assert state.activated_experiences == ["exp-1"]
        ec.publish.assert_called_once()
        event = ec.publish.call_args.kwargs["event"]
        assert event.key == "activated_experiences"


# =====================================================================
# update_metadata
# =====================================================================


class TestUpdateMetadata:

    def test_merges_and_publishes(self):
        state = _make_agent_state()
        state.metadata = {"existing": "value"}
        ec = _bind_event_center(state)

        state.update_metadata(new_key="new_value")

        assert state.metadata == {"existing": "value", "new_key": "new_value"}
        ec.publish.assert_called_once()
        event = ec.publish.call_args.kwargs["event"]
        assert event.key == "metadata"

    def test_no_event_on_empty_kwargs(self):
        state = _make_agent_state()
        ec = _bind_event_center(state)

        state.update_metadata()

        ec.publish.assert_not_called()

    def test_overwrites_existing_key(self):
        state = _make_agent_state()
        state.metadata = {"k": "old"}
        _bind_event_center(state)

        state.update_metadata(k="new")

        assert state.metadata["k"] == "new"


# =====================================================================
# replace_todos
# =====================================================================


class TestReplaceTodos:

    def test_replaces_and_publishes(self):
        state = _make_agent_state()
        ec = _bind_event_center(state)
        new_todos = [{"task": "do something"}]

        state.replace_todos(new_todos)

        assert state.todos == new_todos
        ec.publish.assert_called_once()
        event = ec.publish.call_args.kwargs["event"]
        assert event.key == "todos"

    def test_no_event_when_identical(self):
        state = _make_agent_state()
        state.todos = [{"task": "same"}]
        ec = _bind_event_center(state)

        state.replace_todos([{"task": "same"}])

        ec.publish.assert_not_called()


# =====================================================================
# set_blocked_actions / set_blocked_messages
# =====================================================================


class TestSetBlockedActions:

    def test_sets_and_publishes(self):
        state = _make_agent_state()
        ec = _bind_event_center(state)

        state.set_blocked_actions({"act-1": "dangerous"})

        assert state.blocked_actions == {"act-1": "dangerous"}
        ec.publish.assert_called_once()
        event = ec.publish.call_args.kwargs["event"]
        assert event.key == "blocked_actions"

    def test_no_event_when_identical(self):
        state = _make_agent_state()
        state.blocked_actions = {"a": "r"}
        ec = _bind_event_center(state)

        state.set_blocked_actions({"a": "r"})

        ec.publish.assert_not_called()


class TestSetBlockedMessages:

    def test_sets_and_publishes(self):
        state = _make_agent_state()
        ec = _bind_event_center(state)

        state.set_blocked_messages({"msg-1": "sensitive"})

        assert state.blocked_messages == {"msg-1": "sensitive"}
        ec.publish.assert_called_once()
        event = ec.publish.call_args.kwargs["event"]
        assert event.key == "blocked_messages"


# =====================================================================
# block_action / pop_blocked_action / block_message / pop_blocked_message
# =====================================================================


class TestBlockAction:

    def test_adds_entry_and_publishes(self):
        state = _make_agent_state()
        ec = _bind_event_center(state)

        state.block_action("act-1", "too risky")

        assert state.blocked_actions == {"act-1": "too risky"}
        ec.publish.assert_called_once()

    def test_pop_removes_and_publishes(self):
        state = _make_agent_state()
        state.block_action("act-1", "reason")
        ec = _bind_event_center(state)
        ec.publish.reset_mock()

        reason = state.pop_blocked_action("act-1")

        assert reason == "reason"
        assert "act-1" not in state.blocked_actions
        ec.publish.assert_called_once()

    def test_pop_returns_none_when_absent(self):
        state = _make_agent_state()
        ec = _bind_event_center(state)

        result = state.pop_blocked_action("nonexistent")

        assert result is None
        ec.publish.assert_not_called()


class TestBlockMessage:

    def test_adds_entry_and_publishes(self):
        state = _make_agent_state()
        ec = _bind_event_center(state)

        state.block_message("msg-1", "sensitive")

        assert state.blocked_messages == {"msg-1": "sensitive"}
        ec.publish.assert_called_once()

    def test_pop_removes_and_publishes(self):
        state = _make_agent_state()
        state.block_message("msg-1", "secret")
        ec = _bind_event_center(state)
        ec.publish.reset_mock()

        reason = state.pop_blocked_message("msg-1")

        assert reason == "secret"
        assert "msg-1" not in state.blocked_messages
        ec.publish.assert_called_once()


# =====================================================================
# set_main_agent_flag
# =====================================================================


class TestSetMainAgentFlag:

    def test_changes_and_publishes(self):
        state = _make_agent_state()
        ec = _bind_event_center(state)

        state.set_main_agent_flag(False)

        assert state.is_main_agent is False
        ec.publish.assert_called_once()
        event = ec.publish.call_args.kwargs["event"]
        assert event.key == "is_main_agent"

    def test_no_event_when_same(self):
        state = _make_agent_state()
        assert state.is_main_agent is True
        ec = _bind_event_center(state)

        state.set_main_agent_flag(True)

        ec.publish.assert_not_called()


# =====================================================================
# mark_running / mark_finish
# =====================================================================


class TestMarkRunning:

    def test_sets_status_and_started_at(self):
        state = _make_agent_state()
        ec = _bind_event_center(state)

        state.mark_running()

        assert state.execution_status == ExecutionStatus.RUNNING
        assert state.started_at is not None
        assert ec.publish.call_count == 2  # execution_status + started_at


class TestMarkFinish:

    def test_sets_status_completed_at_and_metadata(self):
        state = _make_agent_state()
        ec = _bind_event_center(state)

        state.mark_finish(result_summary="done")

        assert state.execution_status == ExecutionStatus.FINISHED
        assert state.completed_at is not None
        assert state.metadata.get("result_summary") == "done"
        assert ec.publish.call_count == 3  # execution_status + completed_at + metadata

    def test_no_metadata_when_no_summary(self):
        state = _make_agent_state()
        _bind_event_center(state)

        state.mark_finish()

        assert "result_summary" not in state.metadata
