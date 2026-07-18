from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_agent_profile_service
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
from app.core.services.agent_profile_service import AgentProfileService

router = APIRouter(prefix="/api/v1/agent-config", tags=["agent-config"])


@router.get("/llm-configs", response_model=list[UserLlmConfig])
async def list_llm_configs(
    user_id: str,
    service: AgentProfileService = Depends(get_agent_profile_service),
):
    return await service.list_llm_configs(user_id)


@router.post("/llm-configs", response_model=UserLlmConfig)
async def create_llm_config(
    request: CreateUserLlmConfigRequest,
    service: AgentProfileService = Depends(get_agent_profile_service),
):
    try:
        return await service.create_llm_config(request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/skills", response_model=list[SkillProfile])
async def list_skills(
    user_id: str,
    enabled: bool | None = None,
    service: AgentProfileService = Depends(get_agent_profile_service),
):
    return await service.list_skills(user_id, enabled=enabled)


@router.post("/skills", response_model=SkillProfile)
async def create_skill(
    request: CreateSkillProfileRequest,
    service: AgentProfileService = Depends(get_agent_profile_service),
):
    try:
        return await service.create_skill(request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/skills/{skill_id}", response_model=SkillProfile)
async def update_skill(
    skill_id: str,
    request: UpdateSkillProfileRequest,
    service: AgentProfileService = Depends(get_agent_profile_service),
):
    try:
        return await service.update_skill(skill_id, request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/prompts", response_model=list[PromptConfig])
async def list_prompts(
    user_id: str,
    enabled: bool | None = None,
    service: AgentProfileService = Depends(get_agent_profile_service),
):
    return await service.list_prompts(user_id, enabled=enabled)


@router.post("/prompts", response_model=PromptConfig)
async def create_prompt(
    request: CreatePromptConfigRequest,
    service: AgentProfileService = Depends(get_agent_profile_service),
):
    try:
        return await service.create_prompt(request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/prompts/{prompt_id}", response_model=PromptConfig)
async def update_prompt(
    prompt_id: str,
    request: UpdatePromptConfigRequest,
    service: AgentProfileService = Depends(get_agent_profile_service),
):
    try:
        return await service.update_prompt(prompt_id, request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))




@router.get("/subagent-configs", response_model=list[SubAgentConfig])

async def list_subagent_configs(

    user_id: str,

    enabled: bool | None = None,

    service: AgentProfileService = Depends(get_agent_profile_service),

):

    return await service.list_subagent_configs(user_id, enabled=enabled)


@router.post("/subagent-configs", response_model=SubAgentConfig)
async def create_subagent_config(
    request: CreateSubAgentConfigRequest,
    service: AgentProfileService = Depends(get_agent_profile_service),
):
    try:
        return await service.create_subagent_config(request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/subagent-configs/{config_id}", response_model=SubAgentConfig)
async def update_subagent_config(
    config_id: str,
    request: UpdateSubAgentConfigRequest,
    service: AgentProfileService = Depends(get_agent_profile_service),
):
    try:
        return await service.update_subagent_config(config_id, request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
