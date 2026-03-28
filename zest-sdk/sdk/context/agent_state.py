"""Agent状态管理模块

设计原则：
1. Agent级独立状态：包含Agent的完整执行上下文
2. 支持嵌套：通过parent_agent_id和depth追踪层级关系
3. 支持并行/串行：通过execution_mode和依赖关系管理
4. 线程安全：支持多SubAgent并发执行
5. 事件驱动：状态变更通过EventCenter发布事件
6. 数据解耦：不持有ConversationState引用，通过RunnerContext访问共享数据
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from enum import Enum
from threading import Lock
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field, PrivateAttr

from sdk.context.agent_context import AgentContext
from sdk.event.base import Event
from sdk.event.event_center import EventConsumer

# ⭐ 不再需要 AgentConfig - 已简化
# from sdk.conversation.agent_config import AgentConfig
from sdk.llm.llm import LLM
from sdk.logger import get_logger
from sdk.tool.spec import Tool


if TYPE_CHECKING:
    from sdk.agent.base import AgentBase
    from sdk.conversation.event_store import EventLog
    from sdk.conversation.state import ConversationState

logger = get_logger(__name__)


class AgentExecutionMode(str, Enum):
    """Agent执行模式"""

    SEQUENTIAL = "sequential"  # 串行执行
    PARALLEL = "parallel"  # 并行执行
    DEPENDENT = "dependent"  # 依赖执行（等待依赖的Agent完成）


class AgentExecutionStatus(str, Enum):
    """Agent执行状态"""

    PENDING = "pending"  # 等待执行
    RUNNING = "running"  # 执行中
    COMPLETED = "completed"  # 执行完成
    FAILED = "failed"  # 执行失败
    CANCELLED = "cancelled"  # 已取消
    WAITING = "waiting"  # 等待依赖


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


class AgentState(BaseModel):
    """Agent级独立状态 - 单个Agent的完整执行上下文

    设计原则：
    1. 只存储状态和轻量级配置，不持有重量级实例
    4. 支持checkpoint：所有字段都可序列化
    5. 不持有ConversationState引用（解耦），通过RunnerContext访问共享数据

    核心字段：
    - agent_id: 唯一标识
    - agent_type: Agent类型（用于重建SubAgent）
    - is_main_agent: 是否为主Agent
    - parent_agent_id: 父Agent ID（用于追踪层级）
    - depth: 嵌套层级
    - execution_status: 执行状态
    - execution_mode: 执行模式（串行/并行/依赖）
    - depends_on: 依赖的Agent ID列表
    - agent_config: Agent配置（用于重建SubAgent）
    - activated_knowledge_skills: 激活的知识技能
    - blocked_actions: 被阻止的动作
    - blocked_messages: 被阻止的消息
    - metadata: 扩展元数据（错误信息、自定义字段等）
    - _events: agent 的历史事件。
    - llm: llm 配置
    - tools： 工具配置
    - mcp_config： mcp配置
    - filter_tools_regex 工具名称过滤正则表达式
    - include_default_tools 包含的默认工具列表
    - critic_config Critic 配置（可选）
        - system_prompt_filename 系统 prompt 文件名
    - custom_system_prompt 自定义系统 prompt（优先于 system_prompt_filename）
    - agent_context_config AgentContext 配置（skills, system_message_suffix 等）
    """

    # ===== 基础元数据 =====
    agent_id: str = Field(..., description="Agent唯一标识")

    agent_type: str = Field(
        default="Agent",
        description="Agent类型（用于重建SubAgent，如'Agent'、'CodeActAgent'）",
    )

    is_main_agent: bool = Field(default=True, description="是否为主Agent")

    parent_agent_id: str | None = Field(
        default=None, description="父Agent ID（仅SubAgent有值）"
    )

    depth: int = Field(default=0, description="嵌套层级（Main=0, Sub=1, SubSub=2...）")

    task_description: str = Field(default="", description="当前任务描述")

    # ===== 执行控制（核心元数据）=====
    execution_status: AgentExecutionStatus = Field(
        default=AgentExecutionStatus.PENDING, description="执行状态"
    )

    execution_mode: AgentExecutionMode = Field(
        default=AgentExecutionMode.SEQUENTIAL, description="执行模式"
    )

    depends_on: list[str] = Field(
        default_factory=list,
        description="依赖的Agent ID列表（执行前需要等待这些Agent完成）",
    )

    # ===== 时间戳（元数据）=====
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")

    started_at: datetime | None = Field(default=None, description="开始执行时间")

    completed_at: datetime | None = Field(default=None, description="完成时间")

    # ===== Agent配置（直接持有，Pydantic模型自动序列化）=====
    # ⭐ 简化：不需要 AgentConfig 中间层，直接持有 Agent 的配置字段
    llm: LLM | None = Field(
        default=None,
        description="LLM 配置（Pydantic 模型，自动序列化）。恢复时需重新注入 API key。",
    )

    tools: list[Tool] | None = Field(
        default=None, description="工具列表（Pydantic 模型，自动序列化）"
    )

    agent_context: AgentContext | None = Field(
        default=None,
        description="Agent 上下文配置（Pydantic 模型，自动序列化）。"
        "注意：memory_manager 是运行时对象，不会序列化。",
    )

    mcp_config: dict[str, Any] = Field(default_factory=dict, description="MCP 配置")

    filter_tools_regex: str | None = Field(default=None, description="工具过滤正则")

    include_default_tools: list[str] = Field(
        default_factory=list, description="默认工具列表"
    )

    custom_system_prompt: str | None = Field(
        default=None, description="自定义系统 prompt"
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

    # ===== 扩展元数据（轻量级键值对）=====
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "自定义元数据（错误信息、执行时间、最终结果引用等）。"
            "注意：不存储重量级数据，只存储标量、字符串等轻量值"
        ),
    )

    # ===== 私有属性 =====
    _events: EventLog = PrivateAttr()
    # 注意，私有属性不会被序列化，所以需要后续重新调整
    _has_load_base_memory: bool = PrivateAttr(default=False)

    class Config:
        arbitrary_types_allowed = True

    # ===== 构建方法（简化版）=====

    @classmethod
    def build(
        cls,
        conversation_state: ConversationState,
        agent: AgentBase,
        parent_agent_id: str | None = None,
        task_description: str = "",
    ) -> AgentState:
        """从ConversationState和Agent构建AgentState（简化版）

        ⭐ 简化原则：直接持有 Agent 的配置字段，不需要 AgentConfig 中间层

        Args:
            conversation_state: 会话状态（公共数据）
            agent: Agent实例（Pydantic模型，可直接序列化）
            parent_agent_id: 父Agent ID（SubAgent才有）
            task_description: 任务描述

        Returns:
            构建完成的AgentState
        """
        from sdk.conversation.event_store import EventLog

        # 创建独立的事件日志（基于ConversationState的FileStore）
        if parent_agent_id is None:
            agent_events_dir = f"agents/{agent.id}/events"
        else:
            agent_events_dir = f"agents/sub/{agent.id}/events" 
        
        events = EventLog(conversation_state._fs, dir_path=agent_events_dir)

        # ⭐ 简化：直接从 Agent 提取配置字段（Pydantic 自动序列化）

        agent_state = cls(
            agent_id=str(agent.id),
            agent_type=agent.__class__.__name__,
            is_main_agent=(parent_agent_id is None),
            parent_agent_id=parent_agent_id,
            depth=0 if parent_agent_id is None else 1,
            task_description=task_description,
            # ⭐ 直接持有 Agent 的配置（Pydantic 模型）
            llm=agent.llm,
            tools=agent.tools,
            agent_context=agent.agent_context,
            mcp_config=agent.mcp_config,
            filter_tools_regex=agent.filter_tools_regex,
            include_default_tools=agent.include_default_tools,
            custom_system_prompt=agent.custom_system_prompt,
        )

        # 设置私有属性
        agent_state._events = events

        # 注册到ConversationState的agent_state_registry
        conversation_state.agent_state_registry.register(agent_state)

        logger.info(
            f"Built AgentState for agent {agent.id} "
            f"(type={agent_state.agent_type}, "
            f"is_main_agent={agent_state.is_main_agent}, "
            f"parent={parent_agent_id}, task={task_description})"
        )

        return agent_state

    @property
    def events(self) -> EventLog:
        """获取 Agent 的事件历史"""
        return self._events

    # ===== 状态转换方法 =====

    def mark_running(self):
        """标记为执行中"""
        self.execution_status = AgentExecutionStatus.RUNNING
        self.started_at = datetime.now()
        logger.debug(f"Agent {self.agent_id} marked as RUNNING")

    def mark_completed(self, result_summary: str | None = None):
        """标记为完成

        Args:
            result_summary: 结果摘要（轻量级字符串，不存储完整结果）
        """
        self.execution_status = AgentExecutionStatus.COMPLETED
        self.completed_at = datetime.now()
        if result_summary:
            self.metadata["result_summary"] = result_summary
        logger.info(
            f"Agent {self.agent_id} COMPLETED in {self.get_execution_duration():.2f}s"
        )

    def mark_failed(self, error_message: str):
        """标记为失败"""
        self.execution_status = AgentExecutionStatus.FAILED
        self.completed_at = datetime.now()
        self.metadata["error_message"] = error_message
        logger.error(f"Agent {self.agent_id} FAILED: {error_message}")

    def mark_waiting(self, waiting_for: list[str]):
        """标记为等待依赖"""
        self.execution_status = AgentExecutionStatus.WAITING
        self.metadata["waiting_for"] = waiting_for
        logger.debug(f"Agent {self.agent_id} WAITING for {waiting_for}")

    def mark_cancelled(self, reason: str = ""):
        """标记为已取消"""
        self.execution_status = AgentExecutionStatus.CANCELLED
        self.completed_at = datetime.now()
        if reason:
            self.metadata["cancel_reason"] = reason
        logger.info(f"Agent {self.agent_id} CANCELLED: {reason}")

    # ===== 辅助方法 =====

    def is_ready_to_run(self, registry: AgentStateRegistry) -> bool:
        """检查是否可以开始执行

        检查逻辑：
        1. 状态必须为PENDING或WAITING
        2. 如果有依赖，所有依赖的Agent必须已完成
        """
        if self.execution_status not in [
            AgentExecutionStatus.PENDING,
            AgentExecutionStatus.WAITING,
        ]:
            return False

        # 检查依赖
        if self.depends_on:
            for dep_id in self.depends_on:
                dep_state = registry.get(dep_id)
                if not dep_state:
                    logger.warning(f"Dependency {dep_id} not found for {self.agent_id}")
                    return False
                if dep_state.execution_status != AgentExecutionStatus.COMPLETED:
                    return False

        return True

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
        """序列化为字典（用于持久化）

        ⭐ 简化版：直接使用 Pydantic 的 model_dump_json()
        注意：api_key 等敏感字段会被自动排除（exclude=True）
        """
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "is_main_agent": self.is_main_agent,
            "parent_agent_id": self.parent_agent_id,
            "depth": self.depth,
            "task_description": self.task_description,
            "execution_status": self.execution_status.value,
            "execution_mode": self.execution_mode.value,
            "depends_on": self.depends_on,
            # ⭐ 直接序列化 Agent 配置字段（Pydantic 自动处理）
            "llm": self.llm.model_dump_json() if self.llm else None,
            "tools": [
                tool.model_dump_json() if hasattr(tool, "model_dump_json") else str(tool)
                for tool in (self.tools or [])
            ],
            "agent_context": self.agent_context.model_dump_json()
            if self.agent_context
            else None,
            "mcp_config": self.mcp_config,
            "filter_tools_regex": self.filter_tools_regex,
            "include_default_tools": self.include_default_tools,
            "custom_system_prompt": self.custom_system_prompt,
            # 状态管理字段
            "activated_knowledge_skills": self.activated_knowledge_skills,
            "blocked_actions": self.blocked_actions,
            "blocked_messages": self.blocked_messages,
            # 时间戳
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentState:
        """从字典反序列化（用于恢复）

        ⭐ 简化版：直接使用 Pydantic 的 model_validate()

        Note:
            恢复后需要重新注入敏感信息（如 API key）：
            agent_state.llm.api_key = SecretStr(os.getenv("LLM_API_KEY"))
        """
        from datetime import datetime

        # ⭐ 反序列化 Agent 配置字段（Pydantic 自动处理）
        llm = None
        if data.get("llm"):
            from sdk.llm import LLM

            llm = LLM.model_validate(data["llm"])

        tools = None
        if data.get("tools"):
            from sdk.tool import Tool

            tools = [
                Tool.model_validate(t) if isinstance(t, dict) else t
                for t in data["tools"]
            ]

        agent_context = None
        if data.get("agent_context"):
            from sdk.context.agent_context import AgentContext

            agent_context = AgentContext.model_validate(data["agent_context"])

        return cls(
            agent_id=data["agent_id"],
            agent_type=data.get("agent_type", "Agent"),
            is_main_agent=data.get("is_main_agent", True),
            parent_agent_id=data.get("parent_agent_id"),
            depth=data.get("depth", 0),
            task_description=data.get("task_description", ""),
            execution_status=AgentExecutionStatus(data["execution_status"]),
            execution_mode=AgentExecutionMode(data.get("execution_mode", "sequential")),
            depends_on=data.get("depends_on", []),
            # ⭐ 直接使用反序列化的配置对象
            llm=llm,
            tools=tools,
            agent_context=agent_context,
            mcp_config=data.get("mcp_config", {}),
            filter_tools_regex=data.get("filter_tools_regex"),
            include_default_tools=data.get("include_default_tools", []),
            custom_system_prompt=data.get("custom_system_prompt"),
            # 状态管理字段
            activated_knowledge_skills=data.get("activated_knowledge_skills", []),
            blocked_actions=data.get("blocked_actions", {}),
            blocked_messages=data.get("blocked_messages", {}),
            # 时间戳
            created_at=datetime.fromisoformat(data["created_at"]),
            started_at=datetime.fromisoformat(data["started_at"])
            if data.get("started_at")
            else None,
            completed_at=datetime.fromisoformat(data["completed_at"])
            if data.get("completed_at")
            else None,
            metadata=data.get("metadata", {}),
        )


class AgentEventPersistentConsumer(EventConsumer):
    def __init__(
        self,
        agent_state: AgentState,
        conversation_id: uuid.UUID | str | None = None,
        agent_id: uuid.UUID | str | None = None,
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


class AgentStateRegistry(BaseModel):
    """Agent状态注册表 - 管理所有Agent状态

    核心职责：
    1. 注册和管理所有Agent状态
    2. 支持按条件查询Agent状态
    3. 管理Agent执行依赖关系
    4. 提供线程安全的状态访问
    5. 支持并行/串行执行调度
    """

    _states: dict[str, AgentState] = PrivateAttr(default_factory=dict)
    _lock: Lock = PrivateAttr(default_factory=Lock)

    class Config:
        arbitrary_types_allowed = True

    # ===== 基础操作 =====

    def register(self, agent_state: AgentState):
        """注册Agent状态（线程安全）"""
        with self._lock:
            if agent_state.agent_id in self._states:
                logger.warning(
                    f"Agent {agent_state.agent_id} already registered, overwriting"
                )
            self._states[agent_state.agent_id] = agent_state
            logger.debug(f"Registered agent state: {agent_state.agent_id}")

    def get(self, agent_id: str) -> AgentState | None:
        """获取Agent状态（线程安全）"""
        with self._lock:
            return self._states.get(agent_id)

    def remove(self, agent_id: str):
        """移除Agent状态（线程安全）"""
        with self._lock:
            if agent_id in self._states:
                del self._states[agent_id]
                logger.debug(f"Removed agent state: {agent_id}")

    def get_all(self) -> dict[str, AgentState]:
        """获取所有Agent状态的副本（线程安全）"""
        with self._lock:
            return self._states.copy()

    def clear(self):
        """清空所有状态（线程安全）"""
        with self._lock:
            self._states.clear()
            logger.debug("Cleared all agent states")

    # ===== 查询方法 =====

    def get_main_agent_state(self) -> AgentState:
        """获取MainAgent状态"""
        with self._lock:
            for state in self._states.values():
                if state.is_main_agent:
                    return state
        raise ValueError("mainAgentState is null")

    def get_sub_agents(self, parent_id: str) -> list[AgentState]:
        """获取指定父Agent的所有子Agent"""
        with self._lock:
            return [
                state
                for state in self._states.values()
                if state.parent_agent_id == parent_id
            ]

    def get_by_status(self, status: AgentExecutionStatus) -> list[AgentState]:
        """按执行状态查询"""
        with self._lock:
            return [
                state
                for state in self._states.values()
                if state.execution_status == status
            ]

    def get_by_mode(self, mode: AgentExecutionMode) -> list[AgentState]:
        """按执行模式查询"""
        with self._lock:
            return [
                state for state in self._states.values() if state.execution_mode == mode
            ]

    def get_ready_agents(self) -> list[AgentState]:
        """获取所有准备就绪可执行的Agent

        准备就绪的条件：
        1. 状态为PENDING或WAITING
        2. 所有依赖的Agent已完成
        """
        ready_agents = []
        with self._lock:
            for state in self._states.values():
                if state.is_ready_to_run(self):
                    ready_agents.append(state)
        return ready_agents

    # ===== 并行/串行调度支持 =====

    def get_next_executable_agents(
        self, parent_id: str | None = None
    ) -> list[AgentState]:
        """获取下一批可执行的Agent

        调度逻辑：
        1. 并行模式的Agent可以同时执行
        2. 串行模式的Agent按注册顺序依次执行
        3. 依赖模式的Agent等待依赖完成后执行

        Args:
            parent_id: 如果指定，只返回该父Agent下的子Agent

        Returns:
            可以立即执行的Agent列表
        """
        executable = []
        with self._lock:
            # 获取目标Agent列表
            if parent_id:
                candidates = [
                    s for s in self._states.values() if s.parent_agent_id == parent_id
                ]
            else:
                candidates = list(self._states.values())

            # 检查是否有正在运行的串行Agent
            has_running_sequential = any(
                s.execution_status == AgentExecutionStatus.RUNNING
                and s.execution_mode == AgentExecutionMode.SEQUENTIAL
                for s in candidates
            )

            for state in candidates:
                # 跳过非PENDING/WAITING状态
                if state.execution_status not in [
                    AgentExecutionStatus.PENDING,
                    AgentExecutionStatus.WAITING,
                ]:
                    continue

                # 检查依赖
                if not state.is_ready_to_run(self):
                    continue

                # 并行模式：直接加入
                if state.execution_mode == AgentExecutionMode.PARALLEL:
                    executable.append(state)

                # 串行模式：如果没有其他串行Agent在运行，可以执行
                elif state.execution_mode == AgentExecutionMode.SEQUENTIAL:
                    if not has_running_sequential:
                        executable.append(state)
                        has_running_sequential = True  # 标记为已有串行Agent

                # 依赖模式：依赖已满足，可以执行
                elif state.execution_mode == AgentExecutionMode.DEPENDENT:
                    executable.append(state)

        return executable

    def has_pending_agents(self, parent_id: str | None = None) -> bool:
        """检查是否还有待执行的Agent"""
        with self._lock:
            candidates = (
                [s for s in self._states.values() if s.parent_agent_id == parent_id]
                if parent_id
                else list(self._states.values())
            )

            return any(
                s.execution_status
                in [AgentExecutionStatus.PENDING, AgentExecutionStatus.WAITING]
                for s in candidates
            )

    def all_completed(self, parent_id: str | None = None) -> bool:
        """检查是否所有Agent都已完成（成功或失败）"""
        with self._lock:
            candidates = (
                [s for s in self._states.values() if s.parent_agent_id == parent_id]
                if parent_id
                else list(self._states.values())
            )

            if not candidates:
                return True

            return all(
                s.execution_status
                in [
                    AgentExecutionStatus.COMPLETED,
                    AgentExecutionStatus.FAILED,
                    AgentExecutionStatus.CANCELLED,
                ]
                for s in candidates
            )

    # ===== 统计方法 =====

    def get_statistics(self, parent_id: str | None = None) -> dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            candidates = (
                [s for s in self._states.values() if s.parent_agent_id == parent_id]
                if parent_id
                else list(self._states.values())
            )

            stats = {
                "total": len(candidates),
                "pending": 0,
                "running": 0,
                "completed": 0,
                "failed": 0,
                "waiting": 0,
                "cancelled": 0,
                "parallel_agents": 0,
                "sequential_agents": 0,
                "dependent_agents": 0,
            }

            for state in candidates:
                # 统计状态
                if state.execution_status == AgentExecutionStatus.PENDING:
                    stats["pending"] += 1
                elif state.execution_status == AgentExecutionStatus.RUNNING:
                    stats["running"] += 1
                elif state.execution_status == AgentExecutionStatus.COMPLETED:
                    stats["completed"] += 1
                elif state.execution_status == AgentExecutionStatus.FAILED:
                    stats["failed"] += 1
                elif state.execution_status == AgentExecutionStatus.WAITING:
                    stats["waiting"] += 1
                elif state.execution_status == AgentExecutionStatus.CANCELLED:
                    stats["cancelled"] += 1

                # 统计模式
                if state.execution_mode == AgentExecutionMode.PARALLEL:
                    stats["parallel_agents"] += 1
                elif state.execution_mode == AgentExecutionMode.SEQUENTIAL:
                    stats["sequential_agents"] += 1
                elif state.execution_mode == AgentExecutionMode.DEPENDENT:
                    stats["dependent_agents"] += 1

            return stats

    # ===== 序列化 =====

    def to_dict(self) -> dict[str, dict]:
        """序列化为字典"""
        with self._lock:
            return {
                agent_id: state.to_dict() for agent_id, state in self._states.items()
            }

    @classmethod
    def from_dict(cls, data: dict[str, dict]) -> AgentStateRegistry:
        """从字典反序列化"""
        registry = cls()
        for agent_id, state_dict in data.items():
            # 简化反序列化，只恢复基本信息
            agent_state = AgentState(
                agent_id=state_dict["agent_id"],
                agent_type=state_dict.get("agent_type", "Agent"),
                is_main_agent=state_dict["is_main_agent"],
                parent_agent_id=state_dict.get("parent_agent_id"),
                depth=state_dict["depth"],
                task_description=state_dict["task_description"],
                execution_status=AgentExecutionStatus(state_dict["execution_status"]),
                execution_mode=AgentExecutionMode(state_dict["execution_mode"]),
                depends_on=state_dict.get("depends_on", []),
                agent_config=state_dict.get("agent_config", {}),
                metadata=state_dict.get("metadata", {}),
            )
            registry.register(agent_state)
        return registry


class AgentStateRegistryConsumer(EventConsumer):
    _agent_state_registry: AgentStateRegistry

    def __init__(self, conversation_id=None, agent_id=None):
        event_types = [AgentState]
        super().__init__(conversation_id, agent_id, event_types)
        self._agent_state_registry = AgentStateRegistry()

    def on_event(self, event):
        self._agent_state_registry.register(event)
