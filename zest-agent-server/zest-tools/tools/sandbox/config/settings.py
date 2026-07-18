from dataclasses import dataclass, field
from enum import Enum

class RuntimeType(Enum):
    """运行时类型"""
    PROCESS = "process"              # 本地进程
    DOCKER = "docker"                # 本地容器
    DISTRIBUTED = "distributed"      # 分布式容器
    KUBERNETES = "kubernetes"        # Kubernetes
    

@dataclass
class NetworkPolicy:
    """网络策略配置"""
    enabled: bool = False               # 是否启用网络隔离（进程模式不支持）
    allowed_hosts: list[str] = field(default_factory=list)
    blocked_hosts: list[str] = field(default_factory=lambda: ["metadata.google.internal"])

@dataclass
class SecurityPolicy:
    sandbox_user: str = "sandbox" # 沙箱用户？
    allowed_modules: list[str] = field(default_factory=list)  # 允许的模块白名单
    blocked_modules: list[str] = field(default_factory=lambda: [
        "os", "sys", "subprocess", "socket", "ctypes", "importlib"
    ])  # 禁止的模块
    max_file_size_mb: int = 10          # 最大文件大小 (MB)
    allowed_paths: list[str] = field(default_factory=lambda: ["/tmp"])  # 允许访问的路径

@dataclass
class ResourceLimits:
    """资源限制配置"""
    cpu_limit: float = 2.0              # CPU 核心数
    memory_limit_mb: int = 512          # 内存限制 (MB)
    disk_limit_mb: int = 1024           # 磁盘限制 (MB)
    timeout_seconds: int = 30           # 执行超时 (秒)
    max_processes: int = 10             # 最大进程数

@dataclass
class SandboxConfig:
    mode: RuntimeType = RuntimeType.PROCESS
    max_sandboxes: int = 10
    idle_timeout: int = 600
    enable_sandbox_reuse: bool= True # 启用沙箱复用
    
    #隔离策略
    resources: ResourceLimits=field(default_factory=ResourceLimits)
    network: NetworkPolicy=field(default_factory=NetworkPolicy)
    security: SecurityPolicy=field(default_factory=SecurityPolicy)
    
    environment: dict[str, str] = field(default_factory=lambda: {
        "PYTHONUNBUFFERED": "1",
        "SANDBOX_MODE": "process"
    })
    
@dataclass
class DistributedConfig:
    """分布式协调配置"""
    redis_url: str = "redis://localhost:6379/0"
    heartbeat_interval: int = 10      # 心跳间隔（秒）
    heartbeat_timeout: int = 30       # 心跳超时（秒）
    lock_timeout: int = 10            # 分布式锁超时（秒）
    instance_id: str = ""             # 实例 ID（自动生成）
    
@dataclass
class KubernetesConfig:
    """Kubernetes 配置"""
    namespace: str = "sandboxes"
    kubeconfig_path: str = ""         # 空表示使用 in-cluster 配置
    service_account: str = "default"