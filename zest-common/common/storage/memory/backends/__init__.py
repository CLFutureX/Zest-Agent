"""Layer 3 实现聚合 + 注册到 Layer 2 注册表。

导入本包即自动把各后端注册到 BaseMemoryBackendRegistry / ExperienceMemoryBackendRegistry，
Layer 1 协调层与工厂通过注册表按"存储类型"解析到对应实现。
"""

from common.storage.memory.backend import (
    BaseMemoryBackendRegistry,
    ExperienceMemoryBackendRegistry,
)
from common.storage.memory.backends.base_local import FileMemoryStore
from common.storage.memory.backends.base_es import ESBaseMemoryStore
from common.storage.memory.backends.base_cached import CachedBaseMemoryStore
from common.storage.memory.backends.experience_es import ESMemoryStore

# 新命名别名（推荐新代码使用）—— 与旧类名等价
LocalFileBaseMemoryBackend = FileMemoryStore
ESBaseMemoryBackend = ESBaseMemoryStore
CachedBaseMemoryBackend = CachedBaseMemoryStore
ESExperienceMemoryBackend = ESMemoryStore


# 基础记忆后端工厂：接受统一 kwargs，按需取用
def _local_factory(*, fs=None, base_dir: str = "memory", **_):
    return FileMemoryStore(fs=fs, base_dir=base_dir)


def _es_base_factory(*, es_config=None, **_):
    if es_config is None:
        raise ValueError("ES 基础记忆后端缺少 es_config 配置。")
    return ESBaseMemoryStore(es_config=es_config)


def _es_experience_factory(*, es_config=None, embedding_base=None, **_):
    if es_config is None:
        raise ValueError("ES 经验记忆后端缺少 es_config 配置。")
    if embedding_base is None:
        from common.storage.memory.embedding import get_default_embedding
        embedding_base = get_default_embedding()
    return ESMemoryStore(es_config=es_config, embedding_base=embedding_base)


BaseMemoryBackendRegistry.register("local", _local_factory)
BaseMemoryBackendRegistry.register("es", _es_base_factory)
ExperienceMemoryBackendRegistry.register("es", _es_experience_factory)


__all__ = [
    "FileMemoryStore",
    "ESBaseMemoryStore",
    "CachedBaseMemoryStore",
    "ESMemoryStore",
    # 新别名
    "LocalFileBaseMemoryBackend",
    "ESBaseMemoryBackend",
    "CachedBaseMemoryBackend",
    "ESExperienceMemoryBackend",
]
