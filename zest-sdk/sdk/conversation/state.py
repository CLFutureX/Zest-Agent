# state.py
import json
from collections.abc import Sequence
from enum import Enum
from pathlib import Path
from typing import Any, Self

from pydantic import Field, PrivateAttr, model_validator

from sdk.agent.base import AgentBase
from sdk.context.agent_state import (
    AgentExecutionStatus,
    AgentState,
    AgentStateRegistry,
)
from sdk.conversation.conversation_stats import ConversationStats
from sdk.conversation.fifo_lock import FIFOLock
from sdk.conversation.persistence_const import BASE_STATE
from sdk.conversation.secret_registry import SecretRegistry
from sdk.conversation.types import ConversationCallbackType, ConversationID
from sdk.event import ActionEvent, ObservationEvent, UserRejectObservation
from sdk.event.base import Event
from sdk.io import FileStore, InMemoryFileStore, LocalFileStore
from sdk.logger import get_logger
from sdk.security.analyzer import SecurityAnalyzerBase
from sdk.security.confirmation_policy import (
    ConfirmationPolicyBase,
    NeverConfirm,
)
from sdk.utils.cipher import Cipher
from sdk.utils.models import ZestAgent
from sdk.workspace.base import BaseWorkspace


logger = get_logger(__name__)


class ConversationExecutionStatus(str, Enum):
    """Enum representing the current execution state of the conversation."""

    IDLE = "idle"  # Conversation is ready to receive tasks
    RUNNING = "running"  # Conversation is actively processing
    PAUSED = "paused"  # Conversation execution is paused by user
    WAITING_FOR_CONFIRMATION = (
        "waiting_for_confirmation"  # Conversation is waiting for user confirmation
    )
    FINISHED = "finished"  # Conversation has completed the current task
    ERROR = "error"  # Conversation encountered an error (optional for future use)
    STUCK = "stuck"  # Conversation is stuck in a loop or unable to proceed
    DELETING = "deleting"  # Conversation is in the process of being deleted


class ConversationState(ZestAgent):
    """会话状态 - 存储会话级别的公共共享数据

    职责：
    1. 管理会话级共享资源（workspace, secret_registry, event_center 等）
    2. 管理所有 Agent 的状态（agent_state_registry）
    3. 提供会话级配置（confirmation_policy, security_analyzer 等）
    4. 提供持久化机制（_fs, _cipher）

    设计原则：
    - 只包含多个 Agent 共享的数据
    - Agent 独立数据存储在 AgentState 中
    - 通过 agent_state_registry 管理所有 Agent 状态

    新架构数据流：
    ConversationState (公共共享数据)
        ├─ AgentState (MainAgent)
        │   ├─ agent, llm, tools
        │   ├─ blocked_actions, _events
        │   └─ conversation_state 引用 ───┐
        │                                 │
        ├─ AgentState (SubAgent1)         │
        │   └─ conversation_state 引用 ───┤
        │                                 │
        └─ AgentState (SubAgent2)         │
            └─ conversation_state 引用 ───┘
    """

    # ===== 基础标识 =====
    id: ConversationID = Field(description="Unique conversation ID")

    # ===== 运行时控制标志 =====
    # is_paused: bool = Field(
    #     default=False,
    #     description="会话是否被暂停（运行时控制标志，不持久化到状态）"
    # )

    # ===== 会话级执行状态（新增）=====
    execution_status: ConversationExecutionStatus = Field(
        default=ConversationExecutionStatus.IDLE,
        description="会话级执行状态（基于所有Agent状态聚合计算）",
    )

    # ===== 会话级共享资源 =====
    workspace: BaseWorkspace = Field(
        ...,
        description=(
            "Workspace used by the agent to execute commands and read/write files. "
            "Not the process working directory."
        ),
    )
    persistence_dir: str | None = Field(
        default="workspace/conversations",
        description="Directory for persisting conversation state and events. "
        "If None, conversation will not be persisted.",
    )

    # ===== 会话级配置 =====
    max_iterations: int = Field(
        default=500,
        gt=0,
        description="Maximum number of iterations the agent can "
        "perform in a single run.",
    )
    stuck_detection: bool = Field(
        default=True,
        description="Whether to enable stuck detection for the agent.",
    )

    # ===== 会话级安全策略（所有 Agent 共享）=====
    confirmation_policy: ConfirmationPolicyBase = NeverConfirm()
    security_analyzer: SecurityAnalyzerBase | None = Field(
        default=None,
        description="Optional security analyzer to evaluate action risks.",
    )

    # ===== 会话级知识池 =====
    # activated_experiences: list[str] = Field(
    #     default_factory=list, description="激活的经验id"
    # )

    # ===== Agent 状态注册表（核心）=====
    agent_state_registry: AgentStateRegistry = Field(
        default_factory=AgentStateRegistry,
        description="Agent状态注册表，管理MainAgent和所有SubAgent的状态。支持checkpoint断点续跑。",
    )

    # ===== 会话级统计与秘钥管理 =====
    stats: ConversationStats = Field(
        default_factory=ConversationStats,
        description="Conversation statistics for tracking LLM metrics",
    )

    secret_registry: SecretRegistry = Field(
        default_factory=SecretRegistry,
        description="Registry for handling secrets in bash commands (environment variables)",
    )

    # ===== Private attrs (NOT Fields) =====
    _fs: FileStore = PrivateAttr()  # filestore for persistence
    _cipher: Cipher | None = PrivateAttr(default=None)  # cipher for secret encryption
    _autosave_enabled: bool = PrivateAttr(
        default=False
    )  # to avoid recursion during init
    _on_state_change: ConversationCallbackType | None = PrivateAttr(
        default=None
    )  # callback for state changes
    _lock: FIFOLock = PrivateAttr(
        default_factory=FIFOLock
    )  # FIFO lock for thread safety
    _user_id: str | None = PrivateAttr(
        default=None
    )  # optional user ID for multi-user contexts
    _has_load_base_memory: bool = PrivateAttr(default=False)

    @model_validator(mode="before")
    @classmethod
    def _handle_secrets_manager_alias(cls, data: Any) -> Any:
        """Handle legacy 'secrets_manager' field name for backward compatibility."""
        if isinstance(data, dict) and "secrets_manager" in data:
            data["secret_registry"] = data.pop("secrets_manager")
        return data

    @property
    def user_id(self) -> str | None:
        """Optional user ID associated with this conversation (for multi-user contexts)."""
        return self._user_id

    @property
    def env_observation_persistence_dir(self) -> str | None:
        """Directory for persisting environment observation files."""
        if self.persistence_dir is None:
            return None
        return str(Path(self.persistence_dir) / "observations")

    def set_on_state_change(self, callback: ConversationCallbackType | None) -> None:
        """Set a callback to be called when state changes.

        Args:
            callback: A function that takes an Event (ConversationStateUpdateEvent)
                     or None to remove the callback
        """
        self._on_state_change = callback

    # ===== Base snapshot helpers (same FileStore usage you had) =====
    def _save_base_state(self, fs: FileStore) -> None:
        """
        Persist base state snapshot (no events; events are file-backed).

        If a cipher is configured, secrets will be encrypted. Otherwise, they
        will be redacted (serialized as '**********').
        """
        context = {"cipher": self._cipher} if self._cipher else None
        # Warn if secrets exist but no cipher is configured
        if not self._cipher and self.secret_registry.secret_sources:
            logger.warning(
                f"Saving conversation state without cipher - "
                f"{len(self.secret_registry.secret_sources)} secret(s) will be "
                "redacted and lost on restore. Consider providing a cipher to "
                "preserve secrets."
            )
        print(f"context type: {type(context)}")
        print(f"context attributes: {dir(context) if hasattr(context, '__dict__') else 'no __dict__'}")
        print(f"context keys: {context.keys() if isinstance(context, dict) else 'not a dict'}")
        payload = self.model_dump_json(exclude_none=True, context=context)
     
        # payload = self.model_dump_json(exclude_none=True, context=context)
        fs.write(BASE_STATE, payload, cache=False)

    def set_load_base_memory(self):
        self._has_load_base_memory = True

    @property
    def load_base_memory(self) -> bool:
        return self._has_load_base_memory

    # ===== Factory: open-or-create (no load/save methods needed) =====
    @classmethod
    def create(
        cls: type["ConversationState"],
        id: ConversationID,
        agent: AgentBase,
        workspace: BaseWorkspace,
        persistence_dir: str | None = None,
        max_iterations: int = 500,
        stuck_detection: bool = True,
        cipher: Cipher | None = None,
    ) -> "ConversationState":
        """Create a new conversation state or resume from persistence.

        This factory method handles both new conversation creation and resumption
        from persisted state.

        **New conversation:**
        The provided Agent is stored in MainAgent's AgentState. Pydantic validation
        happens via the cls() constructor.

        **Restored conversation:**
        The AgentStateRegistry is restored from checkpoint, containing all Agent states.
        The provided Agent is used to update the MainAgent's AgentState.

        Args:
            id: Unique conversation identifier
            agent: The MainAgent to use (stored in AgentState, not ConversationState)
            workspace: Working directory for agent operations
            persistence_dir: Directory for persisting state and events
            max_iterations: Maximum iterations per run
            stuck_detection: Whether to enable stuck detection
            cipher: Optional cipher for encrypting/decrypting secrets in
                    persisted state. If provided, secrets are encrypted when
                    saving and decrypted when loading. If not provided, secrets
                    are redacted (lost) on serialization.

        Returns:
            ConversationState ready for use

        Raises:
            ValueError: If conversation ID mismatch on restore
            ValidationError: If fields fail Pydantic validation
        """
        file_store = (
            LocalFileStore(persistence_dir, cache_limit_size=max_iterations)
            if persistence_dir
            else InMemoryFileStore()
        )

        try:
            base_text = file_store.read(BASE_STATE)
        except FileNotFoundError:
            base_text = None

        # ---- Resume path ----
        if base_text:
            # Use cipher context for decrypting secrets if provided
            context = {"cipher": cipher} if cipher else None
            state = cls.model_validate(json.loads(base_text), context=context)

            # Restore the conversation with the same id
            if state.id != id:
                raise ValueError(
                    f"Conversation ID mismatch: provided {id}, "
                    f"but persisted state has {state.id}"
                )

            # Attach filestore and cipher
            state._fs = file_store
            state._cipher = cipher

            # Commit runtime-provided values (may autosave)
            state._autosave_enabled = True
            state.workspace = workspace
            state.max_iterations = max_iterations

            # Note: stats and agent_state_registry are already deserialized from checkpoint.

            # AgentStateRegistry 已经通过 model_validate 自动从 checkpoint 恢复
            agent_count = len(state.agent_state_registry.get_all())

            # 用户提供的 agent 参数可能与 checkpoint 不一致，这里我们：
            # 1. 如果用户提供了新的 agent（如重新配置了 LLM），则使用新的 agent
            # 2. 否则从 AgentState 重建 agent
            main_agent_state = state.get_main_agent_state()
            if main_agent_state:
                if agent:
                    # 用户提供了新的 agent，更新 AgentState 的配置
                    logger.info("Updating MainAgent config with new agent instance")

                    # 重新提取配置（不再需要 agent_secret_registry）
                    state.update_agent_config(agent)
                    # Note: 实际的 Agent 实例由外部（Conversation）持有，不存储在 AgentState 中
                else:
                    # 目前一定会提供agent 用户没有提供 agent，从 checkpoint 重建
                    logger.info("Rebuilding MainAgent from checkpoint")

                    # TODO: 需要让用户重新提供 API key
                    # 这里只是占位，实际使用时需要外部提供
                    logger.warning(
                        "Rebuilding agent from checkpoint requires secrets. "
                        "Make sure API keys are provided via environment variables or other means."
                    )

            else:
                logger.warning("No MainAgent state found after resume")

            logger.info(
                f"Resumed conversation {state.id} from checkpoint.\n"
                f"Restored {agent_count} agent states (Main + SubAgents).\n"
                f"State: {state.model_dump(exclude={'agent_state_registry'})}\n"
            )

            # 打印恢复的Agent状态统计
            if agent_count > 0:
                stats_summary = state.agent_state_registry.get_statistics()
                logger.info(f"Agent states statistics: {stats_summary}")

            return state

        # ---- Fresh path ----
        if agent is None:
            raise ValueError(
                "agent is required when initializing a new ConversationState"
            )

        state = cls(
            id=id,
            workspace=workspace,
            persistence_dir=persistence_dir,
            max_iterations=max_iterations,
            stuck_detection=stuck_detection,
        )
        state._fs = file_store
        state._cipher = cipher
        state.stats = ConversationStats()

        main_agent_state = AgentState.build(
            conversation_state=state,
            agent=agent,
            parent_agent_id=None,
            task_description="Main conversation task",
        )
        state.agent_state_registry.register(main_agent_state)

        logger.info(f"Created main agent state for new conversation {id}")

        state._save_base_state(file_store)  # initial snapshot
        state._autosave_enabled = True
        logger.info(
            f"Created new conversation {state.id}\nState: {state.model_dump()}\n"
        )
        return state

    # ===== Auto-persist base on public field changes =====
    def __setattr__(self, name, value):
        # Only autosave when:
        # - autosave is enabled (set post-init)
        # - the attribute is a *public field* (not a PrivateAttr)
        # - we have a filestore to write to
        _sentinel = object()
        old = getattr(self, name, _sentinel)
        super().__setattr__(name, value)

        is_field = name in self.__class__.model_fields
        autosave_enabled = getattr(self, "_autosave_enabled", False)
        fs = getattr(self, "_fs", None)

        if not (autosave_enabled and is_field and fs is not None):
            return

        if old is _sentinel or old != value:
            try:
                self._save_base_state(fs)
            except Exception as e:
                logger.exception("Auto-persist base_state failed", exc_info=True)
                raise e

            # Call state change callback if set
            callback = getattr(self, "_on_state_change", None)
            if callback is not None and old is not _sentinel:
                try:
                    # Import here to avoid circular imports
                    from sdk.event.conversation_state import (
                        ConversationStateUpdateEvent,
                    )

                    # Create a ConversationStateUpdateEvent with the changed field
                    state_update_event = ConversationStateUpdateEvent(
                        key=name, value=value
                    )
                    callback(state_update_event)
                except Exception:
                    logger.exception(
                        f"State change callback failed for field {name}", exc_info=True
                    )

    # ===== AgentState操作的辅助方法 =====

    def block_action(self, agent_id: str, action_id: str, reason: str) -> None:
        """在指定Agent的状态中阻止一个动作

        Args:
            agent_id: Agent ID
            action_id: 动作 ID
            reason: 阻止原因
        """
        agent_state = self.agent_state_registry.get(agent_id)
        if agent_state:
            agent_state.blocked_actions = {
                **agent_state.blocked_actions,
                action_id: reason,
            }
        else:
            logger.warning(
                f"Agent {agent_id} not found, cannot block action {action_id}"
            )

    def pop_blocked_action(self, agent_id: str, action_id: str) -> str | None:
        """从指定Agent的状态中移除并返回被阻止的动作原因

        Args:
            agent_id: Agent ID
            action_id: 动作 ID

        Returns:
            阻止原因，如果不存在则返回 None
        """
        agent_state = self.agent_state_registry.get(agent_id)
        if not agent_state:
            return None

        if action_id not in agent_state.blocked_actions:
            return None
        updated = dict(agent_state.blocked_actions)
        reason = updated.pop(action_id)
        agent_state.blocked_actions = updated
        return reason

    def block_message(self, agent_id: str, message_id: str, reason: str) -> None:
        """在指定Agent的状态中阻止一个消息

        Args:
            agent_id: Agent ID
            message_id: 消息 ID
            reason: 阻止原因
        """
        agent_state = self.agent_state_registry.get(agent_id)
        if agent_state:
            agent_state.blocked_messages = {
                **agent_state.blocked_messages,
                message_id: reason,
            }
        else:
            logger.warning(
                f"Agent {agent_id} not found, cannot block message {message_id}"
            )

    def pop_blocked_message(self, agent_id: str, message_id: str) -> str | None:
        """从指定Agent的状态中移除并返回被阻止的消息原因

        Args:
            agent_id: Agent ID
            message_id: 消息 ID

        Returns:
            阻止原因，如果不存在则返回 None
        """
        agent_state = self.agent_state_registry.get(agent_id)
        if not agent_state:
            return None

        if message_id not in agent_state.blocked_messages:
            return None
        updated = dict(agent_state.blocked_messages)
        reason = updated.pop(message_id)
        agent_state.blocked_messages = updated
        return reason

    @staticmethod
    def get_unmatched_actions(events: Sequence[Event]) -> list[ActionEvent]:
        """Find actions in the event history that don't have matching observations.

        This method identifies ActionEvents that don't have corresponding
        ObservationEvents or UserRejectObservations, which typically indicates
        actions that are pending confirmation or execution.

        Args:
            events: List of events to search through

        Returns:
            List of ActionEvent objects that don't have corresponding observations,
            in chronological order
        """
        observed_action_ids = set()
        unmatched_actions = []
        # Search in reverse - recent events are more likely to be unmatched
        for event in reversed(events):
            if isinstance(event, (ObservationEvent, UserRejectObservation)):
                observed_action_ids.add(event.action_id)
            elif isinstance(event, ActionEvent):
                # Only executable actions (validated) are considered pending
                if event.action is not None and event.id not in observed_action_ids:
                    # Insert at beginning to maintain chronological order in result
                    unmatched_actions.insert(0, event)

        return unmatched_actions

    # ===== FIFOLock delegation methods =====
    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        """
        Acquire the lock.

        Args:
            blocking: If True, block until lock is acquired. If False, return
                     immediately.
            timeout: Maximum time to wait for lock (ignored if blocking=False).
                    -1 means wait indefinitely.

        Returns:
            True if lock was acquired, False otherwise.
        """
        return self._lock.acquire(blocking=blocking, timeout=timeout)

    def release(self) -> None:
        """
        Release the lock.

        Raises:
            RuntimeError: If the current thread doesn't own the lock.
        """
        self._lock.release()

    def __enter__(self: Self) -> Self:
        """Context manager entry."""
        self._lock.acquire()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self._lock.release()

    def locked(self) -> bool:
        """
        Return True if the lock is currently held by any thread.
        """
        return self._lock.locked()

    def owned(self) -> bool:
        """
        Return True if the lock is currently held by the calling thread.
        """
        return self._lock.owned()

    # ===== AgentStateRegistry 辅助方法 =====

    def get_main_agent_state(self) -> AgentState:
        """获取MainAgent的状态"""

        return self.agent_state_registry.get_main_agent_state()

    def update_agent_config(
        self, agent: AgentBase, agent_id: str | None = None
    ) -> None:
        """更新Agent配置（当Agent发生变化时，如加载插件后）

        ⭐ 简化版：直接更新 AgentState 的配置字段，不再使用 AgentConfig

        Args:
            agent: 新的Agent实例（用于提取配置）
            agent_id: 要更新的Agent ID。如果为None，则更新MainAgent
        """
        from sdk.logger import get_logger

        logger = get_logger(__name__)

        # 如果没有指定agent_id，更新MainAgent
        if agent_id is None:
            agent_state = self.get_main_agent_state()
            if not agent_state:
                logger.warning("Cannot update agent config: MainAgent state not found")
                return
        else:
            agent_state = self.agent_state_registry.get(agent_id)
            if not agent_state:
                logger.warning(
                    f"Cannot update agent config: AgentState {agent_id} not found"
                )
                return

        # ⭐ 直接更新 AgentState 的配置字段（不使用 AgentConfig）
        agent_state.llm = agent.llm
        agent_state.tools = agent.tools
        agent_state.agent_context = agent.agent_context
        agent_state.mcp_config = agent.mcp_config
        agent_state.filter_tools_regex = agent.filter_tools_regex
        agent_state.include_default_tools = agent.include_default_tools
        agent_state.custom_system_prompt = agent.custom_system_prompt

        logger.debug(
            f"Updated agent config in state (agent_id: {agent_state.agent_id}, "
            f"llm: {agent_state.llm.model if agent_state.llm else 'None'}, "
            f"tools: {len(agent_state.tools) if agent_state.tools else 0})"
        )

    def create_sub_agent_state(
        self,
        subagent_name: str,
        task_description: str,
        parent_agent_id: str | None = None,
        execution_mode: str = "sequential",
        depends_on: list[str] | None = None,
    ) -> AgentState:
        """为SubAgent创建状态

        Args:
            subagent_name: SubAgent名称
            task_description: 任务描述
            parent_agent_id: 父Agent ID，如果为None则使用MainAgent
            execution_mode: 执行模式（sequential/parallel/dependent）
            depends_on: 依赖的Agent ID列表

        Returns:
            创建的AgentState
        """
        from sdk.context.agent_state import (
            AgentExecutionMode,
            AgentExecutionStatus,
        )

        # 如果没有指定父Agent，使用MainAgent
        if parent_agent_id is None:
            parent_state = self.get_main_agent_state()
            if not parent_state:
                raise ValueError("Main agent state not found")
            parent_agent_id = parent_state.agent_id
        else:
            parent_state = self.agent_state_registry.get(parent_agent_id)
            if not parent_state:
                raise ValueError(f"Parent agent {parent_agent_id} not found")

        depth = parent_state.depth + 1

        # 转换执行模式
        mode_map = {
            "sequential": AgentExecutionMode.SEQUENTIAL,
            "parallel": AgentExecutionMode.PARALLEL,
            "dependent": AgentExecutionMode.DEPENDENT,
        }
        exec_mode = mode_map.get(execution_mode, AgentExecutionMode.SEQUENTIAL)

        subagent_state = AgentState(
            agent_id=f"sub_{subagent_name}_{id(self)}_{depth}",
            is_main_agent=False,
            parent_agent_id=parent_agent_id,
            depth=depth,
            task_description=task_description,
            execution_mode=exec_mode,
            execution_status=AgentExecutionStatus.PENDING,
            depends_on=depends_on or [],
        )

        self.agent_state_registry.register(subagent_state)
        logger.info(
            f"Created sub-agent state: {subagent_state.agent_id} "
            f"(parent: {parent_agent_id}, depth: {depth}, mode: {execution_mode})"
        )

        return subagent_state

    def get_agent_execution_summary(self) -> dict[str, Any]:
        """获取Agent执行摘要（用于调试和监控）"""
        stats = self.agent_state_registry.get_statistics()
        main_state = self.get_main_agent_state()

        return {
            "conversation_id": self.id,
            "main_agent_id": main_state.agent_id if main_state else None,
            "main_execution_status": main_state.execution_status.value
            if main_state
            else None,
            "agent_statistics": stats,
            "sub_agents": [
                {
                    "agent_id": state.agent_id,
                    "task": state.task_description,
                    "status": state.execution_status.value,
                    "mode": state.execution_mode.value,
                    "duration": state.get_execution_duration(),
                }
                for state in self.agent_state_registry.get_sub_agents(
                    main_state.agent_id if main_state else ""
                )
            ],
        }

    # ===== 会话状态聚合方法（新增）=====

    def compute_conversation_status(self) -> ConversationExecutionStatus:
        """基于所有 Agent 的状态计算会话级状态

        聚合规则：
        1. 任何 Agent RUNNING → RUNNING
        2. 全部 COMPLETED → FINISHED
        3. 至少一个 FAILED 且无 RUNNING → ERROR
        4. 至少一个 PENDING 且无 RUNNING → IDLE
        5. 其他保持当前状态

        Returns:
            计算出的会话状态
        """
        all_agents = self.agent_state_registry.get_all()

        if not all_agents:
            return ConversationExecutionStatus.IDLE

        # 检查是否有 RUNNING 的 Agent
        has_running = any(
            agent.execution_status == AgentExecutionStatus.RUNNING
            for agent in all_agents
        )
        if has_running:
            return ConversationExecutionStatus.RUNNING

        # 检查是否全部 COMPLETED
        all_completed = all(
            agent.execution_status == AgentExecutionStatus.COMPLETED
            for agent in all_agents
        )
        if all_completed:
            return ConversationExecutionStatus.FINISHED

        # 检查是否有 FAILED
        has_failed = any(
            agent.execution_status == AgentExecutionStatus.FAILED
            for agent in all_agents
        )
        if has_failed:
            return ConversationExecutionStatus.ERROR

        # 检查是否有 PENDING
        has_pending = any(
            agent.execution_status == AgentExecutionStatus.PENDING
            for agent in all_agents
        )
        if has_pending:
            return ConversationExecutionStatus.IDLE

        # 保持当前状态
        return self.execution_status

    def update_conversation_status(self) -> None:
        """更新会话状态（基于Agent状态聚合）"""
        new_status = self.compute_conversation_status()
        if new_status != self.execution_status:
            logger.debug(
                f"Conversation status changed: {self.execution_status.value} → {new_status.value}"
            )
            self.execution_status = new_status
