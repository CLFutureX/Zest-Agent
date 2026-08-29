import asyncio
import json
import os
import tempfile
from datetime import datetime
from enum import Enum
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Awaitable, Callable
from uuid import uuid4

import psutil
from pydantic import BaseModel, Field
from redis.asyncio import Redis
 
from common.logger import get_logger

logger = get_logger(__name__)


class ServerStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class AgentServerInfo(BaseModel):
    server_id: str
    host: str
    port: int
    status: ServerStatus = Field(default=ServerStatus.HEALTHY)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    last_heartbeat: datetime = Field(default_factory=datetime.utcnow)
    registered_at: datetime = Field(default_factory=datetime.utcnow)
    version: str | None = None
    tags: list[str] = Field(default_factory=list)


class DefaultServerInfoProvider:
    """AgentServer 默认信息提供器。"""

    def __init__(
        self,
        server_id: str,
        host: str,
        port: int,
        version_value: str | None = None,
        tags: list[str] | None = None,
        status: ServerStatus = ServerStatus.HEALTHY,
    ) -> None:
        self.server_id = server_id
        self.host = host
        self.port = port
        self.version = version_value or self._detect_version()
        self.tags = tags or []
        self.status = status
        self.registered_at = datetime.utcnow()

    def _detect_version(self) -> str | None:
        try:
            return version("zest-service")
        except PackageNotFoundError:
            return None

    def collect_metrics(self) -> dict[str, Any]:
        memory = psutil.virtual_memory()
        metrics: dict[str, Any] = {
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

    def get_capabilities(self) -> dict[str, Any]:
        raise NotImplementedError("Capability collection is not implemented yet")

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


class RedisAgentRegistryClient:
    """AgentServer 侧 Redis 注册客户端。"""

    def __init__(
        self,
        redis_client: Redis,
        server_info_provider: DefaultServerInfoProvider,
        heartbeat_interval: int,
        ttl_seconds: int,
        key_prefix: str,
    ) -> None:
        self.redis_client = redis_client
        self.server_info_provider = server_info_provider
        self.heartbeat_interval = heartbeat_interval
        self.ttl_seconds = ttl_seconds
        self.key_prefix = key_prefix
        self._is_running = False
        self._is_first_register = True

    @property
    def server_id(self) -> str:
        return self.server_info_provider.server_id

    def _build_key(self, server_id: str) -> str:
        return f"{self.key_prefix}:{server_id}"

    def _serialize_datetime(self, value: datetime) -> str:
        return value.isoformat()

    def _serialize_json_field(self, value: object) -> str:
        return json.dumps(value, ensure_ascii=False)

    def _build_full_mapping(self, server: AgentServerInfo) -> dict[str, str]:
        return {
            "server_id": server.server_id,
            "host": server.host,
            "port": str(server.port),
            "status": server.status.value,
            "capabilities": self._serialize_json_field(server.capabilities),
            "metrics": self._serialize_json_field(server.metrics),
            "last_heartbeat": self._serialize_datetime(server.last_heartbeat),
            "registered_at": self._serialize_datetime(server.registered_at),
            "version": server.version or "",
            "tags": self._serialize_json_field(server.tags),
        }

    def _build_heartbeat_mapping(self, server: AgentServerInfo) -> dict[str, str]:
        return {
            "status": server.status.value,
            "metrics": self._serialize_json_field(server.metrics),
            "last_heartbeat": self._serialize_datetime(server.last_heartbeat),
        }

    async def _resolve_server_info(self) -> AgentServerInfo:
        return await self.server_info_provider()

    async def _expire_key(self, key: str) -> None:
        await self.redis_client.expire(key, self.ttl_seconds)

    async def _register_full(self, server: AgentServerInfo) -> None:
        key = self._build_key(server.server_id)
        mapping_map = self._build_full_mapping(server)
        await self.redis_client.hmset(key, mapping=mapping_map)
        logger.debug(f"_register_full hmset key:{key},mapping:{mapping_map}")
        await self._expire_key(key)

    async def _heartbeat_partial(self, server: AgentServerInfo) -> None:
        key = self._build_key(server.server_id)
        mapping_map = self._build_heartbeat_mapping(server)
        await self.redis_client.hmset(key, mapping=mapping_map)
        logger.debug(f"_heartbeat_partial hmset key:{key},mapping:{mapping_map}")
        await self._expire_key(key)

    async def register_loop(self) -> None:
        self._is_running = True
        while self._is_running:
            try:
                server = await self._resolve_server_info()
                await self._register_full(server)
                # if self._is_first_register:
                #     await self._register_full(server)
                #     self._is_first_register = False
                # else:
                #     await self._heartbeat_partial(server)
                logger.debug("Registered agent heartbeat: %s", server.server_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Failed to register agent heartbeat")

            await asyncio.sleep(self.heartbeat_interval)

    async def deregister(self, service_id: str) -> None:
        self._is_running = False
        self._is_first_register = True
        await self.redis_client.delete(self._build_key(service_id))
        logger.info("Deregistered agent server: %s", service_id)

    async def close(self) -> None:
        await self.redis_client.close()




class LocalAgentRegistryClient:
    """AgentServer 侧本地文件注册客户端。

    与 ``RedisAgentRegistryClient`` 行为对齐：周期性把 ``AgentServerInfo`` 写到
    ``registry_dir/<server_id>.json``，退出时删除文件。app-server 端的
    ``LocalAgentRegistryServer`` 通过扫描同一目录感知存活服务。

    设计约束：
    - 不引入额外网络依赖（无 HTTP / Redis），仅依赖标准库 + app-server 共享路径。
    - 写文件采用 ``tmp + rename`` 原子写，避免 app-server 扫描时读到半截 json。
    """

    def __init__(
        self,
        registry_dir: "str | os.PathLike[str]",
        server_info_provider: "Callable[[], Awaitable[Any]]",
        heartbeat_interval: int,
    ) -> None: 
        pre_path = Path.home() / ".zest"
        self.registry_dir = pre_path/registry_dir 
        self.registry_dir.mkdir(parents=True, exist_ok=True)
        self.server_info_provider = server_info_provider
        self.heartbeat_interval = heartbeat_interval
        self._is_running = False

    @property
    def server_id(self) -> str:
        return self.server_info_provider.server_id  # type: ignore[attr-defined]

    def _server_file(self, server_id: str):
        safe = server_id.replace("/", "_").replace("\\", "_")
        return self.registry_dir / f"{safe}.json"

    def _write_atomic(self, path, payload: str) -> None:
        tmp_fd, tmp_path = tempfile.mkstemp(
            prefix=".tmp-", suffix=".json", dir=str(path.parent)
        )
 
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as fp:
                fp.write(payload)
            os.replace(tmp_path, path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    async def register_loop(self) -> None:
        self._is_running = True
        while self._is_running:
            try:
                server = await self.server_info_provider()
                payload = server.model_dump_json()
                await asyncio.get_running_loop().run_in_executor(
                    None, self._write_atomic, self._server_file(server.server_id), payload
                )
                logger.debug("Local registry heartbeat written: %s", server.server_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Failed to write local registry heartbeat")
            await asyncio.sleep(self.heartbeat_interval)

    async def deregister(self, service_id: str) -> None:
        self._is_running = False
        try:
            fp = self._server_file(service_id)
            await asyncio.get_running_loop().run_in_executor(
                None, lambda: fp.unlink(missing_ok=True)
            )
            logger.info("Deregistered agent server (local): %s", service_id)
        except Exception:
            logger.exception("Failed to remove local registry file: %s", service_id)

    async def close(self) -> None:
        # 本地模式没有需要释放的连接资源。
        return


def build_default_server_id(host: str, port: int) -> str:
    return f"agent-{host}-{port}-{uuid4().hex[:8]}"
