"""Base Memory Tool — 支持分类记忆保存，每条记忆有唯一 ID。

对齐渐进式披露理念：
- profile: 用户个人信息（身份、账号、联系方式等）
- preferences: 用户偏好（语言风格、代码偏好、工作习惯等）
- domain_context: 领域知识（业务领域规则、行业术语等）
- project_context: 项目/程序上下文（仓库结构、技术栈、规范等）

每条记忆包含：
- id: 自动生成（格式 mem_xxxxxxxx）
- name: 记忆名称
- description: 记忆描述
- content: 记忆具体内容
"""
from collections.abc import Sequence
import uuid

from common.storage.memory.base import BaseMemoryEvent
from pydantic import Field
from rich.text import Text

from sdk.agent.runner_context import RunnerContext
from common.storage.memory.store import MemoryCategory
from sdk.llm.message import TextContent
from sdk.tool.registry import register_tool
from sdk.tool.schema import Action, Observation
from sdk.tool.tool import ToolAnnotations, ToolDefinition, ToolExecutor


FILE_PATH = "memory/memory.md"

CATEGORY_DESCRIPTIONS = {
    MemoryCategory.PROFILE: "用户个人信息（身份、账号、联系方式等）",
    MemoryCategory.PREFERENCES: "用户偏好（语言风格、代码偏好、工作习惯等）",
    MemoryCategory.DOMAIN_CONTEXT: "领域知识（业务领域规则、行业术语等）",
    MemoryCategory.PROJECT_CONTEXT: "项目/程序上下文（仓库结构、技术栈、规范等）",
}

CATEGORY_HINT = (
    "category 取值: "
    + ", ".join(f"'{c.value}' ({desc})" for c, desc in CATEGORY_DESCRIPTIONS.items())
    + "。不指定则默认 'profile'。"
)

MODE_HINT = (
    "mode 取值: 'append'（默认，追加新条目或根据 ID 更新已有条目）"
    "或 'overwrite'（全量覆盖）。"
    "如果提供了 entry_id，append 模式会更新该条目而非追加。"
)

BASE_MEMORY_TOOL_DESCRIPTION = f"""<memory_guidelines>
    The above <agent_memory> was loaded in from files in your filesystem. As you learn from your interactions with the user, you can save new knowledge by calling the `memory` tool.

    **Memory categories (progressive disclosure):**
    - profile: User personal information (identity, accounts, contact details, etc.)
    - preferences: User preferences (language style, coding preferences, work habits, etc.)
    - domain_context: Domain knowledge (business rules, industry terms, etc.)
    - project_context: Project/program context (repo structure, tech stack, conventions, etc.)

    When saving memories, choose the most appropriate category based on the content.
    This enables progressive disclosure — only the most relevant memories are loaded at any time.

    **Memory entry structure:**
    Each memory entry has: name, description, content. An ID is auto-generated.
    - name: A short title for this memory (e.g. "User prefers TypeScript")
    - description: A brief explanation of why this is being remembered
    - content: The actual memory content

    **Learning from feedback:**
    - One of your MAIN PRIORITIES is to learn from your interactions with the user.
    - When you need to remember something, updating memory must be your FIRST, IMMEDIATE action.
    - When user says something is better/worse, capture WHY and encode it as a pattern.
    - Each correction is a chance to improve permanently.
    - Look for the underlying principle behind corrections, not just the specific mistake.
    - The user might not explicitly ask you to remember something, but if they provide information that is useful for future use, you should update your memories immediately.

    **Asking for information:**
    - If you lack context to perform an action, you should explicitly ask the user for this information.
    - When the user provides information that is useful for future use, update your memories immediately.

    **When to update memories:**
    - When the user explicitly asks you to remember something
    - When the user describes your role or how you should behave
    - When the user gives feedback on your work
    - When the user provides information required for tool use
    - When you discover new patterns or preferences

    **When to NOT update memories:**
    - When the information is temporary or transient
    - When the information is a one-time task request
    - When the information is a simple question
    - When the information is an acknowledgment or small talk
    - Never store API keys, access tokens, passwords, or any other credentials.
</memory_guidelines>"""


class BaseMemoryAction(Action):
    """Represents an action to save information to memory with a specific category and mode."""

    name: str = Field(default="", description="记忆名称（简短标题）")
    description: str = Field(default="", description="记忆描述（为什么记住这条）")
    content: str = Field(description="记忆具体内容")
    category: str = Field(
        default="profile",
        description=CATEGORY_HINT,
    )
    mode: str = Field(
        default="append",
        description=MODE_HINT,
    )
    entry_id: str = Field(
        default="",
        description="要更新的已有记忆条目 ID。留空则新增。",
    )

    @property
    def visualize(self) -> Text:
        """Return Rich Text representation of this action."""
        content = Text()
        content.append("Call BaseMemoryAction to save:\n", style="bold blue")
        content.append(f"Name: {self.name}\n")
        content.append(f"Category: {self.category}\n")
        content.append(f"Mode: {self.mode}\n")
        if self.entry_id:
            content.append(f"Entry ID: {self.entry_id}\n")
        content.append(f"Content: {self.content}")
        return content


class BaseMemoryObservation(Observation):
    """Represents the result of a memory action."""

    success: bool = Field(default=True, description="是否执行成功")
    error_message: str | None = Field(default=None, description="错误信息")
    entry_id: str | None = Field(default=None, description="写入/更新的记忆条目 ID")

    @property
    def visualize(self) -> Text:
        """Return Rich Text representation of this observation."""
        content = Text()
        content.append("MemoryObservation:\n", style="bold green")
        content.append(f"Content: {self.content}")
        return content


class BaseMemoryExecutor(ToolExecutor):
    """Execute memory save operation, routing to the appropriate category store."""

    def __call__(
        self,
        action: BaseMemoryAction,
        context: RunnerContext | None = None,
    ) -> BaseMemoryObservation:
        """执行记忆保存操作，按 category 路由到对应的分类存储。

        Args:
            action: 包含要保存的记忆内容、名称、描述、分类的动作
            context: 运行上下文

        Returns:
            BaseMemoryObservation: 执行结果
        """
        from common.logger import get_logger
        logger = get_logger(__name__)

        if context is None:
            return BaseMemoryObservation(
                success=False,
                error_message="RunnerContext 未提供，无法保存记忆",
            )

 

        # 解析 category
        category_str = action.category or "profile"
        try:
            category = MemoryCategory(category_str)
        except ValueError:
            category = MemoryCategory.PROFILE

        # 解析 mode
        mode = getattr(action, "mode", "append") or "append"
        if mode not in ("append", "overwrite"):
            logger.warning(f"无效的 mode '{mode}'，使用默认 append")
            mode = "append"

        # 写入分类记忆
        user_id = getattr(context, "user_id", None) or "default"
        entry_id = f"mem_{uuid.uuid4().hex[:8]}"
        try:
            baseEvent = BaseMemoryEvent(
                user_id = user_id,
                content={
                    "id": entry_id,
                    "name": action.name or "",
                    "description": action.description or "",
                    "content": action.content,
                },
                category=category,
                mode=mode, 
            )
            context.publish_event(baseEvent)
           
            return BaseMemoryObservation(
                content=[
                    TextContent(
                        f"成功保存记忆到 {category.value} 分类（mode={mode} entry_id={entry_id} ）"
                    )
                ],
                success=True,
                entry_id=entry_id,
            )
        except Exception as e:
            return BaseMemoryObservation(
                success=False,
                error_message=f"保存记忆失败: {str(e)}",
            )


class BaseMemoryTool(ToolDefinition[BaseMemoryAction, BaseMemoryObservation]):
    @classmethod
    def create(
        cls,
        context: RunnerContext | None = None,  # noqa: ARG002
    ) -> Sequence["BaseMemoryTool"]:
        return [
            cls(
                name="memory",
                description=BASE_MEMORY_TOOL_DESCRIPTION,
                action_type=BaseMemoryAction,
                observation_type=BaseMemoryObservation,
                executor=BaseMemoryExecutor(),
                annotations=ToolAnnotations(
                    title="Memory Tool",
                    readOnlyHint=False,
                    destructiveHint=False,
                    idempotentHint=False,
                    openWorldHint=True,
                ),
            )
        ]

register_tool(name=BaseMemoryTool.tool_name, factory=BaseMemoryTool)