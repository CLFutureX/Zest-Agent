"""Memory storage utilities — 序列化 / 解析 / 索引辅助函数。

纯函数，无副作用，供 Layer 3 后端实现共享。
"""

from datetime import datetime
import re

from common.storage.memory.base import MemoryCategory, MemoryEntry


ENTRY_SEPARATOR = "\n---\n"


def entry_to_md(entry: MemoryEntry) -> str:
    """将 MemoryEntry 序列化为 markdown 段落。"""
    return (
        f"<id>{entry.id}</id>\n"
        f"<name>{entry.name}</name>\n"
        f"<description>{entry.description}</description>\n"
        f"<content>{entry.content}</content>\n"
        f"<created_time>{entry.created_at}</created_time>\n"
        f"<updated_time>{entry.updated_at}</updated_time>\n"
        f"{ENTRY_SEPARATOR}"
    )


def parse_entries(md_text: str) -> list[MemoryEntry]:
    """从 markdown 文本中解析出 MemoryEntry 列表。"""
    entries: list[MemoryEntry] = []
    blocks = md_text.split(ENTRY_SEPARATOR)

    for block in blocks:
        if not block.strip():
            continue

        id_match = re.search(r"<id>(.*?)</id>", block)
        if not id_match:
            continue

        name_match = re.search(r"<name>(.*?)</name>", block, re.DOTALL)
        desc_match = re.search(r"<description>(.*?)</description>", block, re.DOTALL)
        content_match = re.search(r"<content>(.*?)</content>", block, re.DOTALL)
        created_time_match = re.search(r"<created_time>(.*?)</created_time>", block)
        updated_time_match = re.search(r"<updated_time>(.*?)</updated_time>", block)

        entry_id = id_match.group(1)
        name = name_match.group(1) if name_match else ""
        desc = desc_match.group(1) if desc_match else ""
        content = content_match.group(1) if content_match else ""
        created_time = created_time_match.group(1) if created_time_match else datetime.now().strftime("%Y-%m-%d %H:%M")
        updated_time = updated_time_match.group(1) if updated_time_match else created_time

        entries.append(MemoryEntry(
            id=entry_id,
            name=name,
            description=desc,
            content=content,
            created_at=created_time,
            updated_at=updated_time,
        ))

    return entries


def build_index_key(user_id: str, category: MemoryCategory, entry_id: str) -> str:
    return f"{category.value}:{entry_id}:{user_id}"


def extract_index_version(index_map: dict[str, int], user_id: str, category: MemoryCategory) -> int:
    prefix = f"{category.value}:"
    suffix = f":{user_id}"
    versions = [
        version for key, version in index_map.items()
        if key.startswith(prefix) and key.endswith(suffix)
    ]
    return max(versions, default=0)


def merge_category_entries(entries: list[MemoryEntry], entry: MemoryEntry) -> list[MemoryEntry]:
    merged = list(entries)
    for index, current in enumerate(merged):
        if current.id == entry.id:
            merged[index] = entry
            return merged
    merged.append(entry)
    return merged
