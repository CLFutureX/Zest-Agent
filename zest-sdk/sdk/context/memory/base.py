from datetime import datetime

from pydantic import BaseModel, Field
from streamlit import user


class ExecutionTrace(BaseModel):
    tool_name: str = Field(
        description="Name of the tool used (fill in 'None' if no tool is used). "
        "使用的工具名称（未调用工具则填写'None'）。"
    )
    choice_reason: str = Field(
        description="Thinking process for choosing the tool (or not choosing a tool), combining user questions and solution goals, clear and traceable. "
        "选择该工具（或不选择工具）的思考过程，结合用户问题和解决方案目标，清晰可追溯。"
    )
class ExperienceMemory(BaseModel):
    id: str = Field(description="id")
    user_id: str = Field(description="用户id")
    question: str = Field(description="用户问题")
    solution: str = Field(description="解决方案")
    execute_trace: list[ExecutionTrace] = Field(
        default_factory=list, description="执行过程追踪（包含工具调用和思考过程）"
    )
    domain_type: str  | None= Field( default=None,description="适用领域类型")
    feedback_type: str = Field(description="反馈类型")
    created_at: datetime
    updated_at: datetime | None = Field(default=None, description="更新时间")
