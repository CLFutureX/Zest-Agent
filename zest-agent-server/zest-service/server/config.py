import logging
import os
from pathlib import Path
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from pydantic_settings import BaseSettings, SettingsConfigDict
from server.agent_registry import build_default_server_id
from server.env_parser import from_env
from common.utils.cipher import Cipher
from common.security.security_settings import get_cipher_from_env


# Environment variable constants
ENVIRONMENT_VARIABLE_PREFIX = "ZEST"
_logger = logging.getLogger(__name__)

class WebhookSpec(BaseModel):
    """Spec to create a webhook. All webhook requests use POST method."""

    # General parameters
    event_buffer_size: int = Field(
        default=5,
        ge=1,
        description=(
            "The number of events to buffer locally before posting to the webhook"
        ),
    )
    base_url: str = Field(
        description="The base URL of the webhook service. Events will be sent to "
        "{base_url}/events and conversation info to {base_url}/conversations"
    )
    headers: dict[str, str] = Field(default_factory=dict)
    flush_delay: float = Field(
        default=30.0,
        gt=0,
        description=(
            "The delay in seconds after which buffered events will be flushed to "
            "the webhook, even if the buffer is not full. Timer is reset on each "
            "new event."
        ),
    )

    # Retry parameters
    num_retries: int = Field(
        default=3,
        ge=0,
        description="The number of times to retry if the post operation fails",
    )
    retry_delay: int = Field(default=5, ge=0, description="The delay between retries")
BASE_DIR = Path(__file__).parent.parent
print(f"Base_DIR: {BASE_DIR}")
class Config(BaseSettings):
    """
    Immutable configuration for a server running in local mode.
    (Typically inside a sandbox).
    """

    session_api_keys: list[str] = Field(
        default=[],
        description=(
            "List of valid session API keys used to authenticate incoming requests. "
            "Empty list implies the server will be unsecured. Any key in this list "
            "will be accepted for authentication. Multiple keys are supported to "
            "enable key rotation without service disruption - new keys can be added "
            "to the list, then clients are updated with the new key, and finally the "
            "old key is removed from the list. "
        ),
    )
    allow_cors_origins: list[str] = Field(
        default_factory=list,
        description=(
            "Set of CORS origins permitted by this server (Anything from localhost is "
            "always accepted regardless of what's in here)."
        ),
    )
    conversations_path: Path = Field(
        default=Path("workspace/conversations"),
        description=(
            "The location of the directory where conversations and events are stored."
        ),
    )
    bash_events_dir: Path = Field(
        default=Path("workspace/bash_events"),
        description=(
            "The location of the directory where bash events are stored as files. "
            "Defaults to 'workspace/bash_events'."
        ),
    )
    static_files_path: Path | None = Field(
        default=None,
        description=(
            "The location of the directory containing static files to serve. "
            "If specified and the directory exists, static files will be served "
            "at the /static/ endpoint."
        ),
    )
    webhooks: list[WebhookSpec] = Field(
        default_factory=list,
        description="Webhooks to invoke in response to events",
    )
    enable_vscode: bool = Field(
        default=True,
        description="Whether to enable VSCode server functionality",
    )
    vscode_port: int = Field(
        default=8001,
        ge=1,
        le=65535,
        description="Port on which VSCode server should run",
    )
    enable_vnc: bool = Field(
        default=False,
        description="Whether to enable VNC desktop functionality",
    )
    preload_tools: bool = Field(
        default=True,
        description="Whether to preload tools",
    )
    public_api_base: str | None = Field(
        default=None,
        description="Public HTTP base used by clients to access the runtime API, e.g. http://host:8000/api",
    )
    public_websocket_base: str | None = Field(
        default=None,
        description="Public WebSocket base used by clients to access runtime sockets, e.g. ws://host:8000/sockets",
    )
    agent_server_host: str = Field(
        default="0.0.0.0",
        description="Host reported by the AgentServer registry heartbeat.",
    )
    agent_server_port: int = Field(
        default=8000,
        ge=1,
        le=65535,
        description="Port reported by the AgentServer registry heartbeat.",
    )
    agent_server_id: str | None = Field(
        default=None,
        description="Optional fixed AgentServer instance id used for registry reporting.",
    )
    registry_enabled: bool = Field(
        default=False,
        description="Whether to enable AgentServer registry heartbeat reporting.",
    )
    registry_backend: Literal["redis", "local"] = Field(
        default="redis",
        description="Registry backend: redis (Hash+TTL) or local (shared file directory).",
    )
    registry_dir: str = Field(
        default=".runtime/registry/servers",
        description="Local-mode registry heartbeat file directory (shared with app-server).",
    )
    registry_redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis url used by the AgentServer registry client.",
    )
    registry_key_prefix: str = Field(
        default="agent_registry",
        description="Redis key prefix used to store AgentServer registry entries.",
    )
    heartbeat_interval: int = Field(
        default=10,
        ge=1,
        description="Seconds between AgentServer registry heartbeats.",
    )
    heartbeat_timeout: int = Field(
        default=30,
        ge=1,
        description="Redis TTL for AgentServer registry heartbeats.",
    )
    registry_tags: list[str] = Field(
        default_factory=list,
        description="Additional tags reported with the AgentServer registry payload.",
    )
    model_config: SettingsConfigDict = {
        "env_file": BASE_DIR / ".env",        # 只读取自己目录的.env，绝对隔离
        "env_file_encoding": "utf-8",
        "extra": "ignore",                   # 🔥 忽略无关环境变量（解决报错）
        "frozen": True,                      # 不可变，安全
    }

    @property
    def cipher(self) -> Cipher | None:
        """Delegates cipher creation to common.security."""
        return get_cipher_from_env()

    @property
    def resolved_agent_server_id(self) -> str:
        resolved_server_id = getattr(self, "_resolved_agent_server_id", None)
        if resolved_server_id is not None:
            return resolved_server_id
        if self.agent_server_id:
            resolved_server_id = self.agent_server_id
        else:
            resolved_server_id = build_default_server_id(
                self.agent_server_host,
                self.agent_server_port,
            )
        setattr(self, "_resolved_agent_server_id", resolved_server_id)
        return resolved_server_id


_default_config: Config | None = None


def get_default_config() -> Config:
    """Get the default local server config shared across the server"""
    global _default_config
    if _default_config is None:
        # Get the config from the environment variables
        _default_config = from_env(Config, ENVIRONMENT_VARIABLE_PREFIX)
        assert _default_config is not None
    return _default_config