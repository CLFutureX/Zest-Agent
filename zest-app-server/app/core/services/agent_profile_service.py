"""
Agent Profile Service
- 资源 CRUD：llm_config / skill / prompt / subagent
- 调用 ResourceStorage[T] 统一接口（create/get/update/delete/list_by_user）
- update 时过滤掉 user_id 等不可改字段
"""
from __future__ import annotations

import uuid
from typing import Optional

import hashlib
from app.config.settings import settings
from app.core.services.skill_bundle_validator import (
    SkillBundleValidationError,
    validate_zip_bundle,
)
from app.core.storage.oss_client import OssClient


from app.core.models import (
    CreatePromptConfigRequest,
    CreateSkillBundleRequest,
    CreateSkillProfileRequest,
    CreateSubAgentConfigRequest,
    CreateUserLlmConfigRequest,
    MemorySettings,
    PromptConfig,
    SkillProfile,
    SubAgentConfig,
    UpdateMemorySettingsRequest,
    UpdatePromptConfigRequest,
    UpdateSkillProfileRequest,
    UpdateSubAgentConfigRequest,
    UserLlmConfig,
)
from app.core.storage.base import (
    MemorySettingsStorage,
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
        memory_settings_storage: MemorySettingsStorage,
        oss_client: OssClient,
    ):
        self.llm_config_storage = llm_config_storage
        self.skill_storage = skill_storage
        self.prompt_storage = prompt_storage
        self.subagent_config_storage = subagent_config_storage
        self.memory_settings_storage = memory_settings_storage
        self.oss_client = oss_client
        # 策略参数：从全局 settings 读取（限额/OSS 配置）
        self._bundle_max_size_mb = settings.skill_bundle_max_size_mb
        self._bundle_max_uncompressed_mb = settings.skill_bundle_max_uncompressed_mb
        self._bundle_max_file_count = settings.skill_bundle_max_file_count
        self._skill_max_per_user = settings.skill_max_per_user

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

    # ---------------- memory_settings ----------------
    async def get_or_create_memory_settings(self, user_id: str) -> MemorySettings:
        """获取（或初始化）当前用户的记忆开关配置。每用户一条，幂等。"""
        existing = await self.memory_settings_storage.list_by_user(user_id)
        if existing:
            return existing[0]
        settings = MemorySettings(
            id=_resolve_id(None, "mem"),
            user_id=user_id,
            enable_base_memory=True,
            enable_experience_memory=True,
        )
        success = await self.memory_settings_storage.create(settings)
        if not success:
            raise ValueError(f"memory settings create failed for user {user_id}")
        return settings

    async def update_memory_settings(self, request: UpdateMemorySettingsRequest) -> MemorySettings:
        existing = await self.get_or_create_memory_settings(request.user_id)
        updates = {
            k: v for k, v in request.model_dump().items()
            if k not in _IMMUTABLE_FIELDS
        }
        success = await self.memory_settings_storage.update(existing.id, updates)
        if not success:
            raise ValueError(f"memory settings {existing.id} update failed")
        updated = await self.memory_settings_storage.get(existing.id)
        if updated is None:
            raise ValueError(f"memory settings {existing.id} not found")
        return updated

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

    # ---------------- skill bundle（zip 上传）----------------
    async def create_skill_bundle(
        self,
        user_id: str,
        name: str,
        zip_bytes: bytes,
        description: Optional[str] = None,
        enabled: bool = True,
    ) -> SkillProfile:
        """上传 skill bundle（zip）：校验 → OSS 存储 → 元数据入库。

        策略：限额取 settings；OSS 键为 skill-bundles/<uid>/<sid>/<version>.zip；
        version 取 zip 字节 sha256 前 8 位；source 携带 oss:// 标记供运行时物化。
        """ 
        # 每用户配额
        existing_skills = await self.skill_storage.list_by_user(user_id)
        if len(existing_skills) >= self._skill_max_per_user:
            raise ValueError(f"skill 数量已达上限 {self._skill_max_per_user}")

        # 机制层校验（阈值由本层传入）
        try:
            meta = validate_zip_bundle(
                zip_bytes,
                max_size_mb=self._bundle_max_size_mb,
                max_uncompressed_mb=self._bundle_max_uncompressed_mb,
                max_file_count=self._bundle_max_file_count,
            )
        except SkillBundleValidationError as e:
            raise ValueError(str(e)) from e

        # frontmatter 的 name 优先级最高（保证运行时 skill 名一致）
        skill_name = meta.name or name

        content_hash = hashlib.sha256(zip_bytes).hexdigest()
        version = content_hash[:8]
        skill_id = _resolve_id(None, "skill")
        oss_key = f"skill-bundles/{user_id}/{skill_id}/{version}.zip"

        # 机制层存储（键名策略在本层）
        self.oss_client.put_bytes(oss_key, zip_bytes)

        skill = SkillProfile(
            id=skill_id,
            user_id=user_id,
            name=skill_name,
            content="",
            description=description or meta.description,
            source=f"oss://{oss_key}@{version}#{content_hash}",
            trigger=None,
            enabled=enabled,
            bundle_type="zip",
            oss_key=oss_key,
            content_hash=content_hash,
            version=version,
        )
        success = await self.skill_storage.create(skill)
        if not success:
            # 回滚 OSS 对象，避免悬挂
            try:
                self.oss_client.delete(oss_key)
            except Exception:  # noqa: BLE001 —— 回滚失败仅记录，不影响主错误
                pass
            raise ValueError(f"skill bundle {skill_id} create failed")
        return skill

    async def delete_skill_bundle(self, skill_id: str) -> bool:
        """删除 bundle skill：先删 OSS 对象再删元数据（避免悬挂引用）。"""
        existing = await self.skill_storage.get(skill_id)
        if existing is None:
            return False
        if existing.bundle_type and existing.oss_key:
            if self.oss_client is None:
                raise ValueError("OSS 未配置，无法删除 bundle 的 OSS 对象，请先配置 OSS")
            self.oss_client.delete(existing.oss_key)
        return await self.skill_storage.delete(skill_id)

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
