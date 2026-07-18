"""ConversationState 显式 mutation API 单元测试

测试策略：
- 直接构造 ConversationState（绕过 factory 避免依赖 AgentState.build）
- 用 MagicMock 模拟 EventCenter，验证事件发布的 key/value/调用次数
- 验证幂等性：相同值不发布事件
- 验证 update_secrets 覆盖了原本原地修改的问题
"""

from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from common.utils.common import ExecutionStatus
from sdk.agent.agent_state import AgentState
from sdk.conversation.conversation_stats import ConversationStats
from sdk.conversation.snapshot import ConversationStateSnapshot
from sdk.conversation.state import ConversationState
from sdk.security.llm_analyzer import LLMSecurityAnalyzer
from sdk.secret.secret_registry import SecretRegistry
from sdk.security.confirmation_policy import NeverConfirm, AlwaysConfirm


def _make_conversation_state() -> ConversationState:
    """构造一个最小可用的 ConversationState，不依赖 factory。"""
    from sdk.workspace.local import LocalWorkspace
    import tempfile

    workspace = LocalWorkspace(working_dir=tempfile.gettempdir())
    state = ConversationState(
        id="conv-1",
        workspace=workspace,
        max_iterations=500,
        confirmation_policy=NeverConfirm(),
    )
    return state


def _bind_event_center(state: ConversationState) -> MagicMock:
    """给 ConversationState 绑定一个 mock EventCenter，返回 mock 供断言。"""
    ec = MagicMock()
    state.bind_event_center(ec)
    return ec


# =====================================================================
# set_confirmation_policy
# =====================================================================


class TestSetConfirmationPolicy:

    def test_changes_and_publishes(self):
        state = _make_conversation_state()
        ec = _bind_event_center(state)

        new_policy = AlwaysConfirm()
        state.set_confirmation_policy(new_policy)

        assert state.confirmation_policy == new_policy
        ec.publish.assert_called_once()
        event = ec.publish.call_args.kwargs["event"]
        assert event.key == "confirmation_policy"
        assert event.value is new_policy

    def test_no_event_when_same_policy(self):
        state = _make_conversation_state()
        state.confirmation_policy = NeverConfirm()
        ec = _bind_event_center(state)

        state.set_confirmation_policy(state.confirmation_policy)

        ec.publish.assert_not_called()


# =====================================================================
# set_security_analyzer
# =====================================================================


class TestSetSecurityAnalyzer:

    def test_sets_and_publishes(self):
        state = _make_conversation_state()
        ec = _bind_event_center(state)

        analyzer = MagicMock()
        state.set_security_analyzer(analyzer)

        assert state.security_analyzer is analyzer
        ec.publish.assert_called_once()
        event = ec.publish.call_args.kwargs["event"]
        assert event.key == "security_analyzer"

    def test_no_event_when_same_analyzer(self):
        state = _make_conversation_state()
        analyzer = MagicMock()
        state.security_analyzer = analyzer
        ec = _bind_event_center(state)

        state.set_security_analyzer(analyzer)

        ec.publish.assert_not_called()


class TestSetExecutionStatus:

    def test_delegates_to_main_agent_state(self):
        state = _make_conversation_state()
        state.main_agent_state = AgentState(
            agent_id="main-agent",
            agent_type="Agent",
            conversation_id="conv-1",
            execution_status=ExecutionStatus.IDLE,
        )
        ec = _bind_event_center(state)

        state.set_execution_status(ExecutionStatus.RUNNING)

        assert state.execution_status == ExecutionStatus.RUNNING
        ec.publish.assert_not_called()

    def test_delegates_to_main_agent_state_mock(self):
        state = _make_conversation_state()
        agent_state = MagicMock(spec=AgentState)
        type(agent_state).execution_status = PropertyMock(return_value=ExecutionStatus.IDLE)
        state.main_agent_state = agent_state
        ec = _bind_event_center(state)

        state.set_execution_status(ExecutionStatus.RUNNING)

        agent_state.set_execution_status.assert_called_once_with(ExecutionStatus.RUNNING)
        ec.publish.assert_not_called()

    def test_no_event_when_same_status(self):
        state = _make_conversation_state()
        state.main_agent_state = AgentState(
            agent_id="main-agent",
            agent_type="Agent",
            conversation_id="conv-1",
            execution_status=ExecutionStatus.IDLE,
        )
        ec = _bind_event_center(state)

        state.set_execution_status(ExecutionStatus.IDLE)

        ec.publish.assert_not_called()

    def test_raises_without_main_agent(self):
        state = _make_conversation_state()

        with pytest.raises(RuntimeError, match="has no main_agent_state"):
            state.set_execution_status(ExecutionStatus.ERROR)

    def test_reads_status_from_main_agent_state(self):
        state = _make_conversation_state()
        agent_state = MagicMock(spec=AgentState)
        type(agent_state).execution_status = PropertyMock(return_value=ExecutionStatus.ERROR)
        state.main_agent_state = agent_state

        assert state.execution_status == ExecutionStatus.ERROR

    def test_read_raises_without_main_agent(self):
        state = _make_conversation_state()

        with pytest.raises(RuntimeError, match="has no main_agent_state"):
            _ = state.execution_status


# =====================================================================
# update_secrets
# =====================================================================


class TestUpdateSecrets:

    def test_updates_registry_and_publishes(self):
        state = _make_conversation_state()
        ec = _bind_event_center(state)

        state.update_secrets({"API_KEY": "secret-value"})

        assert "API_KEY" in state.secret_registry.secret_sources
        ec.publish.assert_called_once()
        event = ec.publish.call_args.kwargs["event"]
        assert event.key == "secret_registry"

    def test_no_event_without_event_center(self):
        state = _make_conversation_state()

        state.update_secrets({"API_KEY": "secret-value"})

        assert "API_KEY" in state.secret_registry.secret_sources


# =====================================================================
# attach_main_agent_state
# =====================================================================


class TestUpdateAgentConfig:

    def test_delegates_to_agent_state(self):
        state = _make_conversation_state()
        agent_state = AgentState(agent_id="agent-1", agent_type="Agent", conversation_id="conv-1")
        agent_state._events = []
        state.main_agent_state = agent_state

        mock_agent = MagicMock()
        mock_agent.mcp_config = {"mcp": True}
        mock_agent.filter_tools_regex = ".*"
        mock_agent.include_default_tools = ["tool1"]
        mock_agent.custom_system_prompt = "custom prompt"
        mock_agent.system_prompt_filename = "custom.j2"
        mock_agent.security_policy_filename = "custom_security.j2"
        mock_agent.system_prompt_kwargs = {"key": "value"}

        state.update_agent_config(mock_agent)

        assert agent_state.mcp_config == {"mcp": True}
        assert agent_state.filter_tools_regex == ".*"
        assert agent_state.include_default_tools == ["tool1"]
        assert agent_state.custom_system_prompt == "custom prompt"
        assert agent_state.system_prompt_filename == "custom.j2"
        assert agent_state.security_policy_filename == "custom_security.j2"
        assert agent_state.system_prompt_kwargs == {"key": "value"}


# =====================================================================
# from_snapshot
# =====================================================================


class TestFromSnapshot:

    @patch("sdk.conversation.state.create_event_log")
    def test_rehydrates_main_agent_event_log(self, create_event_log_mock):
        workspace = _make_conversation_state().workspace
        restored_event_log = MagicMock()
        create_event_log_mock.return_value = restored_event_log

        agent_state = AgentState(
            agent_id="main-agent",
            agent_type="Agent",
            conversation_id="conv-1",
            is_main_agent=True,
        )
        snapshot = ConversationStateSnapshot(
            id="conv-1",
            main_agent_state=agent_state,
            stats=ConversationStats(),
            secret_registry=SecretRegistry(),
        )

        state = ConversationState.from_snapshot(
            snapshot=snapshot,
            user_id="user-1",
            workspace=workspace,
        )

        create_event_log_mock.assert_called_once_with(
            conversation_id="conv-1",
            agent_id="main-agent",
            main_agent=True,
        )
        assert state.main_agent_state is not None
        assert state.main_agent_state.events is restored_event_log
        assert state.user_id == "user-1"

    @patch("sdk.conversation.state.create_event_log")
    def test_restores_confirmation_policy_from_snapshot(self, create_event_log_mock):
        workspace = _make_conversation_state().workspace
        create_event_log_mock.return_value = MagicMock()

        snapshot = ConversationStateSnapshot(
            id="conv-1",
            confirmation_policy=AlwaysConfirm(),
            main_agent_state=AgentState(
                agent_id="main-agent",
                agent_type="Agent",
                conversation_id="conv-1",
            ),
            stats=ConversationStats(),
            secret_registry=SecretRegistry(),
        )

        state = ConversationState.from_snapshot(
            snapshot=snapshot,
            user_id=None,
            workspace=workspace,
        )

        assert isinstance(state.confirmation_policy, AlwaysConfirm)

    @patch("sdk.conversation.state.create_event_log")
    def test_restores_security_analyzer_from_snapshot(self, create_event_log_mock):
        workspace = _make_conversation_state().workspace
        create_event_log_mock.return_value = MagicMock()

        snapshot = ConversationStateSnapshot(
            id="conv-1",
            security_analyzer=LLMSecurityAnalyzer(),
            main_agent_state=AgentState(
                agent_id="main-agent",
                agent_type="Agent",
                conversation_id="conv-1",
            ),
            stats=ConversationStats(),
            secret_registry=SecretRegistry(),
        )

        state = ConversationState.from_snapshot(
            snapshot=snapshot,
            user_id=None,
            workspace=workspace,
        )

        assert isinstance(state.security_analyzer, LLMSecurityAnalyzer)

    @patch("sdk.conversation.state.create_event_log")
    def test_skips_event_log_rehydration_without_main_agent_state(self, create_event_log_mock):
        workspace = _make_conversation_state().workspace
        snapshot = ConversationStateSnapshot(
            id="conv-1",
            stats=ConversationStats(),
            secret_registry=SecretRegistry(),
        )

        state = ConversationState.from_snapshot(
            snapshot=snapshot,
            user_id=None,
            workspace=workspace,
        )

        create_event_log_mock.assert_not_called()
        assert state.main_agent_state is None
        with pytest.raises(RuntimeError, match="has no main_agent_state"):
            _ = state.execution_status

    @patch("sdk.conversation.state.create_event_log")
    def test_prefers_main_agent_status_over_snapshot_status(self, create_event_log_mock):
        workspace = _make_conversation_state().workspace
        create_event_log_mock.return_value = MagicMock()

        snapshot = ConversationStateSnapshot(
            id="conv-1",
            execution_status=ExecutionStatus.RUNNING,
            main_agent_state=AgentState(
                agent_id="main-agent",
                agent_type="Agent",
                conversation_id="conv-1",
                execution_status=ExecutionStatus.ERROR,
            ),
            stats=ConversationStats(),
            secret_registry=SecretRegistry(),
        )

        state = ConversationState.from_snapshot(
            snapshot=snapshot,
            user_id=None,
            workspace=workspace,
        )

        assert state.execution_status == ExecutionStatus.ERROR


class TestToSnapshot:

    def test_raises_without_main_agent_state(self):
        state = _make_conversation_state()

        with pytest.raises(RuntimeError, match="has no main_agent_state"):
            state.to_snapshot()

    def test_includes_confirmation_policy(self):
        state = _make_conversation_state()
        state.main_agent_state = AgentState(
            agent_id="main-agent",
            agent_type="Agent",
            conversation_id="conv-1",
        )
        state.set_confirmation_policy(AlwaysConfirm())

        snapshot = state.to_snapshot()

        assert isinstance(snapshot.confirmation_policy, AlwaysConfirm)

    def test_includes_security_analyzer(self):
        state = _make_conversation_state()
        state.main_agent_state = AgentState(
            agent_id="main-agent",
            agent_type="Agent",
            conversation_id="conv-1",
        )
        state.set_security_analyzer(LLMSecurityAnalyzer())

        snapshot = state.to_snapshot()

        assert isinstance(snapshot.security_analyzer, LLMSecurityAnalyzer)

    def test_uses_main_agent_status_for_snapshot(self):
        state = _make_conversation_state()
        state.main_agent_state = AgentState(
            agent_id="main-agent",
            agent_type="Agent",
            conversation_id="conv-1",
            execution_status=ExecutionStatus.FINISHED,
        )

        snapshot = state.to_snapshot()

        assert snapshot.execution_status == ExecutionStatus.FINISHED
