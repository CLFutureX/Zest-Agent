"""
会话路由
- 统一前缀 /api/v1/conversations
- 创建 / 查询 / 删除 / 用户列表 / 确认响应
"""
from __future__ import annotations

import logging

from common.models.model import ConfirmationResponseRequest
from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_app_conversation_service, get_scheduler
from app.core.models import ConversationResponse, CreateConversationRequest, TaskInfo
from app.core.services.app_conversation_service import AppConversationService
from app.core.services.scheduler import Scheduler

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/conversations", tags=["conversation"])


@router.post("", response_model=ConversationResponse)
async def create_conversation(
    request: CreateConversationRequest,
    app_conversation_service: AppConversationService = Depends(get_app_conversation_service),
    scheduler: Scheduler = Depends(get_scheduler),
):
    """统一打开会话入口。"""
    try:
        conversation_info = await app_conversation_service.create_app_conversation(request)
        task: TaskInfo = await scheduler.schedule(conversation_info)
        resp = await app_conversation_service.get_app_compose_conversation(conversation_info.id)
        if resp is None:
            raise HTTPException(status_code=404, detail=f"conversation {conversation_info.id} not found")
        logger.info("create_conversation resp: %s", resp.model_dump())
        return resp
    except HTTPException:
        raise
    except Exception as e:
        logger.error("create_conversation error: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{id}", response_model=ConversationResponse)
async def get_app_conversation(
    id: str,
    scheduler: Scheduler = Depends(get_scheduler),
    app_conversation_service: AppConversationService = Depends(get_app_conversation_service),
):
    """获取会话详情（若无 task 则调度一次）"""
    conversation_info = await app_conversation_service.get_app_conversation(id)
    if conversation_info is None:
        raise HTTPException(status_code=404, detail=f"conversation {id} not found")
    await scheduler.schedule(conversation_info)
    resp = await app_conversation_service.get_app_compose_conversation(conversation_info.id)
    if resp is None:
        raise HTTPException(status_code=501, detail=f"conversation {conversation_info.id} resume error")
    return resp


@router.get("/users/{user_id}")
async def list_user_app_conversations(
    user_id: str,
    limit: int = 50,
    offset: int = 0,
    app_conversation_service: AppConversationService = Depends(get_app_conversation_service),
):
    """获取用户会话列表"""
    conversations = await app_conversation_service.list_user_app_conversations(
        user_id=user_id,
        limit=limit,
        offset=offset,
    )
    return {
        "conversation": conversations,
        "total": len(conversations),
        "limit": limit,
        "offset": offset,
    }


@router.delete("/{id}")
async def delete_app_conversation(
    id: str,
    app_conversation_service: AppConversationService = Depends(get_app_conversation_service),
):
    """删除会话"""
    success = await app_conversation_service.delete_app_conversation(id)
    if not success:
        raise HTTPException(status_code=404, detail=f"conversation {id} not found")
    return {"status": "deleted", "id": id}


@router.post("/{id}/respond_to_confirmation")
async def response_to_confirm(
    id: str,
    request: ConfirmationResponseRequest,
    scheduler: Scheduler = Depends(get_scheduler),
    app_conversation_service: AppConversationService = Depends(get_app_conversation_service),
):
    """对 agent 确认请求给出用户响应"""
    conversation_info = await app_conversation_service.get_app_conversation(id)
    if conversation_info is None:
        raise HTTPException(status_code=404, detail=f"conversation {id} not found")
    await scheduler.schedule_confirm(conversation_info, request)
    return {"status": "ok", "id": id}
