"""
远端分发服务
负责向 agentServer 发起会话与消息请求
"""
import logging
import os
from datetime import datetime

from common.models.model import ConfirmationResponseRequest
import httpx

from app.config.settings import settings
from app.core.models import (
    AppConversationInfo,
    ConfirmationPolicyPayload,
    ConversationCreatePayload,
    ConversationMessagePayload,
    ConversationWorkspacePayload,
    DispatchAccessInfo,
    TaskInfo,
    TaskStatus,
    AgentServerInfo,
)
from app.core.services.agent_config_service import AgentConfigService
from app.core.registry.base import AgentRegistryServer

logger = logging.getLogger(__name__)


class Dispatcher:
    """封装 agentServer 调用细节"""

    def __init__(
        self,
        agent_registry:AgentRegistryServer | None = None,
        request_timeout: int = 60,
        agent_config_service: AgentConfigService | None = None,
    ):
        self.agent_registry = agent_registry
        self.request_timeout = request_timeout
        self.agent_config_service = agent_config_service

    async def create_app_conversation(
        self,
        conversation: AppConversationInfo,
        server: AgentServerInfo,
    ) -> DispatchAccessInfo | None:
        """
        向 agentServer 发起创建会话请求
        dos: 将taskInfo从中移除，使用DispatcherAccessInfo 保证Dispatcher模块的自治性
        """
        host = server.host
        port = server.port
        server_id = server.server_id

        if host == "0.0.0.0":
            host = "127.0.0.1"

        request = await self._build_request(conversation)
        payload = request.model_dump(
            mode="json",
            exclude_none=True,
            context={"expose_secrets": True}
        )
        url = self._build_api_url(host, port, "/conversations")
        headers = self._build_headers()

        try:
            async with httpx.AsyncClient(timeout=self.request_timeout) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                result = resp.json()

            access = self._extract_access(result, server_id)
            return access

        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP dispatch failed for conversation {conversation.id}: "
                f"{e.response.status_code} {e.response.text}"
            )
            return self._fail(f"HTTP {e.response.status_code}: {e.response.text}")

        except httpx.RequestError as e:
            logger.error(f"HTTP dispatch error for conversation {conversation.id}: {e}")
            return self._fail(f"Connection failed: {str(e)}")

        except Exception as e:
            logger.error(f"Unexpected dispatch error for conversation {conversation.id}: {e}")
            return self._fail(str(e))

    async def resume_app_conversation(
        self,
        conversation_id: str,
        server: AgentServerInfo,
    ) -> DispatchAccessInfo | None:
        host = server.host
        port = server.port
        server_id = server.server_id

        if host == "0.0.0.0":
            host = "127.0.0.1"

        url = self._build_api_url(host, port, f"/conversations/{conversation_id}/resume")
        headers = self._build_headers()

        try:
            async with httpx.AsyncClient(timeout=self.request_timeout) as client:
                resp = await client.post(url, headers=headers)
                resp.raise_for_status()
                result = resp.json()

            access = self._extract_access(result, server_id)
            return access

        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP dispatch failed for conversation {conversation_id}: "
                f"{e.response.status_code} {e.response.text}"
            )
            return self._fail(f"HTTP {e.response.status_code}: {e.response.text}")

        except httpx.RequestError as e:
            logger.error(f"HTTP dispatch error for conversation {conversation_id}: {e}")
            return self._fail(f"Connection failed: {str(e)}")

        except Exception as e:
            logger.error(f"Unexpected dispatch error for conversation {conversation_id}: {e}")
            return self._fail(str(e))
     
    async def confirm_app_conversation(self,
        conversation_id: str,
        server: AgentServerInfo,
        request: ConfirmationResponseRequest,):
        payload = request.model_dump(
            mode="json",
            exclude_none=True,
            context={"expose_secrets": True}
        )
        url = self._build_api_url(server.host, server.port, f"/conversations/{conversation_id}/events/respond_to_confirmation")
        headers = self._build_headers()
        try:
            async with httpx.AsyncClient(timeout=self.request_timeout) as client:
                resp = await client.post(url, json = payload, headers=headers)
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"confirm_app_conversation HTTP error {conversation_id}: {e.response.status_code}")
            return None
        except httpx.RequestError as e:
            logger.error(f"confirm_app_conversation request error {conversation_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"confirm_app_conversation unexpected error {conversation_id}: {e}")
            return None
        
    async def get_conversation_state(
        self,
        conversation_id: str,
        agent_server_id: str,
    ) -> dict | None:
        """向 agentServer 查询会话状态视图 (execution_status / todos / task_description / agent_id)"""
        
        server = await self.agent_registry.get_server(agent_server_id) if self.agent_registry else None
        if server is None:
            logger.error(f"get_conversation_state failed: no server found for id {agent_server_id}")
            return None
        host = server.host
        port = server.port
        if host == "0.0.0.0":
            host = "127.0.0.1"
        url = self._build_api_url(host, port, f"/conversations/{conversation_id}/state")
        headers = self._build_headers()
        try:
            async with httpx.AsyncClient(timeout=self.request_timeout) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"get_conversation_state HTTP error {conversation_id}: {e.response.status_code}")
            return None
        except httpx.RequestError as e:
            logger.error(f"get_conversation_state request error {conversation_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"get_conversation_state unexpected error {conversation_id}: {e}")
            return None

    async def send_message(
        self,
        conversation: AppConversationInfo,
        task: TaskInfo,
        message: str,
    ) -> dict:
        """向 agentServer 发送消息"""
        return {
            "status": TaskStatus.RUNNING,
            "agent_server_id":  task.agent_server_id,
            "result": {"message": message},
            "updated_at": datetime.utcnow(),
        }

    async def _build_request(
        self,
        conversation: AppConversationInfo
    ) -> ConversationCreatePayload:
        if self.agent_config_service is None:
            raise RuntimeError("AgentConfigService is required for dispatcher")

        agent_config = await self.agent_config_service.build_agent_config(

            user_id=conversation.user_id,

            model=conversation.model,

            llm_config_id=conversation.llm_config_id,

            skill_ids=conversation.skill_ids,

            prompt_ids=conversation.prompt_ids,

            selected_tool_names=conversation.selected_tool_names,

        )

        workspace_dir = self._get_workspace(conversation)
        initial_message = None
        text = (conversation.initial_message or "").strip()

        if text:
            initial_message = ConversationMessagePayload(
                role="user", text=text, run=True
            )

        # 记忆开关：读取用户持久化配置；conversation.metadata 中的开关可单会话覆盖（优先级最高）
        memory_settings = await self.agent_config_service.resolve_memory_settings(conversation.user_id)
        meta = conversation.metadata or {}
        enable_base_memory = meta.get("enable_base_memory", memory_settings.enable_base_memory)
        enable_experience_memory = meta.get("enable_experience_memory", memory_settings.enable_experience_memory)

        return ConversationCreatePayload(
            user_id=conversation.user_id,
            conversation_id=conversation.id,
            agent_config=agent_config,
            workspace=ConversationWorkspacePayload(working_dir=workspace_dir),
            confirmation_policy=ConfirmationPolicyPayload(),
            initial_message=initial_message,
            enable_base_memory=enable_base_memory,
            enable_experience_memory=enable_experience_memory,
        )

    # task任务： 和下游zest-service中的_build_conversation_access_info冲突了。直接取下游返回的数据
    def _extract_access(
        self,
        result: dict,
        server_id: str,
    ) -> DispatchAccessInfo | None:
        raw = result.get("access")
        if isinstance(raw, dict):
            return DispatchAccessInfo(agent_server_id=server_id, **raw)
        return None

    def _build_api_url(self, host: str, port: int, path: str) -> str:
        base = settings.agent_service_api_prefix.rstrip("/")
        return f"{settings.agent_service_scheme}://{host}:{port}{base}{path}"

    def _build_headers(self) -> dict[str, str]:
        if not settings.agent_service_session_api_key:
            return {}
        return {"X-Session-API-Key": settings.agent_service_session_api_key}

    def _fail(self, error_message: str) -> DispatchAccessInfo:
        return DispatchAccessInfo(error_message=error_message)

    def _get_workspace(self, conversation: AppConversationInfo) -> str:
        workspace = conversation.metadata.get("workspace") or os.getenv(
            "WORK_SPACE", "workspace/project"
        )
        return workspace