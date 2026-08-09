from pydantic import BaseModel, Field, SecretStr, field_serializer, field_validator
from typing import Literal, Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

from app.core.contant import ZestAgentUUID
from common.utils.pydantic_secrets import serialize_secret, validate_secret


# ==============================
# 认证用户模型
# ==============================
class AuthUser(BaseModel):
    """用于注册/登录的用户信息（存储于 users 表）"""
    user_id: str = Field(..., description="用户唯一 ID（UUID）")
    username: str = Field(..., description="用户名")
    email: str = Field(..., description="邮箱")
    password_hash: str = Field(..., description="bcrypt 密码哈希")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = Field(default=True)




# ==============================
# Auth Session 模型
# ==============================
class AuthSessionRecord(BaseModel):
    """服务端 session 记录（内存 / 可换 Redis / DB）"""
    session_id: str = Field(...)
    user_id: str = Field(...)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime
    ip: Optional[str] = None
    user_agent: Optional[str] = None


class AuthSessionUser(BaseModel):
    id: str
    username: str
    display_name: Optional[str] = None
    email: Optional[str] = None


class AuthSessionResponse(BaseModel):
    authenticated: bool
    user: Optional['AuthSessionUser'] = None


class PasswordLoginRequest(BaseModel):
    account: str
    password: str


class PasswordLoginResponse(BaseModel):
    user: 'AuthSessionUser'


class TaskStatus(str, Enum):
    PENDING = "pending"
    DISPATCHING = "dispatching"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ServerStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class AppConversationInfo(BaseModel):

    id: ZestAgentUUID = Field(..., description="业务侧 session 唯一标识")

    user_id: str = Field(..., description="用户标识")

    model: Optional[str] = Field(None, description="会话 model")

    llm_config_id: Optional[str] = Field(None, description="会话使用的 LLM 配置ID")

    skill_ids: List[str] = Field(default_factory=list, description="本次会话启用的技能ID列表")

    prompt_ids: List[str] = Field(default_factory=list, description="本次会话启用的提示词ID列表")

    selected_tool_names: List[str] = Field(default_factory=list, description="本次会话启用的工具列表")

    initial_message: Optional[str] = Field(None, description="可选的首条消息")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="更新时间")
    started_at: Optional[datetime] = Field(None, description="开始时间")
    metadata: Dict = Field(default_factory=dict, description="扩展信息")
    error_message: Optional[str] = Field(None, description="错误信息")


class TaskInfo(BaseModel):
    task_id: str = Field(..., description="任务唯一标识")
    conversation_id: ZestAgentUUID = Field(..., description="关联业务会话")
    user_id: str = Field(..., description="用户标识")
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="任务状态")
    dispatch_attempt: int = Field(default=0, description="调度尝试次数")
    remote_conversation_id: Optional[str] = Field(None, description="远端会话 ID")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="创建时间")
    updated_at: Optional[datetime] = Field(None, description="更新时间")
    result: Optional[Dict] = Field(None, description="任务结果")
    error_message: Optional[str] = Field(None, description="错误信息")
    metadata: Dict = Field(default_factory=dict, description="扩展信息")
    agent_server_id: Optional[str] = Field(None, description="承载任务的 AgentServer")
    base_url: Optional[str] = Field(None, description="zest-service 基础 HTTP 地址")
    events_url: Optional[str] = Field(None, description="发送消息 REST 地址")
    websocket_url: Optional[str] = Field(None, description="实时事件 WebSocket 地址")
    session_api_key: Optional[str] = Field(None, description="前端直连时使用的 session_api_key")

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "a1b2c3d4_e5f6g7h8",
                "conversation_id": "a1b2c3d4",
                "user_id": "user123",
                "status": "pending",
                "metadata": {},
            }
        }


class AgentServerInfo(BaseModel):
    server_id: str = Field(..., description="服务唯一标识")
    host: str = Field(..., description="主机地址")
    port: int = Field(..., description="端口")
    status: ServerStatus = Field(default=ServerStatus.HEALTHY, description="服务状态")
    capabilities: Dict = Field(default_factory=dict, description="支持的能力")
    metrics: Dict = Field(default_factory=dict, description="性能指标")
    last_heartbeat: datetime = Field(default_factory=datetime.utcnow, description="最后心跳时间")
    registered_at: datetime = Field(default_factory=datetime.utcnow, description="注册时间")
    version: Optional[str] = Field(None, description="版本号")
    tags: List[str] = Field(default_factory=list, description="标签")

    class Config:
        json_schema_extra = {
            "example": {
                "server_id": "agent1",
                "host": "192.168.1.100",
                "port": 8081,
                "status": "healthy",
                "capabilities": {
                    "supported_models": ["gpt-4", "claude-3"],
                    "max_concurrent_sessions": 10,
                },
            }
        }


class DispatchAccessInfo(BaseModel):
    error_message: Optional[str] = Field(None, description="错误信息")
    conversation_id: Optional[str] = Field(None, description="zest-service 会话 ID")
    agent_server_id: Optional[str] = Field(None, description="承载会话的 AgentServer")
    base_url: Optional[str] = Field(None, description="zest-service 基础 HTTP 地址")
    events_url: Optional[str] = Field(None, description="发送消息 REST 地址")
    websocket_url: Optional[str] = Field(None, description="实时事件 WebSocket 地址")
    session_api_key: Optional[str] = Field(None, description="前端直连时使用的 session_api_key")


class AgentCapability(BaseModel):
    server_id: str = Field(..., description="服务ID")
    supported_models: List[str] = Field(default_factory=list, description="支持的模型")
    supported_tools: List[str] = Field(default_factory=list, description="支持的工具")
    max_concurrent_sessions: int = Field(..., description="最大并发会话数")
    current_load: float = Field(default=0.0, ge=0.0, le=1.0, description="当前负载 0-1")


# --- User Config ---


class LLMConfig(BaseModel):
    usage_id: str = Field(..., description="LLM 服务标识，如 openai / anthropic")
    model: str = Field(..., description="模型名称，如 openai/gpt-4o")
    api_key: SecretStr = Field(..., description="API Key")

    base_url: Optional[str] = Field(None, description="可选的自定义 base_url")


    @field_validator("api_key", mode="before")

    @classmethod

    def _validate_api_key(cls, v, info):

        return validate_secret(v, info)



    @field_serializer("api_key", when_used="always")

    def _serialize_api_key(self, v, info):

        return serialize_secret(v, info)



class UserInfo(BaseModel):
    user_id: str = Field(..., description="用户唯一标识")
    llm_config: Optional[LLMConfig] = Field(None, description="用户默认 LLM 配置")
    default_workspace: str = Field(default="./workspace", description="用户默认工作目录")
    metadata: Dict = Field(default_factory=dict, description="扩展信息")


class UserLlmConfig(BaseModel):
    id: str = Field(..., description="LLM 配置ID")
    user_id: str = Field(..., description="用户ID")
    usage_id: str = Field(..., description="LLM 服务标识")
    model: str = Field(..., description="模型名称")
    api_key: SecretStr = Field(..., description="API Key")

    base_url: Optional[str] = Field(None, description="可选基础地址")


    @field_validator("api_key", mode="before")

    @classmethod

    def _validate_api_key(cls, v, info):

        return validate_secret(v, info)



    @field_serializer("api_key", when_used="always")

    def _serialize_api_key(self, v, info):

        return serialize_secret(v, info)



class SkillDefinitionPayload(BaseModel):
    name: str = Field(..., description="技能名称")
    content: str = Field(..., description="技能正文")
    description: Optional[str] = Field(None, description="技能说明")
    source: Optional[str] = Field(None, description="技能来源")
    trigger: Optional[Dict[str, Any]] = Field(None, description="技能触发配置")


class SkillProfile(BaseModel):

    id: str = Field(..., description="技能定义ID")

    user_id: str = Field(..., description="用户ID")

    name: str = Field(..., description="技能名称")

    content: str = Field(..., description="技能正文")

    description: Optional[str] = Field(None, description="技能说明")

    source: Optional[str] = Field(None, description="技能来源")

    trigger: Optional[Dict[str, Any]] = Field(None, description="技能触发配置")

    enabled: bool = Field(default=True, description="是否启用该技能")





class PromptConfig(BaseModel):

    id: str = Field(..., description="提示词配置ID")

    user_id: str = Field(..., description="用户ID")

    name: str = Field(..., description="提示词名称")

    content: str = Field(..., description="提示词正文")

    description: Optional[str] = Field(None, description="提示词说明")

    source: Optional[str] = Field(None, description="提示词来源")

    trigger: Optional[Dict[str, Any]] = Field(None, description="提示词触发配置")

    enabled: bool = Field(default=True, description="是否启用该提示词")


class SubAgentConfig(BaseModel):

    id: str = Field(..., description="子 Agent 配置ID")

    user_id: str = Field(..., description="用户ID")

    name: str = Field(..., description="子 Agent 配置名称")

    model: Optional[str] = Field(None, description="指定模型")

    selected_tool_names: List[str] = Field(default_factory=list, description="工具名列表")

    description: Optional[str] = Field(None, description="子 Agent 配置说明")

    custom_system_prompt: str | None = Field(default=None)

    system_prompt_filename: str | None = Field(default=None)

    enabled: bool = Field(default=True, description="是否启用该子 Agent 配置")

    config: Dict[str, Any] = Field(default_factory=dict, description="子 Agent 配置内容")





class AgentConfigPayload(BaseModel):

    llm: LLMConfig = Field(..., description="已装配完成的 LLM 配置")

    selected_tool_names: List[str] = Field(default_factory=list, description="已选工具名列表")

    skills: List[SkillDefinitionPayload] = Field(default_factory=list, description="已展开技能列表")

    prompts: List[str] = Field(default_factory=list, description="已展开提示词正文列表")

    system_prompt_kwargs: Dict[str, Any] = Field(default_factory=dict, description="system prompt 模板参数")

    subagent_configs: List[Dict[str, Any]] = Field(default_factory=list, description="子 Agent 配置")





# Request/Response Models





class CreateConversationRequest(BaseModel):



    user_id: str = Field(..., description="用户ID")



    initial_message: Optional[str] = Field(None, description="可选的首条消息")



    model: Optional[str] = Field(None, description="指定模型")



    llm_config_id: Optional[str] = Field(None, description="指定 LLM 配置ID")



    skill_ids: List[str] = Field(default_factory=list, description="技能ID列表")



    prompt_ids: List[str] = Field(default_factory=list, description="提示词ID列表")



    selected_tool_names: List[str] = Field(default_factory=list, description="工具名列表")



    metadata: Dict[str, Any] = Field(default_factory=dict, description="扩展信息")





class CreateUserLlmConfigRequest(BaseModel):

    id: Optional[str] = Field(default=None, description="LLM 配置ID，为空时由后端自动生成")

    user_id: str = Field(..., description="用户ID")

    usage_id: str = Field(..., description="LLM 服务标识")

    model: str = Field(..., description="模型名称")

    api_key: str = Field(..., description="API Key")

    base_url: Optional[str] = Field(None, description="可选基础地址")





class CreateSkillProfileRequest(BaseModel):



    id: Optional[str] = Field(default=None, description="技能定义ID，为空时由后端自动生成")



    user_id: str = Field(..., description="用户ID")



    name: str = Field(..., description="技能名称")



    content: str = Field(..., description="技能正文")



    description: Optional[str] = Field(None, description="技能说明")



    source: Optional[str] = Field(None, description="技能来源")



    trigger: Optional[Dict[str, Any]] = Field(None, description="技能触发配置")



    enabled: bool = Field(default=True, description="是否启用该技能")





class UpdateSkillProfileRequest(BaseModel):



    user_id: str = Field(..., description="用户ID")



    name: str = Field(..., description="技能名称")



    content: str = Field(..., description="技能正文")



    description: Optional[str] = Field(None, description="技能说明")



    source: Optional[str] = Field(None, description="技能来源")



    trigger: Optional[Dict[str, Any]] = Field(None, description="技能触发配置")



    enabled: bool = Field(default=True, description="是否启用该技能")





class CreatePromptConfigRequest(BaseModel):







    id: Optional[str] = Field(default=None, description="提示词配置ID，为空时由后端自动生成")







    user_id: str = Field(..., description="用户ID")







    name: str = Field(..., description="提示词名称")







    content: str = Field(..., description="提示词正文")







    description: Optional[str] = Field(None, description="提示词说明")







    source: Optional[str] = Field(None, description="提示词来源")







    trigger: Optional[Dict[str, Any]] = Field(None, description="提示词触发配置")







    enabled: bool = Field(default=True, description="是否启用该提示词")











class UpdatePromptConfigRequest(BaseModel):

    user_id: str = Field(..., description="用户ID")

    name: str = Field(..., description="提示词名称")

    content: str = Field(..., description="提示词正文")

    description: Optional[str] = Field(None, description="提示词说明")

    source: Optional[str] = Field(None, description="提示词来源")

    trigger: Optional[Dict[str, Any]] = Field(None, description="提示词触发配置")

    enabled: bool = Field(default=True, description="是否启用该提示词")



class CreateSubAgentConfigRequest(BaseModel):

    id: Optional[str] = Field(default=None, description="子 Agent 配置ID，为空时由后端自动生成")

    user_id: str = Field(..., description="用户ID")

    name: str = Field(..., description="子 Agent 配置名称")

    model: Optional[str] = Field(None, description="指定模型")

    selected_tool_names: List[str] = Field(default_factory=list, description="工具名列表")

    description: Optional[str] = Field(None, description="子 Agent 配置说明")

    custom_system_prompt: str | None = Field(default=None)

    system_prompt_filename: str | None = Field(default=None)

    enabled: bool = Field(default=True, description="是否启用该子 Agent 配置")

    config: Dict[str, Any] = Field(default_factory=dict, description="子 Agent 配置内容")



class UpdateSubAgentConfigRequest(BaseModel):

    user_id: str = Field(..., description="用户ID")

    name: str = Field(..., description="子 Agent 配置名称")

    model: Optional[str] = Field(None, description="指定模型")

    selected_tool_names: List[str] = Field(default_factory=list, description="工具名列表")

    description: Optional[str] = Field(None, description="子 Agent 配置说明")

    custom_system_prompt: str | None = Field(default=None)

    system_prompt_filename: str | None = Field(default=None)

    enabled: bool = Field(default=True, description="是否启用该子 Agent 配置")

    config: Dict[str, Any] = Field(default_factory=dict, description="子 Agent 配置内容")
 
class SnapshotRuntime(BaseModel):
    status: Optional[str] = Field(None)
    updated_at: Optional[str] = Field(None)


class SnapshotSummary(BaseModel):
    last_user_message: Optional[str] = Field(None)


class ConversationRuntimeSnapshot(BaseModel):
    runtime: SnapshotRuntime = Field(default_factory=SnapshotRuntime)
    summary: SnapshotSummary = Field(default_factory=SnapshotSummary)


class ConversationResponse(BaseModel):
    conversation_id: str
    agent_id: Optional[str] = Field(None, description="取自 ConversationStateMeta.agent.id")
    created_at: Optional[str] = Field(None)
    task_id: Optional[str] = Field(None)
    base_url: Optional[str] = Field(None)
    session_api_key: Optional[str] = Field(None)
    error_message: Optional[str] = Field(None)
    snapshot: ConversationRuntimeSnapshot = Field(default_factory=ConversationRuntimeSnapshot)


class ConversationState(str, Enum):
    STOPPED = "STOPPED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    ERROR = "ERROR"
    WAITING_FOR_INPUT = "WAITING_FOR_INPUT"


class ConfirmationPolicyPayload(BaseModel):
    mode: str = "always"
    threshold: Optional[str] = None
    confirm_unknown: bool = True
    need_confirm_tools: List[str] = Field(default_factory=list)


class ConversationWorkspacePayload(BaseModel):
    working_dir: str = Field(
        ...,
        description="Working directory for agent operations and tool execution",
    )


class ConversationMessagePayload(BaseModel):
    role: Literal["user", "system", "assistant", "tool"] = "user"
    text: str = Field(..., description="Plain text message content")
    run: bool = Field(
        default=True,
        description="Whether the agent loop should automatically run after message creation",
    )


class ConversationCreatePayload(BaseModel):
    """发送给 zest-service 的创建会话载荷，由 app-server 完成装配。"""

    agent_config: AgentConfigPayload = Field(..., description="app-server 装配后的完整 AgentConfig")
    workspace: ConversationWorkspacePayload
    initial_message: ConversationMessagePayload | None = None
    user_id: str| None = None
    conversation_id: ZestAgentUUID | None = Field(
        default=None,
        description=(
            "Optional conversation ID. If not provided, a random UUID will be generated."
        ),
    )
    max_iterations: int = Field(
        default=500,
        ge=1,
        description="If set, the max number of iterations the agent will run before stopping.",
    )
    stuck_detection: bool = Field(
        default=True,
        description="If true, the conversation will use stuck detection.",
    )
    enable_base_memory: bool = Field(default=True, description="Whether to enable base memory.")
    enable_experience_memory: bool = Field(default=True, description="Whether to enable experience memory.")
    confirmation_policy: ConfirmationPolicyPayload = Field(default=ConfirmationPolicyPayload())


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=64, description='username')
    email: str = Field(..., description='email')
    password: str = Field(..., min_length=6, description='password')


class RegisterResponse(BaseModel):
    user: 'AuthSessionUser'
