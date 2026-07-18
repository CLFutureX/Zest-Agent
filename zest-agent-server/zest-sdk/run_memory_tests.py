#!/usr/bin/env python3
"""Run memory store tests directly (bypass pytest import overhead)."""
import sys
import os

# Add SDK to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.'))

from common.storage.memory.store import MemoryCategory, MemoryEntry, entry_to_md, parse_entries, FileMemoryStore
from common.storage.file_store.memory import InMemoryFileStore


passed = 0
failed = 0
errors = []


def test(name, func):
    global passed, failed
    try:
        func()
        passed += 1
        print(f"  ✓ {name}")
    except Exception as e:
        failed += 1
        errors.append((name, e))
        print(f"  ✗ {name}: {e}")


def _make_store():
    return FileMemoryStore(InMemoryFileStore(), base_dir="memory")


# ── MemoryEntry ──
print("\n── MemoryEntry ──")

def test_auto_id():
    e1, e2 = MemoryEntry(content="x"), MemoryEntry(content="x")
    assert e1.id.startswith("mem_")
    assert e1.id != e2.id

test("auto_id", test_auto_id)

def test_custom_id():
    e = MemoryEntry(id="mem_x", name="n", content="c")
    assert e.id == "mem_x" and e.name == "n" and e.content == "c"

test("custom_id", test_custom_id)


# ── Markdown roundtrip ──
print("\n── Markdown roundtrip ──")

def test_roundtrip_single():
    e = MemoryEntry(id="mem_abc", name="Title", description="Desc", content="Body")
    entries = parse_entries(entry_to_md(e))
    assert len(entries) == 1
    assert entries[0].id == "mem_abc"
    assert entries[0].name == "Title"
    assert entries[0].description == "Desc"
    assert entries[0].content == "Body"

test("roundtrip_single", test_roundtrip_single)

def test_roundtrip_multiple():
    es = [
        MemoryEntry(id="mem_1", name="A", content="CA"),
        MemoryEntry(id="mem_2", name="B", content="CB"),
        MemoryEntry(id="mem_3", name="C", content="CC"),
    ]
    md = "".join(entry_to_md(e) for e in es)
    entries = parse_entries(md)
    assert len(entries) == 3
    assert [e.name for e in entries] == ["A", "B", "C"]

test("roundtrip_multiple", test_roundtrip_multiple)

def test_parse_empty():
    assert parse_entries("") == []

test("parse_empty", test_parse_empty)


# ── FileMemoryStore: basic ──
print("\n── FileMemoryStore: basic ──")

def test_read_nonexistent():
    s = _make_store()
    assert s.read_category("u1", MemoryCategory.PROFILE) == ""

test("read_nonexistent", test_read_nonexistent)

def test_write_string():
    s = _make_store()
    eid = s.write_category("u1", MemoryCategory.PROFILE, "Hello")
    assert eid is not None
    entries = s.read_category_entries("u1", None, MemoryCategory.PROFILE)
    assert len(entries) == 1 and entries[0].content == "Hello"

test("write_string", test_write_string)

def test_write_entry():
    s = _make_store()
    e = MemoryEntry(id="mem_t1", name="Test", content="TC")
    eid = s.write_category("u1", MemoryCategory.PREFERENCES, e)
    assert eid == "mem_t1"

test("write_entry", test_write_entry)

def test_write_empty():
    s = _make_store()
    r = s.write_category("u1", MemoryCategory.PROFILE, None)
    assert r is None
    assert s.read_category("u1", MemoryCategory.PROFILE) == ""

test("write_empty", test_write_empty)


# ── FileMemoryStore: append ──
print("\n── FileMemoryStore: append ──")

def test_append_multiple():
    s = _make_store()
    s.write_category("u1", MemoryCategory.PROFILE, "A")
    s.write_category("u1", MemoryCategory.PROFILE, "B")
    s.write_category("u1", MemoryCategory.PROFILE, "C")
    entries = s.read_category_entries("u1", None, MemoryCategory.PROFILE)
    assert len(entries) == 3

test("append_multiple", test_append_multiple)

def test_append_update_by_id():
    s = _make_store()
    s.write_category("u1", MemoryCategory.PROFILE, MemoryEntry(id="mem_x", content="Old"))
    s.write_category("u1", MemoryCategory.PROFILE, "Other")
    s.write_category("u1", MemoryCategory.PROFILE, MemoryEntry(id="mem_x", content="New"))
    entries = s.read_category_entries("u1", None, MemoryCategory.PROFILE)
    assert len(entries) == 2
    updated = [e for e in entries if e.id == "mem_x"][0]
    assert updated.content == "New"

test("append_update_by_id", test_append_update_by_id)

def test_categories_isolated():
    s = _make_store()
    s.write_category("u1", MemoryCategory.PROFILE, "P")
    s.write_category("u1", MemoryCategory.PREFERENCES, "PR")
    assert s.read_category_entries("u1", None, MemoryCategory.PROFILE)[0].content == "P"
    assert s.read_category_entries("u1", None, MemoryCategory.PREFERENCES)[0].content == "PR"

test("categories_isolated", test_categories_isolated)

def test_users_isolated():
    s = _make_store()
    s.write_category("ua", MemoryCategory.PROFILE, "A")
    s.write_category("ub", MemoryCategory.PROFILE, "B")
    assert s.read_category_entries("ua", None, MemoryCategory.PROFILE)[0].content == "A"
    assert s.read_category_entries("ub", None, MemoryCategory.PROFILE)[0].content == "B"

test("users_isolated", test_users_isolated)


# ── FileMemoryStore: overwrite ──
print("\n── FileMemoryStore: overwrite ──")

def test_overwrite_replaces_all():
    s = _make_store()
    s.write_category("u1", MemoryCategory.PROFILE, "A")
    s.write_category("u1", MemoryCategory.PROFILE, "B")
    s.write_category("u1", MemoryCategory.PROFILE, "Only", mode="overwrite")
    entries = s.read_category_entries("u1", None, MemoryCategory.PROFILE)
    assert len(entries) == 1 and entries[0].content == "Only"

test("overwrite_replaces_all", test_overwrite_replaces_all)


# ── FileMemoryStore: update/delete ──
print("\n── FileMemoryStore: update/delete ──")

def test_update_entry():
    s = _make_store()
    s.write_category("u1", MemoryCategory.PROFILE, MemoryEntry(id="mem_u1", name="Orig", content="C1"))
    s.write_category("u1", MemoryCategory.PROFILE, "C2")
    ok = s.update_entry("u1", MemoryCategory.PROFILE, MemoryEntry(id="mem_u1", name="Mod", content="Cnew"))
    assert ok
    entries = s.read_category_entries("u1", None, MemoryCategory.PROFILE)
    assert [e for e in entries if e.id == "mem_u1"][0].name == "Mod"

test("update_entry", test_update_entry)

def test_update_not_found():
    s = _make_store()
    s.write_category("u1", MemoryCategory.PROFILE, "X")
    assert not s.update_entry("u1", MemoryCategory.PROFILE, MemoryEntry(id="mem_fake", content="X"))

test("update_not_found", test_update_not_found)

def test_delete_entry():
    s = _make_store()
    s.write_category("u1", MemoryCategory.PROFILE, "Keep")
    s.write_category("u1", MemoryCategory.PROFILE, MemoryEntry(id="mem_d1", content="Delete"))
    ok = s.delete_entry("u1", MemoryCategory.PROFILE, "mem_d1")
    assert ok
    entries = s.read_category_entries("u1", None, MemoryCategory.PROFILE)
    assert len(entries) == 1 and entries[0].content == "Keep"

test("delete_entry", test_delete_entry)

def test_delete_not_found():
    s = _make_store()
    s.write_category("u1", MemoryCategory.PROFILE, "Keep")
    assert not s.delete_entry("u1", MemoryCategory.PROFILE, "mem_fake")

test("delete_not_found", test_delete_not_found)


# ── Backward compat ──
print("\n── Backward compatibility ──")

def test_write_base_memory_str():
    s = _make_store()
    s.write_base_memory("u1", "Legacy")
    entries = s.read_category_entries("u1", None, MemoryCategory.PROFILE)
    assert len(entries) == 1 and entries[0].content == "Legacy"

test("write_base_memory_str", test_write_base_memory_str)

def test_write_base_memory_dict():
    s = _make_store()
    s.write_base_memory("u1", {"category": "preferences", "name": "Style", "content": "2-space"})
    entries = s.read_category_entries("u1", None, MemoryCategory.PREFERENCES)
    assert len(entries) == 1 and entries[0].name == "Style"

test("write_base_memory_dict", test_write_base_memory_dict)

def test_read_base_memory():
    s = _make_store()
    s.write_category("u1", MemoryCategory.PROFILE, "P")
    s.write_category("u1", MemoryCategory.DOMAIN_CONTEXT, "D")
    r = s.read_base_memory("u1")
    assert "[profile]" in r and "P" in r
    assert "[domain_context]" in r and "D" in r

test("read_base_memory", test_read_base_memory)

def test_exists_base_memory():
    s = _make_store()
    assert not s.exists_base_memory("u1")
    s.write_category("u1", MemoryCategory.PROFILE, "X")
    assert s.exists_base_memory("u1")

test("exists_base_memory", test_exists_base_memory)


# ── Summary ──
print(f"\n{'='*50}")
print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
if errors:
    print(f"\nFailures:")
    for name, e in errors:
        print(f"  {name}: {e}")
sys.exit(1 if failed else 0)
