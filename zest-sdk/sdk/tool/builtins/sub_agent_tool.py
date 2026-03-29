"""SubAgent工具 - 直接基于AgentRunner管理生命周期

这个模块实现了SubAgent的完整功能，允许MainAgent委托任务给专门的SubAgent。

核心设计：
1. 直接基于AgentRunner管理SubAgent的生命周期
2. 为每个SubAgent创建独立的ConversationState、RunnerContext和AgentRunner
3. SubAgent和MainAgent的生命周期完全独立
4. SubAgent的事件不会污染MainAgent的事件历史
"""

import json
import re
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Self

from pydantic import BaseModel, Field
from rich.text import Text

from sdk.agent.agent_runner import AgentRunner
from sdk.agent.base import AgentBase
from sdk.agent.runner_context import RunnerContext
from sdk.context.agent_state import   AgentState
from sdk.context.agent_state_consumer import AgentEventPersistentConsumer
from sdk.event.llm_convertible.observation import ObservationEvent
from sdk.llm.message import TextContent
from sdk.logger import get_logger
from sdk.tool.spec import Tool
from sdk.tool.tool import (
    Action,
    Observation,
    ToolAnnotations,
    ToolDefinition,
    ToolExecutor,
)


if TYPE_CHECKING:
    from sdk.conversation.state import ConversationState

logger = get_logger(__name__)


# ============================================================================
# 配置和数据类
# ============================================================================


class OutputField(BaseModel):
    """输出字段定义

    Attributes:
        name: 字段名
        type: 字段类型（str/int/float/bool/list/dict）
        required: 是否必填
        description: 字段描述
    """

    name: str = Field(..., description="字段名")
    type: str = Field(..., description="字段类型: str/int/float/bool/list/dict/any")
    required: bool = Field(default=True, description="是否必填")
    description: str = Field(default="", description="字段描述")


class SubAgentConfig(BaseModel):
    """SubAgent配置 - 极简设计

    Attributes:
        name: SubAgent唯一标识
        description: SubAgent功能描述
        agent: Agent实例
        tools: 可选的自定义tools列表。如果提供，SubAgent将使用这些tools而不是继承MainAgent的tools
    """

    name: str = Field(..., description="SubAgent唯一标识")
    description: str = Field(..., description="SubAgent功能描述")
    agent: AgentBase = Field(..., description="Agent实例")
    tools: list[Tool] = Field(
        default=[],
        description=(
            "Optional custom tools for this SubAgent. If provided, the SubAgent will use "
            "these tools instead of inheriting all tools from the MainAgent. "
            "If not provided (None), the SubAgent will inherit all tools from MainAgent."
        ),
    )

    class Config:
        arbitrary_types_allowed = True


# ============================================================================
# Action和Observation类
# ============================================================================


class SubAgentAction(Action):
    """SubAgent工具的动作

    Attributes:
        subagent_name: SubAgent名称
        task: 要执行的任务
    """

    task: str = Field(..., description="要执行的任务")
    expected_output_fields: list[OutputField] = Field(
        default=[],
        description="期望当前输出字段列表，为空则不校验，此类型是可选的，你可以在某些必要场景下必须需要获取指定字段的数据时, "
        + "可以通过此字段对最终SubAgent返回的数据进行提取",
    )
    output_format: str = Field(
        default="json", description="期望的输出格式：json/text/structured"
    )

    @property
    def visualize(self) -> Text:
        """Return Rich Text representation of this action."""
        content = Text()
        # 主标题保持和原类一致的bold blue样式，贴合SubAgent动作语义
        content.append("Call SubAgent to execute task:\n", style="bold blue")
        content.append(f"Execution Task: {self.task}")
        content.append(f"expected_output_fields: {self.expected_output_fields}")
        content.append(f"output_format:{self.output_format}")
        return content


class SubAgentObservation(Observation):
    """SubAgent工具的观察结果

    Attributes:
        result: SubAgent执行结果
        subagent_name: 执行的SubAgent名称
        success: 是否执行成功
        error_message: 错误信息（如果有）
    """

    result: str = Field(..., description="SubAgent执行结果")
    success: bool = Field(default=True, description="是否执行成功")
    error_message: str | None = Field(default=None, description="错误信息")

    @property
    def visualize(self) -> Text:
        """Return Rich Text representation of this observation."""
        content = Text()
        # 根据执行结果设置主标题样式和文字，成功绿色粗体，失败红色粗体
        if self.success:
            content.append("SubAgent Execution Succeeded:\n", style="bold green")
        else:
            content.append("SubAgent Execution Failed:\n", style="bold red")

        # 固定展示子代理名称，前缀粗体增强标识
        # 展示执行结果，失败时给结果也加浅红样式，和主标题呼应
        result_style = "dim red" if not self.success else ""
        content.append(f"Execution Result: {self.result}\n", style=result_style)

        # 仅当执行失败且有错误信息时，展示错误信息（红色强调）
        if not self.success and self.error_message:
            content.append(f"Error Message: {self.error_message}", style="bold red")

        return content


# ============================================================================
# SubAgentExecutor实现
# ============================================================================


class SubAgentExecutor(ToolExecutor):
    """SubAgent执行器 - 遵循ToolExecutor规范"""

    def __init__(self, subagent_config: SubAgentConfig):
        """初始化SubAgentExecutor

        Args:
            subagent_configs: SubAgent配置列表
        """
        # 直接存储Agent实例
        self.subagent_config = subagent_config

    def __call__(
        self,
        action: SubAgentAction,
        context: "RunnerContext | None" = None,
    ) -> SubAgentObservation:
        """执行SubAgent

        Args:
            action: SubAgent动作，包含SubAgent名称和任务
            context: MainAgent的运行时上下文

        Returns:
            SubAgent执行的观察结果
        """

        if context is None:
            return SubAgentObservation(
                result="Error: RunnerContext is required for SubAgent execution",
                success=False,
                error_message="RunnerContext is required",
            )

        subagent = self.subagent_config.agent
        
        

        try:
            logger.info(f"Starting SubAgent '{self.subagent_config.name}' execution")

            # ===== 1. 获取共享数据（从 MainAgent 的 RunnerContext）=====
            # 新架构：RunnerContext 直接持有共享数据字段，无需通过 conversation_state 属性

            # 为了 AgentState.build 的兼容，需要临时构造一个 ConversationState
            # （AgentState.build 还依赖 conversation_state._fs 等）
            # TODO: 未来可以重构 AgentState.build 来避免这个依赖
            from sdk.conversation.state import ConversationState

            temp_conversation_state = ConversationState(
                id=context.id,
                workspace=context.workspace,
                secret_registry=context.secret_registry,
                confirmation_policy=context.confirmation_policy,
                security_analyzer=context.security_analyzer,
                persistence_dir=context.persistence_dir,
            )
            # 设置私有属性 共用同一个写入fs文件
            temp_conversation_state._fs = context._fs
            temp_conversation_state._cipher = context._cipher
            temp_conversation_state._lock = context._lock
            temp_conversation_state._user_id = context._user_id

            # ===== 2. 处理 tools 继承逻辑 =====
            # 如果 SubAgentConfig 中指定了 tools，则使用这些 tools
            # 否则，从 MainAgent 继承所有 tools
            

            subagent_config = self.subagent_config
            if subagent_config.tools:
                logger.info(
                    f"SubAgent '{self.subagent_config.name}' using custom tools: "
                    f"{[t.name for t in subagent_config.tools]}"
                )
                # 创建一个临时的 Agent 副本，使用自定义的 tools
                subagent = subagent.model_copy(update={"tools": subagent_config.tools})
            else:
                logger.info(
                    f"SubAgent '{self.subagent_config.name}' inheriting tools from MainAgent"
                )

            # ===== 3. 为 SubAgent 创建独立的 AgentState =====
            from sdk.context.agent_state import AgentState

            subagent_state = AgentState.build(
                conversation_state=temp_conversation_state,  # 使用临时的 ConversationState
                agent=subagent,
                parent_agent_id=context.agent_id,  # 设置父 Agent ID
                task_description=action.task,
            )

            logger.info(
                f"Created AgentState for SubAgent '{self.subagent_config.name}' "
                f"(agent_id: {subagent_state.agent_id}, "
                f"parent: {subagent_state.parent_agent_id}, "
                f"task: {action.task})"
            )

            # ===== 4. 为 SubAgent 创建 RunnerContext（扁平化）=====
            subagent_context = RunnerContext.build(
                conversation_state=temp_conversation_state,  # 共享数据来源
                agent_state=subagent_state,  # Agent 数据来源
                event_center=context.event_center,
            )

            eventConsumer = AgentEventPersistentConsumer(
                agent_state=subagent_state,
                conversation_id=context.id,
                agent_id=subagent.id,
            )
            context.event_center.subscribe(eventConsumer)
            logger.debug(
                f"Created RunnerContext for SubAgent '{self.subagent_config.name}'"
            )

            # ===== 5. 初始化 SubAgent =====
            subagent.init_state(temp_conversation_state, subagent_context)

            logger.debug(f"Initialized SubAgent '{self.subagent_config.name}' state")

            # ===== 6. 添加用户任务消息到 SubAgent 的事件历史 =====
            from sdk.event.llm_convertible.message import MessageEvent
            from sdk.llm.message import Message, TextContent

            # 缺少记忆检索
            user_msg = MessageEvent(
                source="user",
                llm_message=Message(
                    role="user",
                    content=[TextContent(text=action.task)],
                ),
            )
            subagent_state._events.append(user_msg)  # type: ignore

            logger.debug(
                f"Added user message to SubAgent '{self.subagent_config.name}'"
            )

            # ===== 7. 创建 SubAgent 的 AgentRunner =====
            subagent_runner = AgentRunner(
                agent=subagent,
                context=subagent_context,
                max_iterations=100,  # 可配置
            )

            logger.debug(
                f"Created AgentRunner for SubAgent '{self.subagent_config.name}'"
            )
            
            # ===== 8. 运行 SubAgent（独立的生命周期） =====
            logger.info(f"Running SubAgent '{self.subagent_config.name}'")
            subagent_runner.run()

            logger.info(f"SubAgent '{self.subagent_config.name}' execution completed")

            # ===== 9. 提取最终结果 =====
            result = self._extract_result_from_agent_state(subagent_state)

            # 验证输出格式（如果指定）
            if action.expected_output_fields:
                self._validate_output(
                    result, action.expected_output_fields, action.output_format
                )

            # ===== 10. 标记为完成 =====
            subagent_state.mark_completed(result_summary=result)

            logger.info(
                f"SubAgent '{self.subagent_config.name}' completed successfully "
                f"(duration: {subagent_state.get_execution_duration():.2f}s)"
            )

            return SubAgentObservation(
                result=result,
                success=True,
            )

        except Exception as e:
            # ===== 11. 标记为失败 =====
            if "subagent_state" in locals():
                subagent_state.mark_failed(str(e))  # type: ignore

            logger.error(
                f"SubAgent '{self.subagent_config.name}' execution failed: {str(e)}",
                exc_info=True,
            )
            return SubAgentObservation(
                result=f"Error: {str(e)}",
                success=False,
                error_message=str(e),
            )

    def _validate_output(
        self, raw_result: str, expected_fields: list[OutputField], output_format: str
    ):
        if output_format == "json":
            json_str = self._extract_json(raw_result)

            if not json_str:
                raise ValueError("未找到JSON格式的输出")

            try:
                data = json.loads(json_str)
                structured_data = data
            except json.JSONDecodeError as e:
                raise ValueError(f"JSON解析失败: {str(e)}")

            # 校验字段
            for field in expected_fields:
                if field.required and field.name not in data:
                    raise ValueError(f"缺少必填字段: {field.name}")

                if field.name in data:
                    # 校验类型
                    actual_value = data[field.name]
                    type_valid = self._check_type(actual_value, field.type)
                    if not type_valid:
                        raise ValueError(
                            f"字段 {field.name} 类型错误: 期望 {field.type}, "
                            f"实际 {type(actual_value).__name__}"
                        )
        else:
            # text格式，简单检查字段名是否出现
            for field in expected_fields:
                if field.required and field.name not in raw_result:
                    raise ValueError(f"输出中未找到字段: {field.name}")

    def _check_type(self, value: Any, expected_type: str) -> bool:
        """检查值的类型

        Args:
            value: 值
            expected_type: 期望的类型名

        Returns:
            是否匹配
        """
        if expected_type == "any":
            return True

        type_map = {
            "str": str,
            "int": int,
            "float": (int, float),  # 允许int赋值给float
            "bool": bool,
            "list": list,
            "dict": dict,
        }

        expected_py_type = type_map.get(expected_type)
        if expected_py_type is None:
            return True  # 未知类型，跳过检查

        return isinstance(value, expected_py_type)

    def _extract_json(self, text: str) -> str | None:
        """从文本中提取JSON

        Args:
            text: 包含JSON的文本

        Returns:
            提取的JSON字符串，如果没有则返回None
        """
        # 尝试提取 ```json ... ``` 或 ``` ... ``` 中的内容
        json_match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
        if json_match:
            return json_match.group(1).strip()

        # 尝试查找 { ... } 或 [ ... ]
        json_match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
        if json_match:
            return json_match.group(1).strip()

        return None

    def _try_extract_json(self, text: str) -> dict[str, Any] | None:
        """尝试提取并解析JSON（不抛异常）

        Args:
            text: 文本

        Returns:
            解析的字典，失败返回None
        """
        json_str = self._extract_json(text)
        if json_str:
            try:
                return json.loads(json_str)
            except:
                pass
        return None

    def _extract_result_from_agent_state(self, agent_state: "AgentState") -> str:
        """从 AgentState 提取 SubAgent 的最终结果

        从 SubAgent 的事件历史中提取最后一条来自 Agent 的消息作为结果。

        Args:
            agent_state: SubAgent 的 AgentState

        Returns:
            提取的结果字符串
        """
        # 获取最后一条 ObservationEvent
        for event in reversed(list(agent_state.events)):
            if isinstance(event, ObservationEvent):
                for content in event.observation.content:
                    if isinstance(content, TextContent):
                        return content.text

        return "No result"


# ============================================================================
# SubAgentTool实现 - 遵循ToolDefinition规范
# ============================================================================

SUBAGENT_DESCRIPTION = """Delegate tasks to specialized subagents.

This tool allows the main agent to delegate specific tasks to specialized subagents.
Each subagent is an independent agent with its own tools and capabilities.

Use this tool when:
1. You need specialized expertise for a specific task
2. You want to parallelize work across multiple agents
3. You need to break down complex tasks into subtasks
4. You want to isolate concerns and improve modularity"""


class SubAgentTool(ToolDefinition[SubAgentAction, SubAgentObservation]):
    """SubAgent工具 - 遵循ToolDefinition规范

    这个工具允许MainAgent委托任务给专门的SubAgent。每个SubAgent有独立的
    生命周期、State、Context和Runner。

    核心特点：
    1. 为每个SubAgent创建独立的ConversationState
    2. 为每个SubAgent创建独立的RunnerContext
    3. 为每个SubAgent创建独立的AgentRunner
    4. SubAgent执行完成后自动清理
    5. SubAgent的事件不会污染MainAgent的事件历史
    """

    @classmethod
    def create(
        cls,
        tools: list[Tool],
        conv_state: "ConversationState | None" = None,
        subagent_config: SubAgentConfig | None = None,
    ) -> Sequence[Self]:
        """创建SubAgentTool实例

        Args:
            conv_state: 会话状态（可选）
            subagent_configs: SubAgent配置列表
            **params: 其他参数

        Returns:
            包含单个SubAgentTool实例的序列

        Raises:
            ValueError: 如果没有提供subagent_configs
        """
        if subagent_config is None:
            raise ValueError("subagent_configs is required for SubAgentTool")

        if not subagent_config:
            raise ValueError("subagent_configs cannot be empty")

        # 构建描述信息- 每个subAgent具有工具描述 +
        # description = f"{subagent_config.name}: {subagent_config.description}"
        # 追加到systemprompt中-将subagent集中声明

        logger.info(f"SubAgentTool create desc:{subagent_config.description}")

        if not subagent_config.tools:
            subagent_config.tools = tools
        # 创建执行器
        executor = SubAgentExecutor(subagent_config)

        return [
            cls(
                name=subagent_config.name,
                description=subagent_config.description,
                action_type=SubAgentAction,
                observation_type=SubAgentObservation,
                executor=executor,
                annotations=ToolAnnotations(
                    title="SubAgent Tool",
                    readOnlyHint=False,
                    destructiveHint=False,
                    idempotentHint=False,
                    openWorldHint=True,
                ),
            )
        ]
