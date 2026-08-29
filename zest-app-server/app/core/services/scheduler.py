"""
调度服务
负责节点选择、任务调度与失败重试
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Optional

from common.models.model import ConfirmationResponseRequest

from app.core.loadbalancer import LoadBalancer
from app.core.models import AgentServerInfo, AppConversationInfo, TaskInfo, TaskStatus
from app.core.registry.base import AgentRegistryServer
from app.core.services.dispatcher import Dispatcher
from app.core.services.task_service import TaskService

logger = logging.getLogger(__name__)


class Scheduler:
    """编排 session 与 task 的调度流程"""

    def __init__(
        self,
        dispatcher: Dispatcher,
        agent_registry: AgentRegistryServer,
        load_balancer: LoadBalancer,
        task_service: TaskService,
        max_dispatch_attempts: int = 3,
    ):
        self.dispatcher = dispatcher
        self.agent_registry = agent_registry
        self.load_balancer = load_balancer
        self.task_service = task_service
        self.max_dispatch_attempts = max_dispatch_attempts

    async def schedule_confirm(
        self,
        conversation: AppConversationInfo,
        request: ConfirmationResponseRequest,
    ):
        old_task = await self.task_service.get_latest_task_by_conversation(conversation.id)
        if not old_task:
            raise ValueError("no existing scheduled task")
        agent_server_info = await self.agent_registry.get_server(old_task.agent_server_id) if old_task.agent_server_id else None
        if not agent_server_info:
            raise ValueError("no existing healthy agent server")
        await self.dispatcher.confirm_app_conversation(conversation.id, agent_server_info, request)

    async def schedule(self, conversation: AppConversationInfo) -> TaskInfo:
        old_task = await self.task_service.get_latest_task_by_conversation(conversation.id)
        priority_id = old_task.agent_server_id if old_task else None
        task = await self.task_service.create_task(conversation=conversation)

        excluded_servers: list[str] = []

        for attempt in range(1, self.max_dispatch_attempts + 1):
            agent_server = await self._select_agent_server(excluded_servers, priority_id)
            if not agent_server:
                task.status = TaskStatus.FAILED
                task.error_message = "no available agent server"
                
                task.updated_at = datetime.utcnow()
                break

            task.status = TaskStatus.DISPATCHING
            task.agent_server_id = agent_server.server_id
            task.dispatch_attempt = attempt
            task.updated_at = datetime.utcnow()
            await self.task_service.update_task(task)

            if old_task:
                access_info = await self.dispatcher.resume_app_conversation(conversation.id, agent_server)
            else:
                access_info = await self.dispatcher.create_app_conversation(conversation, agent_server)

            if not access_info or access_info.error_message is not None:
                task.status = TaskStatus.FAILED
                task.error_message = access_info.error_message if access_info else "dispatch failed"
              
                excluded_servers.append(agent_server.server_id)
                priority_id = None
                continue

            task.status = TaskStatus.RUNNING
            task.remote_conversation_id = access_info.conversation_id
            task.events_url = access_info.events_url
            task.websocket_url = access_info.websocket_url
            task.base_url = access_info.base_url
            task.session_api_key = access_info.session_api_key
            task.updated_at = datetime.utcnow()
            break

        await self.task_service.update_task(task)
        return task

    async def _select_agent_server(
        self,
        excluded_servers: list[str],
        priority_id: Optional[str] = None,
    ) -> Optional[AgentServerInfo]:
        healthy_servers = await self.agent_registry.get_healthy_servers() if self.agent_registry else []
        healthy_servers = [s for s in healthy_servers if s.server_id not in excluded_servers]
        if not healthy_servers:
            if excluded_servers:
                return None
            logger.error("_select_agent_server: no healthy servers")
            return None

        if priority_id:
            for server in healthy_servers:
                if server.server_id == priority_id:
                    return server

        if self.load_balancer:
            selected_server = await self.load_balancer.select_for_new_session(healthy_servers)
            if selected_server:
                return selected_server

        return healthy_servers[0]
