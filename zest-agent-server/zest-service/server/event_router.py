"""
Local Event router for Zest SDK.
"""

import logging
from datetime import datetime
from typing import Annotated

from common.models.model import ConfirmationResponseRequest
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)

from server.dependencies import get_event_service
from server.event_service import EventService
from server.models import ( 
    EventPage,
    EventSortOrder,
    SendMessageRequest,
    Success,
)
from sdk import Message
from sdk.event import Event


event_router = APIRouter(
    prefix="/conversations/{conversation_id}/events", tags=["Events"]
)
logger = logging.getLogger(__name__)


# Read methods


def normalize_datetime_to_server_timezone(dt: datetime) -> datetime:
    """
    Normalize datetime to server timezone for consistent comparison.

    If the datetime has timezone info, convert to server native timezone.
    If it's naive (no timezone), assume it's already in server timezone.

    Args:
        dt: Input datetime (may be timezone-aware or naive)

    Returns:
        Datetime in server native timezone (timezone-aware)
    """
    if dt.tzinfo is not None:
        # Timezone-aware: convert to server native timezone
        return dt.astimezone(None)
    else:
        # Naive datetime: assume it's already in server timezone
        return dt


 
@event_router.post("")
async def send_message(
    request: SendMessageRequest,
    event_service: EventService = Depends(get_event_service),
) -> Success:
    """Send a message to a conversation"""
    message = Message(role=request.role, content=request.content)
    await event_service.send_message(message, request.run)
    return Success()


@event_router.post(
    "/respond_to_confirmation", responses={404: {"description": "Item not found"}}
)
async def respond_to_confirmation(
    request: ConfirmationResponseRequest,
    event_service: EventService = Depends(get_event_service),
) -> Success:
    """Accept or reject a pending action in confirmation mode."""
    await event_service.respond_to_confirmation(request)
    return Success()
