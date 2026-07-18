"""
负载均衡器实现
提供会话亲和性和权重轮询两种策略
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
import random
from app.core.models import AgentServerInfo


class LoadBalancer(ABC):
    """负载均衡抽象接口"""
    
    @abstractmethod
    async def select_for_new_session(
        self,
        available_servers: List[AgentServerInfo], 
    ) -> Optional[AgentServerInfo]:
        """为新会话选择AgentServer"""
        pass
    
    @abstractmethod
    async def get_existing_session(
        self,
        session_id: str
    ) -> Optional[str]:
        """获取已存在会话的AgentServer ID"""
        pass
    
    @abstractmethod
    async def record_session_mapping(
        self,
        session_id: str,
        server_id: str
    ) -> None:
        """记录会话与服务器的映射"""
        pass


class SessionAffinityBalancer(LoadBalancer):
    """基于会话亲和性的负载均衡"""
    
    def __init__(self):
        # session_id -> server_id 映射
        self.session_map: Dict[str, str] = {}
    
    async def select_for_new_session(
        self,
        available_servers: List[AgentServerInfo]
    ) -> Optional[AgentServerInfo]:
        """
        为新会话选择AgentServer
        策略：选择当前负载最低的服务器
        """
        if not available_servers:
            return None
        
        # 过滤出健康的服务器
        healthy_servers = [
            s for s in available_servers 
            if s.status.value in ["healthy", "degraded"]
        ]
        
        if not healthy_servers:
            return None
        
        # 选择当前负载最低的服务器（active_sessions最少）
        selected = min(
            healthy_servers,
            key=lambda s: s.metrics.get("active_sessions", 0)
        )
        
        return selected
    
    async def get_existing_session(
        self,
        session_id: str
    ) -> Optional[str]:
        """获取已存在会话的AgentServer ID"""
        return self.session_map.get(session_id)
    
    async def record_session_mapping(
        self,
        session_id: str,
        server_id: str
    ) -> None:
        """记录会话与服务器的映射"""
        self.session_map[session_id] = server_id


class WeightedRoundRobinBalancer(LoadBalancer):
    """基于权重的轮询负载均衡"""
    
    def __init__(self):
        self.current_index = 0
        self.current_weight = 0
        self.session_map: Dict[str, str] = {}
    
    async def select_for_new_session(
        self,
        available_servers: List[AgentServerInfo]
    ) -> Optional[AgentServerInfo]:
        """
        为新会话选择AgentServer
        策略：权重轮询
        """
        if not available_servers:
            return None
        
        # 过滤出健康的服务器
        healthy_servers = [
            s for s in available_servers 
            if s.status.value in ["healthy", "degraded"]
        ]
        
        if not healthy_servers:
            return None
        
        # 计算总权重
        total_weight = sum(
            s.metrics.get("weight", 1) for s in healthy_servers
        )
        
        # 权重轮询算法
        self.current_index = (self.current_index + 1) % len(healthy_servers)
        selected = healthy_servers[self.current_index]
        
        return selected
    
    async def get_existing_session(
        self,
        session_id: str
    ) -> Optional[str]:
        """获取已存在会话的AgentServer ID"""
        return self.session_map.get(session_id)
    
    async def record_session_mapping(
        self,
        session_id: str,
        server_id: str
    ) -> None:
        """记录会话与服务器的映射"""
        self.session_map[session_id] = server_id


class RandomBalancer(LoadBalancer):
    """随机负载均衡"""
    
    def __init__(self):
        self.session_map: Dict[str, str] = {}
    
    async def select_for_new_session(
        self,
        available_servers: List[AgentServerInfo]
    ) -> Optional[AgentServerInfo]:
        """
        为新会话选择AgentServer
        策略：随机选择
        """
        if not available_servers:
            return None
        
        # 过滤出健康的服务器
        healthy_servers = [
            s for s in available_servers 
            if s.status.value in ["healthy", "degraded"]
        ]
        
        if not healthy_servers:
            return None
        
        # 随机选择
        return random.choice(healthy_servers)
    
    async def get_existing_session(
        self,
        session_id: str
    ) -> Optional[str]:
        """获取已存在会话的AgentServer ID"""
        return self.session_map.get(session_id)
    
    async def record_session_mapping(
        self,
        session_id: str,
        server_id: str
    ) -> None:
        """记录会话与服务器的映射"""
        self.session_map[session_id] = server_id


def create_loadbalancer(strategy: str) -> LoadBalancer:
    """
    工厂方法：创建负载均衡器
    
    Args:
        strategy: 策略名称 (session_affinity, weighted_round_robin, random)
    
    Returns:
        LoadBalancer实例
    """
    strategies = {
        "session_affinity": SessionAffinityBalancer,
        "weighted_round_robin": WeightedRoundRobinBalancer,
        "random": RandomBalancer
    }
    
    balancer_class = strategies.get(strategy)
    if not balancer_class:
        # 默认使用会话亲和性
        balancer_class = SessionAffinityBalancer
    
    return balancer_class()
