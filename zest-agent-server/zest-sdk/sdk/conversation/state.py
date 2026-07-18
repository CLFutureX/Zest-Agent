import pathlib

from collections.abc import Sequence

from pathlib import Path

from typing import TYPE_CHECKING, Any, Mapping, Self



from pydantic import Field, PrivateAttr, computed_field, model_validator







from sdk.agent.base import AgentBase



from sdk.agent.agent_state import AgentState



from sdk.conversation.base import ConversationCallbackType



from sdk.conversation.conversation_stats import ConversationStats



from sdk.utils.fifo_lock import FIFOLock



from sdk.secret.secret_registry import SecretRegistry, SecretValue



from sdk.conversation.snapshot import ConversationStateSnapshot
 
 


from sdk.hooks import manager
from sdk.security.analyzer import SecurityAnalyzerBase



from sdk.security.confirmation_policy import ConfirmationPolicyBase, NeverConfirm



from sdk.workspace.base import BaseWorkspace







from common.storage.event_log import create_event_log
from common.storage.event_log.event_store import EventLog 





from common.logger import get_logger

 

from common.utils.common import ConversationID, ExecutionStatus



from common.utils.models import ZestAgent

if TYPE_CHECKING:
    from sdk.event.event_center import EventCenter



logger = get_logger(__name__)


class ConversationState(ZestAgent):

    """会话状态 - 存储会话级别的公共共享数据
    职责：

    1. 管理会话级共享资源（workspace, secret_registry 等）

    2. 持有MainAgent状态（main_agent_state）

    3. 提供会话级配置（confirmation_policy, security_analyzer 等）

    4. 提供持久化机制（_fs, _cipher）



    设计原则：

    - 只包含多个 Agent 共享的数据

    - Agent 独立数据存储在 AgentState 中

    - AgentState 只服务 MainAgent，SubAgent状态不持久化

    """



    # ===== 基础标识 =====

    id: ConversationID = Field(description="Unique conversation ID")



    # ===== 会话级执行状态 =====

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

        description="Maximum number of iterations the agent can perform in a single run.",

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



    # ===== MainAgent 状态 =====

    main_agent_state: AgentState | None = Field(

        default=None,

        description="MainAgent状态快照，支持checkpoint断点续跑。SubAgent状态不持久化，运行时重建。",

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



    # ===== 私有属性（不序列化）=====

    # _fs: StateStore = PrivateAttr()

    # _cipher: Cipher | None = PrivateAttr(default=None)

    _on_state_change: ConversationCallbackType | None = PrivateAttr(default=None)

    _event_center: "EventCenter | None" = PrivateAttr(default=None)

    _lock: FIFOLock = PrivateAttr(default_factory=FIFOLock)

    _user_id: str | None = PrivateAttr(default=None)



    # ===== Validators =====

    @model_validator(mode="before")

    @classmethod

    def _handle_secrets_manager_alias(cls, data: Any) -> Any:

        """兼容旧版本 secrets_manager 字段"""

        if isinstance(data, dict) and "secrets_manager" in data:

            data["secret_registry"] = data.pop("secrets_manager")

        return data


    @property
    def is_paused(self) -> bool:
        return ExecutionStatus.PAUSED == self.execution_status

    # ===== Properties =====

    def _require_main_agent_state(self, reason: str) -> AgentState:

        if self.main_agent_state is None:

            logger.error(
                "Conversation %s has no main_agent_state while %s",
                self.id,
                reason,
            )
            raise RuntimeError(
                f"Conversation {self.id} has no main_agent_state while {reason}"
            )

        return self.main_agent_state

    @computed_field
    @property
    def execution_status(self) -> ExecutionStatus:

        return self._require_main_agent_state("reading execution_status").execution_status

    @property

    def user_id(self) -> str | None:

        return self._user_id



    @property

    def env_observation_persistence_dir(self) -> str | None:

        if self.persistence_dir is None:

            return None

        return str(Path(self.persistence_dir) / "observations")



    # ===== 回调 =====

    def set_on_state_change(self, callback: ConversationCallbackType | None) -> None:

        self._on_state_change = callback

    def bind_event_center(self, event_center: "EventCenter") -> None:

        self._event_center = event_center
        if self.main_agent_state:
            self.main_agent_state.bind_event_center(event_center)

    def _notify_state_change(self, key: str, value: Any) -> None:

        try:
            event_center = self._event_center
            if event_center is not None:
                from sdk.event.conversation_state import ConversationStateUpdateEvent

                event_center.publish(
                    event=ConversationStateUpdateEvent(key=key, value=value),
                    conversation_id=str(self.id),
                )
        except Exception:

            logger.exception(f"Failed to publish conversation state change for {key}")

            raise

        if self._on_state_change:

            try:

                from sdk.event.conversation_state import ConversationStateUpdateEvent

                evt = ConversationStateUpdateEvent(key=key, value=value)

                self._on_state_change(evt)

            except Exception:

                logger.exception(f"State change callback failed for {key}")

    def set_confirmation_policy(self, policy: ConfirmationPolicyBase) -> None:

        if self.confirmation_policy == policy:

            return

        self.confirmation_policy = policy

        self._notify_state_change("confirmation_policy", policy)

    def set_execution_status(self, status: ExecutionStatus) -> None:

        if self.execution_status == status:

            return

        self._require_main_agent_state("setting execution_status").set_execution_status(status)

    def set_security_analyzer(self, analyzer: SecurityAnalyzerBase | None) -> None:

        if self.security_analyzer == analyzer:

            return

        self.security_analyzer = analyzer

        self._notify_state_change("security_analyzer", analyzer)

    def attach_main_agent_state(self, agent_state: AgentState) -> None:

        self.main_agent_state = agent_state

        self._notify_state_change("main_agent_state", agent_state)

    def update_secrets(self, secrets: Mapping[str, SecretValue]) -> None:

        self.secret_registry.update_secrets(secrets)

        self._notify_state_change("secret_registry", self.secret_registry)

    @property
    def events(self) -> EventLog:

        
        
        return self.main_agent_state.events if self.main_agent_state else []
 

    # ===== 持久化 =====



    def to_snapshot(self) -> ConversationStateSnapshot:



        return ConversationStateSnapshot(
            id=self.id, 
            execution_status=self.execution_status, 
            stuck_detection=self.stuck_detection,
            confirmation_policy=self.confirmation_policy,
            security_analyzer=self.security_analyzer,
            main_agent_state=self.main_agent_state,
            stats=self.stats,
            secret_registry=self.secret_registry,

        )


    @classmethod

    def from_snapshot(cls, snapshot: ConversationStateSnapshot,

                      user_id: str | None,

                      workspace: BaseWorkspace,

                      max_iterations: int = 500,

                      ) -> "ConversationState":

        

        state = cls(

            id=snapshot.id,

            workspace=workspace, 

            max_iterations=max_iterations,

            stuck_detection=snapshot.stuck_detection,

            confirmation_policy=snapshot.confirmation_policy,

            security_analyzer=snapshot.security_analyzer,

            main_agent_state=snapshot.main_agent_state,

            stats=snapshot.stats,

            secret_registry=snapshot.secret_registry,

        )

        if state.main_agent_state is not None:
            state.main_agent_state._events = create_event_log(
                conversation_id=state.id,
                agent_id=state.main_agent_state.agent_id,
                main_agent=state.main_agent_state.is_main_agent,
            )
            if snapshot.execution_status != state.main_agent_state.execution_status:
                logger.warning(
                    "Conversation snapshot execution_status (%s) differs from main agent status (%s) for %s; using main agent status.",
                    snapshot.execution_status,
                    state.main_agent_state.execution_status,
                    state.id,
                )
        else:
            logger.error(
                "Conversation snapshot for %s has no main_agent_state; execution_status is unavailable.",
                state.id,
            )
  
        state._user_id = user_id

        logger.info(

            f"Created new conversation {state.id}\nState: {state.model_dump()}\n"

        )

        return state




    # ===== 锁代理 =====

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:

        return self._lock.acquire(blocking=blocking, timeout=timeout)



    def release(self) -> None:

        self._lock.release()



    def __enter__(self) -> Self:

        self._lock.acquire()

        return self



    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:

        self._lock.release()



    def locked(self) -> bool:

        return self._lock.locked()



    def owned(self) -> bool:

        return self._lock.owned()



    # ===== Agent 配置 =====

    def get_main_agent_state(self) -> AgentState | None:

        return self.main_agent_state

  
 
    def update_agent_config(
        self, agent: AgentBase, agent_id: str | None = None
    ) -> None:
        """更新Agent配置（当Agent发生变化时，如加载插件后）

        ⭐ 简化版：直接更新 AgentState 的配置字段，不再使用 AgentConfig

        Args:
            agent: 新的Agent实例（用于提取配置）
            agent_id: 要更新的Agent ID。如果为None，则更新MainAgent
        """
        from common.logger import get_logger

        logger = get_logger(__name__)

        # 如果没有指定agent_id，更新MainAgent
        if agent_id is None:
            agent_state = self.get_main_agent_state()
            if not agent_state:
                logger.warning("Cannot update agent config: MainAgent state not found")
                return
        else:
            logger.warning(f"update_agent_config(agent_id={agent_id}) is not supported for SubAgents")

        agent_state.update_config_snapshot(agent)



        logger.debug(

            f"Updated agent config in state (agent_id: {agent_state.agent_id}, "

            f"llm: {agent_state.llm.model if agent_state.llm else 'None'}, "

            f"tools: {len(agent_state.tools) if agent_state.tools else 0})"

        )

        logger.debug(f"Updated agent config for {agent_state.agent_id}")
 
 
