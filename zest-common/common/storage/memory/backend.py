"""Memory storage — Layer 2 接口层。

职责：
    1. 定义后端契约（机制层接口）：
       - BaseMemoryBackend        基础记忆单分类 CRUD
       - ExperienceMemoryBackend   经验记忆向量存取检索
    2. 提供注册表（Resolver）：基于"存储类型"字符串选择对应的后端实现工厂。
       策略（选哪个后端）由 Layer 1 协调层 / 工厂决定，机制（怎么存）由 Layer 3 实现层负责。

设计原则：机制与策略分离。本层不含任何具体 I/O 实现，也不含跨分类业务编排
（业务编排放在 Layer 1 coordinator）。为向后兼容，本层保留了 read_all_categories
等跨分类便捷方法作为默认实现（具体后端可覆写）。
"""

from abc import ABC, abstractmethod
from typing import Any, Callable, Union

from common.storage.memory.base import ExperienceMemory, MemoryCategory, MemoryEntry


# ---------------------------------------------------------------------------
# Layer 2 接口：基础记忆后端契约
# ---------------------------------------------------------------------------


class BaseMemoryBackend(ABC):
    """基础记忆后端契约（Layer 2）。

    只关心单分类的读 / 写 / 改 / 删 / 存在性判断，不关心经验记忆检索。
    具体实现见 Layer 3：FileMemoryStore / ESBaseMemoryStore / CachedBaseMemoryStore。
    """

    @abstractmethod
    def read_category(self, user_id: str, category: MemoryCategory) -> str:
        ...

    @abstractmethod
    def read_category_entries(self, user_id: str, entry_ids: list[str] | None, category: MemoryCategory) -> list[MemoryEntry]:
        ...

    @abstractmethod
    def write_category(
        self, user_id: str, category: MemoryCategory, entry: MemoryEntry | str, *, mode: str = "append"
    ) -> str:
        ...

    @abstractmethod
    def update_entry(self, user_id: str, category: MemoryCategory, entry: MemoryEntry) -> bool:
        ...

    @abstractmethod
    def delete_entry(self, user_id: str, category: MemoryCategory, entry_id: str) -> bool:
        ...

    @abstractmethod
    def exists_category(self, user_id: str, category: MemoryCategory) -> bool:
        ...

    # -- 跨分类便捷方法（默认实现，具体后端可覆写）。保留以向后兼容直接使用后端的调用方。--
    def read_all_categories(self, user_id: str) -> dict[str, str]:
        return {cat.value: self.read_category(user_id, cat) for cat in MemoryCategory}

    def read_base_memory(self, user_id: str) -> str:
        cats = self.read_all_categories(user_id)
        parts = []
        for cat in MemoryCategory:
            val = cats.get(cat.value, "")
            if val:
                parts.append(f"[{cat.value}]\n{val}")
        return "\n".join(parts) if parts else ""

    def write_base_memory(self, user_id: str, content: str | dict) -> None:
        if isinstance(content, dict) and "category" in content:
            cat_str = content.pop("category")
            try:
                cat = MemoryCategory(cat_str)
            except ValueError:
                cat = MemoryCategory.PROFILE
            if isinstance(content, dict):
                entry = MemoryEntry(
                    name=content.get("name", ""),
                    description=content.get("description", ""),
                    content=content.get("content", str(content)),
                )
            else:
                entry = MemoryEntry(content=str(content))
            self.write_category(user_id, cat, entry, mode="append")
        elif isinstance(content, str):
            entry = MemoryEntry(content=content)
            self.write_category(user_id, MemoryCategory.PROFILE, entry, mode="append")
        else:
            entry = MemoryEntry(content=str(content))
            self.write_category(user_id, MemoryCategory.PROFILE, entry, mode="append")

    def exists_base_memory(self, user_id: str) -> bool:
        return any(self.exists_category(user_id, cat) for cat in MemoryCategory)


# ---------------------------------------------------------------------------
# Layer 2 接口：经验记忆后端契约
# ---------------------------------------------------------------------------


class ExperienceMemoryBackend(ABC):
    """经验记忆后端契约（Layer 2）。

    只关心经验的存 / 改 / 向量检索，不关心基础记忆 CRUD。
    具体实现见 Layer 3：ESMemoryStore。
    """

    @abstractmethod
    def save_experience(self, experience: ExperienceMemory) -> str:
        ...

    @abstractmethod
    def update_experience(self, doc_id: str, **kwargs: Any) -> bool:
        ...

    @abstractmethod
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
        ...


# ---------------------------------------------------------------------------
# Layer 2 注册表（Resolver）：存储类型 -> 后端工厂
# ---------------------------------------------------------------------------


class BaseMemoryBackendRegistry:
    """基础记忆后端注册表。

    Layer 2 的"选择"职责：根据存储类型字符串（如 'local' / 'es'）解析到对应
    Layer 3 实现的工厂函数。新增后端只需实现 BaseMemoryBackend 并 register。
    """

    _factories: dict[str, Callable[..., BaseMemoryBackend]] = {}

    @classmethod
    def register(cls, backend_type: str, factory: Callable[..., BaseMemoryBackend]) -> Callable[..., BaseMemoryBackend]:
        backend_type = backend_type.lower()
        cls._factories[backend_type] = factory
        return factory

    @classmethod
    def create(cls, backend_type: str, **kwargs: Any) -> BaseMemoryBackend:
        backend_type = backend_type.lower()
        factory = cls._factories.get(backend_type)
        if factory is None:
            raise ValueError(
                f"不支持的基础记忆存储后端: {backend_type}，已注册: {list(cls._factories)}"
            )
        return factory(**kwargs)

    @classmethod
    def supported(cls) -> list[str]:
        return list(cls._factories)


class ExperienceMemoryBackendRegistry:
    """经验记忆后端注册表。语义同 BaseMemoryBackendRegistry。"""

    _factories: dict[str, Callable[..., ExperienceMemoryBackend]] = {}

    @classmethod
    def register(cls, backend_type: str, factory: Callable[..., ExperienceMemoryBackend]) -> Callable[..., ExperienceMemoryBackend]:
        backend_type = backend_type.lower()
        cls._factories[backend_type] = factory
        return factory

    @classmethod
    def create(cls, backend_type: str, **kwargs: Any) -> ExperienceMemoryBackend:
        backend_type = backend_type.lower()
        factory = cls._factories.get(backend_type)
        if factory is None:
            raise ValueError(
                f"不支持的经验记忆存储后端: {backend_type}，已注册: {list(cls._factories)}"
            )
        return factory(**kwargs)

    @classmethod
    def supported(cls) -> list[str]:
        return list(cls._factories)


# ---------------------------------------------------------------------------
# 向后兼容别名
# ---------------------------------------------------------------------------

# 旧代码以 MemoryStore 作为联合类型标注（base_store / experience_store 均可能）。
# 这里定义为两个后端接口的 Union，保持旧类型标注可用。
MemoryStore = Union[BaseMemoryBackend, ExperienceMemoryBackend]

# 旧 BaseMemoryStore 现等价于基础记忆后端接口。
BaseMemoryStore = BaseMemoryBackend
