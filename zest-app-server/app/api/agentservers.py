"""
AgentServer管理路由
提供 AgentServer 列表、健康服务、详情、健康检查 API
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_registry
from app.core.models import ServerStatus
from app.core.registry import AgentRegistryServer

router = APIRouter(prefix="/api/v1/agentservers", tags=["agentservers"])


@router.get("")
async def list_agent_servers(
    status: Optional[str] = None,
    agent_registry: AgentRegistryServer = Depends(get_registry),
):
    """获取 AgentServer 列表，可按 status 过滤。"""
    all_servers = await agent_registry.get_all_servers()
    if status:
        servers = [s for s in all_servers if s.status.value == status]
    else:
        servers = all_servers
    return {"servers": servers, "total": len(servers)}


@router.get("/healthy")
async def list_healthy_servers(
    agent_registry: AgentRegistryServer = Depends(get_registry),
):
    """获取健康的 AgentServer 列表。"""
    servers = await agent_registry.get_healthy_servers()
    return {"servers": servers, "total": len(servers)}


@router.get("/{server_id}")
async def get_server(
    server_id: str,
    agent_registry: AgentRegistryServer = Depends(get_registry),
):
    """获取 AgentServer 详情。"""
    server = await agent_registry.get_server(server_id)
    if not server:
        raise HTTPException(status_code=404, detail=f"AgentServer {server_id} not found")
    return server


@router.post("/health-check")
async def health_check(
    agent_registry: AgentRegistryServer = Depends(get_registry),
):
    """执行健康检查。

    - 触发一次 refresh（registry 内部 watch_loop 已周期刷新缓存，这里仅取最新视图）
    - 返回当前 unhealthy 服务列表
    """
    unhealthy = await agent_registry.health_checker().list_unhealthy()
    return {
        "unhealthy_servers": unhealthy,
        "count": len(unhealthy),
    }
