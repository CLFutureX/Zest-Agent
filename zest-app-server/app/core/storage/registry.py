"""
StorageRegistry：应用启动后唯一的存储入口。

替代 dependencies.py 中分散的 15+ 全局单例变量。
backend 由 init_storage() 根据 settings 装配，运行时通过 storage_registry.backend 取用。
"""
from __future__ import annotations

from typing import Optional

from app.core.storage.backend import StorageBackend


class StorageRegistry:
    def __init__(self) -> None:
        self._backend: Optional[StorageBackend] = None

    def configure(self, backend: StorageBackend) -> None:
        self._backend = backend

    @property
    def backend(self) -> StorageBackend:
        if self._backend is None:
            raise RuntimeError("Storage backend not initialized. Call init_storage() first.")
        return self._backend

    @property
    def is_configured(self) -> bool:
        return self._backend is not None


storage_registry = StorageRegistry()
