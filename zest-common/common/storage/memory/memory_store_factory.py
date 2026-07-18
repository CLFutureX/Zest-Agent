"""Memory Store 工厂 — 统一入口。"""

from typing import TYPE_CHECKING

from common.logger import get_logger
from common.storage.file_store import FileStore, MemoryLRUCache
from common.storage.memory.elasticsearch_config import ElasticsearchConfig
from common.storage.memory.embedding.embedding_base import EmbeddingBase
from common.storage.storage_settings import StorageSettings, resolve_memory_local_dir
from common.storage.memory.store import MemoryStore

logger = get_logger(__name__)


def _build_es_config(
    index_name: str,
    es_settings: object | None,
    embedding_dims: int = 1536
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


def create_base_memory_store(
    *, 
    backend: str | None = None,
    cache_limit_size: int = 100,
    cache_limit_memory: int = 1024 * 1024,
    es_config: object | None = None,
    fs: FileStore | None = None, 
    storage_settings: StorageSettings | None = None,
) -> MemoryStore:
    """统一的基础记忆存储工厂方法。"""
    from common.storage.file_store.local import LocalFileStore
    from common.storage.file_store.memory import InMemoryFileStore
    from common.storage.memory.store import CachedBaseMemoryStore, ESBaseMemoryStore, FileMemoryStore
    from common.storage.storage_settings import load_storage_settings_from_env

    settings = storage_settings or load_storage_settings_from_env()
    base_settings = settings.memory.base

    if not base_settings.enable:
        logger.info("create_base_memory_store not enable")
        return

    resolved_backend = (backend or base_settings.backend).lower()
    
    resolved_cache_limit_size = cache_limit_size or base_settings.cache_limit_size
    resolved_cache_limit_memory = cache_limit_memory or base_settings.cache_limit_memory

    resolved_es_config = es_config or _build_es_config(
        index_name=base_settings.index_name,
        es_settings=base_settings.es,
    )

    if resolved_backend == "local":
        if fs is None:
            fs = LocalFileStore(root=settings.local.root_dir)  
        memory_dir  =  resolve_memory_local_dir(settings=settings)
        logger.info(f"使用 FileMemoryStore (本地存储),memory_dir={memory_dir}")
        return FileMemoryStore(fs=fs, base_dir=memory_dir)

    if resolved_backend == "es":
        if resolved_es_config is None:
            raise ValueError("ES 基础记忆后端缺少 es_config 配置。")

        logger.info("使用 CachedBaseMemoryStore (ES + LRU 本地缓存)")
        return CachedBaseMemoryStore(
            remote_store=ESBaseMemoryStore(es_config=resolved_es_config),
            cache=MemoryLRUCache(
                max_memory=resolved_cache_limit_memory,
                max_size=max(resolved_cache_limit_size, 1),
            ),
        )

    raise ValueError(f"不支持的基础记忆存储后端: {resolved_backend}，仅支持 'local' 或 'es'")


def create_experience_memory_store(
    *,
    backend: str | None = None,
    es_config: object | None = None,
    embedding_base: EmbeddingBase | None = None,
    storage_settings: StorageSettings | None = None,
) -> MemoryStore:
    """统一的经验记忆存储工厂方法。"""
    from common.storage.memory.store import ESMemoryStore
    from common.storage.storage_settings import load_storage_settings_from_env
    from common.storage.memory.embedding import get_default_embedding

    settings = storage_settings or load_storage_settings_from_env()
    experience_settings = settings.memory.experience

    if not experience_settings.enable:
        logger.info("create_experience_memory_store not enable")
        return

    resolved_backend = (backend or experience_settings.backend).lower()
    resolved_es_config = es_config or _build_es_config(
        index_name=experience_settings.index_name,
        es_settings=experience_settings.es,
        embedding_dims=experience_settings.embedding_dims,
    )

    if resolved_backend != "es":
        raise ValueError(f"不支持的经验记忆存储后端: {resolved_backend}，仅支持 'es'")

    if resolved_es_config is None:
        raise ValueError("ES 经验记忆后端需要 es_config 和 embedding_base 参数，请提供。")

    if embedding_base is None:
        embedding_base = get_default_embedding()

    logger.info("使用 ESMemoryStore (Elasticsearch)")
    return ESMemoryStore(
        es_config=resolved_es_config,
        embedding_base=embedding_base,
    )