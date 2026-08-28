"""Agent状态管理模块

设计原则：
1. Agent级独立状态：包含Agent的完整执行上下文
2. 支持checkpoint：所有字段都可序列化
3. 不持有ConversationState引用（解耦），通过RunnerContext访问共享数据
4. SubAgent状态不持久化，会话恢复时由MainAgent重建
"""

from collections.abc import Sequence
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any



from common.event.event import Event
from common.event.types import EventID
from pydantic import BaseModel, Field, PrivateAttr



from sdk.agent.agent_spec import AgentContextSpec, AgentSpec 
from sdk.event.agent_state import AgentStateUpdateEvent

from sdk.event.llm_convertible.action import ActionEvent
from sdk.event.llm_convertible.observation import AgentErrorEvent, ObservationEvent, UserRejectObservation
from sdk.llm.llm import LLM

from common.logger import get_logger

from common.storage.storage_settings import StorageSettings

from sdk.tool.spec import Tool

from common.utils.common import ConversationID, ExecutionStatus


from common.storage.event_log import EventLog 


if TYPE_CHECKING:
    from sdk.event.event_center import EventCenter

logger = get_logger(__name__)


class AgentExecutionStatus(str, Enum):
    """Agent执行状态"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    WAITING = "waiting"


class AgentState(BaseModel):
    """Agent级独立状态 - 单个Agent的完整执行上下文

    职责：
    1. 持有MainAgent的配置快照（LLM、tools、context等）
    2. 存储Agent执行状态（execution_status、blocked_actions等）
    3. 支持checkpoint序列化与恢复

    设计原则：
    - 只存储状态和轻量级配置，不持有重量级实例
    - 支持checkpoint：所有字段都可序列化
    - 不持有ConversationState引用（解耦），通过RunnerContext访问共享数据
    - SubAgent状态不持久化，会话恢复时由MainAgent重建
    """

    # ===== 基础元数据 =====
    agent_id: str = Field(..., description="Agent唯一标识")
    
    conversation_id: ConversationID = Field(...,description="Agent唯一标识")
    agent_type: str = Field(
        default="Agent",
        description="Agent类型（用于重建，如'Agent'、'CodeActAgent'）",
    )

    is_main_agent: bool = Field(default=True, description="是否为主Agent")

    task_description: str = Field(default="", description="当前任务描述")

    # ===== 执行状态 =====
    execution_status: ExecutionStatus = Field(
        default=ExecutionStatus.IDLE, description="执行状态"
    )

    # ===== 时间戳 =====
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    started_at: datetime | None = Field(default=None, description="开始执行时间")
    completed_at: datetime | None = Field(default=None, description="完成时间")

    # ===== Agent配置（直接持有，Pydantic模型自动序列化）=====
    llm: LLM | None = Field(
        default=None,
        description="LLM 配置（Pydantic 模型，自动序列化）。恢复时需重新注入 API key。",
    )

    tools: list[Tool] | None = Field(
        default=None, description="工具列表（Pydantic 模型，自动序列化）"
    )

    agent_context_spec: AgentContextSpec | None = Field(
        default=None,
        description="Agent 上下文配置（Pydantic 模型，自动序列化）。",
    )

    mcp_config: dict[str, Any] = Field(default_factory=dict, description="MCP 配置")

    filter_tools_regex: str | None = Field(default=None, description="工具过滤正则")

    include_default_tools: list[str] = Field(

        default_factory=list, description="默认工具列表"

    )

    custom_system_prompt: str | None = Field(

        default=None, description="自定义系统 prompt"

    )

    system_prompt_filename: str = Field(default="system_prompt.j2")

    security_policy_filename: str = Field(default="security_policy.j2")

    system_prompt_kwargs: dict[str, object] = Field(

        default_factory=dict, description="系统 prompt 模板参数"

    )



    # ===== 状态管理（Agent独立）=====
    activated_knowledge_skills: list[str] = Field(
        default_factory=list, description="已激活的知识技能列表"
    )
    activated_experiences: list[str] = Field(
        default_factory=list, description="激活的经验id"
    )

    blocked_actions: dict[str, str] = Field(
        default_factory=dict, description="被阻止的动作，键为动作ID，值为阻止原因"
    )

    blocked_messages: dict[str, str] = Field(
        default_factory=dict, description="被阻止的消息，键为消息ID，值为阻止原因"
    )

    # ===== 任务追踪（随 checkpoint 持久化，由 task_tracker 工具读写）=====
    todos: list[dict] = Field(
        default_factory=list,
        description="当前任务列表，每项为 TaskItem 的 dict 表示，随 AgentState checkpoint 持久化",
    )

    # ===== 扩展元数据 =====
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="自定义元数据（错误信息、执行时间、最终结果引用等）",
    )

    # ===== 私有属性 =====
    _events: EventLog = PrivateAttr()
    _has_load_base_memory: bool = PrivateAttr(default=False)
    _event_center: "EventCenter | None" = PrivateAttr(default=None)
    _conversation_id: ConversationID | None = PrivateAttr(default=None)
    

    class Config:
        arbitrary_types_allowed = True

    # ===== 构建方法 =====

    @classmethod

    def build(



        cls, 

 
        conversation_id: ConversationID,


        agent_spec: AgentSpec,
 
        task_description: str = "",
 
        storage_settings: StorageSettings | None = None,



    ) -> "AgentState":



        """从ConversationState和Agent构建AgentState



        Args: 

            agent: Agent实例

            task_description: 任务描述



        Returns:

            构建完成的AgentState

        """

        from common.storage.event_log import create_event_log



        

        events = create_event_log( 
            conversation_id=conversation_id,
            agent_id=agent_spec.id,
            main_agent=True,
            storage_settings=storage_settings,
        )
        # 很多数据都分离了，所以需要从agentRunner中完成此操作，而不是当前的会话
        agent_state = cls(

            agent_id=str(agent_spec.id),
            conversation_id = conversation_id,
            agent_type=agent_spec.__class__.__name__,

            is_main_agent=True,

            task_description=task_description,

            llm=agent_spec.llm,

            tools=agent_spec.tools,

            agent_context_spec=agent_spec.agent_context_spec,

            mcp_config=agent_spec.mcp_config,

            filter_tools_regex=agent_spec.filter_tools_regex,

            include_default_tools=agent_spec.include_default_tools,

            custom_system_prompt=agent_spec.custom_system_prompt,

            system_prompt_filename=agent_spec.system_prompt_filename,

            security_policy_filename=agent_spec.security_policy_filename,

            system_prompt_kwargs=agent_spec.system_prompt_kwargs,

        )

        agent_state._events = events

        logger.info(
            f"Built AgentState for agent {agent_spec.id} "
            f"(type={agent_state.agent_type}, task={task_description})"
        )

        return agent_state

    @property
    def events(self) -> EventLog:
        """获取 Agent 的事件历史"""
        return self._events

    def bind_event_center(
        self, event_center: "EventCenter" 
    ) -> None:
        """Bind EventCenter so explicit AgentState mutations can publish events."""
        self._event_center = event_center
        

    def _publish_state_change(self, key: str, value: Any) -> None:
        event_center = self._event_center
         
        if event_center is None:
            return

        event_center.publish(
            event=AgentStateUpdateEvent(
                agent_id=str(self.agent_id),
                key=key,
                value=value,
            ),
            conversation_id=str(self.conversation_id),
            agent_id=str(self.agent_id),
        )

    def set_execution_status(self, status: ExecutionStatus) -> None:
        if self.execution_status == status:
            return
        self.execution_status = status
        self._publish_state_change("execution_status", status)

    def activate_knowledge_skills(self, skill_names: list[str]) -> None:
        if not skill_names:
            return
        updated = [*self.activated_knowledge_skills, *skill_names]
        if updated == self.activated_knowledge_skills:
            return
        self.activated_knowledge_skills = updated
        self._publish_state_change(
            "activated_knowledge_skills", self.activated_knowledge_skills
        )

    def activate_experiences(self, experience_ids: list[str]) -> None:
        if not experience_ids:
            return
        updated = [*self.activated_experiences, *experience_ids]
        if updated == self.activated_experiences:
            return
        self.activated_experiences = updated
        self._publish_state_change("activated_experiences", self.activated_experiences)

    def update_metadata(self, **kwargs: Any) -> None:
        if not kwargs:
            return
        updated = {**self.metadata, **kwargs}
        if updated == self.metadata:
            return
        self.metadata = updated
        self._publish_state_change("metadata", self.metadata)

    def replace_todos(self, todos: list[dict]) -> None:
        if self.todos == todos:
            return
        self.todos = todos
        self._publish_state_change("todos", self.todos)

    def set_blocked_actions(self, blocked_actions: dict[str, str]) -> None:
        if self.blocked_actions == blocked_actions:
            return
        self.blocked_actions = blocked_actions
        self._publish_state_change("blocked_actions", self.blocked_actions)

    def set_blocked_messages(self, blocked_messages: dict[str, str]) -> None:
        if self.blocked_messages == blocked_messages:
            return
        self.blocked_messages = blocked_messages
        self._publish_state_change("blocked_messages", self.blocked_messages)

    def update_config_snapshot(self, agent_spec: AgentSpec) -> None:
        updates = {
            "mcp_config": agent_spec.mcp_config,
            "filter_tools_regex": agent_spec.filter_tools_regex,
            "include_default_tools": agent_spec.include_default_tools,
            "custom_system_prompt": agent_spec.custom_system_prompt,
            "system_prompt_filename": agent_spec.system_prompt_filename,
            "security_policy_filename": agent_spec.security_policy_filename,
            "system_prompt_kwargs": dict(agent_spec.system_prompt_kwargs),
        }
        for key, value in updates.items():
            if getattr(self, key) == value:
                continue
            setattr(self, key, value)
            self._publish_state_change(key, value)

    def set_main_agent_flag(self, is_main_agent: bool) -> None:
        if self.is_main_agent == is_main_agent:
            return
        self.is_main_agent = is_main_agent
        self._publish_state_change("is_main_agent", is_main_agent)

    # ===== 状态转换方法 =====

    def mark_running(self):
        """标记为执行中"""
        now = datetime.now()
        self.set_execution_status(ExecutionStatus.RUNNING)
        self.started_at = now
        self._publish_state_change("started_at", self.started_at)
        logger.debug(f"Agent {self.agent_id} marked as RUNNING")

    def mark_finish(self, result_summary: str | None = None):
        """标记为完成"""
        self.set_execution_status(ExecutionStatus.FINISHED)
        self.completed_at = datetime.now()
        self._publish_state_change("completed_at", self.completed_at)
        if result_summary:
            self.update_metadata(result_summary=result_summary)
        logger.info(
            f"Agent {self.agent_id} COMPLETED in {self.get_execution_duration():.2f}s"
        )

    # ===== 辅助方法 =====

    def get_execution_duration(self) -> float:
        """获取执行时长（秒）"""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        elif self.started_at:
            return (datetime.now() - self.started_at).total_seconds()
        return 0.0

    def is_terminal_state(self) -> bool:
        """是否为终止状态"""
        return self.execution_status in [
            AgentExecutionStatus.COMPLETED,
            AgentExecutionStatus.FAILED,
            AgentExecutionStatus.CANCELLED,
        ]

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典（用于持久化）"""
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "is_main_agent": self.is_main_agent,
            "task_description": self.task_description,
            "execution_status": self.execution_status.value,
            # Agent 配置字段
            "llm": self.llm.model_dump_json() if self.llm else None,
            "tools": [
                tool.model_dump_json() if hasattr(tool, "model_dump_json") else str(tool)
                for tool in (self.tools or [])
            ],
            "agent_context_spec": self.agent_context_spec.model_dump_json()
            if self.agent_context_spec
            else None,
            "mcp_config": self.mcp_config,
            "filter_tools_regex": self.filter_tools_regex,
            "include_default_tools": self.include_default_tools,
            "custom_system_prompt": self.custom_system_prompt,
            # 状态管理字段
            "activated_knowledge_skills": self.activated_knowledge_skills,
            "blocked_actions": self.blocked_actions,
            "blocked_messages": self.blocked_messages,
            "todos": self.todos,
            # 时间戳
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentState":
        """从字典反序列化（用于恢复）"""
        from datetime import datetime

        llm = None
        if data.get("llm"):
            from sdk.llm import LLM

            llm = (
                LLM.model_validate_json(data["llm"])
                if isinstance(data["llm"], str)
                else LLM.model_validate(data["llm"])
            )

        tools = None
        if data.get("tools"):
            from sdk.tool import Tool

            tools = [
                Tool.model_validate_json(t) if isinstance(t, str) else Tool.model_validate(t)
                for t in data["tools"]
            ]

        agent_context_spec = None
        if data.get("agent_context_spec"):
            spec_data = data["agent_context_spec"]
            agent_context_spec = (
                AgentContextSpec.model_validate_json(spec_data)
                if isinstance(spec_data, str)
                else AgentContextSpec.model_validate(spec_data)
            )

        return cls(
            agent_id=data["agent_id"],
            agent_type=data.get("agent_type", "Agent"),
            is_main_agent=data.get("is_main_agent", True),
            task_description=data.get("task_description", ""),
            execution_status=ExecutionStatus(data["execution_status"]),
            llm=llm,
            tools=tools,
            agent_context_spec=agent_context_spec,
            mcp_config=data.get("mcp_config", {}),
            filter_tools_regex=data.get("filter_tools_regex"),
            include_default_tools=data.get("include_default_tools", []),
            custom_system_prompt=data.get("custom_system_prompt"),
            activated_knowledge_skills=data.get("activated_knowledge_skills", []),
            blocked_actions=data.get("blocked_actions", {}),
            blocked_messages=data.get("blocked_messages", {}),
            todos=data.get("todos", []),
            created_at=datetime.fromisoformat(data["created_at"]),
            started_at=datetime.fromisoformat(data["started_at"])
            if data.get("started_at")
            else None,
            completed_at=datetime.fromisoformat(data["completed_at"])
            if data.get("completed_at")
            else None,
            metadata=data.get("metadata", {}),
        )


    def block_action(self, action_id: str, reason: str) -> None:
        """Persistently record a hook-blocked action."""
        self.set_blocked_actions({**self.blocked_actions, action_id: reason})

    def pop_blocked_action(self, action_id: str) -> str | None:
        """Remove and return a hook-blocked action reason, if present."""
        if action_id not in self.blocked_actions:
            return None
        updated = dict(self.blocked_actions)
        reason = updated.pop(action_id)
        self.set_blocked_actions(updated)
        return reason

    def block_message(self, message_id: str, reason: str) -> None:
        """Persistently record a hook-blocked user message."""
        self.set_blocked_messages({**self.blocked_messages, message_id: reason})

    def pop_blocked_message(self, message_id: str) -> str | None:
        """Remove and return a hook-blocked message reason, if present."""
        if message_id not in self.blocked_messages:
            return None
        updated = dict(self.blocked_messages)
        reason = updated.pop(message_id)
        self.set_blocked_messages(updated)
        return reason

    @staticmethod
    def get_unmatched_actions(events: Sequence[Event]) -> list[ActionEvent]:
        """Find actions in the event history that don't have matching observations.

        This method identifies ActionEvents that don't have corresponding
        ObservationEvents, UserRejectObservations, or AgentErrorEvents,
        which typically indicates actions that are pending confirmation or execution.

        Note: AgentErrorEvent is matched by tool_call_id (not action_id) because
        it doesn't have an action_id field. This is important for crash recovery
        scenarios where an error event is emitted after a server restart.

        Args:
            events: List of events to search through

        Returns:
            List of ActionEvent objects that don't have corresponding observations,
            in chronological order
        """
        observed_action_ids: set[EventID] = set()
        observed_tool_call_ids: set[str] = set()
        unmatched_actions = []
        # Search in reverse - recent events are more likely to be unmatched
        for event in reversed(events):
            if isinstance(event, (ObservationEvent, UserRejectObservation)):
                observed_action_ids.add(event.action_id)
            elif isinstance(event, AgentErrorEvent):
                # AgentErrorEvent doesn't have action_id, match by tool_call_id
                observed_tool_call_ids.add(event.tool_call_id)
            elif isinstance(event, ActionEvent):
                # Only executable actions (validated) are considered pending
                # Check both action_id and tool_call_id for matching
                if (
                    event.action is not None
                    and event.id not in observed_action_ids
                    and event.tool_call_id not in observed_tool_call_ids
                ):
                    # Insert at beginning to maintain chronological order in result
                    unmatched_actions.insert(0, event)

        return unmatched_actions
