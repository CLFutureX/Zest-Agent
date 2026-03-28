import json
import random
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Literal, List, Optional

from pydantic import Field, BaseModel
from rich.text import Text

from sdk.agent.runner_context import RunnerContext
from sdk.context.memory.base import ExecutionTrace, ExperienceMemory
from sdk.tool.schema import Action, Observation
from sdk.tool.tool import ToolAnnotations, ToolDefinition, ToolExecutor


# 新增：对应Prompt中的ExecutionTrace模型，用于记录工具调用及思考过程
# class ExecutionTrace(BaseModel):
#     tool_name: str = Field(
#         description="Name of the tool used (fill in 'None' if no tool is used). "
#         "使用的工具名称（未调用工具则填写'None'）。"
#     )
#     choice_reason: str = Field(
#         description="Thinking process for choosing the tool (or not choosing a tool), combining user questions and solution goals, clear and traceable. "
#         "选择该工具（或不选择工具）的思考过程，结合用户问题和解决方案目标，清晰可追溯。"
#     )


class ExperienceMemoryAction(Action):
    """Action for recording experience data based on user feedback.
    基于用户反馈记录经验数据的动作，需包含问题、解决方案、反馈类型等核心要素，严格匹配Prompt规范。
    """

    question: str = Field(
        ...,
        description="The original question/prompt from user that led to this experience (summary of the core problem, 50-200 characters), consistent with the user's initial question, no extra modifications. "
        "用户触发该经验的原始问题/指令（核心问题摘要，50-200字），与用户最初提出的问题保持一致，不添加额外修饰。",
    )
    solution: str = Field(
        ...,
        description="Detailed solution/process to solve the user's problem (include key steps, tool usage, and core logic, 100-500 characters), completely reproduce the original solution without deletion or modification. "
        "解决用户问题的具体方案/过程（包含关键步骤、使用的工具、核心逻辑，100-500字），完整复刻原始解决方案，不删减、不修改核心信息。",
    )
    # 优化：对齐Prompt反馈类型，新增optimization类型，删除neutral（Prompt无此类型）
    feedback_type: Literal["positive", "negative", "optimization"] = Field(
        ...,
        description="User's feedback type on the solution (strictly select one, no customization): positive (approve the solution, problem solved), negative (solution invalid, problem unsolved), optimization (approve the core, put forward optimization suggestions). "
        "用户对解决方案的反馈类型（严格选择其一，不得自定义）：positive（认可解决方案，问题已解决）、negative（解决方案无效，问题未解决）、optimization（认可方案核心，提出优化建议）。",
    )
    # experience_summary: Optional[str] = Field(
    #     default=None,
    #     description="Brief summary of the experience (10-50 characters, highlight core insight/lesson learned). "
    #     "经验核心摘要（10-50字，突出核心启示/教训），可选但建议填写。",
    # )
    # 新增：对应Prompt中的execute_trace，记录工具调用及思考过程，不可为空
    execute_trace: List[ExecutionTrace] = Field(
        default_factory=list,
        description="List of execution process traces, each element is an ExecutionTrace object, including all tool calls and corresponding thinking processes (cannot be empty; if no tool is used, fill in the corresponding ExecutionTrace with tool_name 'None'). "
        "执行过程追踪列表，每个元素为ExecutionTrace对象，包含所有工具调用及对应思考过程（不可为空，未调用工具需填写tool_name为'None'的对应ExecutionTrace）。",
    )
    # 新增：对应Prompt中的domain_type，标注适用领域
    domain_type: Optional[str] = Field(
        default=None,
        description="Applicable domain type of the question and solution (e.g., 'Customer Service', 'Technical Support'), fill in None if not clearly determined. "
        "问题及解决方案所属的适用领域类型（如'Customer Service'、'Technical Support'），无法明确判断则填写None。",
    )

    @property
    def visualize(self) -> Text:
        """Return Rich Text representation of this action."""
        content = Text()
        content.append(
            "Call ExperienceMemoryAction to save feedback-based experience:\n",
            style="bold blue",
        )
        content.append(f"Question: {self.question}\n", style="italic")
        content.append(f"Solution: {self.solution}\n", style="italic")
        content.append(f"Feedback Type: {self.feedback_type}\n", style="italic")
        content.append(f"Domain Type: {self.domain_type if self.domain_type else 'None'}\n", style="italic")
        content.append("Execute Trace:\n", style="italic")
        for idx, trace in enumerate(self.execute_trace, 1):
            content.append(f"  {idx}. Tool: {trace.tool_name}, Reason: {trace.choice_reason}\n", style="italic")
      
        return content


class ExperienceMemoryObservation(Observation):
    """Observation for the result of recording an experience based on user feedback."""

    success: bool = Field(
        default=True,
        description="Whether the experience was recorded successfully (True/False). "
        "经验数据是否成功记录（是/否）。",
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Error message if recording failed (e.g., missing key fields, storage exception). "
        "记录失败时的错误信息（如缺失关键字段、存储异常）。",
    )
    experience_id: Optional[str] = Field(
        default=None,
        description="Unique ID of the recorded experience (auto-generated if successful), format: user_id-timestamp-4 random digits. "
        "已记录经验的唯一标识ID（成功时自动生成），格式：user_id-时间戳-4位随机数。",
    )

    @property
    def visualize(self) -> Text:
        """Return Rich Text representation of this observation."""
        content = Text()
        content.append("ExperienceMemoryObservation:\n", style="bold green")
        content.append(f"Success: {self.success}\n")
        if self.experience_id:
            content.append(f"Experience ID: {self.experience_id}\n")
        if self.error_message:
            content.append(f"Error Message: {self.error_message}", style="bold red")
        return content


# 优化：同步更新EXPERIENCE_PROMPT，保持与工具实现一致（英文版，与打开的Canvas Prompt呼应）
EXPERIENCE_PROMPT = """### Task Objective
As the experience precipitation module of the Agent, you need to automatically complete the experience summary when the user gives feedback on the historical solution in the multi-turn dialogue, organize the relevant information into the ExperienceMemory format, and deposit it as historical experience to provide reference for solving similar problems in the future. Ensure that the summary content is true, complete, consistent with user feedback, and strictly matches the field requirements.

### Trigger Condition
The experience summary task shall be executed immediately if and only if the user clearly gives feedback on the previously provided solution (including positive feedback, negative feedback, optimization suggestions, etc.) in the multi-turn dialogue, and shall not be omitted or triggered in advance.

### Core Requirements (Strictly match the following field specifications, no missing or incorrect filling allowed)
#### 1. ExperienceMemory Field Filling Specifications
- id: Generate a unique identifier in the format of "user_id-timestamp-4 random digits" (the timestamp is the current time when the summary is generated, format: YYYYMMDDHHMMSS) to ensure global uniqueness without duplication.
- user_id: Fill in the unique identifier of the current dialogue user, which is completely consistent with the user id obtained in the dialogue and must not be incorrect.
- question: Accurately extract the original question corresponding to the user's current feedback, which should be complete and concise, without additional modifications, consistent with the question initially raised by the user, and avoid ambiguity.
- solution: Fill in the historical solution corresponding to the current feedback, which should completely reproduce the solution provided to the user at that time, without deleting or modifying core information, and ensure complete consistency with the original solution.
- execute_trace: It is a list type, and each element is an ExecutionTrace object. It is necessary to completely restore the execution process of the solution, including all tool calls and corresponding thinking processes. The specific requirements are as follows:
  - tool_name: Fill in the names of all tools used in the execution process. If no tools are used, fill in "None"; if multiple tools are used, fill them in the order of calling, and each tool corresponds to one ExecutionTrace element.
  - choice_reason: Fill in the thinking process of calling the tool (or not calling the tool). It is necessary to clearly explain the reason for choosing the tool and the thinking logic in combination with the user's question and the solution goal, ensuring that it is truly traceable, not empty or perfunctory.
- domain_type: Fill in the applicable domain type of the question and solution (such as "Customer Service", "Technical Support", "Product Consultation", etc.). If it cannot be clearly judged, fill in None (do not fill in specific content, keep the default value of the field).
- feedback_type: Clearly fill in the type of user feedback. Only one of the following options can be selected, and no customization is allowed: Positive Feedback (approve the solution, the problem has been solved), Negative Feedback (the solution is invalid, the problem has not been solved), Optimization Feedback (approve the core of the solution and put forward specific optimization suggestions).
- created_at: Fill in the current time when the experience summary is generated, in datetime type (example: 2024-05-20 14:30:00), which is consistent with the timestamp in the id.
- updated_at: Fill in None (do not fill in specific content) when initially generated. If the experience summary is modified later, fill in the datetime type time when the modification is made.

#### 2. Supplementary Instructions for ExecutionTrace Fields
Each ExecutionTrace object shall correspond to one tool call (or no tool call). The thinking process shall focus on "why choose this tool" and "how this tool assists in solving the user's problem". If no tool is used, it is necessary to explain "the reason for not using the tool (e.g., the problem can be directly answered through common sense/built-in knowledge without tool support)".

### Operation Process
1.  Identify User Feedback: Determine whether the user's current speech is feedback on the historical solution, and confirm the feedback type (positive/negative/optimization).
2.  Extract Core Information: Extract the user id, original question, corresponding solution, and execution process (tool call + thinking process) from the dialogue history.
3.  Fill in Field Content: Strictly fill in all fields of ExperienceMemory and ExecutionTrace one by one in accordance with the above specifications to ensure no missing, no incorrect filling, and correct format.
4.  Verify Completeness: Check whether all fields meet the requirements, whether the id is unique, whether the execute_trace completely restores the execution process, whether the feedback type is accurate, and whether the time format is correct.
5.  Complete Precipitation: Store the fully filled ExperienceMemory object as historical experience in the Agent's experience library to ensure that it can be called for similar problems in the future.

### Notes
1.  It is strictly prohibited to tamper with the user's original question, solution and feedback content. All information must be truly reproduced from the dialogue history.
2.  execute_trace shall not be empty. If no tool is used, it is necessary to clearly fill in "None" as the tool name and the corresponding thinking process.
3.  If domain_type cannot be clearly determined, fill in None, and do not leave it blank or fill in irrelevant content.
4.  The time format must strictly follow the datetime type, and the format shall not be modified at will.
5.  The summary content shall be concise and accurate, avoid redundancy, and focus on the core of the problem, solution, execution process and user feedback."""


class ExperienceMemoryExecutor(ToolExecutor):
    """Executor for recording experience data to local file (can be extended to ES/MinIO), strictly following Prompt specifications."""

    def __init__(self, storage_path: str = "./agent_experiences"):
        self.storage_path = Path(storage_path)
        # 创建存储目录（不存在则新建）
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def _generate_experience_id(self, user_id: Optional[str] = None) -> str:
        """Generate unique ID for experience, following Prompt format: user_id-timestamp-4 random digits."""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        # 生成4位随机数字（0000-9999），确保格式统一
        random_suffix = f"{random.randint(0, 9999):04d}"
        # 若用户ID不存在，用"unknown_user"替代，保证ID格式完整
        user_id_part = user_id if user_id else "unknown_user"
        return f"{user_id_part}-{timestamp}-{random_suffix}"

    def __call__(
        self,
        action: ExperienceMemoryAction,
        context: Optional[RunnerContext] = None,
    ) -> ExperienceMemoryObservation:
        try:
            # 1. 校验核心字段（严格遵循Prompt注意事项，避免缺失/错误）
            if not action.question.strip() or not action.solution.strip():
                return ExperienceMemoryObservation(
                    success=False,
                    error_message="Question and solution cannot be empty (问题和解决方案不能为空)。",
                )
            # 校验execute_trace：不可为空，未调用工具时需有对应记录
            if not action.execute_trace:
                return ExperienceMemoryObservation(
                    success=False,
                    error_message="execute_trace cannot be empty; if no tool is used, please add an ExecutionTrace with tool_name 'None' (execute_trace不可为空，未调用工具请添加tool_name为'None'的ExecutionTrace)。",
                )
            # 校验feedback_type：严格匹配Prompt规定的三种类型
            if action.feedback_type not in ["positive", "negative", "optimization"]:
                return ExperienceMemoryObservation(
                    success=False,
                    error_message="feedback_type must be one of 'positive', 'negative', 'optimization' (feedback_type必须是'positive'、'negative'、'optimization'之一)。",
                )

            current_time = datetime.now()
            user_id = context.user_id if context else None
            # 2. 生成结构化经验数据（完整匹配Prompt的ExperienceMemory字段）
            experience_id = self._generate_experience_id(user_id=user_id)
            # 格式化execute_trace为字典列表，便于存储
            
            experience_memory = ExperienceMemory(
                id=experience_id,
                user_id=user_id, # type: ignore
                question=action.question,
                solution=action.solution,
                execute_trace=action.execute_trace,
                domain_type=action.domain_type,
                feedback_type=action.feedback_type,
                created_at=current_time,
                 )
            if context:
                context.event_center.publish(
                    event=experience_memory,
                    conversation_id=str(context.id), agent_id=str(context.agent_id))
            

            # # 3. 持久化到本地文件（可扩展至ES/MinIO，符合工具注释说明）
            # file_path = self.storage_path / f"{experience_id}.json"
            # with open(file_path, "w", encoding="utf-8") as f:
            #     json.dump(experience_data, f, ensure_ascii=False, indent=2)

            # 4. 返回成功结果（包含经验ID，符合Prompt要求）
            return ExperienceMemoryObservation(
                success=True, experience_id=experience_id
            )

        except Exception as e:
            # 捕获所有异常，返回错误信息（中英文对照，便于调试）
            return ExperienceMemoryObservation(
                success=False,
                error_message=f"Failed to record experience: {str(e)} (记录经验失败：{str(e)})",
            )


class ExperienceMemoryTool(
    ToolDefinition[ExperienceMemoryAction, ExperienceMemoryObservation]
):
    """"\n\n"
    "【中文说明】\n"
    "基于用户反馈记录结构化经验数据的工具，严格遵循经验沉淀Prompt规范。\n"
    "### 使用条件：\n"
    "1. 仅在用户对之前的解决方案给出明确反馈（正面/负面/优化建议）时调用；\n"
    "2. 需记录的经验必须包含：用户核心问题 + 详细解决过程 + 反馈类型 + 执行过程追踪（工具调用及思考过程）；\n"
    "3. 严格按照Prompt字段规范填写，不得缺失、错填关键信息。\n"
    "### 核心目的：\n"
    "根据用户反馈总结最近的问题及解决过程，生成结构化经验数据，供后续Agent复用，实现经验沉淀。"""
    @classmethod
    def create(
        cls, storage_path: str = "./agent_experiences"
    ) -> Sequence["ExperienceMemoryTool"]:
        return [
            cls(
                name="experience_memory",  # 工具名贴合“记忆经验”语义，保持不变
                description=EXPERIENCE_PROMPT,  # 描述直接使用Prompt内容，确保工具说明与Prompt完全一致
                # description=(
                #     "A tool for recording structured experience data based on user feedback, strictly following the experience precipitation Prompt specifications. "
                #     "### Usage Conditions (使用条件):\n"
                #     "1. Must be used only when the user provides clear feedback (positive/negative/optimization suggestions) on the previous solution;\n"
                #     "2. The experience to record must include: core user question + detailed solution process + feedback type + execution trace (tool calls and thinking processes);\n"
                #     "3. Fill in all fields strictly in accordance with Prompt specifications, no missing or incorrect filling of key information.\n"
                #     "### Core Purpose (核心目的):\n"
                #     "Summarize the latest user question and its solution process based on feedback, generate structured experience data for future Agent reuse and experience precipitation. "
                # ),
                action_type=ExperienceMemoryAction,
                observation_type=ExperienceMemoryObservation,
                executor=ExperienceMemoryExecutor(storage_path=storage_path),
                annotations=ToolAnnotations(
                    title="Experience Memory Tool (经验记忆工具)",
                    readOnlyHint=False,
                    destructiveHint=False,
                    idempotentHint=True,  # 重复调用不会产生重复数据（经验ID唯一）
                    openWorldHint=True,
                ),
            )
        ]