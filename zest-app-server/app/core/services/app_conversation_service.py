"""
会话服务
处理会话相关的业务逻辑
"""
from __future__ import annotations

import logging
import uuid
from typing import List, Optional

from app.core.models import (
    AppConversationInfo,
    ConversationResponse,
    ConversationRuntimeSnapshot,
    CreateConversationRequest,
    SnapshotRuntime,
    SnapshotSummary,
    TaskInfo,
)
from app.core.storage.base import AppConversationStorage
from app.core.services.task_service import TaskService

logger = logging.getLogger(__name__)


class AppConversationService:
    """会话服务"""

    def __init__(self, conversation_storage: AppConversationStorage, task_service: TaskService):
        self.conversation_storage = conversation_storage
        self.task_service = task_service

    async def create_app_conversation(self, request: CreateConversationRequest) -> AppConversationInfo:
        """创建新会话，仅保存初始信息，不承担调度职责。"""
        id = f"conv_{uuid.uuid4().hex[:12]}"
        conversation = AppConversationInfo(
            id=id,
            user_id=request.user_id,
            model=request.model,
            llm_config_id=request.llm_config_id,
            skill_ids=request.skill_ids,
            prompt_ids=request.prompt_ids,
            selected_tool_names=request.selected_tool_names,
            initial_message=request.initial_message,
            metadata=request.metadata if request.metadata is not None else {},
        )

        success = await self.conversation_storage.create_app_conversation(conversation)
        if not success:
            raise Exception("Failed to create conversation")

        logger.info("conversation created: %s", id)
        return conversation

    def _compose_response(self, conversation: AppConversationInfo, task: Optional[TaskInfo]) -> ConversationResponse:
        snapshot = ConversationRuntimeSnapshot(
            runtime=SnapshotRuntime(
                status=task.status.value if task and task.status else "created",
                updated_at=task.updated_at.isoformat() if task and task.updated_at else None,
            ),
            summary=SnapshotSummary(
                last_user_message=conversation.initial_message,
            ),
        )
        return ConversationResponse(
            conversation_id=conversation.id,
            agent_id=task.remote_conversation_id if task else None,
            created_at=(
                task.created_at.isoformat() if task and task.created_at
                else conversation.created_at.isoformat()
            ),
            task_id=task.task_id if task else None,
            base_url=task.base_url if task else None,
            session_api_key=task.session_api_key if task else None,
            error_message=task.error_message if task else conversation.error_message,
            snapshot=snapshot,
        )

    async def get_app_conversation(self, id: str) -> Optional[AppConversationInfo]:
        return await self.conversation_storage.get_app_conversation(id)

    async def get_app_compose_conversation(self, id: str) -> Optional[ConversationResponse]:
        """获取会话详情（含最新 task 装配）"""
        conversation = await self.conversation_storage.get_app_conversation(id)
        if not conversation:
            return None
        task = await self.task_service.get_latest_task_by_conversation(id)
        return self._compose_response(conversation, task)

    async def list_user_app_conversations(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ConversationResponse]:
        """获取用户会话列表"""
        conversations = await self.conversation_storage.list_app_conversations_by_user(
            user_id=user_id,
            limit=limit,
            offset=offset,
        )
        result: List[ConversationResponse] = []
        for conversation in conversations:
            task = await self.task_service.get_latest_task_by_conversation(conversation.id)
            result.append(self._compose_response(conversation, task))
        return result

    async def delete_app_conversation(self, session_id: str) -> bool:
        """删除会话"""
        success = await self.conversation_storage.delete_app_conversation(session_id)
        if success:
            logger.info("conversation deleted: %s", session_id)
        return success
