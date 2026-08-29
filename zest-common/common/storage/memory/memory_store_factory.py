"""Memory Store 工厂 — 统一入口。

提供两套等价入口：
    - 推荐（Layer 1 协调对象）:
        create_base_memory_storage       -> BaseMemoryStorage | None
        create_experience_memory_storage -> ExperienceMemoryStorage | None
    - 兼容（Layer 3 后端对象，供历史调用方 / isinstance 判断）:
        create_base_memory_store         -> BaseMemoryBackend | None
        create_experience_memory_store   -> ExperienceMemoryBackend | None

后端选择通过 Layer 2 注册表按"存储类型"解析；缓存作为策略在工厂层透明包裹，
不再与具体后端绑定。
"""

from typing import TYPE_CHECKING

from common.logger import get_logger
from common.storage.file_store import FileStore, MemoryLRUCache
from common.storage.memory.elasticsearch_config import ElasticsearchConfig
from common.storage.memory.embedding.embedding_base import EmbeddingBase
from common.storage.storage_settings import StorageSettings, resolve_memory_local_dir

# 导入 store 触发 backends 注册到 Layer 2 注册表
from common.storage.memory import store as _store  # noqa: F401
from common.storage.memory.backend import (
    BaseMemoryBackend,
    BaseMemoryBackendRegistry,
    ExperienceMemoryBackend,
    ExperienceMemoryBackendRegistry,
)
from common.storage.memory.coordinator import BaseMemoryStorage, ExperienceMemoryStorage

logger = get_logger(__name__)


def _build_es_config(
    index_name: str,
    es_settings: object | None,
    embedding_dims: int = 1536,
) -> ElasticsearchConfig | None:
    if es_settings is None:
        return None

    return ElasticsearchConfig(
        collection_name=index_name,
        host=getattr(es_settings, "host", None),
        port=getattr(es_settings, "port", None),
        user=getattr(es_settings, "user", None),
        password=getattr(es_settings, "password", None),
        cloud_id=getattr(es_settings, "cloud_id", None),
        api_key=getattr(es_settings, "api_key", None),
        embedding_model_dims=embedding_dims,
        verify_certs=getattr(es_settings, "verify_certs", True),
        use_ssl=getattr(es_settings, "use_ssl", False),
        auto_create_index=getattr(es_settings, "auto_create_index", True),
        headers=getattr(es_settings, "headers", None),
    )


def _resolve_base_es_config(base_settings, es_config):
    return es_config or _build_es_config(
        index_name=base_settings.index_name,
        es_settings=base_settings.es,
    )


def _resolve_experience_es_config(experience_settings, es_config):
    return es_config or _build_es_config(
        index_name=experience_settings.index_name,
        es_settings=experience_settings.es,
        embedding_dims=experience_settings.embedding_dims,
    )


# ---------------------------------------------------------------------------
# 基础记忆
# ---------------------------------------------------------------------------


def create_base_memory_store(
    *,
    backend: str | None = None,
    cache_limit_size: int = 100,
    cache_limit_memory: int = 1024 * 1024,
    es_config: object | None = None,
    fs: FileStore | None = None,
    storage_settings: StorageSettings | None = None,
) -> BaseMemoryBackend | None:
    """基础记忆后端工厂（兼容入口）。

    返回 Layer 3 后端对象（FileMemoryStore / CachedBaseMemoryStore），
    保留 isinstance 判断能力。新代码建议用 create_base_memory_storage。
    """
    from common.storage.file_store.local import LocalFileStore
    from common.storage.storage_settings import load_storage_settings_from_env

    settings = storage_settings or load_storage_settings_from_env()
    base_settings = settings.memory.base

    if not base_settings.enable:
        logger.info("create_base_memory_store not enable")
        return None

    resolved_backend = (backend or base_settings.backend).lower()
    resolved_cache_limit_size = cache_limit_size or base_settings.cache_limit_size
    resolved_cache_limit_memory = cache_limit_memory or base_settings.cache_limit_memory
    resolved_es_config = _resolve_base_es_config(base_settings, es_config)

    if resolved_backend == "local":
        if fs is None:
            fs = LocalFileStore(root=settings.local.root_dir)
        memory_dir = resolve_memory_local_dir(settings=settings)
        logger.info(f"使用 FileMemoryStore (本地存储),memory_dir={memory_dir}")
        return BaseMemoryBackendRegistry.create("local", fs=fs, base_dir=memory_dir)

    if resolved_backend == "es":
        if resolved_es_config is None:
            raise ValueError("ES 基础记忆后端缺少 es_config 配置。")
        logger.info("使用 CachedBaseMemoryStore (ES + LRU 本地缓存)")
        remote = BaseMemoryBackendRegistry.create("es", es_config=resolved_es_config)
        return _wrap_base_cache(remote, resolved_cache_limit_size, resolved_cache_limit_memory)

    raise ValueError(f"不支持的基础记忆存储后端: {resolved_backend}，仅支持 'local' 或 'es'")


def create_base_memory_storage(
    *,
    backend: str | None = None,
    cache_limit_size: int = 100,
    cache_limit_memory: int = 1024 * 1024,
    es_config: object | None = None,
    fs: FileStore | None = None,
    storage_settings: StorageSettings | None = None,
) -> BaseMemoryStorage | None:
    """基础记忆协调对象工厂（推荐入口）。

    返回 Layer 1 协调对象 BaseMemoryStorage，内部引用解析出的后端。
    返回 None 表示该记忆未启用。
    """
    backend_obj = create_base_memory_store(
        backend=backend,
        cache_limit_size=cache_limit_size,
        cache_limit_memory=cache_limit_memory,
        es_config=es_config,
        fs=fs,
        storage_settings=storage_settings,
    )
    if backend_obj is None:
        return None
    return BaseMemoryStorage(backend=backend_obj)


# ---------------------------------------------------------------------------
# 经验记忆
# ---------------------------------------------------------------------------


def create_experience_memory_store(
    *,
    backend: str | None = None,
    es_config: object | None = None,
    embedding_base: EmbeddingBase | None = None,
    storage_settings: StorageSettings | None = None,
) -> ExperienceMemoryBackend | None:
    """经验记忆后端工厂（兼容入口）。返回 Layer 3 后端对象 ESMemoryStore。"""
    from common.storage.storage_settings import load_storage_settings_from_env

    settings = storage_settings or load_storage_settings_from_env()
    experience_settings = settings.memory.experience

    if not experience_settings.enable:
        logger.info("create_experience_memory_store not enable")
        return None

    resolved_backend = (backend or experience_settings.backend).lower()
    resolved_es_config = _resolve_experience_es_config(experience_settings, es_config)

    if resolved_backend != "es":
        raise ValueError(f"不支持的经验记忆存储后端: {resolved_backend}，仅支持 'es'")
    if resolved_es_config is None:
        raise ValueError("ES 经验记忆后端需要 es_config 和 embedding_base 参数，请提供。")

    logger.info("使用 ESMemoryStore (Elasticsearch)")
    return ExperienceMemoryBackendRegistry.create(
        "es", es_config=resolved_es_config, embedding_base=embedding_base,
    )


def create_experience_memory_storage(
    *,
    backend: str | None = None,
    es_config: object | None = None,
    embedding_base: EmbeddingBase | None = None,
    storage_settings: StorageSettings | None = None,
) -> ExperienceMemoryStorage | None:
    """经验记忆协调对象工厂（推荐入口）。返回 Layer 1 协调对象。"""
    backend_obj = create_experience_memory_store(
        backend=backend,
        es_config=es_config,
        embedding_base=embedding_base,
        storage_settings=storage_settings,
    )
    if backend_obj is None:
        return None
    return ExperienceMemoryStorage(backend=backend_obj)


# ---------------------------------------------------------------------------
# 内部：缓存策略（透明包裹基础记忆后端）
# ---------------------------------------------------------------------------


def _wrap_base_cache(remote: BaseMemoryBackend, cache_limit_size: int, cache_limit_memory: int) -> BaseMemoryBackend:
    """将缓存作为策略透明包裹后端。cache_limit_size<=0 时不包裹。"""
    if cache_limit_size and cache_limit_size > 0:
        from common.storage.memory.backends.base_cached import CachedBaseMemoryStore
        return CachedBaseMemoryStore(
            remote_store=remote,
            cache=MemoryLRUCache(
                max_memory=cache_limit_memory,
                max_size=max(cache_limit_size, 1),
            ),
        )
    return remote
