"""
依赖注入
提供FastAPI依赖注入支持
"""
import asyncio
import logging
 
from typing import TYPE_CHECKING, Generator
from redis.asyncio import from_url as redis_from_url

from common.query.conversation_read_facade import ConversationReadFacade
 


from app.config.settings import settings

from app.core.storage.base import (
    AgentServerStorage,
    AppConversationStorage,
    PromptConfigStorage,
    SkillProfileStorage,
    SubAgentConfigStorage,
    TaskStorage,
    UserLlmConfigStorage,
)
from app.core.loadbalancer import LoadBalancer, create_loadbalancer
from app.core.services.task_service import TaskService
from app.core.services.app_conversation_service import AppConversationService
from app.core.services.agent_config_service import AgentConfigService
from app.core.services.agent_profile_service import AgentProfileService
from app.core.services.agent_service import AgentServerService
from app.core.services.conversation_query_service import ConversationQueryService 
from app.core.services.scheduler import Scheduler
from app.core.services.dispatcher import Dispatcher
from app.core.services.auth_session_service import AuthSessionService
from app.core.services.user_service import UserService
from app.core.services.auth_service import AuthService
from app.core.healthcheck import HealthChecker
from app.core.registry.redis_registry import RedisAgentRegistryServer

if TYPE_CHECKING:
    from app.core.registry.base import AgentRegistryServer

logger = logging.getLogger(name=__name__)

# ==============================
# 全局单例实例
# ==============================
_app_conversation_storage = None
_task_storage = None
_agent_server_storage = None
_user_llm_config_storage = None
_skill_profile_storage = None
_prompt_config_storage = None
_subagent_config_storage = None
_load_balancer = None
_conversation_read_facade = None


_user_storage = None
_auth_session_service = None
# 服务注册中心
_registry = None
_health_checker = None
_grpc_receiver = None
_registry_watch_task = None

# ==============================
# 存储实例获取
# ==============================
def get_app_conversation_storage() -> AppConversationStorage:
    """获取会话存储实例"""
    global _app_conversation_storage
    if _app_conversation_storage is None:
        from app.core.storage.local import LocalFileAppConversationStorage
        _app_conversation_storage = LocalFileAppConversationStorage()
    return _app_conversation_storage


def get_task_storage() -> TaskStorage:
    """获取任务存储实例"""
    global _task_storage
    if _task_storage is None:
        from app.core.storage.local import LocalFileTaskStorage
        _task_storage = LocalFileTaskStorage()
    return _task_storage


def get_agent_server_storage() -> AgentServerStorage:
    """获取AgentServer存储实例"""
    global _agent_server_storage
    if _agent_server_storage is None:
        from app.core.storage.local import LocalFileAgentServerStorage
        _agent_server_storage = LocalFileAgentServerStorage()
    return _agent_server_storage


def get_user_llm_config_storage() -> UserLlmConfigStorage:
    global _user_llm_config_storage
    if _user_llm_config_storage is None:
        from app.core.storage.mongo import MongoUserLlmConfigStorage
        _user_llm_config_storage = MongoUserLlmConfigStorage()
    return _user_llm_config_storage


def get_skill_profile_storage() -> SkillProfileStorage:
    global _skill_profile_storage
    if _skill_profile_storage is None:
        from app.core.storage.mongo import MongoSkillProfileStorage
        _skill_profile_storage = MongoSkillProfileStorage()
    return _skill_profile_storage


def get_prompt_config_storage() -> PromptConfigStorage:
    global _prompt_config_storage
    if _prompt_config_storage is None:
        from app.core.storage.mongo import MongoPromptConfigStorage
        _prompt_config_storage = MongoPromptConfigStorage()
    return _prompt_config_storage


def get_subagent_config_storage() -> SubAgentConfigStorage:
    global _subagent_config_storage
    if _subagent_config_storage is None:
        from app.core.storage.mongo import MongoSubAgentConfigStorage
        _subagent_config_storage = MongoSubAgentConfigStorage()
    return _subagent_config_storage


def get_load_balancer() -> LoadBalancer:
    """获取负载均衡器实例"""
    global _load_balancer
    if _load_balancer is None:
        _load_balancer = create_loadbalancer(settings.lb_strategy)
    return _load_balancer

# ==============================
# 服务获取（FastAPI 依赖）
# ==============================
def get_app_conversation_service() -> Generator[AppConversationService, None, None]:
    """获取会话服务（依赖注入）"""
    conversation_storage = get_app_conversation_storage()
    task_service = get_task_service()
    service = AppConversationService(
        conversation_storage=conversation_storage,
        task_service=task_service,
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
    agent_registry = get_registry()
    load_balancer = get_load_balancer()
    dispatcher = get_dispatcher()
    task_service = get_task_service()

    scheduler = Scheduler(
        dispatcher=dispatcher,
        agent_registry=agent_registry,
        load_balancer=load_balancer,
        task_service=task_service,
    )
    yield scheduler


def get_task_service() -> TaskService:
    """获取任务服务（依赖注入）"""
    task_storage = get_task_storage()
    return TaskService(task_storage=task_storage)


def get_agent_profile_service() -> AgentProfileService:
    return AgentProfileService(
        llm_config_storage=get_user_llm_config_storage(),
        skill_storage=get_skill_profile_storage(),
        prompt_storage=get_prompt_config_storage(),
        subagent_config_storage=get_subagent_config_storage(),
    )


def _create_conversation_read_facade() -> ConversationReadFacade:

    from common.query.conversation_read_facade import ConversationReadFacadeImpl
 

    return ConversationReadFacadeImpl( 
    )


def get_conversation_query_service() -> ConversationQueryService:
    return ConversationQueryService(
        read_facade=_create_conversation_read_facade(),
        dispatcher=get_dispatcher(),
        task_service=get_task_service(), 
    )


def get_agent_server_service() -> Generator[AgentServerService, None, None]:
    """获取AgentServer服务（依赖注入）"""
    agent_server_storage = get_agent_server_storage()
    service = AgentServerService(
        agent_server_storage=agent_server_storage,
        heartbeat_timeout=settings.heartbeat_timeout
    )
    yield service


def get_agent_server_service_direct() -> AgentServerService:
    """直接返回 AgentServerService 实例（非 Generator，供非路由场景使用）"""
    agent_server_storage = get_agent_server_storage()
    return AgentServerService(
        agent_server_storage=agent_server_storage,
        heartbeat_timeout=settings.heartbeat_timeout
    )



def get_user_storage():
    """Return the initialized user storage (set by init_storage)."""
    global _user_storage
    if _user_storage is None:
        # Fallback for tests / standalone use
        from app.core.storage.local import InMemoryUserStorage
        _user_storage = InMemoryUserStorage()
    return _user_storage


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
    """启动时预置一个默认用户（仅 local 模式，用于本地开发调试）"""
    if settings.storage_mode != 'local':
        return
    from app.core.services.user_service import UserService
    us = UserService(user_storage=get_user_storage())
    existing = await us.get_user_by_account("admin")
    if existing is None:
        user = await us.create_user(
            username="admin",
            email="admin@zest.local",
            password="admin123",
        )
        if user:
            logger.info(f"Seeded default user: admin / admin123 (id={user.user_id})")

# ==============================
# 初始化与关闭
# ==============================
async def init_storage():
    """初始化存储（应用启动时调用）"""
    global _app_conversation_storage, _task_storage, _agent_server_storage
    global _user_llm_config_storage, _skill_profile_storage, _prompt_config_storage, _subagent_config_storage
    global _load_balancer, _user_storage

    if settings.storage_mode == "mysql":
        from app.core.storage.mysql import (
            init_mysql_pool,
            MysqlAppConversationStorage,
            MysqlTaskStorage,
            MysqlAgentServerStorage
        )
        await init_mysql_pool(settings.mysql_url)

        from app.core.storage.mysql import MysqlUserStorage
        _app_conversation_storage = MysqlAppConversationStorage()
        _task_storage = MysqlTaskStorage()
        _agent_server_storage = MysqlAgentServerStorage()
        _user_storage = MysqlUserStorage()

        await _app_conversation_storage.ensure_indexes()
        await _task_storage.ensure_indexes()
        await _agent_server_storage.ensure_indexes()
        await _user_storage.ensure_indexes()

    else:
        from app.core.storage.local import (
            LocalFileAppConversationStorage,
            LocalFileTaskStorage,
            LocalFileAgentServerStorage
        )
        from app.core.storage.local import InMemoryUserStorage
        _app_conversation_storage = LocalFileAppConversationStorage()
        _task_storage = LocalFileTaskStorage()
        _agent_server_storage = LocalFileAgentServerStorage()
        _user_storage = InMemoryUserStorage()

    _user_llm_config_storage = get_user_llm_config_storage()
    _skill_profile_storage = get_skill_profile_storage()
    _prompt_config_storage = get_prompt_config_storage()
    _subagent_config_storage = get_subagent_config_storage()

    await _user_llm_config_storage.ensure_indexes()
    await _skill_profile_storage.ensure_indexes()
    await _prompt_config_storage.ensure_indexes()
    await _subagent_config_storage.ensure_indexes()

    _load_balancer = create_loadbalancer(settings.lb_strategy)


async def init_registry():
    """初始化服务注册中心（应用启动时调用）"""
    global _registry, _health_checker, _grpc_receiver, _registry_watch_task

    if _registry is None:
        if settings.registry_mode == "local":
            from app.core.registry.local_registry import LocalAgentRegistryServer
            _registry = LocalAgentRegistryServer(
                registry_dir=settings.resolved_registry_dir,
                heartbeat_timeout=settings.heartbeat_timeout,
                watch_interval=settings.registry_watch_interval,
            )
            logger.info("Registry backend: local (dir=%s)", settings.resolved_registry_dir)
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
    global _registry, _health_checker, _registry_watch_task

    if _health_checker:
        await _health_checker.stop()
        _health_checker = None

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


def get_registry() -> "AgentRegistryServer":
    """获取服务注册中心实例"""
    global _registry
    if _registry is None:
        raise RuntimeError("Registry has not been initialized")
    return _registry


def get_health_checker() -> HealthChecker:
    """获取健康检查器实例"""
    global _health_checker
    if _health_checker is None:
        registry = get_registry()
        _health_checker = HealthChecker(
            registry=registry,
            check_interval=settings.health_check_interval,
            heartbeat_timeout=settings.heartbeat_timeout,
        )
    return _health_checker
