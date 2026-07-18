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


from sdk.agent.runner_context import RunnerContext

from sdk.agent.agent_state import AgentState

from sdk.agent.agent_state_consumer import AgentEventPersistentConsumer

from sdk.agent.sub_agent_config import SubAgentSpec

from sdk.agent.sub_agent_resolver import SubAgentResolver

from sdk.event.llm_convertible.message import MessageEvent
from sdk.event.llm_convertible.observation import ObservationEvent

from sdk.llm.message import ImageContent, Message, TextContent

from common.logger import get_logger

from sdk.tool.spec import Tool

from sdk.tool.tool import (

    Action,

    Observation,

    ToolAnnotations,

    ToolDefinition,

    ToolExecutor,

)
 

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
       
        subagent_name: 执行的SubAgent名称
        success: 是否执行成功
        error_message: 错误信息（如果有）
    """
 
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
        result = self.content[0].text if isinstance(self.content[0], TextContent) else self.content[0].image_urls  
        content.append(f"Execution Result: {result}\n", style=result_style)

        # 仅当执行失败且有错误信息时，展示错误信息（红色强调）
        if not self.success and self.error_message:
            content.append(f"Error Message: {self.error_message}", style="bold red")

        return content


# ============================================================================
# SubAgentExecutor实现
# ============================================================================


class SubAgentExecutor(ToolExecutor):

    """SubAgent执行器 - 遵循ToolExecutor规范"""



    def __init__(self, sub_agent_spec: SubAgentSpec):

        """初始化SubAgentExecutor。"""

        self.sub_agent_spec = sub_agent_spec



    def __call__(

        self,

        action: SubAgentAction,

        context: "RunnerContext | None" = None,

    ) -> SubAgentObservation:

        """执行SubAgent。"""



        if context is None:

            return SubAgentObservation(

                result="Error: RunnerContext is required for SubAgent execution",

                success=False,

                error_message="RunnerContext is required",

            )



        try:



            subagent_spec = SubAgentResolver.resolve(context.agent_state, self.sub_agent_spec)



            logger.info(f"Starting SubAgent '{self.sub_agent_spec.name}' execution")



            subagent_state = AgentState.build(



                conversation_id=context.conversation_id,



                agent_spec=subagent_spec,



                task_description=action.task,



            )



            subagent_state.set_main_agent_flag(False)



            logger.info(



                f"Created AgentState for SubAgent '{self.sub_agent_spec.name}' "



                f"(agent_id: {subagent_state.agent_id}, "



                f"parent: {context.agent_id}, "



                f"task: {action.task})"



            )



            subagent_context = RunnerContext.build_clone(



                ref_context=context,



                agent_state=subagent_state,



                event_center=context.event_center,



            )



            eventConsumer = AgentEventPersistentConsumer(



                agent_state=subagent_state,



                conversation_id=context.conversation_id,



                agent_id=subagent_spec.id,

            )

            context.event_center.subscribe(eventConsumer)

            logger.debug(

                f"Created RunnerContext for SubAgent '{self.sub_agent_spec.name}'"

            )
            
            from sdk.agent.agent_runner import AgentRunner

            subagent_runner = AgentRunner(

 
                agent_spec=subagent_spec,



                context=subagent_context,



                max_iterations=100,



            )



            logger.debug(f"Initialized SubAgent '{self.sub_agent_spec.name}' state")



            from sdk.event.llm_convertible.message import MessageEvent

            from sdk.llm.message import Message, TextContent



            user_msg = MessageEvent(

                source="user",

                llm_message=Message(

                    role="user",

                    content=[TextContent(text=action.task)],

                ),

            )

            subagent_state._events.append(user_msg)  # type: ignore



            logger.debug(

                f"Added user message to SubAgent '{self.sub_agent_spec.name}'"

            )



            logger.debug(

                f"Created AgentRunner for SubAgent '{self.sub_agent_spec.name}'"

            )



            logger.info(f"Running SubAgent '{self.sub_agent_spec.name}'")

            subagent_runner.run()

            logger.info(f"SubAgent '{self.sub_agent_spec.name}' execution completed")



            content = self._extract_result_from_agent_state(subagent_state)



            # if action.expected_output_fields:

            #     self._validate_output(

            #         result, action.expected_output_fields, action.output_format

            #     )
            
            logger.info(

                f"SubAgent '{self.sub_agent_spec.name}' completed successfully "

                f"(duration: {subagent_state.get_execution_duration():.2f}s)"

            )



            return SubAgentObservation(

                content=content,

                success=True,

            )

        except Exception as e:

            logger.error(

                f"SubAgent '{self.sub_agent_spec.name}' execution failed: {str(e)}",

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

    def _extract_result_from_agent_state(self, agent_state: "AgentState") ->  list[TextContent | ImageContent] :
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
                return event.observation.content 
                 
            if isinstance(event, MessageEvent) and event.source == "agent":
                return event.llm_message.content
           

        return [TextContent(text="no Result Found")]


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

        subagent_spec: SubAgentSpec | None = None,

    ) -> Sequence[Self]:

        """创建SubAgentTool实例。"""

        if subagent_spec is None:

            raise ValueError("subagent_spec is required for SubAgentTool")



        logger.info(f"SubAgentTool create desc:{subagent_spec.description}")



        executor = SubAgentExecutor(subagent_spec)



        return [

            cls(

                name=subagent_spec.name,

                description=subagent_spec.description,

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
