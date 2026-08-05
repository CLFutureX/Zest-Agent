"""
配置管理模块
支持从环境变量和配置文件加载配置
"""
from pydantic import Field
from pydantic_settings import BaseSettings
from typing import Literal, Optional
from pathlib import Path
import os

from common.security.security_settings import get_cipher_from_env
from common.utils.cipher import Cipher

# baseSetting 代表会从.env文件中加载
class Settings(BaseSettings):
    """应用配置"""
    
    # 应用配置
    app_name: str = "zest-agent-appserver"
    host: str = "0.0.0.0"
    port: int = 9000
    debug: bool = True
    workers: int = 4
    
    # 存储配置
    storage_mode: Literal["mysql", "local"] = "local"
    mysql_url: str = "mysql+aiomysql://root:root@localhost:3306/zest_agent"
    local_data_dir: str = "./data"
    
    # 服务注册配置
    registry_mode: Literal["redis", "local"] = "redis"
    redis_url: str = "redis://localhost:6379/0"
    registry_key_prefix: str = "agent_registry"
    heartbeat_interval: int = 10  # 秒
    heartbeat_timeout: int = 30   # 秒
    registry_watch_interval: int = 5  # 秒
    registry_dir: str = ".runtime/registry/servers"  # 本地模式：心跳文件目录
    
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
        "extra":"ignore",
    }
    
    def model_post_init(self, __context):
        # 如果 log_file 为空，使用默认值
        if not self.log_file or self.log_file.strip() == "":
            self.log_file = "logs/appserver.log"

        # 获取日志目录
        log_dir = os.path.dirname(self.log_file)

        # 目录不存在则自动创建
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

    @property
    def resolved_registry_dir(self) -> str:
        # 本地模式下把相对路径相对项目根 Zest-Agent 解析，确保
        # app-server 与 agent-server 两侧扫描/写入到同一绝对目录。
        p = Path(self.registry_dir)
        if p.is_absolute():
            return str(p)
        return str((_PROJECT_ROOT / p).resolve())
    
    


# 项目根锚点：app-server/app/config/settings.py 的 parents[3] 即 Zest-Agent
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


# 全局配置实例
settings = Settings()


def get_cipher() -> Cipher | None:
    """Get the shared cipher for encrypting/decrypting sensitive fields.

    Delegates to common.security.security_settings.get_cipher_from_env().
    Uses the ZEST_SECRET_KEY environment variable (same as zest-service).
    Returns None if no secret key is configured (secrets are redacted).
    """
    return get_cipher_from_env()