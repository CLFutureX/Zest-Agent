"""Memory system public API.

三层架构：
    Layer 1 协调层  : BaseMemoryStorage / ExperienceMemoryStorage
                      （对外返回的领域存储对象，内部引用后端）
    Layer 2 接口层 : BaseMemoryBackend / ExperienceMemoryBackend
                      （后端契约 + 注册表：按存储类型选实现）
    Layer 3 实现层 : FileMemoryStore / ESBaseMemoryStore /
                      CachedBaseMemoryStore / ESMemoryStore

推荐入口：
    from common.storage.memory import (
        BaseMemoryStorage, ExperienceMemoryStorage,
        create_base_memory_storage, create_experience_memory_storage,
    )

旧入口（create_base_memory_store / create_experience_memory_store 及各类 *Store 类名）
作为兼容保留，详见 store.py。
"""

from common.storage.memory.base import ExperienceMemory, ExecutionTrace, MemoryCategory, MemoryEntry
from common.storage.memory.backend import (
    BaseMemoryBackend,
    ExperienceMemoryBackend,
    BaseMemoryBackendRegistry,
    ExperienceMemoryBackendRegistry,
    MemoryStore,
    BaseMemoryStore,
)
from common.storage.memory.coordinator import BaseMemoryStorage, ExperienceMemoryStorage
from common.storage.memory.backends import (
    FileMemoryStore,
    ESBaseMemoryStore,
    CachedBaseMemoryStore,
    ESMemoryStore,
)
from common.storage.memory.utils import entry_to_md, parse_entries

__all__ = [
    # Layer 1 协调层（推荐对外 API）
    "BaseMemoryStorage",
    "ExperienceMemoryStorage",
    # Layer 2 接口层
    "BaseMemoryBackend",
    "ExperienceMemoryBackend",
    "BaseMemoryBackendRegistry",
    "ExperienceMemoryBackendRegistry",
    # Layer 3 实现层
    "FileMemoryStore",
    "ESBaseMemoryStore",
    "CachedBaseMemoryStore",
    "ESMemoryStore",
    # 域模型
    "MemoryCategory",
    "MemoryEntry",
    "ExperienceMemory",
    "ExecutionTrace",
    # 工具
    "parse_entries",
    "entry_to_md",
    # 兼容别名
    "MemoryStore",
    "BaseMemoryStore",
]
