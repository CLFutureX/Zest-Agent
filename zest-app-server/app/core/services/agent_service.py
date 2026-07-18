"""
AgentServer管理服务
处理AgentServer的注册、注销、心跳等
"""
from typing import Optional, List
from datetime import datetime
import logging

from app.core.models import AgentServerInfo, ServerStatus
from app.core.storage.base import AgentServerStorage

logger = logging.getLogger(__name__)


class AgentServerService:
    """AgentServer管理服务"""
    
    def __init__(
        self,
        agent_server_storage: AgentServerStorage,
        heartbeat_timeout: int = 30
    ):
        self.agent_server_storage = agent_server_storage
        self.heartbeat_timeout = heartbeat_timeout
    
    async def register_server(self, server: AgentServerInfo) -> bool:
        """
        注册AgentServer
        
        Args:
            server: AgentServer信息
        
        Returns:
            是否注册成功
        """
        success = await self.agent_server_storage.register_server(server)
        
        if success:
            logger.info(f"AgentServer registered: {server.server_id}")
        
        return success
    
    async def deregister_server(self, server_id: str) -> bool:
        """
        注销AgentServer
        
        Args:
            server_id: AgentServer ID
        
        Returns:
            是否注销成功
        """
        success = await self.agent_server_storage.deregister_server(server_id)
        
        if success:
            logger.info(f"AgentServer deregistered: {server_id}")
        
        return success
    
    async def get_server(self, server_id: str) -> Optional[AgentServerInfo]:
        """获取AgentServer详情"""
        return await self.agent_server_storage.get_server(server_id)
    
    async def update_heartbeat(
        self,
        server_id: str,
        metrics: Optional[dict] = None
    ) -> bool:
        """
        更新心跳
        
        Args:
            server_id: AgentServer ID
            metrics: 性能指标
        
        Returns:
            是否更新成功
        """
        updates = {
            "last_heartbeat": datetime.utcnow()
        }
        
        if metrics:
            updates["metrics"] = metrics
        
        success = await self.agent_server_storage.update_server(
            server_id,
            updates
        )
        
        if success:
            logger.debug(f"Heartbeat updated: {server_id}")
        
        return success
    
    async def list_healthy_servers(self) -> List[AgentServerInfo]:
        """获取健康的AgentServer列表"""
        return await self.agent_server_storage.list_healthy_servers()
    
    async def list_all_servers(self) -> List[AgentServerInfo]:
        """获取所有AgentServer列表"""
        return await self.agent_server_storage.list_all_servers()
    
    async def check_health(self) -> List[str]:
        """
        检查AgentServer健康状态
        
        返回超时的服务器ID列表
        """
        all_servers = await self.list_all_servers()
        unhealthy_servers = []
        
        now = datetime.utcnow()
        
        for server in all_servers:
            # 计算心跳超时
            time_diff = (now - server.last_heartbeat).total_seconds()
            
            if time_diff > self.heartbeat_timeout:
                # 标记为unhealthy
                await self.agent_server_storage.update_server(
                    server.server_id,
                    {"status": ServerStatus.UNHEALTHY}
                )
                unhealthy_servers.append(server.server_id)
                logger.warning(
                    f"AgentServer {server.server_id} marked as unhealthy "
                    f"(last heartbeat: {time_diff}s ago)"
                )
        
        return unhealthy_servers
