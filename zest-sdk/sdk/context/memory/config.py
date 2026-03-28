"""记忆系统配置模块"""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MemoryConfig:
    """记忆系统配置"""

    # 本地存储目录
    local_storage_dir: Path

    # MongoDB连接配置
    mongodb_url: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "agent_memory"

    # 本地文件路径（自动生成）
    user_profile_file: Path | None = field(default=None, init=False)
    user_preferences_file: Path | None = field(default=None, init=False)
    project_constraints_file: Path | None = field(default=None, init=False)
    system_constraints_file: Path | None = field(default=None, init=False)
    metadata_file: Path | None = field(default=None, init=False)

    def __post_init__(self):
        """初始化文件路径"""
        # 确保目录存在
        self.local_storage_dir = Path(self.local_storage_dir)
        self.local_storage_dir.mkdir(parents=True, exist_ok=True)

        # 设置文件路径
        self.user_profile_file = self.local_storage_dir / "user_profile.yaml"
        self.user_preferences_file = self.local_storage_dir / "user_preferences.yaml"
        self.project_constraints_file = (
            self.local_storage_dir / "project_constraints.yaml"
        )
        self.system_constraints_file = (
            self.local_storage_dir / "system_constraints.yaml"
        )
        self.metadata_file = self.local_storage_dir / "metadata.json"

    @classmethod
    def from_env(cls, env_prefix: str = "AGENT_MEMORY_") -> "MemoryConfig":
        """从环境变量创建配置"""
        import os

        local_storage_dir = os.getenv(
            f"{env_prefix}LOCAL_STORAGE_DIR", "./agent_memory"
        )
        mongodb_url = os.getenv(f"{env_prefix}MONGODB_URL", "mongodb://localhost:27017")
        mongodb_db_name = os.getenv(f"{env_prefix}MONGODB_DB_NAME", "agent_memory")

        return cls(
            local_storage_dir=Path(local_storage_dir),
            mongodb_url=mongodb_url,
            mongodb_db_name=mongodb_db_name,
        )
