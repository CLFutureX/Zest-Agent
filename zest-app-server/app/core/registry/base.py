from abc import ABC, abstractmethod
from enum import Enum
from typing import List, Optional 
import logging
from typing import List, Optional 
from datetime import datetime, timedelta
from app.core.models import AgentServerInfo
 

logger = logging.getLogger(__name__)

class EventType(str, Enum):
    REGISTRY = "registry"
    DEREGISTRY = "deregistry"
    MODIFY = "modify"


class AgentRegistryClient(ABC):
    @abstractmethod
    async def register_loop(self) -> None:
        """周期性上报服务信息。"""
        pass

    @abstractmethod
    async def deregister(self, service_id: str) -> None:
        """注销服务。"""
        pass


class AgentRegistryServer(ABC):
    def __init__(self, heartbeat_timeout: int):
         self.heartbeat_timeout = heartbeat_timeout

    def is_expired(self,server: AgentServerInfo,now = datetime.utcnow())-> bool:
        return server.last_heartbeat < now - timedelta(seconds=self.heartbeat_timeout)

    @abstractmethod
    async def watch_loop(self) -> None:
        """监听并刷新服务变化。"""
        pass

    @abstractmethod
    async def get_server(self, server_id: str) -> Optional[AgentServerInfo]:
        """获取指定服务信息。"""
        pass

    @abstractmethod
    async def get_healthy_servers(self) -> List[AgentServerInfo]:
        """获取健康服务列表。"""
        pass

    @abstractmethod
    async def get_all_servers(self, refresh: bool = False) -> List[AgentServerInfo]:
        """获取所有服务列表。"""
        pass

 

    @abstractmethod
    async def close(self) -> None:
        """关闭注册中心连接。"""
        pass

 
ServiceRegistry = AgentRegistryServer