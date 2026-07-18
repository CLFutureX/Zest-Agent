import uuid

from pydantic import BaseModel, ConfigDict, Field

from sdk.llm.llm import LLM
from sdk.tool.spec import Tool


class SubAgentSpec(BaseModel):
    """SubAgent声明规格，仅表达相对主Agent的覆盖项。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: str | uuid.UUID = Field(default_factory=uuid.uuid4, description="Agent 唯一标识")
    name: str = Field(..., description="SubAgent唯一标识")
    description: str = Field(..., description="SubAgent功能描述")
    llm: LLM | None = Field(default=None, description="可选LLM覆盖；为空则继承主Agent")
    tools: list[Tool] | None = Field(
        default=None,
        description="可选tools覆盖；None表示继承主Agent，空列表表示显式无工具",
    )
    custom_system_prompt: str | None = Field(default=None)
    system_prompt_filename: str | None = Field(default=None)
    security_policy_filename: str | None = Field(default=None)
    system_prompt_kwargs: dict[str, object] | None = Field(default=None)

