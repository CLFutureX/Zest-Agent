"""
健康检查和监控路由
- /health                基础健康端点
- /health/status         服务健康统计（基于 registry 内部 HealthChecker）
- /registry/status       注册中心状态
- /metrics               系统指标
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends

from app.api.dependencies import get_health_checker, get_registry
from app.core.registry.base import ServiceRegistry

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """基础健康检查端点。"""
    return {
        "status": "ok",
        "timestamp": datetime.utcnow(),
        "version": "1.0.0",
    }


@router.get("/health/status")
async def get_health_status(
    health_checker=Depends(get_health_checker),
):
    """获取服务健康状态详情。

    - 调用 registry 内部 HealthChecker.get_health_status()
    - 返回 total / healthy / unhealthy_count / unhealthy_ids
    """
    status = await health_checker.get_health_status()
    return {
        "status": "ok",
        "timestamp": datetime.utcnow(),
        "health": status,
    }


@router.get("/registry/status")
async def get_registry_status(
    registry: ServiceRegistry = Depends(get_registry),
):
    """获取服务注册中心状态。"""
    all_servers = await registry.get_all_servers()
    healthy_servers = await registry.get_healthy_servers()

    status_count = {"healthy": 0, "degraded": 0, "unhealthy": 0}
    for server in all_servers:
        status_value = server.status.value if hasattr(server.status, "value") else str(server.status)
        if status_value in status_count:
            status_count[status_value] += 1

    return {
        "status": "ok",
        "timestamp": datetime.utcnow(),
        "total_servers": len(all_servers),
        "healthy_servers": len(healthy_servers),
        "status_count": status_count,
        "servers": all_servers,
    }


@router.get("/metrics")
async def get_metrics(
    registry: ServiceRegistry = Depends(get_registry),
):
    """获取系统指标。"""
    healthy_servers = await registry.get_healthy_servers()
    return {
        "active_sessions": 0,
        "total_requests": 0,
        "avg_response_time": 0.0,
        "healthy_servers": len(healthy_servers),
    }
