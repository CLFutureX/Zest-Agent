"""
Agent Config Service
- 装配 AgentConfigPayload（提供给 zest-service 创建会话时使用）
- 资源解析使用统一 ResourceStorage[T] 接口（get / list_by_user）
"""
from __future__ import annotations

import os

from app.core.models import AgentConfigPayload, LLMConfig, SkillDefinitionPayload
from app.core.storage.base import (
    PromptConfigStorage,
    SkillProfileStorage,
    SubAgentConfigStorage,
    UserLlmConfigStorage,
)


class AgentConfigService:
    """Assemble agent config for conversation creation in business layer."""

    def __init__(
        self,
        llm_config_storage: UserLlmConfigStorage,
        skill_storage: SkillProfileStorage,
        prompt_storage: PromptConfigStorage,
        subagent_config_storage: SubAgentConfigStorage,
    ):
        self.llm_config_storage = llm_config_storage
        self.skill_storage = skill_storage
        self.prompt_storage = prompt_storage
        self.subagent_config_storage = subagent_config_storage

    async def build_agent_config(
        self,
        user_id: str,
        model: str | None = None,
        llm_config_id: str | None = None,
        skill_ids: list[str] | None = None,
        prompt_ids: list[str] | None = None,
        selected_tool_names: list[str] | None = None,
    ) -> AgentConfigPayload:
        llm = await self._resolve_llm(user_id=user_id, model=model, llm_config_id=llm_config_id)
        skills = await self._resolve_skills(user_id=user_id, skill_ids=skill_ids or [])
        prompts = await self._resolve_prompts(user_id=user_id, prompt_ids=prompt_ids or [])
        subagent_configs = await self._resolve_subagents(user_id=user_id)
        return AgentConfigPayload(
            llm=llm,
            selected_tool_names=selected_tool_names or [],
            skills=skills,
            prompts=prompts,
            system_prompt_kwargs={"user_id": user_id},
            subagent_configs=subagent_configs,
        )

    async def _resolve_llm(
        self,
        user_id: str,
        model: str | None,
        llm_config_id: str | None,
    ) -> LLMConfig:
        if llm_config_id:
            llm_resource = await self.llm_config_storage.get(llm_config_id)
            if llm_resource is None or llm_resource.user_id != user_id:
                raise ValueError(f"llm config {llm_config_id} not found")
            return LLMConfig(
                usage_id=llm_resource.usage_id,
                model=model or llm_resource.model,
                api_key=llm_resource.api_key,
                base_url=llm_resource.base_url,
            )

        api_key = os.getenv("LLM_API_KEY")
        if not api_key:
            raise RuntimeError("LLM_API_KEY environment variable is not set.")
        return LLMConfig(
            usage_id=os.getenv("LLM_USAGE_ID", "default"),
            model=model or os.getenv("LLM_MODEL", "dashscope/deepseek-v3.2"),
            api_key=api_key,
            base_url=os.getenv("LLM_BASE_URL"),
        )

    async def _resolve_skills(self, user_id: str, skill_ids: list[str]) -> list[SkillDefinitionPayload]:
        if skill_ids:
            source_skills = []
            for skill_id in skill_ids:
                skill = await self.skill_storage.get(skill_id)
                if skill is not None:
                    source_skills.append(skill)
        else:
            source_skills = await self.skill_storage.list_by_user(
                user_id, filters={"enabled": True}
            )

        skills: list[SkillDefinitionPayload] = []
        for skill in source_skills:
            if skill.user_id != user_id or not skill.enabled:
                continue
            skills.append(
                SkillDefinitionPayload(
                    name=skill.name,
                    content=skill.content,
                    description=skill.description,
                    source=skill.source,
                    trigger=skill.trigger,
                )
            )
        return skills

    async def _resolve_prompts(self, user_id: str, prompt_ids: list[str]) -> list[str]:
        if prompt_ids:
            source_prompts = []
            for prompt_id in prompt_ids:
                prompt = await self.prompt_storage.get(prompt_id)
                if prompt is not None:
                    source_prompts.append(prompt)
        else:
            source_prompts = await self.prompt_storage.list_by_user(
                user_id, filters={"enabled": True}
            )

        prompts: list[str] = []
        for prompt in source_prompts:
            if prompt.user_id != user_id or not prompt.enabled:
                continue
            prompts.append(prompt.content)
        return prompts

    async def _resolve_subagents(self, user_id: str) -> list[dict]:
        source_configs = await self.subagent_config_storage.list_by_user(
            user_id, filters={"enabled": True}
        )

        configs: list[dict] = []
        for config in source_configs:
            if config.user_id != user_id or not config.enabled:
                continue
            resolved_config = dict(config.config)
            if config.model:
                resolved_config.setdefault("model", config.model)
            if config.selected_tool_names:
                resolved_config.setdefault("selected_tool_names", config.selected_tool_names)
            if config.description:
                resolved_config.setdefault("description", config.description)
            if config.custom_system_prompt:
                resolved_config.setdefault("custom_system_prompt", config.custom_system_prompt)
            if config.system_prompt_filename:
                resolved_config.setdefault("system_prompt_filename", config.system_prompt_filename)
            resolved_config.setdefault("name", config.name)
            resolved_config.setdefault("id", config.id)
            configs.append(resolved_config)
        return configs
