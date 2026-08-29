from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.api.dependencies import get_agent_profile_service, is_oss_configured
from app.core.models import (
    CreatePromptConfigRequest,
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


@router.get("/memory-settings", response_model=MemorySettings)
async def get_memory_settings(
    user_id: str,
    service: AgentProfileService = Depends(get_agent_profile_service),
):
    """获取（不存在则初始化）当前用户的记忆开关配置。"""
    return await service.get_or_create_memory_settings(user_id)


@router.put("/memory-settings", response_model=MemorySettings)
async def update_memory_settings(
    request: UpdateMemorySettingsRequest,
    service: AgentProfileService = Depends(get_agent_profile_service),
):
    try:
        return await service.update_memory_settings(request)
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


@router.post("/skills/upload", response_model=SkillProfile)
async def upload_skill_bundle(
    file: UploadFile = File(..., description="skill bundle zip"),
    user_id: str = Form(...),
    name: str = Form(...),
    description: str | None = Form(None),
    enabled: bool = Form(True),
    service: AgentProfileService = Depends(get_agent_profile_service),
):
    """上传 skill bundle（zip）：校验后存 OSS，元数据入库。"""
    if not is_oss_configured():
        raise HTTPException(status_code=400, detail="OSS 未配置或未启用，skill bundle 上传功能不可用")
    zip_bytes = await file.read()
    try:
        return await service.create_skill_bundle(
            user_id=user_id,
            name=name,
            zip_bytes=zip_bytes,
            description=description,
            enabled=enabled,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/skills/{skill_id}/bundle", response_model=dict)
async def delete_skill_bundle(
    skill_id: str,
    service: AgentProfileService = Depends(get_agent_profile_service),
):
    if not is_oss_configured():
        raise HTTPException(status_code=400, detail="OSS 未配置或未启用，skill bundle 上传功能不可用")
    """删除 bundle skill（同时删除 OSS 对象与元数据）。"""
    success = await service.delete_skill_bundle(skill_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"skill bundle {skill_id} not found")
    return {"success": True}


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
