"""Rewrite models.py with CRLF line endings."""
import os

content = """\
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime
from enum import Enum


class SessionStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"
    PAUSED = "paused"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ServerStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class SessionInfo(BaseModel):
    session_id: str = Field(..., description="会话唯一标识，同时作为 conversation_id")
    user_id: str = Field(..., description="用户标识")
    agent_server_id: str = Field(..., description="分配的AgentServer")
    status: SessionStatus = Field(default=SessionStatus.CREATED, description="会话状态")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="更新时间")
    started_at: Optional[datetime] = Field(None, description="开始时间")
    conversation_id: Optional[str] = Field(None, description="映射到 zest-service 的 conversation UUID")
    metadata: Dict = Field(default_factory=dict, description="扩展信息")
    error_message: Optional[str] = Field(None, description="错误信息")


class TaskInfo(BaseModel):
    task_id: str = Field(..., description="任务唯一标识")
    session_id: str = Field(..., description="关联会话")
    user_id: str = Field(..., description="用户标识")
    title: str = Field(..., description="任务标题")
    description: Optional[str] = Field(None, description="任务描述")
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="任务状态")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="创建时间")
    updated_at: Optional[datetime] = Field(None, description="更新时间")
    result: Optional[Dict] = Field(None, description="任务结果")
    error_message: Optional[str] = Field(None, description="错误信息")
    metadata: Dict = Field(default_factory=dict, description="扩展信息")

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "a1b2c3d4_e5f6g7h8",
                "session_id": "a1b2c3d4",
                "user_id": "user123",
                "title": "数据分析任务",
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
    api_key: str = Field(..., description="API Key（当前阶段明文，后续可加密）")
    base_url: Optional[str] = Field(None, description="可选的自定义 base_url")


class UserInfo(BaseModel):
    user_id: str = Field(..., description="用户唯一标识")
    llm_config: Optional[LLMConfig] = Field(None, description="用户默认 LLM 配置")
    default_workspace: str = Field(
        default="./workspace", description="用户默认工作目录"
    )
    metadata: Dict = Field(default_factory=dict, description="扩展信息")


# Request/Response Models


class CreateSessionRequest(BaseModel):
    user_id: str = Field(..., description="用户ID")
    message: str = Field(..., description="用户消息")
    model: Optional[str] = Field(None, description="指定模型")
    metadata: Dict = Field(default_factory=dict, description="扩展信息")


class CreateTaskRequest(BaseModel):
    title: str = Field(..., description="任务标题")
    description: Optional[str] = Field(None, description="任务描述")
    message: str = Field(..., description="用户初始消息内容")
    metadata: Dict = Field(default_factory=dict, description="扩展信息")
"""

target = os.path.join(os.path.dirname(__file__), "..", "app", "core", "models.py")
with open(target, "w", newline="\r\n") as f:
    f.write(content)
print(f"Rewrote {target} with CRLF")
