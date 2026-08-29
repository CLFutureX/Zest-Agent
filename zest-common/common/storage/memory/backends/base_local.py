"""Layer 3 实现 — 本地文件基础记忆后端 (FileMemoryStore)。

类名保留为 FileMemoryStore 以向后兼容现有调用方与测试。
机制层：仅负责单分类 markdown 文件的读写。
"""

from datetime import datetime

from common.storage.file_store import FileStore
from common.storage.memory.backend import BaseMemoryBackend
from common.storage.memory.base import MemoryCategory, MemoryEntry
from common.storage.memory.utils import entry_to_md, parse_entries, merge_category_entries
from common.logger import get_logger

logger = get_logger(__name__)


class FileMemoryStore(BaseMemoryBackend):
    """基于 FileStore 的本地记忆存储。"""

    CATEGORY_FILE_MAP = {
        MemoryCategory.PROFILE: "_profile.md",
        MemoryCategory.PREFERENCES: "_preferences.md",
        MemoryCategory.DOMAIN_CONTEXT: "_domain_context.md",
        MemoryCategory.PROJECT_CONTEXT: "_project_context.md",
    }

    def __init__(self, fs: FileStore, base_dir: str = "memory") -> None:
        self._fs = fs
        self._base_dir = base_dir

    def _category_path(self, user_id: str, category: MemoryCategory) -> str:
        suffix = self.CATEGORY_FILE_MAP[category]
        return f"{self._base_dir}/{user_id}{suffix}"

    def read_category(self, user_id: str, category: MemoryCategory) -> str:
        try:
            raw = self._fs.read(self._category_path(user_id, category))
            return raw.strip() if raw else ""
        except FileNotFoundError:
            return ""
        except Exception as e:
            logger.error(f"加载用户 {user_id} 分类 {category.value} 失败: {e}")
            return ""

    def read_category_entries(self, user_id: str, entry_ids: list[str] | None, category: MemoryCategory) -> list[MemoryEntry]:
        md_text = self.read_category(user_id, category)
        if not md_text:
            logger.debug("本地基础记忆为空: user_id=%s category=%s", user_id, category.value)
            return []

        entries = parse_entries(md_text)
        if entry_ids:
            filtered_entries = [entry for entry in entries if entry.id in entry_ids]
            logger.info(
                "本地基础记忆按ID读取: user_id=%s category=%s requested_ids=%s returned=%s",
                user_id,
                category.value,
                entry_ids,
                len(filtered_entries),
            )
            return filtered_entries
        logger.info("本地基础记忆读取: user_id=%s category=%s returned=%s", user_id, category.value, len(entries))
        return entries

    def write_category(
        self, user_id: str, category: MemoryCategory, entry: MemoryEntry | str | None = None, *, mode: str = "append"
    ) -> str | None:
        if entry is None or (isinstance(entry, str) and not entry.strip()):
            self._fs.write(self._category_path(user_id, category), "")
            logger.info(f"用户 {user_id} 分类 {category.value} 已初始化为空")
            return None

        if isinstance(entry, str):
            entry = MemoryEntry(content=entry)

        if mode == "overwrite":
            payload = entry_to_md(entry)
        else:
            existing = self.read_category(user_id, category)
            entries = parse_entries(existing)
            entries = merge_category_entries(entries, entry)
            payload = "".join(entry_to_md(e) for e in entries)

        self._fs.write(self._category_path(user_id, category), payload)
        logger.info(f"用户 {user_id} 分类 {category.value} 已写入（mode={mode}, id={entry.id}）")
        return entry.id

    def update_entry(self, user_id: str, category: MemoryCategory, entry: MemoryEntry) -> bool:
        existing = self.read_category(user_id, category)
        entries = parse_entries(existing)
        for i, current in enumerate(entries):
            if current.id == entry.id:
                entry.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
                entries[i] = entry
                payload = "".join(entry_to_md(item) for item in entries)
                self._fs.write(self._category_path(user_id, category), payload)
                logger.info(f"用户 {user_id} 分类 {category.value} 条目 {entry.id} 已更新")
                return True
        return False

    def delete_entry(self, user_id: str, category: MemoryCategory, entry_id: str) -> bool:
        existing = self.read_category(user_id, category)
        entries = parse_entries(existing)
        new_entries = [entry for entry in entries if entry.id != entry_id]
        if len(new_entries) == len(entries):
            return False
        payload = "".join(entry_to_md(entry) for entry in new_entries) if new_entries else ""
        self._fs.write(self._category_path(user_id, category), payload)
        logger.info(f"用户 {user_id} 分类 {category.value} 条目 {entry_id} 已删除")
        return True

    def exists_category(self, user_id: str, category: MemoryCategory) -> bool:
        try:
            raw = self._fs.read(self._category_path(user_id, category))
            return bool(raw and raw.strip())
        except FileNotFoundError:
            return False
