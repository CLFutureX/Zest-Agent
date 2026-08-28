"""
会话查询路由
- 统一前缀 /api/v1/conversations
- 事件 / 记忆 / 状态视图
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from common.query.query_models import ConversationStateView

from app.api.dependencies import get_conversation_query_service
from app.core.services.conversation_query_service import ConversationQueryService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/conversations", tags=["conversation-query"])


@router.get("/{id}/events")
async def get_conversation_events(
    id: str,
    user_id: str,
    cursor: str | None = None,
    limit: int = 20,
    query_service: ConversationQueryService = Depends(get_conversation_query_service),
):
    return query_service.get_events(id, cursor=cursor, limit=limit, user_id=user_id)


@router.get("/{id}/memories/base")
async def get_conversation_base_memories(
    id: str,
    user_id: str,
    query_service: ConversationQueryService = Depends(get_conversation_query_service),
):
    return query_service.get_base_memories(user_id=user_id)


@router.get("/{id}/memories/experience")
async def get_conversation_experience_memories(
    id: str,
    user_id: str,
    query_service: ConversationQueryService = Depends(get_conversation_query_service),
):
    return query_service.get_experience_memories(user_id=user_id)


@router.get("/{id}/state", response_model=ConversationStateView)
async def get_conversation_state(
    id: str,
    query_service: ConversationQueryService = Depends(get_conversation_query_service),
) -> ConversationStateView:
    view = await query_service.get_state_view(id)
    if view is None:
        raise HTTPException(status_code=404, detail="Conversation state not found")
    return view
