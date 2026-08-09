"""
LocalFile 资源 storage 泛型实现
4 个资源（llm_config / skill / prompt / subagent）共用一份代码。

设计要点：
- 每条资源以 <id>.json 文件存储，整体 read → filter → write 模式。
- 复用 PydanticJsonSerializer，cipher context 与 Mongo/MySQL 行为一致。
- 并发：单实例 asyncio.Lock，避免多协程下读写竞态。
- 适用场景：单机开发、本地化部署；不跨进程共享。
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, Generic, List, Optional, Type, TypeVar

from app.core.storage.base import ResourceStorage
from app.core.storage.serializer import PydanticJsonSerializer

logger = logging.getLogger(__name__)

T = TypeVar("T")


class LocalFileResourceStorage(ResourceStorage[T], Generic[T]):
    def __init__(self, dir_: Path, model_cls: Type[T]) -> None:
        self.dir = Path(dir_)
        self.model_cls = model_cls
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self._serializer = PydanticJsonSerializer()

    def _file_path(self, item_id: str) -> Path:
        safe = str(item_id).replace("/", "_").replace("\\", "_")
        return self.dir / f"{safe}.json"

    async def ensure_indexes(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)

    async def create(self, item) -> bool:
        async with self._lock:
            path = self._file_path(getattr(item, self.id_field))
            if path.exists():
                return False
            path.write_text(self._serializer.to_store(item), encoding="utf-8")
            return True

    async def get(self, item_id: str) -> Optional[T]:
        path = self._file_path(item_id)
        if not path.exists():
            return None
        raw = path.read_text(encoding="utf-8")
        return self._serializer.from_store(raw, self.model_cls)

    async def update(self, item_id: str, updates: dict) -> bool:
        async with self._lock:
            path = self._file_path(item_id)
            if not path.exists():
                return False
            raw = path.read_text(encoding="utf-8")
            item = self._serializer.from_store(raw, self.model_cls)
            if item is None:
                return False
            for k, v in updates.items():
                if hasattr(item, k):
                    setattr(item, k, v)
            path.write_text(self._serializer.to_store(item), encoding="utf-8")
            return True

    async def delete(self, item_id: str) -> bool:
        async with self._lock:
            path = self._file_path(item_id)
            if not path.exists():
                return False
            path.unlink()
            return True

    async def list_by_user(
        self,
        user_id: str,
        filters: Optional[Dict] = None,
    ) -> List[T]:
        results: List[T] = []
        for path in self.dir.glob("*.json"):
            try:
                raw = path.read_text(encoding="utf-8")
                item = self._serializer.from_store(raw, self.model_cls)
            except Exception:
                logger.warning("Failed to parse %s", path, exc_info=True)
                continue
            if item is None:
                continue
            if getattr(item, self.user_field, None) != user_id:
                continue
            if filters:
                matched = True
                for k, v in filters.items():
                    if getattr(item, k, None) != v:
                        matched = False
                        break
                if not matched:
                    continue
            results.append(item)
        return results
