from abc import ABC, abstractmethod

from tools.sandbox.base import Sandbox, SandboxInfo


class SandboxProvider(ABC):
    """
    沙箱提供者
    职责：  
    - 沙箱创建，复用和淘汰策略
    - 资源分配和限制
    不职责：
    - 不直接与沙箱提供层交互
    - 不直接执行代码
    """
    
    @abstractmethod
    async def get(
        self,
        sandbox_id: str,
        workspace_root: str | None = None,
    ) -> Sandbox:
        pass
    
    
    @abstractmethod
    async def release(self, sandbox_id:str)->None:
        pass
    
    @abstractmethod
    async def destroy(self, sandbox_id: str) -> None:
        pass
    
    @abstractmethod
    async def destroy_all(self) -> None:
        """销毁所有沙箱"""
        pass
    
    @abstractmethod
    async def reclaim_idle(self) -> int:
        """
        回收空闲超时的沙箱
        
        Returns:
            int: 回收的沙箱数量
        """
        pass
    
    @abstractmethod
    def get_stats(self) -> dict:
        """
        获取沙箱统计信息
        
        Returns:
            Dict: 统计信息
        """
        pass
    
    @abstractmethod
    async def list_sandboxes(self) -> list[SandboxInfo]:
        """
        列出所有沙箱
        
        Returns:
            List[SandboxInfo]: 沙箱信息列表
        """
        pass
    
    @abstractmethod
    async def health_check(self, session_id: str) -> bool:
        """
        检查沙箱健康状态
        
        Args:
            session_id: 会话 ID
            
        Returns:
            bool: 是否健康
        """
        pass