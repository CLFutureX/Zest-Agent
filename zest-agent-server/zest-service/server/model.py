"""Shared models between zest-app-server and zest-service."""
from enum import Enum
from datetime import datetime
from typing import Literal, Optional, List, Dict, Any
from pydantic import BaseModel, Field
from server.utils import ZestAgentUUID
 
 
# Simplified conversation create payload aligned with zest-service external API


 




class ConfirmationPolicyPayload(BaseModel):
    mode: str = "never"
    threshold: Optional[str] = None
    confirm_unknown: bool = True
    need_confirm_tools: List[str] = Field(default_factory=list)


class ConversationWorkspacePayload(BaseModel):
    working_dir: str = Field(
        ...,
        description="Working directory for agent operations and tool execution",
    )


class ConversationMessagePayload(BaseModel):
    role: Literal["user", "system", "assistant", "tool"] = "user"
    text: str = Field(..., description="Plain text message content")
    run: bool = Field(
        default=True,
        description="Whether the agent loop should automatically run after message creation",
    )


class ConversationLLMPayload(BaseModel):
    usage_id: str = "default"
    model: str = "openai/gpt-4o"
    api_key: str = ""
    base_url: str | None = None


class SkillDefinitionPayload(BaseModel):
    name: str
    content: str
    description: str | None = None
    source: str | None = None
    trigger: dict | None = None


class AgentConfigPayload(BaseModel):
    llm: ConversationLLMPayload
    selected_tool_names: List[str] = Field(default_factory=list)
    skills: List[SkillDefinitionPayload] = Field(default_factory=list)
    custom_system_prompt: str | None = None
    system_prompt_kwargs: Dict[str, Any] = Field(default_factory=dict)
    subagent_configs: List[Dict[str, Any]] = Field(default_factory=list)


class ConversationCreatePayload(BaseModel):
    """External API payload with agent config fully assembled by app-server."""

    agent_config: AgentConfigPayload
    workspace: ConversationWorkspacePayload
    initial_message: ConversationMessagePayload | None = None
    conversation_id: ZestAgentUUID | None = Field(
        default=None,
        description=(
            "Optional conversation ID. If not provided, a random UUID will be generated."
        ),
    )
    user_id: str| None = None
    max_iterations: int = Field(
        default=500,
        ge=1,
        description="If set, the max number of iterations the agent will run before stopping.",
    )
    stuck_detection: bool = Field(
        default=True,
        description="If true, the conversation will use stuck detection.",
    )
    enable_base_memory: bool = Field(default=True, description="Whether to enable base memory for the conversation.")
    enable_experience_memory: bool = Field(default=True, description="Whether to enable experience memory for the conversation.")
    confirmation_policy: ConfirmationPolicyPayload = Field(default=ConfirmationPolicyPayload())
