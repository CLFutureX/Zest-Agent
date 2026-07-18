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

    async def create_llm_config(self, request: CreateUserLlmConfigRequest) -> UserLlmConfig:
        config = UserLlmConfig(**request.model_dump())
        success = await self.llm_config_storage.create_llm_config(config)
        if not success:
            raise ValueError(f"llm config {request.id} create failed")
        return config

    async def list_llm_configs(self, user_id: str) -> list[UserLlmConfig]:
        return await self.llm_config_storage.list_llm_configs_by_user(user_id)

    async def create_skill(self, request: CreateSkillProfileRequest) -> SkillProfile:

        skill = SkillProfile(**request.model_dump())

        success = await self.skill_storage.create_skill(skill)

        if not success:

            raise ValueError(f"skill {request.id} create failed")

        return skill



    async def update_skill(self, skill_id: str, request: UpdateSkillProfileRequest) -> SkillProfile:

        existing = await self.skill_storage.get_skill(skill_id)

        if existing is None or existing.user_id != request.user_id:

            raise ValueError(f"skill {skill_id} not found")

        updates = request.model_dump()

        success = await self.skill_storage.update_skill(skill_id, updates)

        if not success:

            raise ValueError(f"skill {skill_id} update failed")

        updated = await self.skill_storage.get_skill(skill_id)

        if updated is None:

            raise ValueError(f"skill {skill_id} not found")

        return updated



    async def list_skills(self, user_id: str, enabled: bool | None = None) -> list[SkillProfile]:

        return await self.skill_storage.list_skills_by_user(user_id, enabled=enabled)



    async def create_prompt(self, request: CreatePromptConfigRequest) -> PromptConfig:

        prompt = PromptConfig(**request.model_dump())

        success = await self.prompt_storage.create_prompt(prompt)

        if not success:

            raise ValueError(f"prompt {request.id} create failed")

        return prompt



    async def update_prompt(self, prompt_id: str, request: UpdatePromptConfigRequest) -> PromptConfig:

        existing = await self.prompt_storage.get_prompt(prompt_id)

        if existing is None or existing.user_id != request.user_id:

            raise ValueError(f"prompt {prompt_id} not found")

        updates = request.model_dump()

        success = await self.prompt_storage.update_prompt(prompt_id, updates)

        if not success:

            raise ValueError(f"prompt {prompt_id} update failed")

        updated = await self.prompt_storage.get_prompt(prompt_id)

        if updated is None:

            raise ValueError(f"prompt {prompt_id} not found")

        return updated



    async def list_prompts(self, user_id: str, enabled: bool | None = None) -> list[PromptConfig]:



        return await self.prompt_storage.list_prompts_by_user(user_id, enabled=enabled)



    async def create_subagent_config(self, request: CreateSubAgentConfigRequest) -> SubAgentConfig:

        resolved_id = _resolve_id(request.id, "subagent")
        config = SubAgentConfig(**{**request.model_dump(), "id": resolved_id})

        success = await self.subagent_config_storage.create_subagent_config(config)

        if not success:

            raise ValueError(f"subagent config {request.id} create failed")

        return config



    async def update_subagent_config(self, config_id: str, request: UpdateSubAgentConfigRequest) -> SubAgentConfig:

        existing = await self.subagent_config_storage.get_subagent_config(config_id)

        if existing is None or existing.user_id != request.user_id:

            raise ValueError(f"subagent config {config_id} not found")



        updates = request.model_dump()

        success = await self.subagent_config_storage.update_subagent_config(config_id, updates)

        if not success:

            raise ValueError(f"subagent config {config_id} update failed")



        updated = await self.subagent_config_storage.get_subagent_config(config_id)

        if updated is None:

            raise ValueError(f"subagent config {config_id} not found")

        return updated



    async def list_subagent_configs(self, user_id: str, enabled: bool | None = None) -> list[SubAgentConfig]:

        return await self.subagent_config_storage.list_subagent_configs_by_user(user_id, enabled=enabled)
