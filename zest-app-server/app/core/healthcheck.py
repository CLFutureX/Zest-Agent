"""
[已废弃] HealthChecker 已合并到 AgentRegistryServer 内部类。
请改用：
    from app.core.registry.base import AgentRegistryServer
    checker = registry.health_checker()
    status = await checker.get_health_status()

保留此文件仅为兼容历史 import；任何对本模块的 import 都会失败。
"""
raise ImportError(
    "app.core.healthcheck has been removed. "
    "Use AgentRegistryServer.health_checker() instead."
)
