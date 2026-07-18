"""Conversation router for Zest SDK."""

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from pydantic import SecretStr

from common.utils.common import ConversationID
from common.query.query_models import ConversationStateView
from server.conversation_service import ConversationService
from server.dependencies import get_conversation_service
from server.model import (
    AgentConfigPayload,
    ConversationCreatePayload,
    ConversationLLMPayload,
    ConversationMessagePayload,
    ConversationWorkspacePayload,
)
from server.models import (
    AskAgentRequest,
    AskAgentResponse,
    ConversationInfo,
    ConversationPage,
    ConversationSortOrder,
    SendMessageRequest,
    SetConfirmationPolicyRequest,
    SetSecurityAnalyzerRequest,
    Success,
    UpdateSecretsRequest,
)
from sdk.conversation.state import ExecutionStatus
from sdk.secret.secret_registry import SecretValue


conversation_router = APIRouter(prefix="/conversations", tags=["Conversations"])


# Examples
START_CONVERSATION_EXAMPLES = [
    ConversationCreatePayload(
        agent_config=AgentConfigPayload(
            llm=ConversationLLMPayload(
                usage_id="your-llm-service",
                model="your-model-provider/your-model-name",
                api_key="your-api-key-here",
            )
        ),
        workspace=ConversationWorkspacePayload(working_dir="workspace/project"),
        initial_message=ConversationMessagePayload(
            role="user", text="Flip a coin!", run=True
        ),
    ).model_dump(exclude_defaults=True, mode="json")
]

 

# @conversation_router.get("/count")
# async def count_conversations(
#     status: Annotated[
#         ExecutionStatus | None,
#         Query(title="Optional filter by conversation execution status"),
#     ] = None,
#     conversation_service: ConversationService = Depends(get_conversation_service),
# ) -> int:
#     """Count conversations matching the given filters"""
#     count = await conversation_service.count_conversations(status)
#     return count


@conversation_router.get(
    "/{conversation_id}/state", responses={404: {"description": "Item not found"}}
)
async def get_conversation_state(
    conversation_id: str,
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> ConversationStateView:
    """Return a lightweight state view (execution_status, todos, task_description, agent_id) for a conversation."""
    view = await conversation_service.get_state_view(conversation_id)
    if view is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return view


@conversation_router.get(
    "/{conversation_id}", responses={404: {"description": "Item not found"}}
)
async def get_conversation(
    conversation_id: str,
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> ConversationInfo:
    """Given an id, get a conversation"""
    conversation = await conversation_service.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return conversation


@conversation_router.get("")
async def batch_get_conversations(
    ids: Annotated[list[str], Query()],
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> list[ConversationInfo | None]:
    """Get a batch of conversations given their ids, returning null for
    any missing item"""
    assert len(ids) < 100
    conversations = await conversation_service.batch_get_conversations(ids)
    return conversations


# Write Methods
@conversation_router.post("")
async def start_conversation(
    request: Annotated[
        ConversationCreatePayload, Body(examples=START_CONVERSATION_EXAMPLES)
    ],
    response: Response,
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> ConversationInfo:
    """Start a conversation in the local environment."""
    internal_request = conversation_service.convert_create_payload(request)
    info, is_new = await conversation_service.start_conversation(internal_request)
    response.status_code = status.HTTP_201_CREATED if is_new else status.HTTP_200_OK
    return info


@conversation_router.post("/{conversation_id}/resume")
async def resume_conversation(
    conversation_id: str,
    response: Response,
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> ConversationInfo:
    info, is_new = await conversation_service.resume_conversation(conversation_id)
    response.status_code = status.HTTP_201_CREATED if is_new else status.HTTP_200_OK
    return info


@conversation_router.post(
    "/{conversation_id}/pause", responses={404: {"description": "Item not found"}}
)
async def pause_conversation(
    conversation_id: str,
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> Success:
    """Pause a conversation, allowing it to be resumed later."""
    paused = await conversation_service.pause_conversation(conversation_id)
    if not paused:
        raise HTTPException(status.HTTP_400_BAD_REQUEST)
    return Success()


@conversation_router.delete(
    "/{conversation_id}", responses={404: {"description": "Item not found"}}
)
async def delete_conversation(
    conversation_id: ConversationID,
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> Success:
    """Permanently delete a conversation."""
    deleted = await conversation_service.delete_conversation(conversation_id)
    if not deleted:
        raise HTTPException(status.HTTP_400_BAD_REQUEST)
    return Success()


@conversation_router.post(
    "/{conversation_id}/run",
    responses={
        404: {"description": "Item not found"},
        409: {"description": "Conversation is already running"},
    },
)
async def run_conversation(
    conversation_id: ConversationID,
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> Success:
    """Start running the conversation in the background."""
    event_service = await conversation_service.get_event_service(conversation_id)
    if event_service is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    try:
        await event_service.run()
    except ValueError as e:
        if str(e) == "conversation_already_running":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Conversation already running. Wait for completion or pause first."
                ),
            )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return Success()


@conversation_router.post(
    "/{conversation_id}/secrets", responses={404: {"description": "Item not found"}}
)
async def update_conversation_secrets(
    conversation_id: ConversationID,
    request: UpdateSecretsRequest,
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> Success:
    """Update secrets for a conversation."""
    event_service = await conversation_service.get_event_service(conversation_id)
    if event_service is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    secrets = cast(dict[str, SecretValue], request.secrets)
    await event_service.update_secrets(secrets)
    return Success()


@conversation_router.post(
    "/{conversation_id}/confirmation_policy",
    responses={404: {"description": "Item not found"}},
)
async def set_conversation_confirmation_policy(
    conversation_id: ConversationID,
    request: SetConfirmationPolicyRequest,
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> Success:
    """Set the confirmation policy for a conversation."""
    event_service = await conversation_service.get_event_service(conversation_id)
    if event_service is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    await event_service.set_confirmation_policy(request.policy)
    return Success()


@conversation_router.post(
    "/{conversation_id}/security_analyzer",
    responses={404: {"description": "Item not found"}},
)
async def set_conversation_security_analyzer(
    conversation_id: ConversationID,
    request: SetSecurityAnalyzerRequest,
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> Success:
    """Set the security analyzer for a conversation."""
    event_service = await conversation_service.get_event_service(conversation_id)
    if event_service is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    await event_service.set_security_analyzer(request.security_analyzer)
    return Success()


@conversation_router.post(
    "/{conversation_id}/ask_agent",
    responses={404: {"description": "Item not found"}},
)
async def ask_agent(
    conversation_id: ConversationID,
    request: AskAgentRequest,
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> AskAgentResponse:
    """Ask the agent a simple question without affecting conversation state."""
    response = await conversation_service.ask_agent(conversation_id, request.question)
    if response is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR)
    return AskAgentResponse(response=response)
 

 

@conversation_router.post(
    "/{conversation_id}/condense",
    responses={404: {"description": "Item not found"}},
)
async def condense_conversation(
    conversation_id: ConversationID,
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> Success:
    """Force condensation of the conversation history."""
    success = await conversation_service.condense(conversation_id)
    if not success:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return Success()
 
