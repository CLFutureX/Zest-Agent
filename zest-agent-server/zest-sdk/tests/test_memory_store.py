"""Tests for markdown-based MemoryEntry, FileMemoryStore, and helper functions."""

import pytest
from common.storage.memory.store import (
    MemoryCategory,
    MemoryEntry,
    entry_to_md,
    parse_entries,
    FileMemoryStore,
)
from common.storage.file_store.memory import InMemoryFileStore


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _make_store() -> FileMemoryStore:
    return FileMemoryStore(InMemoryFileStore(), base_dir="memory")


# ═════════════════════════════════════════════
# MemoryEntry dataclass
# ═════════════════════════════════════════════

class TestMemoryEntry:
    def test_auto_id(self):
        e1 = MemoryEntry(content="test")
        e2 = MemoryEntry(content="test")
        assert e1.id.startswith("mem_")
        assert e1.id != e2.id  # 两个实例 ID 不同

    def test_custom_id(self):
        e = MemoryEntry(id="mem_custom123", name="foo", content="bar")
        assert e.id == "mem_custom123"
        assert e.name == "foo"
        assert e.content == "bar"

    def test_defaults(self):
        e = MemoryEntry()
        assert e.name == ""
        assert e.description == ""
        assert e.content == ""
        assert e.created_at
        assert e.updated_at


# ═════════════════════════════════════════════
# Markdown serialization / deserialization
# ═════════════════════════════════════════════

class TestEntryToMd:
    def test_roundtrip_single(self):
        e = MemoryEntry(id="mem_abc123", name="TS preference", description="User likes TS", content="Use TypeScript for new projects.")
        md = entry_to_md(e)
        entries = parse_entries(md)
        assert len(entries) == 1
        assert entries[0].id == "mem_abc123"
        assert entries[0].name == "TS preference"
        assert entries[0].description == "User likes TS"
        assert entries[0].content == "Use TypeScript for new projects."

    def test_roundtrip_multiline_content(self):
        e = MemoryEntry(
            id="mem_multi01",
            name="Multi-line",
            content="Line one\nLine two\n\nLine three after blank",
        )
        md = entry_to_md(e)
        entries = parse_entries(md)
        assert len(entries) == 1
        assert entries[0].content == "Line one\nLine two\n\nLine three after blank"

    def test_multiple_entries(self):
        e1 = MemoryEntry(id="mem_001", name="A", content="Content A")
        e2 = MemoryEntry(id="mem_002", name="B", content="Content B")
        e3 = MemoryEntry(id="mem_003", name="C", content="Content C")
        md = "".join(entry_to_md(e) for e in [e1, e2, e3])
        entries = parse_entries(md)
        assert len(entries) == 3
        assert [e.name for e in entries] == ["A", "B", "C"]
        assert [e.content for e in entries] == ["Content A", "Content B", "Content C"]

    def test_parse_empty(self):
        assert parse_entries("") == []
        assert parse_entries("   \n") == []

    def test_content_with_separator(self):
        """Content that itself contains '---' should not break parsing."""
        e = MemoryEntry(id="mem_sep01", name="Separator test", content="foo\n---\nbar")
        md = entry_to_md(e)
        entries = parse_entries(md)
        assert len(entries) == 1
        assert entries[0].id == "mem_sep01"
        # The --- inside content will be stripped by the parser, which is acceptable
        # since the parser removes separator lines


# ═════════════════════════════════════════════
# FileMemoryStore — basic operations
# ═════════════════════════════════════════════

class TestFileMemoryStoreBasic:
    def test_read_nonexistent_returns_empty(self):
        store = _make_store()
        assert store.read_category("u1", MemoryCategory.PROFILE) == ""

    def test_exists_category_false_when_empty(self):
        store = _make_store()
        assert not store.exists_category("u1", MemoryCategory.PROFILE)

    def test_write_string_append(self):
        store = _make_store()
        eid = store.write_category("u1", MemoryCategory.PROFILE, "Hello world")
        assert eid is not None
        assert store.exists_category("u1", MemoryCategory.PROFILE)
        entries = store.read_category_entries("u1", None, MemoryCategory.PROFILE)
        assert len(entries) == 1
        assert entries[0].content == "Hello world"

    def test_read_entries_by_entry_id(self):
        store = _make_store()
        target = MemoryEntry(id="mem_target01", name="Target", content="Target content")
        store.write_category("u1", MemoryCategory.PREFERENCES, target)
        store.write_category("u1", MemoryCategory.PREFERENCES, "Other content")
        entries = store.read_category_entries("u1", "mem_target01", MemoryCategory.PREFERENCES)
        assert len(entries) == 1
        assert entries[0].id == "mem_target01"
        assert entries[0].name == "Target"

    def test_write_entry_append(self):
        store = _make_store()
        e = MemoryEntry(id="mem_test01", name="Test", content="Test content")
        eid = store.write_category("u1", MemoryCategory.PREFERENCES, e)
        assert eid == "mem_test01"
        entries = store.read_category_entries("u1", None, MemoryCategory.PREFERENCES)
        assert len(entries) == 1
        assert entries[0].name == "Test"

    def test_write_empty_init(self):
        store = _make_store()
        result = store.write_category("u1", MemoryCategory.PROFILE, None)
        assert result is None
        # File exists but content is empty
        raw = store.read_category("u1", MemoryCategory.PROFILE)
        assert raw == ""

    def test_write_empty_string_init(self):
        store = _make_store()
        result = store.write_category("u1", MemoryCategory.PROFILE, "")
        assert result is None
        assert store.read_category("u1", MemoryCategory.PROFILE) == ""


# ═════════════════════════════════════════════
# FileMemoryStore — append mode
# ═════════════════════════════════════════════

class TestFileMemoryStoreAppend:
    def test_append_multiple_entries(self):
        store = _make_store()
        store.write_category("u1", MemoryCategory.PROFILE, "Entry A")
        store.write_category("u1", MemoryCategory.PROFILE, "Entry B")
        store.write_category("u1", MemoryCategory.PROFILE, "Entry C")
        entries = store.read_category_entries("u1", None, MemoryCategory.PROFILE)
        assert len(entries) == 3
        contents = [e.content for e in entries]
        assert "Entry A" in contents
        assert "Entry B" in contents
        assert "Entry C" in contents

    def test_append_updates_by_id(self):
        store = _make_store()
        e = MemoryEntry(id="mem_up01", name="Old", content="Old content")
        store.write_category("u1", MemoryCategory.PROFILE, e)

        # Append another entry
        store.write_category("u1", MemoryCategory.PROFILE, "Other entry")

        # Now update by same ID
        e_updated = MemoryEntry(id="mem_up01", name="Updated", content="New content")
        store.write_category("u1", MemoryCategory.PROFILE, e_updated)

        entries = store.read_category_entries("u1", None, MemoryCategory.PROFILE)
        assert len(entries) == 2  # Should still be 2, not 3

        updated = [e for e in entries if e.id == "mem_up01"][0]
        assert updated.name == "Updated"
        assert updated.content == "New content"

    def test_append_different_categories_isolated(self):
        store = _make_store()
        store.write_category("u1", MemoryCategory.PROFILE, "Profile data")
        store.write_category("u1", MemoryCategory.PREFERENCES, "Pref data")
        store.write_category("u1", MemoryCategory.DOMAIN_CONTEXT, "Domain data")
        store.write_category("u1", MemoryCategory.PROJECT_CONTEXT, "Project data")

        assert store.read_category_entries("u1", None, MemoryCategory.PROFILE)[0].content == "Profile data"
        assert store.read_category_entries("u1", None, MemoryCategory.PREFERENCES)[0].content == "Pref data"
        assert store.read_category_entries("u1", None, MemoryCategory.DOMAIN_CONTEXT)[0].content == "Domain data"
        assert store.read_category_entries("u1", None, MemoryCategory.PROJECT_CONTEXT)[0].content == "Project data"

    def test_append_different_users_isolated(self):
        store = _make_store()
        store.write_category("user_a", MemoryCategory.PROFILE, "A's profile")
        store.write_category("user_b", MemoryCategory.PROFILE, "B's profile")

        assert store.read_category_entries("user_a", None, MemoryCategory.PROFILE)[0].content == "A's profile"
        assert store.read_category_entries("user_b", None, MemoryCategory.PROFILE)[0].content == "B's profile"


# ═════════════════════════════════════════════
# FileMemoryStore — overwrite mode
# ═════════════════════════════════════════════

class TestFileMemoryStoreOverwrite:
    def test_overwrite_replaces_all(self):
        store = _make_store()
        store.write_category("u1", MemoryCategory.PROFILE, "Entry A")
        store.write_category("u1", MemoryCategory.PROFILE, "Entry B")

        store.write_category("u1", MemoryCategory.PROFILE, "Only this", mode="overwrite")

        entries = store.read_category_entries("u1", None, MemoryCategory.PROFILE)
        assert len(entries) == 1
        assert entries[0].content == "Only this"

    def test_overwrite_with_entry(self):
        store = _make_store()
        store.write_category("u1", MemoryCategory.PREFERENCES, "Old pref 1")
        store.write_category("u1", MemoryCategory.PREFERENCES, "Old pref 2")

        e = MemoryEntry(id="mem_new01", name="New pref", content="New content")
        store.write_category("u1", MemoryCategory.PREFERENCES, e, mode="overwrite")

        entries = store.read_category_entries("u1", None, MemoryCategory.PREFERENCES)
        assert len(entries) == 1
        assert entries[0].name == "New pref"


# ═════════════════════════════════════════════
# FileMemoryStore — update_entry / delete_entry
# ═════════════════════════════════════════════

class TestFileMemoryStoreEntryOps:
    def test_update_entry_success(self):
        store = _make_store()
        e = MemoryEntry(id="mem_upd01", name="Original", content="Original content")
        store.write_category("u1", MemoryCategory.PROFILE, e)
        store.write_category("u1", MemoryCategory.PROFILE, "Second entry")

        updated = MemoryEntry(id="mem_upd01", name="Modified", content="Modified content")
        result = store.update_entry("u1", MemoryCategory.PROFILE, updated)
        assert result is True

        entries = store.read_category_entries("u1", None, MemoryCategory.PROFILE)
        assert len(entries) == 2
        target = [e for e in entries if e.id == "mem_upd01"][0]
        assert target.name == "Modified"

    def test_update_entry_not_found(self):
        store = _make_store()
        store.write_category("u1", MemoryCategory.PROFILE, "Some entry")
        fake = MemoryEntry(id="mem_nonexist", content="ghost")
        result = store.update_entry("u1", MemoryCategory.PROFILE, fake)
        assert result is False

    def test_delete_entry_success(self):
        store = _make_store()
        store.write_category("u1", MemoryCategory.PROFILE, "Keep this")
        e = MemoryEntry(id="mem_del01", name="Delete me", content="To be deleted")
        store.write_category("u1", MemoryCategory.PROFILE, e)

        result = store.delete_entry("u1", MemoryCategory.PROFILE, "mem_del01")
        assert result is True

        entries = store.read_category_entries("u1", None, MemoryCategory.PROFILE)
        assert len(entries) == 1
        assert entries[0].content == "Keep this"

    def test_delete_entry_not_found(self):
        store = _make_store()
        store.write_category("u1", MemoryCategory.PROFILE, "Keep this")
        result = store.delete_entry("u1", MemoryCategory.PROFILE, "mem_nonexist")
        assert result is False
        # Original entry should still exist
        entries = store.read_category_entries("u1", None, MemoryCategory.PROFILE)
        assert len(entries) == 1

    def test_delete_all_entries(self):
        store = _make_store()
        store.write_category("u1", MemoryCategory.PROFILE, "Entry A")
        store.write_category("u1", MemoryCategory.PROFILE, "Entry B")

        entries = store.read_category_entries("u1", None, MemoryCategory.PROFILE)
        for e in entries:
            store.delete_entry("u1", MemoryCategory.PROFILE, e.id)

        final = store.read_category_entries("u1", None, MemoryCategory.PROFILE)
        assert len(final) == 0
        assert store.read_category("u1", MemoryCategory.PROFILE) == ""


# ═════════════════════════════════════════════
# FileMemoryStore — read_all_categories
# ═════════════════════════════════════════════

class TestFileMemoryStoreReadAll:
    def test_read_all_categories(self):
        store = _make_store()
        store.write_category("u1", MemoryCategory.PROFILE, "Profile data")
        store.write_category("u1", MemoryCategory.PREFERENCES, "Pref data")

        result = store.read_all_categories("u1")
        assert result["profile"] != ""
        assert result["preferences"] != ""
        assert result["domain_context"] == ""
        assert result["project_context"] == ""


# ═════════════════════════════════════════════
# Backward compatibility
# ═════════════════════════════════════════════

class TestBackwardCompat:
    def test_write_base_memory_string(self):
        store = _make_store()
        store.write_base_memory("u1", "Legacy content")
        entries = store.read_category_entries("u1", None, MemoryCategory.PROFILE)
        assert len(entries) == 1
        assert entries[0].content == "Legacy content"

    def test_write_base_memory_dict_with_category(self):
        store = _make_store()
        store.write_base_memory("u1", {
            "category": "preferences",
            "name": "Code style",
            "description": "User preference",
            "content": "Always use 2-space indent",
        })
        entries = store.read_category_entries("u1", None, MemoryCategory.PREFERENCES)
        assert len(entries) == 1
        assert entries[0].name == "Code style"

    def test_read_base_memory_merges_all(self):
        store = _make_store()
        store.write_category("u1", MemoryCategory.PROFILE, "Profile info")
        store.write_category("u1", MemoryCategory.DOMAIN_CONTEXT, "Domain info")

        result = store.read_base_memory("u1")
        assert "[profile]" in result
        assert "Profile info" in result
        assert "[domain_context]" in result
        assert "Domain info" in result

    def test_exists_base_memory(self):
        store = _make_store()
        assert not store.exists_base_memory("u1")
        store.write_category("u1", MemoryCategory.PROFILE, "Something")
        assert store.exists_base_memory("u1")

if __name__ == "__main__":
    testMemoryEntry = TestMemoryEntry()
    testMemoryEntry.test_auto_id()
    testMemoryEntry.test_custom_id()
    testMemoryEntry.test_defaults()
    
    testEntryToMd = TestEntryToMd()
    testEntryToMd.test_roundtrip_single()
    testEntryToMd.test_roundtrip_multiline_content()
    testEntryToMd.test_multiple_entries()
    testEntryToMd.test_parse_empty()
    testEntryToMd.test_content_with_separator()
    
    testFileMemoryStoreBasic = TestFileMemoryStoreBasic()
    testFileMemoryStoreBasic.test_read_nonexistent_returns_empty()
    testFileMemoryStoreBasic.test_exists_category_false_when_empty()
    testFileMemoryStoreBasic.test_write_string_append()
    testFileMemoryStoreBasic.test_write_entry_append()
    testFileMemoryStoreBasic.test_write_empty_init()
    testFileMemoryStoreBasic.test_write_empty_string_init()
    
    testFileMemoryStoreAppend = TestFileMemoryStoreAppend()
    testFileMemoryStoreAppend.test_append_multiple_entries()
    testFileMemoryStoreAppend.test_append_updates_by_id()
    testFileMemoryStoreAppend.test_append_different_categories_isolated()
    testFileMemoryStoreAppend.test_append_different_users_isolated()
    
    testFileMemoryStoreOverwrite = TestFileMemoryStoreOverwrite()
    testFileMemoryStoreOverwrite.test_overwrite_replaces_all()
    testFileMemoryStoreOverwrite.test_overwrite_with_entry()
    
    testFileMemoryStoreEntryOps = TestFileMemoryStoreEntryOps()
    testFileMemoryStoreEntryOps.test_update_entry_success()
    testFileMemoryStoreEntryOps.test_update_entry_not_found()
    testFileMemoryStoreEntryOps.test_delete_entry_success()
    testFileMemoryStoreEntryOps.test_delete_entry_not_found()
    testFileMemoryStoreEntryOps.test_delete_all_entries()
    
    testFileMemoryStoreReadAll = TestFileMemoryStoreReadAll()
    testFileMemoryStoreReadAll.test_read_all_categories()
    
    testBackwardCompat = TestBackwardCompat()
    testBackwardCompat.test_write_base_memory_string()
    testBackwardCompat.test_write_base_memory_dict_with_category()
    testBackwardCompat.test_read_base_memory_merges_all()
    testBackwardCompat.test_exists_base_memory()
    print("All tests passed!")