"""
LocalFile 存储实现
使用本地 JSON 文件存储数据，适用于单机开发环境。

设计约定：
- 一文件一记录：``<data_dir>/<id>.json``
- 写入采用 ``tmp + os.replace`` 原子写，避免扫描读到半截 json
- 列表查询采用全扫 + 内存过滤，规模小可接受
- 含 SecretStr 字段（如 UserLlmConfig.api_key）通过 cipher 上下文加密/解密
"""
import json
import asyncio
import os
import tempfile
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from app.core.storage.base import (
    AppConversationStorage,
    TaskStorage,
    UserStorage,
    UserLlmConfigStorage,
    SkillProfileStorage,
    PromptConfigStorage,
    SubAgentConfigStorage,
)
from app.core.models import (
    AppConversationInfo,
    TaskInfo,
    AgentServerInfo,
    ServerStatus,
    AuthUser,
    UserLlmConfig,
    SkillProfile,
    PromptConfig,
    SubAgentConfig,
)
from app.config.settings import get_cipher


def _write_atomic(path: Path, payload: str) -> None:
    """原子写：先写临时文件再 os.replace，避免读到半截 json。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fp:
            fp.write(payload)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _cipher_ctx() -> dict:
    cipher = get_cipher()
    return {"cipher": cipher} if cipher is not None else {}


class LocalFileAppConversationStorage(AppConversationStorage):
    """本地文件会话存储"""

    def __init__(self, data_dir: str = "./data/conversations"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    def _get_file_path(self, id: str) -> Path:
        return self.data_dir / f"{id}.json"

    async def create_app_conversation(self, conversation: AppConversationInfo) -> bool:
        async with self._lock:
            file_path = self._get_file_path(conversation.id)
            if file_path.exists():
                return False
            payload = json.dumps(conversation.dict(), default=str)
            await asyncio.get_running_loop().run_in_executor(
                None, _write_atomic, file_path, payload
            )
            return True

    async def get_app_conversation(self, id: str) -> Optional[AppConversationInfo]:
        file_path = self._get_file_path(id)
        if not file_path.exists():
            return None
        data = json.loads(file_path.read_text(encoding="utf-8"))
        return AppConversationInfo(**data)

    async def update_app_conversation(self, id: str, updates: dict) -> bool:
        async with self._lock:
            conversation = await self.get_app_conversation(id)
            if not conversation:
                return False
            for key, value in updates.items():
                setattr(conversation, key, value)
            conversation.updated_at = datetime.utcnow()
            file_path = self._get_file_path(id)
            payload = json.dumps(conversation.dict(), default=str)
            await asyncio.get_running_loop().run_in_executor(
                None, _write_atomic, file_path, payload
            )
            return True

    async def delete_app_conversation(self, id: str) -> bool:
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
        conversations = []
        for file_path in self.data_dir.glob("*.json"):
            data = json.loads(file_path.read_text(encoding="utf-8"))
            conversation = AppConversationInfo(**data)
            if conversation.user_id == user_id:
                conversations.append(conversation)
        conversations.sort(key=lambda s: s.created_at, reverse=True)
        return conversations[offset:offset+limit]


class LocalFileTaskStorage(TaskStorage):
    """本地文件任务存储"""

    def __init__(self, data_dir: str = "./data/tasks"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    def _get_file_path(self, task_id: str) -> Path:
        return self.data_dir / f"{task_id}.json"

    async def save_task(self, task: TaskInfo) -> bool:
        async with self._lock:
            file_path = self._get_file_path(task.task_id)
            payload = json.dumps(task.dict(), default=str)
            await asyncio.get_running_loop().run_in_executor(
                None, _write_atomic, file_path, payload
            )
            return True

    async def create_task(self, task: TaskInfo) -> bool:
        async with self._lock:
            file_path = self._get_file_path(task.task_id)
            if file_path.exists():
                return False
            payload = json.dumps(task.dict(), default=str)
            await asyncio.get_running_loop().run_in_executor(
                None, _write_atomic, file_path, payload
            )
            return True

    async def get_task(self, task_id: str) -> Optional[TaskInfo]:
        file_path = self._get_file_path(task_id)
        if not file_path.exists():
            return None
        data = json.loads(file_path.read_text(encoding="utf-8"))
        return TaskInfo(**data)

    async def update_task(self, task_id: str, updates: dict) -> bool:
        async with self._lock:
            task = await self.get_task(task_id)
            if not task:
                return False
            for key, value in updates.items():
                setattr(task, key, value)
            file_path = self._get_file_path(task_id)
            payload = json.dumps(task.dict(), default=str)
            await asyncio.get_running_loop().run_in_executor(
                None, _write_atomic, file_path, payload
            )
            return True

    async def delete_task(self, task_id: str) -> bool:
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
        tasks = []
        for file_path in self.data_dir.glob("*.json"):
            data = json.loads(file_path.read_text(encoding="utf-8"))
            task = TaskInfo(**data)
            if task.user_id == user_id:
                if not status or task.status.value == status:
                    tasks.append(task)
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return tasks[offset:offset+limit]

    async def list_tasks_by_app_conversation(self, id: str) -> List[TaskInfo]:
        tasks = []
        for file_path in self.data_dir.glob("*.json"):
            data = json.loads(file_path.read_text(encoding="utf-8"))
            task = TaskInfo(**data)
            if task.conversation_id == id:
                tasks.append(task)
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return tasks


class LocalFileUserStorage(UserStorage):
    """本地文件用户存储（持久化到 ./data/users/<user_id>.json）。"""

    def __init__(self, data_dir: str = "./data/users"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    def _get_file_path(self, user_id: str) -> Path:
        safe = user_id.replace("/", "_").replace("\\", "_")
        return self.data_dir / f"{safe}.json"

    def _scan_all(self) -> List[AuthUser]:
        users = []
        for file_path in self.data_dir.glob("*.json"):
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                users.append(AuthUser(**data))
            except Exception:
                continue
        return users

    async def ensure_indexes(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)

    async def create_user(self, user: AuthUser) -> bool:
        async with self._lock:
            existing = self._scan_all()
            if any(u.username == user.username for u in existing):
                return False
            if user.email and any(u.email == user.email for u in existing):
                return False
            file_path = self._get_file_path(user.user_id)
            payload = json.dumps(user.dict(), default=str)
            await asyncio.get_running_loop().run_in_executor(
                None, _write_atomic, file_path, payload
            )
            return True

    async def get_user_by_id(self, user_id: str) -> Optional[AuthUser]:
        file_path = self._get_file_path(user_id)
        if not file_path.exists():
            return None
        data = json.loads(file_path.read_text(encoding="utf-8"))
        return AuthUser(**data)

    async def get_user_by_username(self, username: str) -> Optional[AuthUser]:
        for user in self._scan_all():
            if user.username == username:
                return user
        return None

    async def get_user_by_email(self, email: str) -> Optional[AuthUser]:
        for user in self._scan_all():
            if user.email == email:
                return user
        return None

    async def update_user(self, user_id: str, updates: dict) -> bool:
        async with self._lock:
            user = await self.get_user_by_id(user_id)
            if not user:
                return False
            for k, v in updates.items():
                setattr(user, k, v)
            user.updated_at = datetime.utcnow()
            file_path = self._get_file_path(user_id)
            payload = json.dumps(user.dict(), default=str)
            await asyncio.get_running_loop().run_in_executor(
                None, _write_atomic, file_path, payload
            )
            return True


class LocalFileUserLlmConfigStorage(UserLlmConfigStorage):
    """本地文件 LLM 配置存储。api_key 通过 cipher 加密落盘。"""

    def __init__(self, data_dir: str = "./data/user_llm_configs"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    def _get_file_path(self, config_id: str) -> Path:
        safe = config_id.replace("/", "_").replace("\\", "_")
        return self.data_dir / f"{safe}.json"

    async def ensure_indexes(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)

    async def create_llm_config(self, config: UserLlmConfig) -> bool:
        async with self._lock:
            file_path = self._get_file_path(config.id)
            if file_path.exists():
                return False
            payload = json.dumps(
                config.model_dump(context=_cipher_ctx()),
                default=str,
                ensure_ascii=False,
            )
            await asyncio.get_running_loop().run_in_executor(
                None, _write_atomic, file_path, payload
            )
            return True

    async def get_llm_config(self, config_id: str) -> Optional[UserLlmConfig]:
        file_path = self._get_file_path(config_id)
        if not file_path.exists():
            return None
        data = json.loads(file_path.read_text(encoding="utf-8"))
        return UserLlmConfig.model_validate(data, context=_cipher_ctx())

    async def list_llm_configs_by_user(self, user_id: str) -> List[UserLlmConfig]:
        result = []
        for file_path in self.data_dir.glob("*.json"):
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                cfg = UserLlmConfig.model_validate(data, context=_cipher_ctx())
                if cfg.user_id == user_id:
                    result.append(cfg)
            except Exception:
                continue
        return result


class LocalFileSkillProfileStorage(SkillProfileStorage):
    """本地文件技能定义存储。"""

    def __init__(self, data_dir: str = "./data/skill_profiles"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    def _get_file_path(self, skill_id: str) -> Path:
        safe = skill_id.replace("/", "_").replace("\\", "_")
        return self.data_dir / f"{safe}.json"

    async def ensure_indexes(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)

    async def create_skill(self, skill: SkillProfile) -> bool:
        async with self._lock:
            file_path = self._get_file_path(skill.id)
            if file_path.exists():
                return False
            payload = json.dumps(skill.dict(), default=str, ensure_ascii=False)
            await asyncio.get_running_loop().run_in_executor(
                None, _write_atomic, file_path, payload
            )
            return True

    async def get_skill(self, skill_id: str) -> Optional[SkillProfile]:
        file_path = self._get_file_path(skill_id)
        if not file_path.exists():
            return None
        data = json.loads(file_path.read_text(encoding="utf-8"))
        return SkillProfile(**data)

    async def update_skill(self, skill_id: str, updates: dict) -> bool:
        async with self._lock:
            skill = await self.get_skill(skill_id)
            if not skill:
                return False
            for k, v in updates.items():
                setattr(skill, k, v)
            file_path = self._get_file_path(skill_id)
            payload = json.dumps(skill.dict(), default=str, ensure_ascii=False)
            await asyncio.get_running_loop().run_in_executor(
                None, _write_atomic, file_path, payload
            )
            return True

    async def list_skills_by_user(
        self, user_id: str, enabled: Optional[bool] = None
    ) -> List[SkillProfile]:
        result = []
        for file_path in self.data_dir.glob("*.json"):
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                skill = SkillProfile(**data)
                if skill.user_id != user_id:
                    continue
                if enabled is not None and skill.enabled != enabled:
                    continue
                result.append(skill)
            except Exception:
                continue
        return result


class LocalFilePromptConfigStorage(PromptConfigStorage):
    """本地文件提示词配置存储。"""

    def __init__(self, data_dir: str = "./data/prompt_configs"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    def _get_file_path(self, prompt_id: str) -> Path:
        safe = prompt_id.replace("/", "_").replace("\\", "_")
        return self.data_dir / f"{safe}.json"

    async def ensure_indexes(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)

    async def create_prompt(self, prompt: PromptConfig) -> bool:
        async with self._lock:
            file_path = self._get_file_path(prompt.id)
            if file_path.exists():
                return False
            payload = json.dumps(prompt.dict(), default=str, ensure_ascii=False)
            await asyncio.get_running_loop().run_in_executor(
                None, _write_atomic, file_path, payload
            )
            return True

    async def get_prompt(self, prompt_id: str) -> Optional[PromptConfig]:
        file_path = self._get_file_path(prompt_id)
        if not file_path.exists():
            return None
        data = json.loads(file_path.read_text(encoding="utf-8"))
        return PromptConfig(**data)

    async def update_prompt(self, prompt_id: str, updates: dict) -> bool:
        async with self._lock:
            prompt = await self.get_prompt(prompt_id)
            if not prompt:
                return False
            for k, v in updates.items():
                setattr(prompt, k, v)
            file_path = self._get_file_path(prompt_id)
            payload = json.dumps(prompt.dict(), default=str, ensure_ascii=False)
            await asyncio.get_running_loop().run_in_executor(
                None, _write_atomic, file_path, payload
            )
            return True

    async def list_prompts_by_user(
        self, user_id: str, enabled: Optional[bool] = None
    ) -> List[PromptConfig]:
        result = []
        for file_path in self.data_dir.glob("*.json"):
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                prompt = PromptConfig(**data)
                if prompt.user_id != user_id:
                    continue
                if enabled is not None and prompt.enabled != enabled:
                    continue
                result.append(prompt)
            except Exception:
                continue
        return result


class LocalFileSubAgentConfigStorage(SubAgentConfigStorage):
    """本地文件子 Agent 配置存储。"""

    def __init__(self, data_dir: str = "./data/subagent_configs"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    def _get_file_path(self, config_id: str) -> Path:
        safe = config_id.replace("/", "_").replace("\\", "_")
        return self.data_dir / f"{safe}.json"

    async def ensure_indexes(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)

    async def create_subagent_config(self, config: SubAgentConfig) -> bool:
        async with self._lock:
            file_path = self._get_file_path(config.id)
            if file_path.exists():
                return False
            payload = json.dumps(config.dict(), default=str, ensure_ascii=False)
            await asyncio.get_running_loop().run_in_executor(
                None, _write_atomic, file_path, payload
            )
            return True

    async def get_subagent_config(self, config_id: str) -> Optional[SubAgentConfig]:
        file_path = self._get_file_path(config_id)
        if not file_path.exists():
            return None
        data = json.loads(file_path.read_text(encoding="utf-8"))
        return SubAgentConfig(**data)

    async def update_subagent_config(self, config_id: str, updates: dict) -> bool:
        async with self._lock:
            config = await self.get_subagent_config(config_id)
            if not config:
                return False
            for k, v in updates.items():
                setattr(config, k, v)
            file_path = self._get_file_path(config_id)
            payload = json.dumps(config.dict(), default=str, ensure_ascii=False)
            await asyncio.get_running_loop().run_in_executor(
                None, _write_atomic, file_path, payload
            )
            return True

    async def list_subagent_configs_by_user(
        self, user_id: str, enabled: Optional[bool] = None
    ) -> List[SubAgentConfig]:
        result = []
        for file_path in self.data_dir.glob("*.json"):
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                cfg = SubAgentConfig(**data)
                if cfg.user_id != user_id:
                    continue
                if enabled is not None and cfg.enabled != enabled:
                    continue
                result.append(cfg)
            except Exception:
                continue
        return result


class InMemoryUserStorage(UserStorage):
    """内存用户存储（仅供测试使用；生产请用 LocalFileUserStorage 或 MysqlUserStorage）。"""

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
