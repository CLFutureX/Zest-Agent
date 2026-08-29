"""Memory Store — 向后兼容入口（shim）。

重构后采用三层架构：
    Layer 1 协调层  : coordinator.BaseMemoryStorage / ExperienceMemoryStorage
    Layer 2 接口层 : backend.BaseMemoryBackend / ExperienceMemoryBackend (+ 注册表)
    Layer 3 实现层 : backends/ 下的 FileMemoryStore / ESBaseMemoryStore /
                     CachedBaseMemoryStore / ESMemoryStore

本文件保留旧导入路径兼容：历史代码 `from common.storage.memory.store import ...`
仍可使用，名称全部指向新实现。新代码请直接从 common.storage.memory 导入
协调层对象或使用 create_base_memory_storage / create_experience_memory_storage。
"""

# Layer 2 接口 + 兼容别名
from common.storage.memory.backend import (
    BaseMemoryBackend,
    ExperienceMemoryBackend,
    BaseMemoryBackendRegistry,
    ExperienceMemoryBackendRegistry,
    MemoryStore,
    BaseMemoryStore,
)

# Layer 3 实现（导入即触发注册）
from common.storage.memory.backends import (
    FileMemoryStore,
    ESBaseMemoryStore,
    CachedBaseMemoryStore,
    ESMemoryStore,
)

# 域模型与工具
from common.storage.memory.base import ExperienceMemory, MemoryCategory, MemoryEntry
from common.storage.memory.utils import (
    entry_to_md,
    parse_entries,
    build_index_key,
    extract_index_version,
    merge_category_entries,
    ENTRY_SEPARATOR,
)

__all__ = [
    # Layer 2 接口
    "BaseMemoryBackend",
    "ExperienceMemoryBackend",
    "BaseMemoryBackendRegistry",
    "ExperienceMemoryBackendRegistry",
    # 兼容别名
    "MemoryStore",
    "BaseMemoryStore",
    # Layer 3 实现
    "FileMemoryStore",
    "ESBaseMemoryStore",
    "CachedBaseMemoryStore",
    "ESMemoryStore",
    # 域模型
    "MemoryCategory",
    "MemoryEntry",
    "ExperienceMemory",
    # 工具
    "entry_to_md",
    "parse_entries",
    "build_index_key",
    "extract_index_version",
    "merge_category_entries",
    "ENTRY_SEPARATOR",
]
