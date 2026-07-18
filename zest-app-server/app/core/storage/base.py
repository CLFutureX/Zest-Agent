"""
存储层抽象接口
定义Session、Task、AgentServer及配置资源的最小化存储接口
"""
from abc import ABC, abstractmethod
from typing import List, Optional
from app.core.models import (
    AppConversationInfo,
    TaskInfo,
    AgentServerInfo,
    AuthUser,
    PromptConfig,
    SkillProfile,
    SubAgentConfig,
    UserLlmConfig,
)


class AppConversationStorage(ABC):
    """会话存储抽象接口"""

    @abstractmethod
    async def create_app_conversation(self, conversation: AppConversationInfo) -> bool:
        pass

    @abstractmethod
    async def get_app_conversation(self, id: str) -> Optional[AppConversationInfo]:
        pass

    @abstractmethod
    async def update_app_conversation(self, id: str, updates: dict) -> bool:
        pass

    @abstractmethod
    async def delete_app_conversation(self, session_id: str) -> bool:
        pass

    @abstractmethod
    async def list_app_conversations_by_user(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[AppConversationInfo]:
        pass


class TaskStorage(ABC):
    """任务存储抽象接口"""

    @abstractmethod
    async def save_task(self, task: TaskInfo) -> bool:
        pass

    @abstractmethod
    async def create_task(self, task: TaskInfo) -> bool:
        pass

    @abstractmethod
    async def get_task(self, task_id: str) -> Optional[TaskInfo]:
        pass

    @abstractmethod
    async def update_task(self, task_id: str, updates: dict) -> bool:
        pass

    @abstractmethod
    async def delete_task(self, task_id: str) -> bool:
        pass

    @abstractmethod
    async def list_tasks_by_user(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[TaskInfo]:
        pass

    @abstractmethod
    async def list_tasks_by_app_conversation(self, session_id: str) -> List[TaskInfo]:
        pass


class AgentServerStorage(ABC):
    """AgentServer存储抽象接口"""

    @abstractmethod
    async def register_server(self, server: AgentServerInfo) -> bool:
        pass

    @abstractmethod
    async def deregister_server(self, server_id: str) -> bool:
        pass

    @abstractmethod
    async def get_server(self, server_id: str) -> Optional[AgentServerInfo]:
        pass

    @abstractmethod
    async def update_server(self, server_id: str, updates: dict) -> bool:
        pass

    @abstractmethod
    async def list_healthy_servers(self) -> List[AgentServerInfo]:
        pass

    @abstractmethod
    async def list_all_servers(self) -> List[AgentServerInfo]:
        pass


class UserLlmConfigStorage(ABC):
    """用户 LLM 配置存储接口，仅提供资源读写能力。"""

    @abstractmethod
    async def ensure_indexes(self) -> None:
        pass

    @abstractmethod
    async def create_llm_config(self, config: UserLlmConfig) -> bool:
        pass

    @abstractmethod
    async def get_llm_config(self, config_id: str) -> Optional[UserLlmConfig]:
        pass

    @abstractmethod
    async def list_llm_configs_by_user(self, user_id: str) -> List[UserLlmConfig]:
        pass


class SkillProfileStorage(ABC):
    """技能资源存储接口，仅提供资源读写能力。"""

    @abstractmethod
    async def ensure_indexes(self) -> None:
        pass

    @abstractmethod
    async def create_skill(self, skill: SkillProfile) -> bool:
        pass

    @abstractmethod

    async def get_skill(self, skill_id: str) -> Optional[SkillProfile]:

        pass



    @abstractmethod

    async def update_skill(self, skill_id: str, updates: dict) -> bool:

        pass



    @abstractmethod

    async def list_skills_by_user(self, user_id: str, enabled: Optional[bool] = None) -> List[SkillProfile]:

        pass





class PromptConfigStorage(ABC):

    """提示词资源存储接口，仅提供资源读写能力。"""



    @abstractmethod

    async def ensure_indexes(self) -> None:

        pass



    @abstractmethod

    async def create_prompt(self, prompt: PromptConfig) -> bool:

        pass



    @abstractmethod

    async def get_prompt(self, prompt_id: str) -> Optional[PromptConfig]:

        pass



    @abstractmethod

    async def update_prompt(self, prompt_id: str, updates: dict) -> bool:

        pass



    @abstractmethod

    async def list_prompts_by_user(self, user_id: str, enabled: Optional[bool] = None) -> List[PromptConfig]:

        pass


class SubAgentConfigStorage(ABC):

    """子 Agent 配置资源存储接口，仅提供资源读写能力。"""



    @abstractmethod

    async def ensure_indexes(self) -> None:

        pass



    @abstractmethod

    async def create_subagent_config(self, config: SubAgentConfig) -> bool:

        pass



    @abstractmethod

    async def get_subagent_config(self, config_id: str) -> Optional[SubAgentConfig]:

        pass



    @abstractmethod

    async def update_subagent_config(self, config_id: str, updates: dict) -> bool:

        pass



    @abstractmethod

    async def list_subagent_configs_by_user(

        self,

        user_id: str,

        enabled: Optional[bool] = None,

    ) -> List[SubAgentConfig]:

        pass


class UserStorage(ABC):
    """用户存储抽象接口（认证用）"""

    @abstractmethod
    async def ensure_indexes(self) -> None:
        pass

    @abstractmethod
    async def create_user(self, user: AuthUser) -> bool:
        pass

    @abstractmethod
    async def get_user_by_id(self, user_id: str) -> Optional[AuthUser]:
        pass

    @abstractmethod
    async def get_user_by_username(self, username: str) -> Optional[AuthUser]:
        pass

    @abstractmethod
    async def get_user_by_email(self, email: str) -> Optional[AuthUser]:
        pass

    @abstractmethod
    async def update_user(self, user_id: str, updates: dict) -> bool:
        pass
