"""
Agent Profile Service
- 资源 CRUD：llm_config / skill / prompt / subagent
- 调用 ResourceStorage[T] 统一接口（create/get/update/delete/list_by_user）
- update 时过滤掉 user_id 等不可改字段
"""
from __future__ import annotations

import uuid
from typing import Optional

from app.core.models import (
    CreatePromptConfigRequest,
    CreateSkillProfileRequest,
    CreateSubAgentConfigRequest,
    CreateUserLlmConfigRequest,
    PromptConfig,
    SkillProfile,
    SubAgentConfig,
    UpdatePromptConfigRequest,
    UpdateSkillProfileRequest,
    UpdateSubAgentConfigRequest,
    UserLlmConfig,
)
from app.core.storage.base import (
    PromptConfigStorage,
    SkillProfileStorage,
    SubAgentConfigStorage,
    UserLlmConfigStorage,
)


def _resolve_id(request_id: Optional[str], prefix: str) -> str:
    """为新建资源生成稳定 ID：传入则用之，否则生成 prefix_xxx。"""
    if request_id:
        return request_id
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# 各资源的不可更新字段（属于身份字段，不能在 update 时改）
_IMMUTABLE_FIELDS = {"id", "user_id"}


class AgentProfileService:
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

    # ---------------- llm_config ----------------
    async def create_llm_config(self, request: CreateUserLlmConfigRequest) -> UserLlmConfig:
        resolved_id = _resolve_id(request.id, "llm")
        config = UserLlmConfig(**{**request.model_dump(), "id": resolved_id})
        success = await self.llm_config_storage.create(config)
        if not success:
            raise ValueError(f"llm config {resolved_id} create failed")
        return config

    async def list_llm_configs(self, user_id: str) -> list[UserLlmConfig]:
        return await self.llm_config_storage.list_by_user(user_id)

    async def delete_llm_config(self, config_id: str) -> bool:
        return await self.llm_config_storage.delete(config_id)

    # ---------------- skill ----------------
    async def create_skill(self, request: CreateSkillProfileRequest) -> SkillProfile:
        resolved_id = _resolve_id(request.id, "skill")
        skill = SkillProfile(**{**request.model_dump(), "id": resolved_id})
        success = await self.skill_storage.create(skill)
        if not success:
            raise ValueError(f"skill {resolved_id} create failed")
        return skill

    async def update_skill(self, skill_id: str, request: UpdateSkillProfileRequest) -> SkillProfile:
        existing = await self.skill_storage.get(skill_id)
        if existing is None or existing.user_id != request.user_id:
            raise ValueError(f"skill {skill_id} not found")
        updates = {k: v for k, v in request.model_dump().items() if k not in _IMMUTABLE_FIELDS}
        success = await self.skill_storage.update(skill_id, updates)
        if not success:
            raise ValueError(f"skill {skill_id} update failed")
        updated = await self.skill_storage.get(skill_id)
        if updated is None:
            raise ValueError(f"skill {skill_id} not found")
        return updated

    async def delete_skill(self, skill_id: str) -> bool:
        return await self.skill_storage.delete(skill_id)

    async def list_skills(self, user_id: str, enabled: Optional[bool] = None) -> list[SkillProfile]:
        filters = {"enabled": enabled} if enabled is not None else None
        return await self.skill_storage.list_by_user(user_id, filters=filters)

    # ---------------- prompt ----------------
    async def create_prompt(self, request: CreatePromptConfigRequest) -> PromptConfig:
        resolved_id = _resolve_id(request.id, "prompt")
        prompt = PromptConfig(**{**request.model_dump(), "id": resolved_id})
        success = await self.prompt_storage.create(prompt)
        if not success:
            raise ValueError(f"prompt {resolved_id} create failed")
        return prompt

    async def update_prompt(self, prompt_id: str, request: UpdatePromptConfigRequest) -> PromptConfig:
        existing = await self.prompt_storage.get(prompt_id)
        if existing is None or existing.user_id != request.user_id:
            raise ValueError(f"prompt {prompt_id} not found")
        updates = {k: v for k, v in request.model_dump().items() if k not in _IMMUTABLE_FIELDS}
        success = await self.prompt_storage.update(prompt_id, updates)
        if not success:
            raise ValueError(f"prompt {prompt_id} update failed")
        updated = await self.prompt_storage.get(prompt_id)
        if updated is None:
            raise ValueError(f"prompt {prompt_id} not found")
        return updated

    async def delete_prompt(self, prompt_id: str) -> bool:
        return await self.prompt_storage.delete(prompt_id)

    async def list_prompts(self, user_id: str, enabled: Optional[bool] = None) -> list[PromptConfig]:
        filters = {"enabled": enabled} if enabled is not None else None
        return await self.prompt_storage.list_by_user(user_id, filters=filters)

    # ---------------- subagent ----------------
    async def create_subagent_config(self, request: CreateSubAgentConfigRequest) -> SubAgentConfig:
        resolved_id = _resolve_id(request.id, "subagent")
        config = SubAgentConfig(**{**request.model_dump(), "id": resolved_id})
        success = await self.subagent_config_storage.create(config)
        if not success:
            raise ValueError(f"subagent config {resolved_id} create failed")
        return config

    async def update_subagent_config(self, config_id: str, request: UpdateSubAgentConfigRequest) -> SubAgentConfig:
        existing = await self.subagent_config_storage.get(config_id)
        if existing is None or existing.user_id != request.user_id:
            raise ValueError(f"subagent config {config_id} not found")
        updates = {k: v for k, v in request.model_dump().items() if k not in _IMMUTABLE_FIELDS}
        success = await self.subagent_config_storage.update(config_id, updates)
        if not success:
            raise ValueError(f"subagent config {config_id} update failed")
        updated = await self.subagent_config_storage.get(config_id)
        if updated is None:
            raise ValueError(f"subagent config {config_id} not found")
        return updated

    async def delete_subagent_config(self, config_id: str) -> bool:
        return await self.subagent_config_storage.delete(config_id)

    async def list_subagent_configs(self, user_id: str, enabled: Optional[bool] = None) -> list[SubAgentConfig]:
        filters = {"enabled": enabled} if enabled is not None else None
        return await self.subagent_config_storage.list_by_user(user_id, filters=filters)
