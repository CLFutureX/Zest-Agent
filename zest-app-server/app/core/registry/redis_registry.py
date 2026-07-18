import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Awaitable, Callable, Dict, List, Optional

from redis.asyncio import Redis

from app.core.models import AgentServerInfo, ServerStatus
from app.core.registry.base import AgentRegistryClient, AgentRegistryServer

logger = logging.getLogger(__name__)

ServerInfoProvider = Callable[[], AgentServerInfo | Awaitable[AgentServerInfo]]

 

class RedisAgentRegistryServer(AgentRegistryServer):
    """基于 Redis Hash 的 AppServer 注册中心实现。"""

    def __init__(
        self,
        redis_client: Redis,
        heartbeat_timeout: int = 30,
        watch_interval: int = 5, 
        key_prefix: str = "agent_registry",
    ) -> None:
        super().__init__(heartbeat_timeout)
        self.redis_client = redis_client
        self.watch_interval = watch_interval 
        self.key_prefix = key_prefix
        self._servers: Dict[str, AgentServerInfo] = {}
        self._lock = asyncio.Lock()
        self._closed = False

    def _build_key(self, server_id: str) -> str:
        return f"{self.key_prefix}:{server_id}"

    def _pattern(self) -> str:
        return f"{self.key_prefix}:*"

    def _parse_datetime(self, value: Optional[str]) -> datetime:
        if not value:
            return datetime.utcnow()
        return datetime.fromisoformat(value)

    def _parse_json_field(self, value: Optional[str], default: object) -> object:
        if value in (None, ""):
            return default
        return json.loads(value)

    def _parse_server(self, payload: Dict[str, str]) -> AgentServerInfo:
        server = AgentServerInfo(
            server_id=payload["server_id"],
            host=payload["host"],
            port=int(payload["port"]),
            status=ServerStatus(payload.get("status", ServerStatus.HEALTHY.value)),
            capabilities=self._parse_json_field(payload.get("capabilities"), {}),
            metrics=self._parse_json_field(payload.get("metrics"), {}),
            last_heartbeat=self._parse_datetime(payload.get("last_heartbeat")),
            registered_at=self._parse_datetime(payload.get("registered_at")),
            version=payload.get("version") or None,
            tags=self._parse_json_field(payload.get("tags"), []),
        ) 
        return server

    def _build_update_mapping(self, updates: dict) -> Dict[str, str]:
        mapping: Dict[str, str] = {}
        for key, value in updates.items():
            if key in {"capabilities", "metrics", "tags"}:
                mapping[key] = self._serialize_json_field(value)
            elif key in {"last_heartbeat", "registered_at"} and isinstance(value, datetime):
                mapping[key] = self._serialize_datetime(value)
            elif key == "status" and isinstance(value, ServerStatus):
                mapping[key] = value.value
            elif value is None:
                mapping[key] = ""
            else:
                mapping[key] = str(value)
        return mapping

    def _serialize_datetime(self, value: datetime) -> str:
        return value.isoformat()

    def _serialize_json_field(self, value: object) -> str:
        return json.dumps(value, ensure_ascii=False)

    def _is_healthy(self, server: AgentServerInfo) -> bool:
        if server.status == ServerStatus.UNHEALTHY:
            return False
         
        return True

    async def _fetch_servers(self) -> Dict[str, AgentServerInfo]:
        servers: Dict[str, AgentServerInfo] = {}
        cursor = 0
        now = datetime.utcnow()
        while True:
            cursor, keys = await self.redis_client.scan(
                cursor=cursor,
                match=self._pattern(),
                count=100,
            )
            if keys:
                for key in keys:
                    raw_payload = await self.redis_client.hgetall(key)
                    if not raw_payload:
                        continue
                    if isinstance(key, bytes):
                        key = key.decode("utf-8")
                    payload = {
                        (field.decode("utf-8") if isinstance(field, bytes) else field):
                        (value.decode("utf-8") if isinstance(value, bytes) else value)
                        for field, value in raw_payload.items()
                    }
                    try:
                        server = self._parse_server(payload)
                        if(self.is_expired(server,now)):
                            server.status = ServerStatus.UNHEALTHY
                        servers[server.server_id] = server
                    except Exception:
                        logger.exception("Failed to parse server payload from key: %s", key)
            if cursor == 0:
                break
        return servers

    async def _refresh_servers(self) -> List[AgentServerInfo]:
        latest_servers = await self._fetch_servers()
        
        async with self._lock:
            self._servers = latest_servers

            servers = list(self._servers.values())
        servers.sort(key=lambda item: item.registered_at)
        return servers

    async def watch_loop(self) -> None:
        while not self._closed:
            try:
                await self._refresh_servers()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Failed to refresh registry servers")
            await asyncio.sleep(self.watch_interval)

    async def get_server(self, server_id: str) -> Optional[AgentServerInfo]:
        async with self._lock:
            return self._servers.get(server_id)

    async def get_healthy_servers(self) -> List[AgentServerInfo]:
        async with self._lock:
            servers = list(self._servers.values())
        healthy_servers = [server for server in servers if self._is_healthy(server)]
        healthy_servers.sort(key=lambda item: item.registered_at)
        return healthy_servers

    async def get_all_servers(self, refresh: bool = False) -> List[AgentServerInfo]:
        if refresh:
            return await self._refresh_servers()
        async with self._lock:
            servers = list(self._servers.values())
        servers.sort(key=lambda item: item.registered_at)
        return servers
 
    async def close(self) -> None:
        self._closed = True
        await self.redis_client.close()