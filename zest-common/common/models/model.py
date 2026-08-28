"""Shared models between zest-app-server and zest-service."""
from enum import Enum
from datetime import datetime
from typing import Literal, Optional, List, Dict, Any
from pydantic import BaseModel, Field
from common.models.contant import ZestAgentUUID
 
  
# Simplified conversation create payload aligned with zest-service external API


 




class ConfirmationPolicyPayload(BaseModel):

    mode: str = "never"

    threshold: Optional[str] = None

    confirm_unknown: bool = True

    need_confirm_tools: List[str] = Field(default_factory=list)






class ConversationLLMPayload(BaseModel):

    usage_id: str = "default"

    model: str = "openai/gpt-4o"

    api_key: str = ""

    base_url: str | None = None

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

class ConversationCreatePayload(BaseModel):



    """External API payload with basic conversation input data."""



    llm: ConversationLLMPayload



    workspace: ConversationWorkspacePayload



    initial_message: ConversationMessagePayload | None = None



    conversation_id: ZestAgentUUID | None = Field(



        default=None,



        description=(



            "Optional conversation ID. If not provided, a random UUID will be "



            "generated."



        ),



    )



    max_iterations: int = Field(



        default=500,



        ge=1,



        description="If set, the max number of iterations the agent will run before stopping.",



    )



    stuck_detection: bool = Field(



        default=True,



        description="If true, the conversation will use stuck detection.",



    )



    confirmation_policy: ConfirmationPolicyPayload = Field(



        default=ConfirmationPolicyPayload()



    )

 
class ConfirmationResponseRequest(BaseModel):
    """Payload to accept or reject a pending action."""

    accept: bool
    reason: str = "User rejected the action."
    payload: dict | None = Field(
        default=None,
        description="用户审核回执 payload。memory_review 工具审核通过时携带 {tool_name, selected_id, edited_content}；后端检测到该 payload 后封装为 ObservationEvent 投递给 agent。",
    )