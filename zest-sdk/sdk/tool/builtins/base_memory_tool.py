from collections.abc import Sequence

from pydantic import Field
from rich.text import Text

from sdk.agent.runner_context import RunnerContext
from sdk.tool.schema import Action, Observation
from sdk.tool.tool import ToolAnnotations, ToolDefinition, ToolExecutor


FILE_PATH = "memory/memory.md"
BASE_MEMORY_TOOL_DESCRIPTION = """<memory_guidelines>
    The above <agent_memory> was loaded in from files in your filesystem. As you learn from your interactions with the user, you can save new knowledge by calling the `edit_file` tool.

    **Learning from feedback:**
    - One of your MAIN PRIORITIES is to learn from your interactions with the user. These learnings can be implicit or explicit. This means that in the future, you will remember this important information.
    - When you need to remember something, updating memory must be your FIRST, IMMEDIATE action - before responding to the user, before calling other tools, before doing anything else. Just update memory immediately.
    - When user says something is better/worse, capture WHY and encode it as a pattern.
    - Each correction is a chance to improve permanently - don't just fix the immediate issue, update your instructions.
    - A great opportunity to update your memories is when the user interrupts a tool call and provides feedback. You should update your memories immediately before revising the tool call.
    - Look for the underlying principle behind corrections, not just the specific mistake.
    - The user might not explicitly ask you to remember something, but if they provide information that is useful for future use, you should update your memories immediately.

    **Asking for information:**
    - If you lack context to perform an action (e.g. send a Slack DM, requires a user ID/email) you should explicitly ask the user for this information.
    - It is preferred for you to ask for information, don't assume anything that you do not know!
    - When the user provides information that is useful for future use, you should update your memories immediately.

    **When to update memories:**
    - When the user explicitly asks you to remember something (e.g., "remember my email", "save this preference")
    - When the user describes your role or how you should behave (e.g., "you are a web researcher", "always do X")
    - When the user gives feedback on your work - capture what was wrong and how to improve
    - When the user provides information required for tool use (e.g., slack channel ID, email addresses)
    - When the user provides context useful for future tasks, such as how to use tools, or which actions to take in a particular situation
    - When you discover new patterns or preferences (coding styles, conventions, workflows)

    **When to NOT update memories:**
    - When the information is temporary or transient (e.g., "I'm running late", "I'm on my phone right now")
    - When the information is a one-time task request (e.g., "Find me a recipe", "What's 25 * 4?")
    - When the information is a simple question that doesn't reveal lasting preferences (e.g., "What day is it?", "Can you explain X?")
    - When the information is an acknowledgment or small talk (e.g., "Sounds good!", "Hello", "Thanks for that")
    - When the information is stale or irrelevant in future conversations
    - Never store API keys, access tokens, passwords, or any other credentials in any file, memory, or system prompt.
    - If the user asks where to put API keys or provides an API key, do NOT echo or save it.

    **Examples:**
    Example 1 (remembering user information):
    User: Can you connect to my google account?
    Agent: Sure, I'll connect to your google account, what's your google account email?
    User: john@example.com
    Agent: Let me save this to my memory.
    Tool Call: file_editor(...) -> remembers that the user's google account email is john@example.com

    Example 2 (remembering implicit user preferences):
    User: Can you write me an example for creating a deep agent in LangChain?
    Agent: Sure, I'll write you an example for creating a deep agent in LangChain <example code in Python>
    User: Can you do this in JavaScript
    Agent: Let me save this to my memory.
    Tool Call: file_editor(...) -> remembers that the user prefers to get LangChaincode examples in JavaScript
    Agent: Sure, here is the JavaScript example<example code in JavaScript>

    Example 3 (do not remember transient information):
    User: I'm going to play basketball tonight so I will be offline for a few hours.
    Agent: Okay I'll add a black to your calendar.
    Tool Call: create_calendar_event(...) -> just calls a tool, does not commit anything to memory, as it is transient information
</memory_guidelines>"""


class BaseMemoryAction(Action):
    """Represents an action to be taken on the memory, such as saving or retrieving information."""

    content: str = Field(description="要保存的经验")
    # 后期统一加上 分类更好：基础信息，用户信息，环境信息等

    @property
    def visualize(self) -> Text:
        """Return Rich Text representation of this action."""
        content = Text()
        # 主标题保持和原类一致的bold blue样式，贴合SubAgent动作语义
        content.append("Call BaseMemoryAction to  save:\n", style="bold blue")
        content.append(f"Content: {self.content}")
        return content


class BaseMemoryObservation(Observation):
    """Represents the result of a memory action, such as the retrieved information."""

    success: bool = Field(default=True, description="是否执行成功")
    error_message: str | None = Field(default=None, description="错误信息")

    @property
    def visualize(self) -> Text:
        """Return Rich Text representation of this observation."""
        content = Text()
        content.append("MemoryObservation:\n", style="bold green")
        content.append(f"Content: {self.content}")
        return content


class BaseMemoryExecutor(ToolExecutor):
    def __call__(
        self,
        action: BaseMemoryAction,
        context: RunnerContext
        | None = None,  # 【修改2】参数名+类型：conversation→context，LocalConversation→RunnerContext
    ) -> BaseMemoryObservation:
        # 这里可以添加实际的内存操作逻辑，例如将内容保存到数据库或文件中
        # 目前仅返回一个成功的观察结果作为示例
        # 先通过llm基于内容和当前要写入的记忆，识别是否存在冲突，存在则覆盖并更新，不存在则直接添加
        # 为了避免对整体记忆的影响，在这里通过llm识别冲突，并返回原始冲突内容，不存在则返回为空即可
        # 这样我们就可以拿着冲突内容去更新记忆，而不是直接覆盖，保留更多原始信息，提升记忆的质量和可用性
        """执行记忆操作。

        Args:
            action: 包含要保存的记忆内容的动作
            context: 运行上下文，包含 LLM 实例

        Returns:
            BaseMemoryObservation: 包含冲突检测结果的观察结果
        """
        return BaseMemoryObservation(success=True)


class BaseMemoryTool(ToolDefinition[BaseMemoryAction, BaseMemoryObservation]):
    @classmethod
    def create(
        cls,
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
