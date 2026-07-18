"""任务服务
处理任务相关的业务逻辑
"""
import uuid
import logging
from datetime import datetime
from typing import Optional, List

from app.core.models import AppConversationInfo, TaskInfo, TaskStatus
from app.core.storage.base import TaskStorage


logger = logging.getLogger(__name__)


class TaskService:
    """任务服务"""

    # TaskInfo 中允许更新的字段
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
    }

    def __init__(
        self,
        task_storage: TaskStorage,
    ):
        self.task_storage = task_storage

    async def create_task(
        self,
        conversation: AppConversationInfo,
    ) -> TaskInfo:
        """基于 conversation 创建 task 任务"""
        task = TaskInfo(
            task_id=str(uuid.uuid4()),
            conversation_id=conversation.id,
            user_id=conversation.user_id,
            status=TaskStatus.PENDING,
            dispatch_attempt=0,
            metadata=conversation.metadata or {},
        )
        await self.task_storage.create_task(task)
        logger.info(f"Task created: {task.task_id} for conversation: {conversation.id}")
        return task

    async def update_task(
        self,
        task_info: Optional[TaskInfo] = None,
        task_id: Optional[str] = None,
        task_updates: Optional[dict] = None,
    ):
        """更新任务

        如果传了 task_info，则直接基于这个进行更新；
        否则如果传了 task_id 和 task_updates，就按需更新。
        注意先对 task_updates 的数据进行过滤，避免多了字段导致更新错误。
        """
        if task_info is not None:
            task_info.updated_at = datetime.utcnow()
            await self.task_storage.update_task(
                task_info.task_id,
                task_info.model_dump(exclude_unset=True),
            )
            logger.info(f"Task updated via object: {task_info.task_id}")
        elif task_id and task_updates:
            filtered_updates = {
                k: v for k, v in task_updates.items() if k in self.UPDATABLE_FIELDS
            }
            if filtered_updates:
                filtered_updates["updated_at"] = datetime.utcnow()
                await self.task_storage.update_task(task_id, filtered_updates)
                logger.info(f"Task updated via dict: {task_id}, fields: {list(filtered_updates.keys())}")
        else:
            logger.warning("update_task called without valid arguments")

    async def get_task(self, task_id: str) -> Optional[TaskInfo]:

        """获取任务详情"""

        return await self.task_storage.get_task(task_id)



    async def get_latest_task_by_conversation(self, conversation_id: str) -> Optional[TaskInfo]:

        """获取会话最近一次任务"""

        tasks = await self.task_storage.list_tasks_by_app_conversation(conversation_id)

        return tasks[0] if tasks else None



    async def list_session_tasks(self, id: str) -> List[TaskInfo]:

        """获取会话关联的任务列表"""

        return await self.task_storage.list_tasks_by_app_conversation(id)

    async def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        task = await self.get_task(task_id)
        if not task:
            return False
        success = await self.task_storage.update_task(
            task_id,
            {
                "status": TaskStatus.CANCELLED,
                "completed_at": None
            }
        )
        if success:
            logger.info(f"Task cancelled: {task_id}")
        return success

    async def delete_task(self, task_id: str) -> bool:
        """删除任务"""
        success = await self.task_storage.delete_task(task_id)
        if success:
            logger.info(f"Task deleted: {task_id}")
        return success

    async def list_user_tasks(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[TaskInfo]:
        """获取用户任务列表"""
        return await self.task_storage.list_tasks_by_user(
            user_id=user_id,
            status=status,
            limit=limit,
            offset=offset
        )
 

    async def get_task(self, task_id: str) -> Optional[TaskInfo]:
        """获取任务详情"""
        return await self.task_storage.get_task(task_id)
    
    # async def update_task(
    #     self,
    #     task_id: str,
    #     updates: TaskUpdateRequest
    # ) -> bool:
    #     """
    #     更新任务状态/进度
        
    #     调用方：AgentServer (通过gRPC回调)
    #     """
    #     # 检查任务是否存在
    #     task = await self.get_task(task_id)
    #     if not task:
    #         return False
        
    #     # 构建更新字典
    #     update_dict = {}
        
    #     if updates.status is not None:
    #         update_dict["status"] = updates.status
    #         if updates.status == TaskStatus.COMPLETED:
    #             update_dict["completed_at"] = datetime.utcnow()
    #             update_dict["progress"] = 100.0
    #         elif updates.status == TaskStatus.RUNNING and task.started_at is None:
    #             update_dict["started_at"] = datetime.utcnow()
        
    #     if updates.progress is not None:
    #         update_dict["progress"] = updates.progress
        
    #     if updates.result is not None:
    #         update_dict["result"] = updates.result
        
    #     if updates.error_message is not None:
    #         update_dict["error_message"] = updates.error_message
        
    #     if updates.metadata is not None:
    #         update_dict["metadata"] = updates.metadata
        
    #     # 更新任务
    #     success = await self.task_storage.update_task(task_id, update_dict)
        
    #     if success:
    #         logger.info(f"Task updated: {task_id}, status: {updates.status}")
        
    #     return success
    
    async def list_user_tasks(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[TaskInfo]:
        """获取用户任务列表"""
        return await self.task_storage.list_tasks_by_user(
            user_id=user_id,
            status=status,
            limit=limit,
            offset=offset
        )
    
    async def list_session_tasks(self, session_id: str) -> List[TaskInfo]:
        """获取会话关联的任务列表"""
        return await self.task_storage.list_tasks_by_session(session_id)
    
    async def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        # 检查任务是否存在
        task = await self.get_task(task_id)
        if not task:
            return False
        
        # 更新任务状态
        success = await self.task_storage.update_task(
            task_id,
            {
                "status": TaskStatus.CANCELLED,
                "completed_at": datetime.utcnow()
            }
        )
        
        if success:
            logger.info(f"Task cancelled: {task_id}")
        
        return success
    
    async def delete_task(self, task_id: str) -> bool:
        """删除任务"""
        success = await self.task_storage.delete_task(task_id)
        
        if success:
            logger.info(f"Task deleted: {task_id}")
        
        return success
