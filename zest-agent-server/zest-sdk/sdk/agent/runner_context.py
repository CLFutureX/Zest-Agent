from collections.abc import Sequence
from typing import Any, Self

from pydantic import BaseModel, Field, PrivateAttr
 
from sdk.agent.agent_state import AgentState
from common.storage.event_log.event_store import EventLog
from sdk.agent.runtime import AgentRuntime
from sdk.memory.memory_manager import MemoryManager, get_memory_manager
from sdk.utils.fifo_lock import FIFOLock
from sdk.secret.secret_registry import SecretRegistry

 
from sdk.event.base import Event
from sdk.event.event_center import EventCenter
from sdk.event.llm_convertible.action import ActionEvent 
from sdk.event.llm_convertible.observation import (
    ObservationEvent,
    UserRejectObservation,
) 
from sdk.security.analyzer import SecurityAnalyzerBase
from sdk.security.confirmation_policy import (
    ConfirmationPolicyBase,
    NeverConfirm,
) 
from common.utils.common import ConversationID
from sdk.workspace.base import BaseWorkspace
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from sdk.conversation.state import (
    ConversationState,
)

class RunnerContext(BaseModel):
    """运行时上下文，提供Agent执行所需的完整环境（扁平化设计）。

    RunnerContext 的职责：
    1. 聚合 Agent 状态（可序列化配置）
    2. 聚合会话级共享数据（扁平化，无引用耦合）
    3. 提供统一的访问接口供 Agent 执行使用
    4. 通过 EventCenter 统一管理事件发布（使用 Topic+Tag 语义）
    5. 提供线程安全的锁机制

    扁平化架构设计：
    RunnerContext (运行时上下文)
        ├─ agent_state: AgentState  # Agent 可序列化状态

        │   ├─ blocked_actions, blocked_messages
        │   └─ _events (Agent 级事件日志)
        │
        └─ 会话级共享数据（直接字段，无嵌套引用）
            ├─ id: ConversationID
            ├─ workspace: BaseWorkspace
            ├─ secret_registry: SecretRegistry
            ├─ event_center: EventCenter
            ├─ confirmation_policy: ConfirmationPolicyBase
            ├─ security_analyzer: SecurityAnalyzerBase
            ├─ persistence_dir: str
            └─ 私有属性（_fs, _cipher, _lock, _user_id）

    职责分离：
    - ✅ AgentRunner 持有 agent 实例（负责调度执行）
    - ✅ RunnerContext 只持有 agent_state（提供状态和共享资源）
    - ✅ Agent.step() 通过 self 访问 LLM 和工具（self.llm, self.tools）

    核心优势：
    - ✅ 清晰分离：agent（由 AgentRunner 持有）与 agent_state（可序列化状态）
    - ✅ 完全解耦：agent_state 不持有任何共享数据引用
    - ✅ 扁平化：共享数据直接作为 RunnerContext 字段，无嵌套
    - ✅ 职责清晰：AgentRunner 负责执行，RunnerContext 负责提供资源
    - ✅ 构建简单：RunnerContext.build(conversation_state, agent_state)

    事件发布语义：
    - conversation_id: 会话 ID（Topic）
    - agent_id: Agent ID（Tag）
    - 支持会话级和 Agent 级的事件发布

    注意：
    - agent 实例由 AgentRunner 创建和管理
    - RunnerContext 只提供共享资源和状态数据
    - checkpoint 时只序列化 agent_state，不序列化 agent
    """

    # ===== Agent 状态（可序列化）=====
    agent_state: AgentState = Field(
        ...,
        description="当前 Agent 状态（agent_config, blocked_actions, blocked_messages, _events）",
    ) 
    
    # ===== 会话级共享数据（直接字段）=====
    conversation_id: ConversationID = Field(..., description="会话唯一标识")

    workspace: BaseWorkspace = Field(
        ..., description="共享 workspace（用于命令执行和文件读写）"
    )

    secret_registry: SecretRegistry = Field(
        default_factory=SecretRegistry, description="共享秘密注册表"
    )

    event_center: EventCenter = Field(
        ..., description="统一的事件中心（Topic+Tag 语义）"
    )
    memory_manager: MemoryManager = Field()

    confirmation_policy: ConfirmationPolicyBase = Field(
        default_factory=NeverConfirm, description="确认策略"
    )

    security_analyzer: SecurityAnalyzerBase | None = Field(
        default=None, description="安全分析器"
    )
    
    cache_limit_size: int = Field(default=500, description="缓存限制")
    persistence_dir: str | None = Field(
        default="workspace/conversations", description="会话持久化目录"
    )
    
    # ===== 私有属性（运行时数据）=====
    
    _lock: FIFOLock = PrivateAttr()
    _user_id: str | None = PrivateAttr(default=None)
    
    
    
    class Config:
        arbitrary_types_allowed = True

    # ===== 便捷属性（代理到 agent_state）=====

    @property
    def agent_id(self) -> str:
        """当前 Agent ID"""
        return self.agent_state.agent_id

    @property
    def activated_knowledge_skills(self) -> list[str]:
        """当前 Agent 的已激活知识技能"""
        return self.agent_state.activated_knowledge_skills

    @property
    def blocked_actions(self) -> dict[str, str]:
        """当前 Agent 的被阻止动作"""
        return self.agent_state.blocked_actions

    @blocked_actions.setter
    def blocked_actions(self, value: dict[str, str]) -> None:
        """设置当前 Agent 的被阻止动作"""
        self.agent_state.set_blocked_actions(value)

    @property
    def blocked_messages(self) -> dict[str, str]:
        """当前 Agent 的被阻止消息"""
        return self.agent_state.blocked_messages

    @blocked_messages.setter
    def blocked_messages(self, value: dict[str, str]) -> None:
        """设置当前 Agent 的被阻止消息"""
        self.agent_state.set_blocked_messages(value)

    @property
    def events(self) -> "EventLog":
        """当前 Agent 的事件日志"""
        return self.agent_state.events  # type: ignore

    @property
    def user_id(self) -> str | None:
        """获取可选的用户ID（如果在多用户上下文中）"""
        return self._user_id

    # ===== 事件发布方法 =====
 

    def publish_event(self, event: Any) -> None:
        """发布事件到 EventCenter（使用 Topic+Tag 语义）

        Args:
            event: 要发布的事件
        """
        self.event_center.publish(
            event=event, conversation_id=str(self.conversation_id), agent_id=str(self.agent_id)
        )
    # ===== 构建方法 =====
    @classmethod
    def build(
        cls,
        conversation_state: "ConversationState",
        agent_state: AgentState,
        event_center: EventCenter,
        memory_manager: MemoryManager,
    ) -> "RunnerContext":
        """从 ConversationState 和 AgentState 构建 RunnerContext（扁平化）。

        这是扁平化架构的核心构建方法：
        1. 从 ConversationState 提取会话级共享数据
        2. 从 AgentState 获取 Agent 状态
        3. 创建 RunnerContext 实例（无任何引用耦合）

        Args:
            conversation_state: 会话状态（共享数据来源）
            agent_state: Agent 状态（Agent 数据来源）

        Returns:
            构建完成的 RunnerContext 实例
        """
        # 创建 RunnerContext 实例（扁平化，直接传入所有字段）
        context = cls(
            # Agent 状态
            agent_state=agent_state,
            # 会话级共享数据（从 ConversationState 提取）
            conversation_id=conversation_state.id,
            workspace=conversation_state.workspace,
            secret_registry=conversation_state.secret_registry,
            event_center=event_center,
            memory_manager=memory_manager,
            confirmation_policy=conversation_state.confirmation_policy,
            security_analyzer=conversation_state.security_analyzer,
            persistence_dir=conversation_state.persistence_dir,
            cache_limit_size=conversation_state.max_iterations,
        )

        # 设置私有属性
        context._lock = conversation_state._lock
        context._user_id = conversation_state._user_id

        return context
    
    @classmethod
    def build_clone(
        cls,
        ref_context: "RunnerContext",
        agent_state: AgentState,
        event_center: EventCenter,
    ) -> "RunnerContext":
        """从 ConversationState 和 AgentState 构建 RunnerContext（扁平化）。

        这是扁平化架构的核心构建方法：
        1. 从 ConversationState 提取会话级共享数据
        2. 从 AgentState 获取 Agent 状态
        3. 创建 RunnerContext 实例（无任何引用耦合）

        Args:
            conversation_state: 会话状态（共享数据来源）
            agent_state: Agent 状态（Agent 数据来源）

        Returns:
            构建完成的 RunnerContext 实例
        """
        # 创建 RunnerContext 实例（扁平化，直接传入所有字段）
        context = cls(
            # Agent 状态
            agent_state=agent_state,
            # 会话级共享数据（从 ConversationState 提取）
            conversation_id=ref_context.conversation_id,
            workspace=ref_context.workspace,
            secret_registry=ref_context.secret_registry,
            event_center=event_center,
            memory_manager=ref_context.memory_manager,
            confirmation_policy=ref_context.confirmation_policy,
            security_analyzer=ref_context.security_analyzer,
            persistence_dir=ref_context.persistence_dir,
            cache_limit_size=ref_context.cache_limit_size,
        )

        # 设置私有属性
        context._lock = ref_context._lock
        context._user_id = ref_context._user_id

        return context

    # ===== 动作阻止管理方法 =====

    def block_action(self, action_id: str, reason: str) -> None:
        """记录被阻止的动作"""
        self.agent_state.block_action(action_id, reason)

    def pop_blocked_action(self, action_id: str) -> str | None:
        """移除并返回被阻止的动作原因"""
        return self.agent_state.pop_blocked_action(action_id)

    def block_message(self, message_id: str, reason: str) -> None:
        """记录被阻止的消息"""
        self.agent_state.block_message(message_id, reason)

    def pop_blocked_message(self, message_id: str) -> str | None:
        """移除并返回被阻止的消息原因"""
        return self.agent_state.pop_blocked_message(message_id)

    # ===== 事件查询方法 =====

    @staticmethod
    def get_unmatched_actions(events: Sequence[Event]) -> list[ActionEvent]:
        """查找没有对应观察的动作。

        此方法识别没有对应ObservationEvent或UserRejectObservation的ActionEvent，
        这通常表示待确认或待执行的动作。

        Args:
            events: 事件列表

        Returns:
            按时间顺序排列的未匹配ActionEvent列表
        """
        # 我们应该仅检索到上一个用户信息即可。
        observed_action_ids = set()
        unmatched_actions = []
        
        for event in reversed(events): 
            if isinstance(event, (ObservationEvent, UserRejectObservation)):
                observed_action_ids.add(event.action_id)
            elif isinstance(event, ActionEvent):
                # 只有可执行的动作（已验证）才被视为待处理
                if event.action is not None and event.id not in observed_action_ids:
                    # 在开头插入以保持结果的时间顺序
                    unmatched_actions.insert(0, event)

        return unmatched_actions
    

    # ===== FIFOLock委托方法 =====

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        """获取锁。

        Args:
            blocking: 如果为True，则阻塞直到获取锁。如果为False，立即返回。
            timeout: 等待锁的最大时间（如果blocking=False则忽略）。
                    -1表示无限等待。

        Returns:
            如果获取了锁则返回True，否则返回False。
        """
        return self._lock.acquire(blocking=blocking, timeout=timeout)

    def release(self) -> None:
        """释放锁。

        Raises:
            RuntimeError: 如果当前线程不拥有该锁。
        """
        self._lock.release()

    def __enter__(self: Self) -> Self:
        """上下文管理器入口"""
        self._lock.acquire()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """上下文管理器出口"""
        self._lock.release()

    def locked(self) -> bool:
        """返回锁是否被任何线程持有"""
        return self._lock.locked()

    def owned(self) -> bool:
        """返回锁是否被调用线程持有"""
        return self._lock.owned()
