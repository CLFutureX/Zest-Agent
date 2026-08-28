"""
LocalFile 运行时存储实现
- 会话 / 任务 / AgentServer / 用户（本地文件）
- 数据目录由 LocalFileBackend 启动时传入，子目录名固定：conversations / tasks / servers / users
- 序列化统一用 PydanticJsonSerializer，cipher context 与 MySQL 行为一致
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from app.core.models import (
    AgentServerInfo,
    AppConversationInfo,
    AuthUser,
    ServerStatus,
    TaskInfo,
    TaskStatus,
)
from app.core.storage.base import (
    AgentServerStorage,
    AppConversationStorage,
    TaskStorage,
    UserStorage,
)
from app.core.storage.serializer import PydanticJsonSerializer

logger = logging.getLogger(__name__)


# ==============================
# 会话
# ==============================
class LocalFileAppConversationStorage(AppConversationStorage):
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self._serializer = PydanticJsonSerializer()

    def _get_file_path(self, id: str) -> Path:
        safe = str(id).replace("/", "_").replace("\\", "_")
        return self.data_dir / f"{safe}.json"

    async def ensure_indexes(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)

    async def create_app_conversation(self, conversation: AppConversationInfo) -> bool:
        async with self._lock:
            path = self._get_file_path(conversation.id)
            if path.exists():
                return False
            path.write_text(self._serializer.to_store(conversation), encoding="utf-8")
            return True

    async def get_app_conversation(self, id: str) -> Optional[AppConversationInfo]:
        path = self._get_file_path(id)
        if not path.exists():
            return None
        return self._serializer.from_store(path.read_text(encoding="utf-8"), AppConversationInfo)

    async def update_app_conversation(self, id: str, updates: dict) -> bool:
        async with self._lock:
            conversation = await self.get_app_conversation(id)
            if not conversation:
                return False
            for key, value in updates.items():
                if hasattr(conversation, key):
                    setattr(conversation, key, value)
            conversation.updated_at = datetime.utcnow()
            path = self._get_file_path(id)
            path.write_text(self._serializer.to_store(conversation), encoding="utf-8")
            return True

    async def delete_app_conversation(self, session_id: str) -> bool:
        async with self._lock:
            path = self._get_file_path(session_id)
            if not path.exists():
                return False
            path.unlink()
            return True

    async def list_app_conversations_by_user(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[AppConversationInfo]:
        conversations: List[AppConversationInfo] = []
        for path in self.data_dir.glob("*.json"):
            try:
                conv = self._serializer.from_store(path.read_text(encoding="utf-8"), AppConversationInfo)
            except Exception:
                logger.warning("Failed to parse %s", path, exc_info=True)
                continue
            if conv is None or conv.user_id != user_id:
                continue
            conversations.append(conv)
        conversations.sort(key=lambda s: s.created_at, reverse=True)
        return conversations[offset:offset + limit]


# ==============================
# 任务
# ==============================
class LocalFileTaskStorage(TaskStorage):
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self._serializer = PydanticJsonSerializer()

    def _get_file_path(self, task_id: str) -> Path:
        safe = str(task_id).replace("/", "_").replace("\\", "_")
        return self.data_dir / f"{safe}.json"

    async def ensure_indexes(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)

    async def save_task(self, task: TaskInfo) -> bool:
        async with self._lock:
            path = self._get_file_path(task.task_id)
            path.write_text(self._serializer.to_store(task), encoding="utf-8")
            return True

    async def create_task(self, task: TaskInfo) -> bool:
        async with self._lock:
            path = self._get_file_path(task.task_id)
            if path.exists():
                return False
            path.write_text(self._serializer.to_store(task), encoding="utf-8")
            return True

    async def get_task(self, task_id: str) -> Optional[TaskInfo]:
        path = self._get_file_path(task_id)
        if not path.exists():
            return None
        return self._serializer.from_store(path.read_text(encoding="utf-8"), TaskInfo)

    async def update_task(self, task_id: str, updates: dict) -> bool:
        async with self._lock:
            task = await self.get_task(task_id)
            if not task:
                return False
            for key, value in updates.items():
                if hasattr(task, key):
                    setattr(task, key, value)
            task.updated_at = datetime.utcnow()
            path = self._get_file_path(task_id)
            path.write_text(self._serializer.to_store(task), encoding="utf-8")
            return True

    async def delete_task(self, task_id: str) -> bool:
        async with self._lock:
            path = self._get_file_path(task_id)
            if not path.exists():
                return False
            path.unlink()
            return True

    async def list_tasks_by_user(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[TaskInfo]:
        tasks: List[TaskInfo] = []
        for path in self.data_dir.glob("*.json"):
            try:
                task = self._serializer.from_store(path.read_text(encoding="utf-8"), TaskInfo)
            except Exception:
                logger.warning("Failed to parse %s", path, exc_info=True)
                continue
            if task is None or task.user_id != user_id:
                continue
            if status and task.status.value != status:
                continue
            tasks.append(task)
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return tasks[offset:offset + limit]

    async def list_tasks_by_app_conversation(self, session_id: str) -> List[TaskInfo]:
        tasks: List[TaskInfo] = []
        for path in self.data_dir.glob("*.json"):
            try:
                task = self._serializer.from_store(path.read_text(encoding="utf-8"), TaskInfo)
            except Exception:
                logger.warning("Failed to parse %s", path, exc_info=True)
                continue
            if task is None or task.conversation_id != session_id:
                continue
            tasks.append(task)
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return tasks


# ==============================
# AgentServer
# ==============================
class LocalFileAgentServerStorage(AgentServerStorage):
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self._serializer = PydanticJsonSerializer()

    def _get_file_path(self, server_id: str) -> Path:
        safe = str(server_id).replace("/", "_").replace("\\", "_")
        return self.data_dir / f"{safe}.json"

    async def ensure_indexes(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)

    async def register_server(self, server: AgentServerInfo) -> bool:
        async with self._lock:
            path = self._get_file_path(server.server_id)
            path.write_text(self._serializer.to_store(server), encoding="utf-8")
            return True

    async def deregister_server(self, server_id: str) -> bool:
        async with self._lock:
            path = self._get_file_path(server_id)
            if not path.exists():
                return False
            path.unlink()
            return True

    async def get_server(self, server_id: str) -> Optional[AgentServerInfo]:
        path = self._get_file_path(server_id)
        if not path.exists():
            return None
        return self._serializer.from_store(path.read_text(encoding="utf-8"), AgentServerInfo)

    async def update_server(self, server_id: str, updates: dict) -> bool:
        async with self._lock:
            server = await self.get_server(server_id)
            if not server:
                return False
            for key, value in updates.items():
                if hasattr(server, key):
                    setattr(server, key, value)
            server.last_heartbeat = datetime.utcnow()
            path = self._get_file_path(server_id)
            path.write_text(self._serializer.to_store(server), encoding="utf-8")
            return True

    async def list_healthy_servers(self) -> List[AgentServerInfo]:
        servers = await self.list_all_servers()
        return [s for s in servers if s.status == ServerStatus.HEALTHY]

    async def list_all_servers(self) -> List[AgentServerInfo]:
        servers: List[AgentServerInfo] = []
        for path in self.data_dir.glob("*.json"):
            try:
                server = self._serializer.from_store(path.read_text(encoding="utf-8"), AgentServerInfo)
            except Exception:
                logger.warning("Failed to parse %s", path, exc_info=True)
                continue
            if server is not None:
                servers.append(server)
        servers.sort(key=lambda s: s.registered_at)
        return servers


# ==============================
# 用户（本地文件存储；运行时 storage_mode=local 时使用）
# ==============================
class LocalFileUserStorage(UserStorage):
    """本地文件用户存储。

    - 每个用户一个 <user_id>.json 文件，存于 data_dir。
    - get_user_by_username / by_email 通过扫描目录实现，适合单机中小规模用户。
    - 重启不丢失；并发写由单实例 asyncio.Lock 保护。
    - 生产环境或大量用户请切换到 MysqlBackend。
    """

    _ALLOWED_UPDATE_FIELDS = {
        "username", "email", "password_hash", "is_active", "updated_at",
    }

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self._serializer = PydanticJsonSerializer()

    def _get_file_path(self, user_id: str) -> Path:
        safe = str(user_id).replace("/", "_").replace("\\", "_")
        return self.data_dir / f"{safe}.json"

    def _iter_users(self):
        for path in self.data_dir.glob("*.json"):
            try:
                raw = path.read_text(encoding="utf-8")
                user = self._serializer.from_store(raw, AuthUser)
            except Exception:
                logger.warning("Failed to parse %s", path, exc_info=True)
                continue
            if user is not None:
                yield user

    async def ensure_indexes(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)

    async def create_user(self, user: AuthUser) -> bool:
        async with self._lock:
            path = self._get_file_path(user.user_id)
            if path.exists():
                return False
            # 用户名/邮箱唯一性：扫描已有文件
            for existing in self._iter_users():
                if existing.user_id == user.user_id:
                    return False
                if existing.username == user.username:
                    return False
                if user.email and existing.email == user.email:
                    return False
            path.write_text(self._serializer.to_store(user), encoding="utf-8")
            return True

    async def get_user_by_id(self, user_id: str) -> Optional[AuthUser]:
        path = self._get_file_path(user_id)
        if not path.exists():
            return None
        return self._serializer.from_store(path.read_text(encoding="utf-8"), AuthUser)

    async def get_user_by_username(self, username: str) -> Optional[AuthUser]:
        for user in self._iter_users():
            if user.username == username:
                return user
        return None

    async def get_user_by_email(self, email: str) -> Optional[AuthUser]:
        if not email:
            return None
        for user in self._iter_users():
            if user.email == email:
                return user
        return None

    async def update_user(self, user_id: str, updates: dict) -> bool:
        filtered = {k: v for k, v in updates.items() if k in self._ALLOWED_UPDATE_FIELDS}
        if not filtered:
            return False
        async with self._lock:
            path = self._get_file_path(user_id)
            if not path.exists():
                return False
            user = self._serializer.from_store(path.read_text(encoding="utf-8"), AuthUser)
            if user is None:
                return False
            for k, v in filtered.items():
                if hasattr(user, k):
                    setattr(user, k, v)
            path.write_text(self._serializer.to_store(user), encoding="utf-8")
            return True

 
