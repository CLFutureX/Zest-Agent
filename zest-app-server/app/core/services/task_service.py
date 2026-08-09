"""
任务服务
处理任务相关的业务逻辑
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import List, Optional

from app.core.models import AppConversationInfo, TaskInfo, TaskStatus
from app.core.storage.base import TaskStorage

logger = logging.getLogger(__name__)


class TaskService:
    """任务服务"""

    UPDATABLE_FIELDS = {
        "status",
        "dispatch_attempt",
        "remote_conversation_id",
        "updated_at",
        "result",
        "error_message",
        "metadata",
        "agent_server_id",
        "base_url",
        "events_url",
        "websocket_url",
        "session_api_key",
        "conversation_id",
        "user_id",
    }

    def __init__(self, task_storage: TaskStorage):
        self.task_storage = task_storage

    async def create_task(self, conversation: AppConversationInfo) -> TaskInfo:
        task = TaskInfo(
            task_id=str(uuid.uuid4()),
            conversation_id=conversation.id,
            user_id=conversation.user_id,
            status=TaskStatus.PENDING,
            dispatch_attempt=0,
            metadata=conversation.metadata or {},
        )
        await self.task_storage.create_task(task)
        logger.info("Task created: %s for conversation: %s", task.task_id, conversation.id)
        return task

    async def update_task(
        self,
        task_info: Optional[TaskInfo] = None,
        task_id: Optional[str] = None,
        task_updates: Optional[dict] = None,
    ) -> None:
        """更新任务

        如果传了 task_info，则直接基于这个进行更新；
        否则如果传了 task_id 和 task_updates，就按需更新。
        """
        if task_info is not None:
            task_info.updated_at = datetime.utcnow()
            await self.task_storage.update_task(
                task_info.task_id,
                task_info.model_dump(exclude_unset=True),
            )
            logger.info("Task updated via object: %s", task_info.task_id)
        elif task_id and task_updates:
            filtered_updates = {
                k: v for k, v in task_updates.items() if k in self.UPDATABLE_FIELDS
            }
            if filtered_updates:
                filtered_updates["updated_at"] = datetime.utcnow()
                await self.task_storage.update_task(task_id, filtered_updates)
                logger.info("Task updated via dict: %s, fields: %s", task_id, list(filtered_updates.keys()))
        else:
            logger.warning("update_task called without valid arguments")

    async def save_task(self, task: TaskInfo) -> bool:
        return await self.task_storage.save_task(task)

    async def get_task(self, task_id: str) -> Optional[TaskInfo]:
        return await self.task_storage.get_task(task_id)

    async def get_latest_task_by_conversation(self, conversation_id: str) -> Optional[TaskInfo]:
        tasks = await self.task_storage.list_tasks_by_app_conversation(conversation_id)
        return tasks[0] if tasks else None

    async def list_session_tasks(self, conversation_id: str) -> List[TaskInfo]:
        """获取会话关联的任务列表"""
        return await self.task_storage.list_tasks_by_app_conversation(conversation_id)

    async def list_user_tasks(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[TaskInfo]:
        return await self.task_storage.list_tasks_by_user(
            user_id=user_id,
            status=status,
            limit=limit,
            offset=offset,
        )

    async def cancel_task(self, task_id: str) -> bool:
        task = await self.get_task(task_id)
        if not task:
            return False
        success = await self.task_storage.update_task(
            task_id,
            {"status": TaskStatus.CANCELLED, "updated_at": datetime.utcnow()},
        )
        if success:
            logger.info("Task cancelled: %s", task_id)
        return success

    async def delete_task(self, task_id: str) -> bool:
        success = await self.task_storage.delete_task(task_id)
        if success:
            logger.info("Task deleted: %s", task_id)
        return success
