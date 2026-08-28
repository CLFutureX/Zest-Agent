"""
依赖注入
- 启动时装配 StorageBackend / AgentRegistryServer / LoadBalancer / HealthChecker
- 运行时通过 storage_registry / get_registry() / get_load_balancer() 取用
- FastAPI 路由用 Depends(get_xxx_service) 拿 service 实例
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Generator

from redis.asyncio import from_url as redis_from_url

from common.query.conversation_read_facade import ConversationReadFacade

from app.config.settings import settings
from app.core.loadbalancer import LoadBalancer, create_loadbalancer
from app.core.models import (
    PromptConfig,
    SkillProfile,
    SubAgentConfig,
    UserLlmConfig,
)
from app.core.registry.redis_registry import RedisAgentRegistryServer
from app.core.storage.backend import LocalFileBackend, MysqlBackend, StorageBackend
from app.core.storage.registry import storage_registry
from app.core.services.agent_config_service import AgentConfigService
from app.core.services.agent_profile_service import AgentProfileService
from app.core.services.agent_service import AgentServerService
from app.core.services.app_conversation_service import AppConversationService
from app.core.services.auth_service import AuthService
from app.core.services.auth_session_service import AuthSessionService
from app.core.services.conversation_query_service import ConversationQueryService
from app.core.services.dispatcher import Dispatcher
from app.core.services.scheduler import Scheduler
from app.core.services.task_service import TaskService
from app.core.services.user_service import UserService

if TYPE_CHECKING:
    from app.core.registry.base import AgentRegistryServer

logger = logging.getLogger(__name__)

# ==============================
# 单例（运行期不变的部分）
# ==============================
_load_balancer: LoadBalancer | None = None
_registry = None
_registry_watch_task: asyncio.Task | None = None
_auth_session_service: AuthSessionService | None = None


# ==============================
# Backend 装配
# ==============================
def _build_backend() -> StorageBackend:
    """根据 settings.storage_mode 装配 StorageBackend。"""
    if settings.storage_mode == "mysql":
        return MysqlBackend(mysql_url=settings.mysql_url)
    return LocalFileBackend(data_dir=Path(settings.local_data_dir))


# ==============================
# 存储实例获取
# ==============================
def get_app_conversation_storage():
    return storage_registry.backend.conversation_storage()


def get_task_storage():
    return storage_registry.backend.task_storage()


def get_agent_server_storage():
    return storage_registry.backend.agent_server_storage()


def get_user_storage():
    return storage_registry.backend.user_storage()


def get_user_llm_config_storage():
    return storage_registry.backend.resource_for(UserLlmConfig)


def get_skill_profile_storage():
    return storage_registry.backend.resource_for(SkillProfile)


def get_prompt_config_storage():
    return storage_registry.backend.resource_for(PromptConfig)


def get_subagent_config_storage():
    return storage_registry.backend.resource_for(SubAgentConfig)


def get_load_balancer() -> LoadBalancer:
    global _load_balancer
    if _load_balancer is None:
        _load_balancer = create_loadbalancer(settings.lb_strategy)
    return _load_balancer


# ==============================
# 服务获取（FastAPI 依赖）
# ==============================
def get_app_conversation_service() -> Generator[AppConversationService, None, None]:
    service = AppConversationService(
        conversation_storage=get_app_conversation_storage(),
        task_service=get_task_service(),
    )
    yield service


def get_agent_config_service() -> AgentConfigService:
    return AgentConfigService(
        llm_config_storage=get_user_llm_config_storage(),
        skill_storage=get_skill_profile_storage(),
        prompt_storage=get_prompt_config_storage(),
        subagent_config_storage=get_subagent_config_storage(),
    )


def get_dispatcher() -> Dispatcher:
    return Dispatcher(
        agent_registry=get_registry(),
        agent_config_service=get_agent_config_service(),
    )


def get_scheduler() -> Generator[Scheduler, None, None]:
    scheduler = Scheduler(
        dispatcher=get_dispatcher(),
        agent_registry=get_registry(),
        load_balancer=get_load_balancer(),
        task_service=get_task_service(),
    )
    yield scheduler


def get_task_service() -> TaskService:
    return TaskService(task_storage=get_task_storage())


def get_agent_profile_service() -> AgentProfileService:
    return AgentProfileService(
        llm_config_storage=get_user_llm_config_storage(),
        skill_storage=get_skill_profile_storage(),
        prompt_storage=get_prompt_config_storage(),
        subagent_config_storage=get_subagent_config_storage(),
    )


def _create_conversation_read_facade() -> ConversationReadFacade:
    from common.query.conversation_read_facade import ConversationReadFacadeImpl
    return ConversationReadFacadeImpl()


def get_conversation_query_service() -> ConversationQueryService:
    return ConversationQueryService(
        read_facade=_create_conversation_read_facade(),
        dispatcher=get_dispatcher(),
        task_service=get_task_service(),
    )


def get_agent_server_service() -> Generator[AgentServerService, None, None]:
    service = AgentServerService(
        agent_server_storage=get_agent_server_storage(),
        heartbeat_timeout=settings.heartbeat_timeout,
    )
    yield service


def get_agent_server_service_direct() -> AgentServerService:
    return AgentServerService(
        agent_server_storage=get_agent_server_storage(),
        heartbeat_timeout=settings.heartbeat_timeout,
    )


def get_user_service() -> UserService:
    return UserService(user_storage=get_user_storage())


def get_auth_session_service() -> AuthSessionService:
    global _auth_session_service
    if _auth_session_service is None:
        _auth_session_service = AuthSessionService()
    return _auth_session_service


def get_auth_service() -> AuthService:
    return AuthService(
        user_service=get_user_service(),
        session_service=get_auth_session_service(),
    )


async def _seed_default_user():
    """启动时预置一个默认用户（仅 local 存储模式，用于本地开发调试）。
    用户数据持久化到 LOCAL_DATA_DIR/users/<user_id>.json，重启不丢失。
    """
    if settings.storage_mode != "local":
        return
    us = get_user_service()
    existing = await us.get_user_by_account("admin")
    if existing is None:
        user = await us.create_user(
            username="admin",
            email="admin@zest.local",
            password="admin123",
        )
        if user:
            logger.info("Seeded default user: admin / admin123 (id=%s)", user.user_id)


# ==============================
# Registry 装配
# ==============================
async def init_storage():
    """初始化存储（应用启动时调用）"""
    backend = _build_backend()
    await backend.startup()
    storage_registry.configure(backend)
    logger.info("Storage initialized: mode=%s", settings.storage_mode)


async def init_registry():
    """初始化服务注册中心（应用启动时调用）"""
    global _registry, _registry_watch_task

    if _registry is None:
        if settings.registry_mode == "local":
            from app.core.registry.local_registry import LocalAgentRegistryServer
            _registry = LocalAgentRegistryServer(
                registry_dir=settings.registry_dir,
                heartbeat_timeout=settings.heartbeat_timeout,
                watch_interval=settings.registry_watch_interval,
            )
            logger.info("Registry backend: local (dir=%s)", settings.registry_dir)
        else:
            redis_client = redis_from_url(settings.redis_url, decode_responses=True)
            _registry = RedisAgentRegistryServer(
                redis_client=redis_client,
                watch_interval=settings.registry_watch_interval,
                key_prefix=settings.registry_key_prefix,
            )
            logger.info("Registry backend: redis (url=%s)", settings.redis_url)
        _registry_watch_task = asyncio.create_task(_registry.watch_loop())


async def close_registry():
    """关闭服务注册中心（应用关闭时调用）"""
    global _registry, _registry_watch_task

    if _registry_watch_task:
        _registry_watch_task.cancel()
        try:
            await _registry_watch_task
        except asyncio.CancelledError:
            pass
        _registry_watch_task = None

    if _registry:
        await _registry.close()
        _registry = None


async def close_storage():
    """关闭存储后端（应用关闭时调用）"""
    if storage_registry.is_configured:
        await storage_registry.backend.shutdown()


def get_registry() -> "AgentRegistryServer":
    if _registry is None:
        raise RuntimeError("Registry has not been initialized")
    return _registry


def get_health_checker():
    """获取 registry 内部健康检查器。

    健康检查已合并到 registry 内部类 HealthChecker，
    这里保留接口便于路由层 Depends 注入。
    """
    return get_registry().health_checker()
