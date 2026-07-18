from abc import ABC
import os
import sys
from typing import Any, Mapping
import uuid

from pydantic import BaseModel, ConfigDict, Field 

from sdk.context.condenser.base import CondenserBase

from sdk.context.skills.skill import Skill

from sdk.critic.base import CriticBase

from sdk.llm.llm import LLM

from sdk.agent.sub_agent_config import SubAgentSpec

from sdk.secret.secrets import SecretValue

from sdk.tool.builtins import BUILT_IN_TOOLS 

from sdk.tool.spec import Tool


class AgentContextSpec(BaseModel):
    """Defines the initial context for the agent, which can be used to render prompts.

    This is separate from AgentSpec because it may contain runtime information
    that is not known at initialization time, such as available skills or secrets.
    """

    skills: list[Skill] = Field(
        default_factory=list,
        description="List of available skills that can extend the user's input.",
    )
    system_message_suffix: str | None = Field(
        default=None, description="Optional suffix to append to the system prompt."
    )
    user_message_suffix: str | None = Field(
        default=None, description="Optional suffix to append to the user's message."
    )
    load_user_skills: bool = Field(
        default=False,
        description=(
            "Whether to automatically load user skills from ~/.Zest/skills/ "
            "and ~/.Zest/microagents/ (for backward compatibility). "
        ),
    )
    load_public_skills: bool = Field(
        default=False,
        description=(
            "Whether to automatically load skills from the public Zest "
            "skills repository at https://github.com/Zest/skills. "
            "This allows you to get the latest skills without SDK updates."
        ),
    )
    secrets: Mapping[str, SecretValue] | None = Field(
        default=None,
        description=(
            "Dictionary mapping secret keys to values or secret sources. "
            "Secrets are used for authentication and sensitive data handling. "
            "Values can be either strings or SecretSource instances "
            "(str | SecretSource)."
        ),
    )


class AgentSpec(BaseModel):
    
    model_config = ConfigDict(

        frozen=True,

        arbitrary_types_allowed=True,

    )
    id: str | uuid.UUID = Field(default_factory=uuid.uuid4, description="Agent 唯一标识")

    llm: LLM = Field(..., description="LLM configuration for the agent.")

    tools: list[Tool] = Field(default_factory=list, frozen=False)

    mcp_config: dict[str, Any] = Field(default_factory=dict)

    filter_tools_regex: str | None = Field(default=None)

    include_default_tools: list[str] = Field(

        default_factory=lambda: [tool.__name__ for tool in BUILT_IN_TOOLS]

    )

    subagent_spec: list[SubAgentSpec] | None = Field(
        default=None,
        description="SubAgent配置列表，用于支持SubAgent功能",
    )

    agent_context_spec: AgentContextSpec | None = Field(default=None)
 
    custom_system_prompt: str | None = Field(default=None)

    system_prompt_filename: str = Field(default="system_prompt.j2")

    security_policy_filename: str = Field(default="security_policy.j2")

    system_prompt_kwargs: dict[str, object] = Field(default_factory=dict)

    condenser: CondenserBase | None = Field(default=None)

    critic: CriticBase | None = Field(default=None)

    

    

    @property

    def prompt_dir(self) -> str:

        module = sys.modules[self.__class__.__module__]

        module_file = module.__file__

        if module_file is None:

            raise ValueError(f"Module file for {module} is None")

        return os.path.join(os.path.dirname(module_file), "prompts")





# SubAgentConfig.model_rebuild(_types_namespace={"AgentSpec": AgentSpec})

# AgentSpec.model_rebuild()
