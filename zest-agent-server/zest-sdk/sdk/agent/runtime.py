from __future__ import annotations
from typing import Any
 
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr
from common.storage.memory.base import ExperienceMemory 
import pathlib as _pathlib
PROMPT_DIR = _pathlib.Path(__file__).parent / 'prompts' / 'templates'
from sdk.context.prompts.prompt import render_template
from sdk.context.skills.skill import Skill, to_prompt
from sdk.context.skills.types import SkillKnowledge
from sdk.llm.message import Message, TextContent
from sdk.llm.utils.model_prompt_spec import get_model_prompt_spec
from sdk.memory.memory_manager import MemoryManager, get_memory_manager
from sdk.secret.secrets import SecretSource, SecretValue
from sdk.tool import ToolDefinition
from collections.abc import Mapping
from common.logger import get_logger

logger = get_logger(__name__)

class AgentRuntime(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    _memory_manager: MemoryManager | None = PrivateAttr(default=None)
    system_message: str = Field(default="")
    tools_map: dict[str, ToolDefinition] = Field(default_factory=dict)
    prompt_trace: list[str] = Field(default_factory=list)
    tool_trace: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    built_by: str | None = Field(default=None)
    skills: list[Skill] = Field(default_factory=list)
    secrets: Mapping[str, SecretValue] | None = Field(default=None)
    user_message_suffix: str | None = Field(default=None) 
 
    def copy_with(self, **updates) -> "AgentRuntime":
        # 1. 浅拷贝模型公开字段，禁用递归深拷贝
        copied = self.model_copy(update=updates, deep=False)
        # 2. 手动把私有内存管理器引用赋值给新实例
        copied._memory_manager = self._memory_manager
        # 3. 返回全新运行时实例
        return copied 
     
    def get_secret_infos(self) -> list[dict[str, str]]:
        """Get secret information (name and description) from the secrets field.

        Returns:
            List of dictionaries with 'name' and 'description' keys.
            Returns an empty list if no secrets are configured.
            Description will be None if not available.
        """
        if not self.secrets:
            return []
        secret_infos = []
        for name, secret_value in self.secrets.items():
            description = None
            if isinstance(secret_value, SecretSource):
                description = secret_value.description
            secret_infos.append({"name": name, "description": description})
        return secret_infos

    @property
    def memory_manager(self) -> MemoryManager | None:
        if self._memory_manager is None:
            self._memory_manager = get_memory_manager()
        return self._memory_manager
    
    def get_user_message_suffix(
        self, user_message: Message, skip_skill_names: list[str]
    ) -> tuple[TextContent, list[str]] | None:
        """Augment the user’s message with knowledge recalled from skills.

        This works by:
        - Extracting the text content of the user message
        - Matching skill triggers against the query
        - Returning formatted knowledge and triggered skill names if relevant skills were triggered
        """  # noqa: E501

        user_message_suffix = None
        if self.user_message_suffix and self.user_message_suffix.strip():
            user_message_suffix = self.user_message_suffix.strip()

        query = "\n".join(
            c.text for c in user_message.content if isinstance(c, TextContent)
        ).strip()
        recalled_knowledge: list[SkillKnowledge] = []
        # skip empty queries, but still return user_message_suffix if it exists
        if not query:
            if user_message_suffix:
                return TextContent(text=user_message_suffix), []
            return None
        # Search for skill triggers in the query
        for skill in self.skills:
            if not isinstance(skill, Skill):
                continue
            trigger = skill.match_trigger(query)
            if trigger and skill.name not in skip_skill_names:
                logger.info(
                    "Skill '%s' triggered by keyword '%s'",
                    skill.name,
                    trigger,
                )
                recalled_knowledge.append(
                    SkillKnowledge(
                        name=skill.name,
                        trigger=trigger,
                        content=skill.content,
                        location=skill.source,
                    )
                )
        if recalled_knowledge:
            # 基于skill内容，对prompt进行渲染
            formatted_skill_text = render_template(
                prompt_dir=str(PROMPT_DIR),
                template_name="skill_knowledge_info.j2",
                triggered_agents=recalled_knowledge,
            )
            if user_message_suffix:
                formatted_skill_text += "\n" + user_message_suffix
            return TextContent(text=formatted_skill_text), [
                k.name for k in recalled_knowledge
            ]

        if user_message_suffix:
            return TextContent(text=user_message_suffix), []
        return None

    def get_user_memory(
        self,
        user_message: Message, 
        activate_ids: list[str] | None = None,
    ) -> tuple[TextContent, list[str]] | None:
        """基于用户消息，加载分类基础记忆和经验记忆，并进行格式化。"""
        if not self.memory_manager:
            return None
        user_memory: dict[str, Any] | None = self.memory_manager.get_user_memory(
            user_message
        )
        if not user_memory:
            return None

        # 向后兼容：优先使用 base_memory_str（合并后的字符串版本）
        base_memory: str = user_memory.get("base_memory_str") or user_memory.get("base_memory", "")  # type: ignore
        experience_memory: list[ExperienceMemory] = user_memory.get("experience_memory")  # type: ignore
        doc_ids: list[str] = user_memory.get("doc_ids")  # type: ignore
        if activate_ids:
            experience_memory = [
                item
                for item in experience_memory
                if  item.id not in activate_ids
            ]
            doc_ids = [item.id for item in experience_memory]

        formatted_memory_text = render_template(
            prompt_dir=str(PROMPT_DIR),
            template_name="user_memory.j2",
            base_memory=base_memory, 
            experience_memory=experience_memory,
        )
        return TextContent(text=formatted_memory_text), doc_ids

