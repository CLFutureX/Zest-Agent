"""
LocalFile存储实现
使用本地JSON文件存储数据，适用于单机开发环境
"""
import json
import asyncio
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from app.core.storage.base import AppConversationStorage, TaskStorage, AgentServerStorage, UserStorage
from app.core.models import AppConversationInfo, TaskInfo, AgentServerInfo, ServerStatus, AuthUser


class LocalFileAppConversationStorage(AppConversationStorage):
    """本地文件会话存储"""
    
    def __init__(self, data_dir: str = "./data/conversations"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
    
    def _get_file_path(self, id: str) -> Path:
        """获取会话文件路径"""
        return self.data_dir / f"{id}.json"
    
    async def create_app_conversation(self, conversation: AppConversationInfo) -> bool:
        """创建会话"""
        async with self._lock:
            file_path = self._get_file_path(conversation.id)
            if file_path.exists():
                return False
            file_path.write_text(json.dumps(conversation.dict(), default=str))
            return True
    
    async def get_app_conversation(self, id: str) -> Optional[AppConversationInfo]:
        """获取会话"""
        file_path = self._get_file_path(id)
        if not file_path.exists():
            return None
        data = json.loads(file_path.read_text())
        return AppConversationInfo(**data)
    
    async def update_app_conversation(self, id: str, updates: dict) -> bool:
        """更新会话"""
        async with self._lock:
            conversation = await self.get_app_conversation(id)
            if not conversation:
                return False
            for key, value in updates.items():
                setattr(conversation, key, value)
            conversation.updated_at = datetime.utcnow()
            file_path = self._get_file_path(id)
            file_path.write_text(json.dumps(conversation.dict(), default=str))
            return True
    
    async def delete_app_conversation(self, id: str) -> bool:
        """删除会话"""
        async with self._lock:
            file_path = self._get_file_path(id)
            if not file_path.exists():
                return False
            file_path.unlink()
            return True
    
    async def list_app_conversations_by_user(
        self,
        user_id: str, 
        limit: int = 50,
        offset: int = 0
    ) -> List[AppConversationInfo]:
        """查询用户会话列表"""
        conversations = []
        for file_path in self.data_dir.glob("*.json"):
            data = json.loads(file_path.read_text())
            conversation = AppConversationInfo(**data)
            if conversation.user_id == user_id:
                conversations.append(conversation)
        
        # 按创建时间倒序排序
        conversations.sort(key=lambda s: s.created_at, reverse=True)
        return conversations[offset:offset+limit]


class LocalFileTaskStorage(TaskStorage):
    """本地文件任务存储"""
    
    def __init__(self, data_dir: str = "./data/tasks"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
    
    def _get_file_path(self, task_id: str) -> Path:
        """获取任务文件路径"""
        return self.data_dir / f"{task_id}.json"
    
    async def save_task(self, task: TaskInfo) -> bool:
        async with self._lock:
            file_path = self._get_file_path(task.task_id)
             
            file_path.write_text(json.dumps(task.dict(), default=str))
            return True
             
                
    async def create_task(self, task: TaskInfo) -> bool:
        """创建任务"""
        async with self._lock:
            file_path = self._get_file_path(task.task_id)
            if file_path.exists():
                return False
            file_path.write_text(json.dumps(task.dict(), default=str))
            return True
    
    async def get_task(self, task_id: str) -> Optional[TaskInfo]:
        """获取任务"""
        file_path = self._get_file_path(task_id)
        if not file_path.exists():
            return None
        data = json.loads(file_path.read_text())
        return TaskInfo(**data)
    
    async def update_task(self, task_id: str, updates: dict) -> bool:
        """更新任务"""
        async with self._lock:
            task = await self.get_task(task_id)
            if not task:
                return False
            for key, value in updates.items():
                setattr(task, key, value)
            file_path = self._get_file_path(task_id)
            file_path.write_text(json.dumps(task.dict(), default=str))
            return True
    
    async def delete_task(self, task_id: str) -> bool:
        """删除任务"""
        async with self._lock:
            file_path = self._get_file_path(task_id)
            if not file_path.exists():
                return False
            file_path.unlink()
            return True
    
    async def list_tasks_by_user(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[TaskInfo]:
        """查询用户任务列表"""
        tasks = []
        for file_path in self.data_dir.glob("*.json"):
            data = json.loads(file_path.read_text())
            task = TaskInfo(**data)
            if task.user_id == user_id:
                if not status or task.status.value == status:
                    tasks.append(task)
        
        # 按创建时间倒序排序
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return tasks[offset:offset+limit]
    
    async def list_tasks_by_app_conversation(self, id: str) -> List[TaskInfo]:

        """查询会话任务列表"""

        tasks = []

        for file_path in self.data_dir.glob("*.json"):

            data = json.loads(file_path.read_text())

            task = TaskInfo(**data)

            if task.conversation_id == id:

                tasks.append(task)
        
        # 按创建时间倒序排序
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return tasks


class LocalFileAgentServerStorage(AgentServerStorage):
    """本地文件AgentServer存储"""
    
    def __init__(self, data_dir: str = "./data/servers"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
    
    def _get_file_path(self, server_id: str) -> Path:
        """获取服务文件路径"""
        return self.data_dir / f"{server_id}.json"
    
    async def register_server(self, server: AgentServerInfo) -> bool:
        """注册服务"""
        async with self._lock:
            file_path = self._get_file_path(server.server_id)
            if file_path.exists():
                return False
            file_path.write_text(json.dumps(server.dict(), default=str))
            return True
    
    async def deregister_server(self, server_id: str) -> bool:
        """注销服务"""
        async with self._lock:
            file_path = self._get_file_path(server_id)
            if not file_path.exists():
                return False
            file_path.unlink()
            return True
    
    async def get_server(self, server_id: str) -> Optional[AgentServerInfo]:
        """获取服务"""
        file_path = self._get_file_path(server_id)
        if not file_path.exists():
            return None
        data = json.loads(file_path.read_text())
        return AgentServerInfo(**data)
    
    async def update_server(self, server_id: str, updates: dict) -> bool:
        """更新服务"""
        async with self._lock:
            server = await self.get_server(server_id)
            if not server:
                return False
            for key, value in updates.items():
                setattr(server, key, value)
            server.last_heartbeat = datetime.utcnow()
            file_path = self._get_file_path(server_id)
            file_path.write_text(json.dumps(server.dict(), default=str))
            return True
    
    async def list_healthy_servers(self) -> List[AgentServerInfo]:
        """获取健康服务列表"""
        servers = []
        for file_path in self.data_dir.glob("*.json"):
            data = json.loads(file_path.read_text())
            server = AgentServerInfo(**data)
            if server.status == ServerStatus.HEALTHY:
                servers.append(server)
        
        # 按注册时间排序
        servers.sort(key=lambda s: s.registered_at)
        return servers
    
    async def list_all_servers(self) -> List[AgentServerInfo]:
        """获取所有服务列表"""
        servers = []
        for file_path in self.data_dir.glob("*.json"):
            data = json.loads(file_path.read_text())
            server = AgentServerInfo(**data)
            servers.append(server)
        
        # 按注册时间排序
        servers.sort(key=lambda s: s.registered_at)
        return servers


class InMemoryUserStorage(UserStorage):
    """内存用户存储（第一版，重启丢失；生产换 DB 实现）"""

    def __init__(self):
        self._users_by_id: dict = {}
        self._users_by_username: dict = {}
        self._users_by_email: dict = {}
        self._lock = asyncio.Lock()

    async def ensure_indexes(self) -> None:
        pass

    async def create_user(self, user) -> bool:
        async with self._lock:
            if user.user_id in self._users_by_id:
                return False
            self._users_by_id[user.user_id] = user
            self._users_by_username[user.username] = user
            if user.email:
                self._users_by_email[user.email] = user
        return True

    async def get_user_by_id(self, user_id: str):
        return self._users_by_id.get(user_id)

    async def get_user_by_username(self, username: str):
        return self._users_by_username.get(username)

    async def get_user_by_email(self, email: str):
        return self._users_by_email.get(email)

    async def update_user(self, user_id: str, updates: dict) -> bool:
        user = self._users_by_id.get(user_id)
        if user is None:
            return False
        for k, v in updates.items():
            setattr(user, k, v)
        return True
