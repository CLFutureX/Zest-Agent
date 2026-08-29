"""
存储层抽象接口
- 运行时数据：会话 / 任务 / AgentServer / 用户
- 资源数据：UserLlmConfig / SkillProfile / PromptConfig / SubAgentConfig

资源数据统一使用 ResourceStorage[T] 泛型基类，子类只需指定 model_cls + collection。
旧 ABC 名（UserLlmConfigStorage 等）保留为 ResourceStorage[Model] 的别名，向后兼容 import。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Generic, List, Optional, Type, TypeVar

from app.core.models import (
    AgentServerInfo,
    AppConversationInfo,
    AuthUser,
    PromptConfig,
    SkillProfile,
    SubAgentConfig,
    TaskInfo,
    UserLlmConfig,
    MemorySettings,
)

T = TypeVar("T")


# ==============================
# 资源数据统一抽象
# ==============================
class ResourceStorage(ABC, Generic[T]):
    """资源 storage 抽象。T 是 pydantic 模型类型。

    子类通过 ``model_cls`` 与 ``collection`` 声明身份，实现统一 CRUD。
    所有方法均以 ``user_id`` 作为多租户隔离维度。
    """

    model_cls: Type[T]
    collection: str
    id_field: str = "id"
    user_field: str = "user_id"

    @abstractmethod
    async def ensure_indexes(self) -> None:
        ...

    @abstractmethod
    async def create(self, item: T) -> bool:
        ...

    @abstractmethod
    async def get(self, item_id: str) -> Optional[T]:
        ...

    @abstractmethod
    async def update(self, item_id: str, updates: dict) -> bool:
        ...

    @abstractmethod
    async def delete(self, item_id: str) -> bool:
        ...

    @abstractmethod
    async def list_by_user(
        self,
        user_id: str,
        filters: Optional[Dict] = None,
    ) -> List[T]:
        ...


# ---- 资源 ABC 别名（向后兼容现有 import）----
UserLlmConfigStorage = ResourceStorage[UserLlmConfig]
SkillProfileStorage = ResourceStorage[SkillProfile]
PromptConfigStorage = ResourceStorage[PromptConfig]
SubAgentConfigStorage = ResourceStorage[SubAgentConfig]
MemorySettingsStorage = ResourceStorage[MemorySettings]


# ==============================
# 运行时数据抽象（保持原有签名）
# ==============================
class AppConversationStorage(ABC):
    """会话存储抽象接口"""

    @abstractmethod
    async def ensure_indexes(self) -> None:
        ...

    @abstractmethod
    async def create_app_conversation(self, conversation: AppConversationInfo) -> bool:
        ...

    @abstractmethod
    async def get_app_conversation(self, id: str) -> Optional[AppConversationInfo]:
        ...

    @abstractmethod
    async def update_app_conversation(self, id: str, updates: dict) -> bool:
        ...

    @abstractmethod
    async def delete_app_conversation(self, session_id: str) -> bool:
        ...

    @abstractmethod
    async def list_app_conversations_by_user(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[AppConversationInfo]:
        ...


class TaskStorage(ABC):
    """任务存储抽象接口"""

    @abstractmethod
    async def ensure_indexes(self) -> None:
        ...

    @abstractmethod
    async def save_task(self, task: TaskInfo) -> bool:
        ...

    @abstractmethod
    async def create_task(self, task: TaskInfo) -> bool:
        ...

    @abstractmethod
    async def get_task(self, task_id: str) -> Optional[TaskInfo]:
        ...

    @abstractmethod
    async def update_task(self, task_id: str, updates: dict) -> bool:
        ...

    @abstractmethod
    async def delete_task(self, task_id: str) -> bool:
        ...

    @abstractmethod
    async def list_tasks_by_user(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[TaskInfo]:
        ...

    @abstractmethod
    async def list_tasks_by_app_conversation(self, session_id: str) -> List[TaskInfo]:
        ...


class AgentServerStorage(ABC):
    """AgentServer 存储抽象接口"""

    @abstractmethod
    async def ensure_indexes(self) -> None:
        ...

    @abstractmethod
    async def register_server(self, server: AgentServerInfo) -> bool:
        ...

    @abstractmethod
    async def deregister_server(self, server_id: str) -> bool:
        ...

    @abstractmethod
    async def get_server(self, server_id: str) -> Optional[AgentServerInfo]:
        ...

    @abstractmethod
    async def update_server(self, server_id: str, updates: dict) -> bool:
        ...

    @abstractmethod
    async def list_healthy_servers(self) -> List[AgentServerInfo]:
        ...

    @abstractmethod
    async def list_all_servers(self) -> List[AgentServerInfo]:
        ...


class UserStorage(ABC):
    """用户存储抽象接口（认证用）"""

    @abstractmethod
    async def ensure_indexes(self) -> None:
        ...

    @abstractmethod
    async def create_user(self, user: AuthUser) -> bool:
        ...

    @abstractmethod
    async def get_user_by_id(self, user_id: str) -> Optional[AuthUser]:
        ...

    @abstractmethod
    async def get_user_by_username(self, username: str) -> Optional[AuthUser]:
        ...

    @abstractmethod
    async def get_user_by_email(self, email: str) -> Optional[AuthUser]:
        ...

    @abstractmethod
    async def update_user(self, user_id: str, updates: dict) -> bool:
        ...