"""
AgentServer管理路由
提供AgentServer注册、注销、心跳、列表等API
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
from app.core.healthcheck import HealthChecker
from app.core.models import  ServerStatus
from app.api.dependencies import   get_health_checker, get_registry
from app.core.registry import AgentRegistryServer

router = APIRouter(prefix="/api/v1/agentservers", tags=["agentservers"])


@router.get("")
async def list_agent_servers(
    status: Optional[str] = None,
    agent_registry: AgentRegistryServer = Depends(get_registry)
):
    """
    获取AgentServer列表
    
    - 如果指定status，过滤对应状态的服务器
    - 否则返回所有服务器
    """
    if status:
        # 获取所有服务器并过滤
        all_servers = await agent_registry.get_all_servers()
        servers = [s for s in all_servers if s.status.value == status]
    else:
        servers = await agent_registry.get_all_servers()
    
    return {
        "servers": servers,
        "total": len(servers)
    }


@router.get("/healthy")
async def list_healthy_servers(
    agent_registry: AgentRegistryServer = Depends(get_registry)
):
    """
    获取健康的AgentServer列表
    
    - 仅返回状态为healthy的服务器
    """
    servers = await agent_registry.get_healthy_servers()
    
    return {
        "servers": servers,
        "total": len(servers)
    }


@router.get("/{server_id}")
async def get_server(
    server_id: str,
    agent_registry: AgentRegistryServer = Depends(get_registry)
):
    """
    获取AgentServer详情
    
    - 返回指定服务器的详细信息
    """
    server = await agent_registry.get_server(server_id)
    if not server:
        raise HTTPException(
            status_code=404,
            detail=f"AgentServer {server_id} not found"
        )
    
    return server


@router.post("/health-check")
async def health_check(
    agent_registry: AgentRegistryServer = Depends(get_registry),
    health_checker: HealthChecker = Depends(get_health_checker),
):
    """
    执行健康检查
    
    - 检查所有AgentServer的心跳
    - 标记超时的服务器为unhealthy
    - 返回不健康的服务器列表
    """
    all_servers = await agent_registry.get_all_servers(refresh=True)
    unhealthy_servers = [item for item in all_servers if item.status == ServerStatus.UNHEALTHY]
    
    return {
        "unhealthy_servers": unhealthy_servers,
        "count": len(unhealthy_servers)
    }
