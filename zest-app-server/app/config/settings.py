"""
配置管理模块
支持从环境变量和 .env 文件加载配置。

存储统一由 STORAGE_MODE 控制：
- local  所有数据（运行时 + 资源）都用本地 JSON 文件
- mysql  所有数据都用 MySQL
"""
from __future__ import annotations

import os
from typing import Literal, Optional

from pydantic import Field
from pydantic_settings import BaseSettings

from common.security.security_settings import get_cipher_from_env
from common.utils.cipher import Cipher

StorageMode = Literal["local", "mysql"]


class Settings(BaseSettings):
    """应用配置"""

    # 应用配置
    app_name: str = "zest-agent-appserver"
    host: str = "0.0.0.0"
    port: int = 9000
    debug: bool = True
    workers: int = 4

    # ---- 存储配置 ----
    storage_mode: StorageMode = "local"

    # MySQL
    mysql_url: str = "mysql+aiomysql://root:root@localhost:3306/zest_agent"

    # Local 文件存储根目录
    local_data_dir: str = "./.data"

    # 服务注册配置
    registry_mode: Literal["redis", "local"] = "redis"
    redis_url: str = "redis://localhost:6379/0"
    registry_key_prefix: str = "agent_registry"
    heartbeat_interval: int = 10
    heartbeat_timeout: int = 30
    registry_watch_interval: int = 5
    registry_dir: str = ".runtime/registry/servers"

    # 负载均衡配置
    lb_strategy: str = "session_affinity"

    # Agent Runtime 直连配置
    agent_service_scheme: str = "http"
    agent_service_ws_scheme: str = "ws"
    agent_service_api_prefix: str = "/api"
    agent_service_session_api_key: Optional[str] = ""

    # 日志配置
    log_level: str = "DEBUG"
    log_file: str = ".data/logs/appserver.log"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }

    def model_post_init(self, __context):
        if not self.log_file or self.log_file.strip() == "":
            self.log_file = "logs/appserver.log"
        log_dir = os.path.dirname(self.log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)


# 全局配置实例
settings = Settings()


def get_cipher() -> Cipher | None:
    """Get the shared cipher for encrypting/decrypting sensitive fields.

    Delegates to common.security.security_settings.get_cipher_from_env().
    Uses the ZEST_SECRET_KEY environment variable (same as zest-service).
    Returns None if no secret key is configured (secrets are redacted).
    """
    return get_cipher_from_env()
