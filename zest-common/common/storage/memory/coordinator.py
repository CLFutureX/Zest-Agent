"""Memory storage — Layer 1 协调层。

职责：
    - 对外暴露领域存储对象 BaseMemoryStorage / ExperienceMemoryStorage。
    - 持有策略（选择的后端类型）并内部引用一个 Layer 2 后端实例。
    - 提供跨分类业务编排（read_all_categories / read_base_memory / exists_base_memory），
      并将单分类 CRUD / 经验向量存取委托给后端。

对外"返回"的即本层协调对象；后端由 Layer 2 注册表按存储类型解析，Layer 3 负责真正实现。
"""

from typing import Any

from common.storage.memory.backend import BaseMemoryBackend, ExperienceMemoryBackend
from common.storage.memory.base import ExperienceMemory, MemoryCategory, MemoryEntry


class BaseMemoryStorage:
    """基础记忆存储对象（Layer 1 协调层）。

    内部引用一个 BaseMemoryBackend，对外提供领域 API 与跨分类编排。
    """

    def __init__(self, backend: BaseMemoryBackend) -> None:
        self._backend = backend

    @property
    def backend(self) -> BaseMemoryBackend:
        """底层后端实例（供需要做 isinstance 判断的调用方使用）。"""
        return self._backend

    # -- 单分类 CRUD：委托 --
    def read_category(self, user_id: str, category: MemoryCategory) -> str:
        return self._backend.read_category(user_id, category)

    def read_category_entries(self, user_id: str, entry_ids: list[str] | None, category: MemoryCategory) -> list[MemoryEntry]:
        return self._backend.read_category_entries(user_id, entry_ids, category)

    def write_category(self, user_id: str, category: MemoryCategory, entry: MemoryEntry | str, *, mode: str = "append") -> str | None:
        return self._backend.write_category(user_id, category, entry, mode=mode)

    def update_entry(self, user_id: str, category: MemoryCategory, entry: MemoryEntry) -> bool:
        return self._backend.update_entry(user_id, category, entry)

    def delete_entry(self, user_id: str, category: MemoryCategory, entry_id: str) -> bool:
        return self._backend.delete_entry(user_id, category, entry_id)

    def exists_category(self, user_id: str, category: MemoryCategory) -> bool:
        return self._backend.exists_category(user_id, category)

    # -- 跨分类业务编排：委托后端默认实现（后端可自行覆写）--
    def read_all_categories(self, user_id: str) -> dict[str, str]:
        return self._backend.read_all_categories(user_id)

    def read_base_memory(self, user_id: str) -> str:
        return self._backend.read_base_memory(user_id)

    def write_base_memory(self, user_id: str, content: str | dict) -> None:
        return self._backend.write_base_memory(user_id, content)

    def exists_base_memory(self, user_id: str) -> bool:
        return self._backend.exists_base_memory(user_id)


class ExperienceMemoryStorage:
    """经验记忆存储对象（Layer 1 协调层）。

    内部引用一个 ExperienceMemoryBackend，对外提供经验存取与向量检索。
    """

    def __init__(self, backend: ExperienceMemoryBackend) -> None:
        self._backend = backend

    @property
    def backend(self) -> ExperienceMemoryBackend:
        """底层后端实例。"""
        return self._backend

    def save_experience(self, experience: ExperienceMemory) -> str:
        return self._backend.save_experience(experience)

    def update_experience(self, doc_id: str, **kwargs: Any) -> bool:
        return self._backend.update_experience(doc_id, **kwargs)

    def search_experiences(
        self,
        user_id: str,
        query: str,
        *,
        domain_type: str | None = None,
        feedback_type: str | None = None,
        k: int = 5,
        threshold: float = 0.85,
    ) -> list[tuple[ExperienceMemory, str]]:
        return self._backend.search_experiences(
            user_id, query,
            domain_type=domain_type, feedback_type=feedback_type,
            k=k, threshold=threshold,
        )
