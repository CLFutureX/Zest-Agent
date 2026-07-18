"""
任务管理路由
提供任务创建、查询、更新、列表等API
"""
import logging

from common.models.model import ConfirmationResponseRequest
from fastapi import APIRouter, HTTPException, Depends

from app.core.models import ConversationResponse, CreateConversationRequest, TaskInfo
from app.api.dependencies import (
    get_app_conversation_service, 
    get_scheduler,
)
from app.core.services.app_conversation_service import AppConversationService 
from app.core.services.scheduler import Scheduler

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/conversation", tags=["conversation"])


@router.post("/conversations", response_model=ConversationResponse)
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

        logger.info(f"create_conversation resp: {resp.model_dump()}")
        return resp
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"create_conversation error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{id}", response_model=ConversationResponse)
async def get_app_conversation(
    id: str,
    scheduler: Scheduler = Depends(get_scheduler),
    app_conversation_service: AppConversationService = Depends(get_app_conversation_service),
):
    """获取会话详情"""
    conversation_info = await app_conversation_service.get_app_conversation(id)
    if conversation_info is None:
        raise HTTPException(status_code=404, detail=f"conversation {id} not found")
    task: TaskInfo = await scheduler.schedule(conversation_info)
    resp = await app_conversation_service.get_app_compose_conversation(conversation_info.id) 

    if resp is None:
        raise HTTPException(status_code=501, detail=f"conversation {conversation_info.id} resume error")

    return resp


@router.get("/users/{user_id}/conversations")
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
        raise HTTPException(status_code=504, detail=f"conversation {id} not found")

    return {"status": "deleted", "id": id}

@router.post("/{id}/respond_to_confirmation")
async def response_to_confirm(id: str,
    request: ConfirmationResponseRequest,
    scheduler: Scheduler = Depends(get_scheduler),
    app_conversation_service: AppConversationService = Depends(get_app_conversation_service)):
    
    conversation_info = await app_conversation_service.get_app_conversation(id)
    if conversation_info is None:
        raise HTTPException(status_code=404, detail=f"conversation {id} not found")
    task: TaskInfo = await scheduler.schedule_confirm(conversation_info,request)