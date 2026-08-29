import os

 
from pydantic import BaseModel, Field





class ElasticsearchConnectionSettings(BaseModel):

    host: str | None = None

    port: int | None = None

    user: str | None = None

    password: str | None = None

    cloud_id: str | None = None

    api_key: str | None = None

    verify_certs: bool = True

    use_ssl: bool = False

    auto_create_index: bool = True

    headers: dict[str, str] | None = None





class MongoConnectionSettings(BaseModel):

    url: str | None = None





class BaseMemorySettings(BaseModel):

    backend: str = "local"
    
    enable: bool = True

    local_dir: str = "./agent_memory"

    cache_limit_size: int = 100

    cache_limit_memory: int = 1024 * 1024

    es: ElasticsearchConnectionSettings | None = None

    index_name: str = "agent_experiences"


class ExperienceMemorySettings(BaseModel):

    backend: str = "es"
    
    enable: bool = False

    es: ElasticsearchConnectionSettings | None = None

    index_name: str = "agent_experiences"

    embedding_dims: int = 1536


class MemoryStorageSettings(BaseModel):

    base: BaseMemorySettings = Field(default_factory=BaseMemorySettings)

    experience: ExperienceMemorySettings = Field(default_factory=ExperienceMemorySettings)


class EmbeddingSettings(BaseModel):
    model: str = Field(..., description="embedding model")
    api_key: str = Field()
    embedding_dims: int = Field(default=1536)
    base_url: str | None = Field(default=None)
    model_kwargs: dict | None = Field(default=None)


class EventLogSettings(BaseModel):

    backend: str = "local"

    local_dir_template: str = "agents/{agent_id}/events"

    mongo: MongoConnectionSettings | None = None

    db_name: str = "agent_events"

    collection_name: str = "event_logs"

    cache_limit_size: int = 1000

    cache_limit_memory: int = 50 * 1024 * 1024


class StateStoreSettings(BaseModel):

    backend: str = "local"

    local_file_name: str = "base_state.json"

    mongo: MongoConnectionSettings | None = None

    db_name: str = "agent_data"

    collection_name: str = "conversation_state"


class LocalStoragePaths(BaseModel):

    root_dir: str = "./.data/storage"

    memory_dir_template: str = "memorys"

    event_dir_template: str = "conversations/{conversation_id}/events/{agent_id}"

    state_file_template: str = "conversations/{conversation_id}/state/base_state.json"


class StorageSettings(BaseModel):

    namespace: str = "default"

    local: LocalStoragePaths = Field(default_factory=LocalStoragePaths)

    memory: MemoryStorageSettings = Field(default_factory=MemoryStorageSettings)

    event_log: EventLogSettings = Field(default_factory=EventLogSettings)

    state_store: StateStoreSettings = Field(default_factory=StateStoreSettings)


def _get_str(name: str, default: str | None = None) -> str | None:

    value = os.getenv(name)

    return value if value not in (None, "") else default


def _get_int(name: str, default: int) -> int:

    value = os.getenv(name)

    return int(value) if value not in (None, "") else default


def _get_bool(name: str, default: bool) -> bool:

    value = os.getenv(name)

    if value in (None, ""):

        return default

    return value.lower() in {"1", "true", "yes", "on"}


def _normalize_relative_path(path: str) -> str:

    return path.replace("\\", "/").strip("/")


def _join_root_and_relative(root_dir: str, relative_path: str) -> str:

    normalized_root = root_dir or "."

    normalized_relative = _normalize_relative_path(relative_path)

    return os.path.join(normalized_root, normalized_relative) if normalized_relative else normalized_root


def _build_memory_local_dir(root_dir: str) -> str:

    return _join_root_and_relative(root_dir, "memory")


def _build_event_local_dir_template(root_dir: str) -> str:

    return _normalize_relative_path(_join_root_and_relative(root_dir, "events/{agent_id}"))


def _build_state_local_file_name(root_dir: str) -> str:

    return _normalize_relative_path(_join_root_and_relative(root_dir, "state/base_state.json"))


def resolve_memory_local_dir(  
    settings: StorageSettings, 
) -> str:
 
    return settings.local.memory_dir_template
         
 


def resolve_event_local_dir( 
    conversation_id: str ,
    agent_id: str,
    settings: StorageSettings
) -> str:

    
    relative_dir = settings.local.event_dir_template.format(conversation_id=conversation_id, agent_id=agent_id)
    return relative_dir
 


def resolve_state_local_file( 
    conversation_id: str,
    settings: StorageSettings
) -> str:

   
    return settings.local.state_file_template.format(conversation_id=conversation_id) 

   


def load_storage_settings_from_env() -> StorageSettings:

    sdk_port = int(_get_str("SDK_MEMORY_ES_PORT", "9200") or "9200")

    storage_root_dir = _get_str("STORAGE_LOCAL_ROOT_DIR", "./.data/storage") or "./.data/storage"

    local_memory_template = _get_str("STORAGE_LOCAL_MEMORY_DIR_TEMPLATE","memorys") 

    local_event_template = _get_str("STORAGE_LOCAL_EVENT_DIR_TEMPLATE", "conversations/{conversation_id}/events/{agent_id}")  

    local_state_template = _get_str("STORAGE_LOCAL_STATE_FILE_TEMPLATE", "conversations/{conversation_id}/state/base_state.json")  

    base_es = ElasticsearchConnectionSettings(

        host=_get_str("STORAGE_MEMORY_BASE_ES_HOST", _get_str("SDK_MEMORY_ES_HOST")),

        port=_get_int("STORAGE_MEMORY_BASE_ES_PORT", sdk_port),

        user=_get_str("STORAGE_MEMORY_BASE_ES_USER", _get_str("SDK_MEMORY_ES_USER")),

        password=_get_str("STORAGE_MEMORY_BASE_ES_PASSWORD", _get_str("SDK_MEMORY_ES_PASSWORD")),

        cloud_id=_get_str("STORAGE_MEMORY_BASE_ES_CLOUD_ID"),

        api_key=_get_str("STORAGE_MEMORY_BASE_ES_API_KEY"),

        verify_certs=_get_bool("STORAGE_MEMORY_BASE_ES_VERIFY_CERTS", True),

        use_ssl=_get_bool("STORAGE_MEMORY_BASE_ES_USE_SSL", False),

    )

    experience_es = ElasticsearchConnectionSettings(

        host=_get_str("STORAGE_MEMORY_EXPERIENCE_ES_HOST", _get_str("SDK_MEMORY_ES_HOST")),

        port=_get_int("STORAGE_MEMORY_EXPERIENCE_ES_PORT", sdk_port),

        user=_get_str("STORAGE_MEMORY_EXPERIENCE_ES_USER", _get_str("SDK_MEMORY_ES_USER")),

        password=_get_str("STORAGE_MEMORY_EXPERIENCE_ES_PASSWORD", _get_str("SDK_MEMORY_ES_PASSWORD")),

        cloud_id=_get_str("STORAGE_MEMORY_EXPERIENCE_ES_CLOUD_ID"),

        api_key=_get_str("STORAGE_MEMORY_EXPERIENCE_ES_API_KEY"),

        verify_certs=_get_bool("STORAGE_MEMORY_EXPERIENCE_ES_VERIFY_CERTS", True),

        use_ssl=_get_bool("STORAGE_MEMORY_EXPERIENCE_ES_USE_SSL", False),

    )

    event_mongo = MongoConnectionSettings(

        url=_get_str("STORAGE_EVENT_MONGO_URL", _get_str("EVENT_STORE_MONGO_URL", _get_str("AGENT_MEMORY_MONGODB_URL", "mongodb://localhost:27017"))),

    )

    state_mongo = MongoConnectionSettings(

        url=_get_str("STORAGE_STATE_MONGO_URL", _get_str("STATE_STORE_MONGO_URL", _get_str("AGENT_MEMORY_MONGODB_URL", "mongodb://localhost:27017"))),

    )

    return StorageSettings(

        namespace=_get_str("STORAGE_NAMESPACE", "default") or "default",

        local=LocalStoragePaths(
            root_dir=storage_root_dir,
            memory_dir_template=local_memory_template,
            event_dir_template=local_event_template,
            state_file_template=local_state_template,
        ),

        memory=MemoryStorageSettings(

            base=BaseMemorySettings(

                backend=(_get_str("STORAGE_MEMORY_BASE_BACKEND", _get_str("MEMORY_STORE_BACKEND", "local")) or "local").lower(),

                local_dir=_get_str("STORAGE_MEMORY_BASE_LOCAL_DIR", _build_memory_local_dir(storage_root_dir)) or _build_memory_local_dir(storage_root_dir),

                cache_limit_size=_get_int("STORAGE_MEMORY_BASE_CACHE_LIMIT_SIZE", 100),

                cache_limit_memory=_get_int("STORAGE_MEMORY_BASE_CACHE_LIMIT_MEMORY", 1024 * 1024),

                es=base_es if base_es.host or base_es.cloud_id else None,

                index_name=_get_str("STORAGE_MEMORY_BASE_INDEX_NAME", _get_str("SDK_MEMORY_ES_COLLECTION", "agent_experiences")) or "agent_experiences",

            ),

            experience=ExperienceMemorySettings(

                backend=(_get_str("STORAGE_MEMORY_EXPERIENCE_BACKEND", "es") or "es").lower(),
                
                enable=_get_bool("STORAGE_MEMORY_EXPERIENCE_ENABLE", False),

                es=experience_es if experience_es.host or experience_es.cloud_id else None,

                index_name=_get_str("STORAGE_MEMORY_EXPERIENCE_INDEX_NAME", _get_str("SDK_MEMORY_ES_COLLECTION", "agent_experiences")) or "agent_experiences",

                embedding_dims=_get_int("STORAGE_MEMORY_EXPERIENCE_EMBEDDING_DIMS", 1536),

            ),

        ),

        event_log=EventLogSettings(

            backend=(_get_str("STORAGE_EVENT_BACKEND", _get_str("EVENT_STORE_BACKEND", "local")) or "local").lower(),

            local_dir_template=_get_str("STORAGE_EVENT_LOCAL_DIR_TEMPLATE", _build_event_local_dir_template(storage_root_dir)) or _build_event_local_dir_template(storage_root_dir),

            mongo=event_mongo if event_mongo.url else None,

            db_name=_get_str("STORAGE_EVENT_MONGO_DB", _get_str("EVENT_STORE_MONGO_DB_NAME", "agent_events")) or "agent_events",

            collection_name=_get_str("STORAGE_EVENT_MONGO_COLLECTION", _get_str("EVENT_STORE_MONGO_COLLECTION_NAME", "event_logs")) or "event_logs",

            cache_limit_size=_get_int("STORAGE_EVENT_CACHE_LIMIT_SIZE", 1000),

            cache_limit_memory=_get_int("STORAGE_EVENT_CACHE_LIMIT_MEMORY", 50 * 1024 * 1024),

        ),

        state_store=StateStoreSettings(

            backend=(_get_str("STORAGE_STATE_BACKEND", _get_str("STATE_STORE_BACKEND", "local")) or "local").lower(),

            local_file_name=_get_str("STORAGE_STATE_LOCAL_FILE_NAME", _build_state_local_file_name(storage_root_dir)) or _build_state_local_file_name(storage_root_dir),

            mongo=state_mongo if state_mongo.url else None,

            db_name=_get_str("STORAGE_STATE_MONGO_DB", "agent_data") or "agent_data",

            collection_name=_get_str("STORAGE_STATE_MONGO_COLLECTION", "conversation_state") or "conversation_state",

        ),

    )
