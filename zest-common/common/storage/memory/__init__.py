"""Memory system public API.

Exports:
    - MemoryStore (abstract base)
    - FileMemoryStore, ESMemoryStore (backends)
    - MemoryCategory (enum: profile, preferences, domain_context, project_context)
    - MemoryEntry (dataclass: id, name, description, content)
    - create_memory_store (factory)
    - MemoryManager, ExperienceMemoryConsumer (business layer)
    - calculate_bm25_score (utility)
"""

from common.storage.memory.base import ExperienceMemory, ExecutionTrace

from common.storage.memory.store import (

    ESMemoryStore,

    FileMemoryStore,

    MemoryCategory,

    MemoryEntry,

    MemoryStore,

    entry_to_md,

    parse_entries,

)



__all__ = [

    # Abstract

    "MemoryStore",

    # Enum

    "MemoryCategory",

    # Models

    "MemoryEntry",

    # Backends

    "FileMemoryStore",

    "ESMemoryStore",

    # Base models

    "ExperienceMemory",

    "ExecutionTrace",

    # Utilities

    "parse_entries",

    "entry_to_md",

]
