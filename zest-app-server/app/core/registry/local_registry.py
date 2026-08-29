"""基于本地文件系统的注册中心实现（server 端）。

设计要点：
- 每个 agent-server 在 ``registry_dir`` 目录下写 ``<server_id>.json``。
- server 端 ``watch_loop`` 周期扫描目录，按 ``last_heartbeat`` 与
  ``heartbeat_timeout`` 比较剔除过期文件（等价 Redis TTL 自然过期）。
- ``get_*`` 只读内存缓存（由 watch_loop 维护），不做 IO，调用方零成本。

该类只是 ``AgentRegistryServer`` 抽象的一个适配器，不引入新的对外接口；
切换 backend 时由 ``init_registry`` 选择实例化 Redis 或 Local 实现。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from app.core.models import AgentServerInfo, ServerStatus
from app.core.registry.base import AgentRegistryServer

logger = logging.getLogger(__name__)


class LocalAgentRegistryServer(AgentRegistryServer):
    """文件系统版的注册中心。仅作为 AgentRegistryServer 抽象的本地适配器。"""

    def __init__(
        self,
        registry_dir: str | os.PathLike[str] = ".runtime/registry/servers",
        heartbeat_timeout: int = 30,
        watch_interval: int = 5,
    ) -> None:
        super().__init__(heartbeat_timeout)
        pre_path = Path.home() / ".zest"
        self.registry_dir = pre_path/registry_dir  
        self.registry_dir.mkdir(parents=True, exist_ok=True) 
        self.watch_interval = watch_interval
        self._servers: Dict[str, AgentServerInfo] = {}
        self._lock = asyncio.Lock()
        self._closed = False
        

    # ---------- 内部辅助 ----------

    def _server_file(self, server_id: str) -> Path:
        # server_id 形如 "agent-127.0.0.1-8000-abcd1234"，文件名安全。
        safe = server_id.replace("/", "_").replace("\\", "_")
        return self.registry_dir / f"{safe}.json"
 
    async def _scan_and_prune(self) -> List[AgentServerInfo]:
        """扫描目录、解析 json、剔除过期文件、更新内存缓存。"""
        now = datetime.utcnow()
        next_servers: Dict[str, AgentServerInfo] = {}
        stale_ids: List[str] = []

        # 在 executor 里跑同步 IO，避免阻塞 event loop。
        def _scan() -> Dict[str, AgentServerInfo]:
            found: Dict[str, AgentServerInfo] = {}
            for path in self.registry_dir.glob("agent-*.json"):
                try:
                    raw = path.read_text(encoding="utf-8")
                    data = json.loads(raw)
                    server = AgentServerInfo(**data)
                    found[server.server_id] = server
                    logger.debug("scan registry file:%d data:%s",path,data)
                except Exception:
                    logger.warning("Failed to parse registry file: %s", path, exc_info=True)
            return found

        found = await asyncio.get_running_loop().run_in_executor(None, _scan)

        for sid, server in found.items():
            if self.is_expired(server, now):
                stale_ids.append(sid)
            else:
                next_servers[sid] = server

 
        async with self._lock:
            self._servers = next_servers
            result = list(self._servers.values())

        result.sort(key=lambda item: item.registered_at)
        if stale_ids:
            logger.debug("Pruned stale registry entries: %s", stale_ids)
        return result

    # ---------- AgentRegistryServer 接口 ----------

    async def watch_loop(self) -> None:
        while not self._closed:
            try:
                await self._scan_and_prune()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Local registry watch loop failed")
            await asyncio.sleep(self.watch_interval)

    async def get_server(self, server_id: str) -> Optional[AgentServerInfo]:
        async with self._lock:
            return self._servers.get(server_id)

    async def get_healthy_servers(self) -> List[AgentServerInfo]:
        async with self._lock:
            servers = list(self._servers.values())
        healthy = [s for s in servers if s.status != ServerStatus.UNHEALTHY]
        healthy.sort(key=lambda item: item.registered_at)
        return healthy

    async def get_all_servers(self, refresh: bool = False) -> List[AgentServerInfo]:
        if refresh:
            return await self._scan_and_prune()
        async with self._lock:
            servers = list(self._servers.values())
        servers.sort(key=lambda item: item.registered_at)
        return servers
 
    async def close(self) -> None:
        self._closed = True
        # 不删文件——agent 重连后会重新心跳，老文件按 TTL 自动过期。
