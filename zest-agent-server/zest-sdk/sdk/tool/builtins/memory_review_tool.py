from collections.abc import Sequence
from typing import List, Optional

from pydantic import Field
from rich.text import Text

from sdk.tool.registry import register_tool
from sdk.tool.schema import Action, Observation
from sdk.tool.tool import ToolAnnotations, ToolDefinition, ToolExecutor
from sdk.agent.runner_context import RunnerContext


class MemoryReviewAction(Action):
    """审核中转 Action：携带相似经验列表 + 新内容，触发用户确认审核。"""

    similar_experiences: List[dict] = Field(
        default_factory=list,
        description="相似经验列表，每项含 id/question/solution/trace_summary/feedback_type。由 experience_memory 工具在审核 observation 中提供。"
    )
    new_content: str = Field(
        ...,
        description="用户新提交的 solution（待合并/替换到选定经验）。"
    )
    question: str = Field(
        ...,
        description="用户问题（与 experience_memory 一致）。"
    )
    feedback_type: str = Field(
        default="optimization",
        description="反馈类型，默认 optimization（审核路径专属）。"
    )

    @property
    def visualize(self) -> Text:
        content = Text()
        content.append("MemoryReviewAction: 审核中转\n", style="bold blue")
        content.append(f"Question: {self.question}\n", style="italic")
        content.append(f"New content: {self.new_content[:80]}...\n", style="italic")
        content.append(f"Similar experiences: {len(self.similar_experiences)} 条\n", style="italic")
        return content


class MemoryReviewObservation(Observation):
    """审核中转 observation：携带用户选择/编辑结果，供 LLM 决策更新。"""

    success: bool = Field(default=True, description="审核是否成功流转。")
    selected_id: Optional[str] = Field(
        default=None,
        description="用户选择的经验 id（用于 LLM 下一步调 experience_memory 时携带）。"
    )
    edited_content: Optional[str] = Field(
        default=None,
        description="用户编辑后的 solution（若用户编辑；否则与 new_content 一致）。"
    )
    error_message: Optional[str] = Field(default=None, description="错误信息。")

    @property
    def visualize(self) -> Text:
        content = Text()
        content.append("MemoryReviewObservation:\n", style="bold green")
        content.append(f"Success: {self.success}\n")
        if self.selected_id:
            content.append(f"Selected ID: {self.selected_id}\n")
        if self.edited_content:
            content.append(f"Edited content: {self.edited_content[:80]}...\n")
        return content


class MemoryReviewExecutor(ToolExecutor):
    """审核中转 executor：防御性实现，正常路径不被调用。

    用户确认后，由 respond_to_confirmation 路径直接发 ObservationEvent（携带用户选择），
    memory_review ActionEvent 即被标记为已匹配，get_unmatched_actions 不再取出，
    executor 不会执行。此处仅在异常路径下返回提示 observation。
    """

    def __call__(
        self,
        action: MemoryReviewAction,
        context: RunnerContext,
    ) -> MemoryReviewObservation:
        return MemoryReviewObservation(
            success=False,
            error_message="memory_review executor 不应被直接执行；用户确认路径由 respond_to_confirmation 处理。若看到此 observation，请检查 confirmation 路径是否正确发 ObservationEvent。"
        )


MEMORY_REVIEW_PROMPT = "记忆审核中转工具。当 experience_memory 工具返回 observation 提示需用户审核时调用本工具。action 携带相似经验列表与用户新提交内容，触发用户确认流程。用户在前端选择某条经验并可选编辑内容，确认后系统会反馈 observation，此时 agent 应再次调用 experience_memory 工具并携带 experience_id 参数完成更新。使用条件：1. 仅在 experience_memory observation 中包含需审核提示时调用；2. similar_experiences 字段必须从 experience_memory observation 中完整复制；3. 不要主动合并或编辑内容，交由用户决策。本工具触发后必须等待用户确认，不要在用户未决策前继续操作。"


class MemoryReviewTool(
    ToolDefinition[MemoryReviewAction, MemoryReviewObservation]
):
    """记忆审核中转工具：LLM 在经验审核时调用，触发用户确认流程。"""

    @classmethod
    def create(
        cls, context: RunnerContext
    ) -> Sequence["MemoryReviewTool"]:
        return [
            cls(
                name="memory_review",
                description=MEMORY_REVIEW_PROMPT,
                action_type=MemoryReviewAction,
                observation_type=MemoryReviewObservation,
                executor=MemoryReviewExecutor(),
                annotations=ToolAnnotations(
                    title="Memory Review Tool (记忆审核中转工具)",
                    ReadOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=False,
                ),
            )
        ]


register_tool(name=MemoryReviewTool.tool_name, factory=MemoryReviewTool)
