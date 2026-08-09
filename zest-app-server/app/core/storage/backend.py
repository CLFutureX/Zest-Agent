"""
StorageBackend 抽象层
- 把"连接管理 / 序列化 / storage 实例化"上提到 backend 层
- 资源 storage 只声明 model_cls + collection，由 backend 工厂统一创建
- 支持运行时/资源分层委托（如 MysqlBackend 内部委托资源数据给 MongoBackend）

backend 实现：
- LocalFileBackend   所有数据都用本地 JSON 文件
- MongoBackend       所有数据都用 Mongo
- MysqlBackend       运行时数据用 MySQL，资源数据委托给另一个 backend（默认 Mongo）
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Generic, Optional, Type, TypeVar

from app.core.storage.base import (
    AgentServerStorage,
    AppConversationStorage,
    TaskStorage,
    UserStorage,
)
from app.core.storage.serializer import ResourceSerializer
from app.core.storage.local_resource import LocalFileResourceStorage 
from app.core.models import (
    AgentServerInfo,
    AppConversationInfo,
    AuthUser,
    PromptConfig,
    SkillProfile,
    SubAgentConfig,
    TaskInfo,
    UserLlmConfig,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ==============================
# 资源 storage 注册表
# ==============================
_RESOURCE_SPECS = {
    # model_cls, collection 名
    UserLlmConfig: "user_llm_configs",
    SkillProfile: "skill_definitions",
    PromptConfig: "prompt_configs",
    SubAgentConfig: "subagent_configs",
}


class StorageBackend(ABC):
    """存储后端：负责连接管理 + 序列化 + 创建 storage 实例。"""

    @abstractmethod
    async def startup(self) -> None:
        """建连接池 / 建目录 / 预检。"""

    @abstractmethod
    async def shutdown(self) -> None:
        """关闭连接池 / flush 文件。"""

    # ---- 运行时数据 storage 工厂 ----
    @abstractmethod
    def conversation_storage(self) -> AppConversationStorage: ...

    @abstractmethod
    def task_storage(self) -> TaskStorage: ...

    @abstractmethod
    def agent_server_storage(self) -> AgentServerStorage: ...

    @abstractmethod
    def user_storage(self) -> UserStorage: ...

    # ---- 资源 storage 工厂（泛型）----
    @abstractmethod
    def resource_storage(self, model_cls: Type[T], collection: str) -> "LocalFileResourceStorage[T] | MongoResourceStorage[T]": ...

    # 便捷方法：按模型类直接取
    def resource_for(self, model_cls: Type[T]) -> "LocalFileResourceStorage[T] | MongoResourceStorage[T]":
        collection = _RESOURCE_SPECS.get(model_cls)
        if collection is None:
            raise ValueError(f"Unknown resource model: {model_cls}")
        return self.resource_storage(model_cls, collection)


# ==============================
# LocalFile
# ==============================
class LocalFileBackend(StorageBackend):
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self._convseration: Optional[AppConversationStorage] = None
        self._task: Optional[TaskStorage] = None
        self._agent_server: Optional[AgentServerStorage] = None
        self._user: Optional[UserStorage] = None

    async def startup(self) -> None:
        from app.core.storage.local import (
            LocalFileAppConversationStorage,
            LocalFileTaskStorage,
            LocalFileAgentServerStorage,
            LocalFileUserStorage,
        )

        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "conversations").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "tasks").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "servers").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "user_llm_configs").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "skill_definitions").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "prompt_configs").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "subagent_configs").mkdir(parents=True, exist_ok=True)

        self._conversation = LocalFileAppConversationStorage(self.data_dir / "conversations")
        self._task = LocalFileTaskStorage(self.data_dir / "tasks")
        self._agent_server = LocalFileAgentServerStorage(self.data_dir / "servers")
        self._user = LocalFileUserStorage(self.data_dir / "users")
        await self._conversation.ensure_indexes()
        await self._task.ensure_indexes()
        await self._agent_server.ensure_indexes()
        await self._user.ensure_indexes()
        logger.info("LocalFileBackend ready at %s", self.data_dir)

    async def shutdown(self) -> None:
        # 文件存储无需显式关闭
        return

    def conversation_storage(self) -> AppConversationStorage:
        assert self._conversation is not None, "LocalFileBackend not started"
        return self._conversation

    def task_storage(self) -> TaskStorage:
        assert self._task is not None, "LocalFileBackend not started"
        return self._task

    def agent_server_storage(self) -> AgentServerStorage:
        assert self._agent_server is not None, "LocalFileBackend not started"
        return self._agent_server

    def user_storage(self) -> UserStorage:
        assert self._user is not None, "LocalFileBackend not started"
        return self._user

    def resource_storage(self, model_cls, collection):
        return LocalFileResourceStorage(self.data_dir / collection, model_cls)

 
# ==============================
# MySQL（运行时） + 委托（资源）
# ==============================
class MysqlBackend(StorageBackend):
    """运行时数据走 MySQL；资源数据委托给另一个 backend（默认 MongoBackend 或 LocalFileBackend）。"""

    def __init__(self, mysql_url: str, resource_backend: StorageBackend) -> None:
        self.mysql_url = mysql_url
        self._resource_backend = resource_backend
        self._conversation = None
        self._task = None
        self._agent_server = None
        self._user = None

    async def startup(self) -> None:
        from app.core.storage.mysql import (
            init_mysql_pool,
            MysqlAppConversationStorage,
            MysqlTaskStorage,
            MysqlAgentServerStorage,
            MysqlUserStorage,
        )

        await init_mysql_pool(self.mysql_url)
        self._conversation = MysqlAppConversationStorage()
        self._task = MysqlTaskStorage()
        self._agent_server = MysqlAgentServerStorage()
        self._user = MysqlUserStorage()
        await self._conversation.ensure_indexes()
        await self._task.ensure_indexes()
        await self._agent_server.ensure_indexes()
        await self._user.ensure_indexes()

        await self._resource_backend.startup()
        logger.info("MysqlBackend ready (resource backend=%s)", type(self._resource_backend).__name__)

    async def shutdown(self) -> None:
        from app.core.storage.mysql import close_mysql_pool

        await close_mysql_pool()
        await self._resource_backend.shutdown()

    def conversation_storage(self) -> AppConversationStorage:
        assert self._conversation is not None, "MysqlBackend not started"
        return self._conversation

    def task_storage(self) -> TaskStorage:
        assert self._task is not None, "MysqlBackend not started"
        return self._task

    def agent_server_storage(self) -> AgentServerStorage:
        assert self._agent_server is not None, "MysqlBackend not started"
        return self._agent_server

    def user_storage(self) -> UserStorage:
        assert self._user is not None, "MysqlBackend not started"
        return self._user

    def resource_storage(self, model_cls, collection):
        return self._resource_backend.resource_storage(model_cls, collection)

    def resource_for(self, model_cls):
        return self._resource_backend.resource_for(model_cls)
