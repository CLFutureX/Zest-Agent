from datetime import datetime
from typing import Dict, List, Optional

import psutil

from app.core.models import AgentServerInfo, ServerStatus


class DefaultServerInfoProvider:
    """默认的 AgentServer 信息提供器。"""

    def __init__(
        self,
        server_id: str,
        host: str,
        port: int,
        version: Optional[str] = None,
        tags: Optional[List[str]] = None,
        status: ServerStatus = ServerStatus.HEALTHY,
    ) -> None:
        self.server_id = server_id
        self.host = host
        self.port = port
        self.version = version
        self.tags = tags or []
        self.status = status
        self.registered_at = datetime.utcnow()

    def collect_metrics(self) -> Dict:
        memory = psutil.virtual_memory()
        metrics = {
            "cpu_percent": psutil.cpu_percent(interval=None),
            "memory_percent": memory.percent,
            "memory_used": memory.used,
            "memory_available": memory.available,
            "memory_total": memory.total,
        }

        try:
            metrics["active_sessions"] = self.get_active_sessions()
        except NotImplementedError:
            pass

        return metrics

    def get_active_sessions(self) -> int:
        raise NotImplementedError("Active session collection is not implemented yet")

    def get_capabilities(self) -> Dict:
        raise NotImplementedError("Capability collection is not implemented yet")

    def to_callable(self) -> "DefaultServerInfoProvider":
        return self

    async def __call__(self) -> AgentServerInfo:
        now = datetime.utcnow()

        try:
            capabilities = self.get_capabilities()
        except NotImplementedError:
            capabilities = {}

        return AgentServerInfo(
            server_id=self.server_id,
            host=self.host,
            port=self.port,
            status=self.status,
            capabilities=capabilities,
            metrics=self.collect_metrics(),
            last_heartbeat=now,
            registered_at=self.registered_at,
            version=self.version,
            tags=list(self.tags),
        )