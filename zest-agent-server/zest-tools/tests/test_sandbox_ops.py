"""Tests for sandbox operations.

Covers: _validate_path, read, write, overwrite, edit, ls_info, glob_info, grep_raw.

All tests use ProcessSandbox via a temporary work_dir so they run on
any OS without external dependencies (no bash required for grep_raw/ls_info).
"""
from __future__ import annotations

import asyncio
import os
import sys
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_sandbox(work_dir: str):
    """Create a ProcessSandbox bound to work_dir."""
    from tools.sandbox.base import BackendType, SandboxInfo, SandboxStatus
    from tools.sandbox.impl.process_sandbox import ProcessSandbox

    info = SandboxInfo(
        id="test",
        sandbox_id="test",
        backend_type=BackendType.PROCESS,
        status=SandboxStatus.RUNNING,
        work_dir=work_dir,
    )
    return ProcessSandbox(info)


def run(coro):
    """Run a coroutine synchronously using a fresh event loop."""
    return asyncio.run(coro)


@pytest.fixture()
def tmp_sandbox(tmp_path):
    """Yield a (sandbox, work_dir_str) tuple backed by a temp directory."""
    work_dir = str(tmp_path)
    sandbox = _make_sandbox(work_dir)
    yield sandbox, work_dir


# ---------------------------------------------------------------------------
# _validate_path
# ---------------------------------------------------------------------------

class TestValidatePath:
    def test_relative_path_resolved_to_work_dir(self, tmp_sandbox):
        sandbox, work_dir = tmp_sandbox
        result = sandbox._validate_path("sub/file.txt")
        expected = os.path.normpath(os.path.join(work_dir, "sub/file.txt"))
        assert result == expected

    def test_absolute_path_inside_work_dir_allowed(self, tmp_sandbox):
        sandbox, work_dir = tmp_sandbox
        abs_path = os.path.join(work_dir, "a.txt")
        assert sandbox._validate_path(abs_path) == os.path.normpath(abs_path)

    def test_work_dir_itself_allowed(self, tmp_sandbox):
        sandbox, work_dir = tmp_sandbox
        assert sandbox._validate_path(work_dir) == os.path.normpath(work_dir)

    def test_dotdot_rejected(self, tmp_sandbox):
        sandbox, _ = tmp_sandbox
        with pytest.raises(ValueError, match="Path traversal not allowed"):
            sandbox._validate_path("../escape.txt")

    def test_tilde_rejected(self, tmp_sandbox):
        sandbox, _ = tmp_sandbox
        with pytest.raises(ValueError, match="Path traversal not allowed"):
            sandbox._validate_path("~/secret")

    def test_absolute_path_outside_work_dir_rejected(self, tmp_sandbox):
        sandbox, _ = tmp_sandbox
        with pytest.raises(ValueError, match="outside sandbox work_dir"):
            sandbox._validate_path("/etc/passwd")

    def test_normalizes_redundant_separators(self, tmp_sandbox):
        sandbox, work_dir = tmp_sandbox
        path = os.path.join(work_dir, "a", "b")
        messy = os.path.join(work_dir, "a", "", "b")
        assert sandbox._validate_path(messy) == os.path.normpath(path)


# ---------------------------------------------------------------------------
# write / read
# ---------------------------------------------------------------------------

class TestWriteRead:
    def test_write_creates_file(self, tmp_sandbox):
        sandbox, work_dir = tmp_sandbox
        fpath = os.path.join(work_dir, "hello.txt")
        err = run(sandbox.write(fpath, "hello world\n"))
        assert err is None
        assert os.path.isfile(fpath)
        assert open(fpath).read() == "hello world\n"

    def test_write_fails_if_file_exists(self, tmp_sandbox):
        sandbox, work_dir = tmp_sandbox
        fpath = os.path.join(work_dir, "exist.txt")
        run(sandbox.write(fpath, "first"))
        err = run(sandbox.write(fpath, "second"))
        assert err is not None
        assert "Error" in err

    def test_write_creates_parent_dirs(self, tmp_sandbox):
        sandbox, work_dir = tmp_sandbox
        fpath = os.path.join(work_dir, "a", "b", "c.txt")
        err = run(sandbox.write(fpath, "nested"))
        assert err is None
        assert os.path.isfile(fpath)

    def test_read_returns_numbered_lines(self, tmp_sandbox):
        sandbox, work_dir = tmp_sandbox
        fpath = os.path.join(work_dir, "lines.txt")
        run(sandbox.write(fpath, "line1\nline2\nline3\n"))
        content = run(sandbox.read(fpath))
        assert "line1" in content
        assert "line2" in content
        assert "line3" in content

    def test_read_offset_and_limit(self, tmp_sandbox):
        sandbox, work_dir = tmp_sandbox
        fpath = os.path.join(work_dir, "many.txt")
        run(sandbox.write(fpath, "\n".join(f"L{i}" for i in range(1, 11))))
        # offset=2, limit=3 → lines 3,4,5
        content = run(sandbox.read(fpath, offset=2, limit=3))
        assert "L3" in content
        assert "L4" in content
        assert "L5" in content
        assert "L1" not in content
        assert "L6" not in content

    def test_read_nonexistent_file_returns_error(self, tmp_sandbox):
        sandbox, work_dir = tmp_sandbox
        content = run(sandbox.read(os.path.join(work_dir, "nope.txt")))
        assert content.startswith("Error:")

    def test_read_empty_file(self, tmp_sandbox):
        sandbox, work_dir = tmp_sandbox
        fpath = os.path.join(work_dir, "empty.txt")
        run(sandbox.write(fpath, ""))
        content = run(sandbox.read(fpath))
        assert "empty" in content.lower() or content == ""


# ---------------------------------------------------------------------------
# overwrite
# ---------------------------------------------------------------------------

class TestOverwrite:
    def test_overwrite_creates_new_file(self, tmp_sandbox):
        sandbox, work_dir = tmp_sandbox
        fpath = os.path.join(work_dir, "new.txt")
        err = run(sandbox.overwrite(fpath, "created"))
        assert err is None
        assert open(fpath).read() == "created"

    def test_overwrite_replaces_existing_file(self, tmp_sandbox):
        sandbox, work_dir = tmp_sandbox
        fpath = os.path.join(work_dir, "replace.txt")
        run(sandbox.write(fpath, "original"))
        err = run(sandbox.overwrite(fpath, "replaced"))
        assert err is None
        assert open(fpath).read() == "replaced"

    def test_overwrite_creates_parent_dirs(self, tmp_sandbox):
        sandbox, work_dir = tmp_sandbox
        fpath = os.path.join(work_dir, "deep", "dir", "file.txt")
        err = run(sandbox.overwrite(fpath, "deep content"))
        assert err is None
        assert open(fpath).read() == "deep content"


# ---------------------------------------------------------------------------
# edit
# ---------------------------------------------------------------------------

class TestEdit:
    def _write(self, sandbox, work_dir, name, content):
        fpath = os.path.join(work_dir, name)
        run(sandbox.write(fpath, content))
        return fpath

    def test_edit_replaces_first_occurrence(self, tmp_sandbox):
        sandbox, work_dir = tmp_sandbox
        fpath = self._write(sandbox, work_dir, "e1.txt", "foo bar foo")
        count, err = run(sandbox.edit(fpath, "foo", "baz"))
        assert err is None
        assert open(fpath).read() == "baz bar foo"

    def test_edit_replace_all(self, tmp_sandbox):
        sandbox, work_dir = tmp_sandbox
        fpath = self._write(sandbox, work_dir, "e2.txt", "x x x")
        count, err = run(sandbox.edit(fpath, "x", "y", replace_all=True))
        assert err is None
        assert count == 3
        assert open(fpath).read() == "y y y"

    def test_edit_string_not_found_returns_error(self, tmp_sandbox):
        sandbox, work_dir = tmp_sandbox
        fpath = self._write(sandbox, work_dir, "e3.txt", "hello")
        count, err = run(sandbox.edit(fpath, "MISSING", "x"))
        assert count is None
        assert err is not None
        assert "not found" in err.lower()

    def test_edit_multiple_occurrences_replaces_first_only(self, tmp_sandbox):
        sandbox, work_dir = tmp_sandbox
        fpath = self._write(sandbox, work_dir, "e4.txt", "a a a")
        count, err = run(sandbox.edit(fpath, "a", "b", replace_all=False))
        assert err is None
        assert open(fpath).read() == "b a a"

    def test_edit_unicode_content(self, tmp_sandbox):
        sandbox, work_dir = tmp_sandbox
        fpath = self._write(sandbox, work_dir, "e5.txt", "你好世界")
        count, err = run(sandbox.edit(fpath, "你好", "再见"))
        assert err is None
        assert open(fpath, encoding="utf-8").read() == "再见世界"


# ---------------------------------------------------------------------------
# ls_info
# ---------------------------------------------------------------------------

class TestLsInfo:
    def test_ls_lists_files_and_dirs(self, tmp_sandbox):
        sandbox, work_dir = tmp_sandbox
        os.makedirs(os.path.join(work_dir, "subdir"))
        open(os.path.join(work_dir, "file.txt"), "w").close()
        infos = run(sandbox.ls_info(work_dir))
        names = {fi.name for fi in infos}
        assert "subdir" in names
        assert "file.txt" in names

    def test_ls_distinguishes_file_and_directory(self, tmp_sandbox):
        sandbox, work_dir = tmp_sandbox
        os.makedirs(os.path.join(work_dir, "d"))
        open(os.path.join(work_dir, "f.txt"), "w").close()
        infos = {fi.name: fi for fi in run(sandbox.ls_info(work_dir))}
        assert infos["d"].is_directory is True
        assert infos["f.txt"].is_directory is False

    def test_ls_empty_dir_returns_empty(self, tmp_sandbox):
        sandbox, work_dir = tmp_sandbox
        empty = os.path.join(work_dir, "empty_dir")
        os.makedirs(empty)
        infos = run(sandbox.ls_info(empty))
        assert infos == []

    def test_ls_nonexistent_returns_empty(self, tmp_sandbox):
        sandbox, work_dir = tmp_sandbox
        infos = run(sandbox.ls_info(os.path.join(work_dir, "ghost")))
        assert infos == []


# ---------------------------------------------------------------------------
# glob_info
# ---------------------------------------------------------------------------

class TestGlobInfo:
    def _setup(self, work_dir):
        """Create a small file tree for glob tests."""
        os.makedirs(os.path.join(work_dir, "src"))
        for name in ("a.py", "b.py", "c.txt"):
            open(os.path.join(work_dir, "src", name), "w").close()
        open(os.path.join(work_dir, "top.py"), "w").close()

    def test_glob_matches_pattern(self, tmp_sandbox):
        sandbox, work_dir = tmp_sandbox
        self._setup(work_dir)
        infos = run(sandbox.glob_info("**/*.py", path=work_dir))
        names = {fi.name for fi in infos}
        assert "a.py" in names
        assert "b.py" in names
        assert "top.py" in names
        assert "c.txt" not in names

    def test_glob_no_match_returns_empty(self, tmp_sandbox):
        sandbox, work_dir = tmp_sandbox
        self._setup(work_dir)
        infos = run(sandbox.glob_info("**/*.go", path=work_dir))
        assert infos == []

    def test_glob_txt_pattern(self, tmp_sandbox):
        sandbox, work_dir = tmp_sandbox
        self._setup(work_dir)
        infos = run(sandbox.glob_info("**/*.txt", path=work_dir))
        names = {fi.name for fi in infos}
        assert "c.txt" in names
        assert "a.py" not in names


# ---------------------------------------------------------------------------
# grep_raw
# ---------------------------------------------------------------------------

class TestGrepRaw:
    def _write(self, work_dir, name, content):
        fpath = os.path.join(work_dir, name)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content)
        return fpath

    def test_grep_finds_pattern(self, tmp_sandbox):
        sandbox, work_dir = tmp_sandbox
        self._write(work_dir, "g1.txt", "hello world\nfoo bar\nhello again\n")
        matches = run(sandbox.grep_raw("hello", path=work_dir))
        assert len(matches) == 2
        assert all(m.text.startswith("hello") for m in matches)

    def test_grep_no_match_returns_empty(self, tmp_sandbox):
        sandbox, work_dir = tmp_sandbox
        self._write(work_dir, "g2.txt", "nothing here\n")
        matches = run(sandbox.grep_raw("ZZZNOPE", path=work_dir))
        assert matches == []

    def test_grep_reports_correct_line_number(self, tmp_sandbox):
        sandbox, work_dir = tmp_sandbox
        self._write(work_dir, "g3.txt", "line1\nline2\nTARGET\nline4\n")
        matches = run(sandbox.grep_raw("TARGET", path=work_dir))
        assert len(matches) == 1
        assert matches[0].line == 3

    def test_grep_glob_filter(self, tmp_sandbox):
        sandbox, work_dir = tmp_sandbox
        self._write(work_dir, "match.py", "needle\n")
        self._write(work_dir, "skip.txt", "needle\n")
        matches = run(sandbox.grep_raw("needle", path=work_dir, glob="*.py"))
        assert len(matches) == 1
        assert matches[0].path.endswith("match.py")

    def test_grep_multiple_files(self, tmp_sandbox):
        sandbox, work_dir = tmp_sandbox
        self._write(work_dir, "f1.txt", "pattern here\n")
        self._write(work_dir, "f2.txt", "pattern there\n")
        self._write(work_dir, "f3.txt", "nothing\n")
        matches = run(sandbox.grep_raw("pattern", path=work_dir))
        assert len(matches) == 2

    def test_grep_unicode(self, tmp_sandbox):
        sandbox, work_dir = tmp_sandbox
        self._write(work_dir, "uni.txt", "中文内容\n英文 line\n中文再来\n")
        matches = run(sandbox.grep_raw("中文", path=work_dir))
        assert len(matches) == 2

    def test_grep_returns_text_content(self, tmp_sandbox):
        sandbox, work_dir = tmp_sandbox
        self._write(work_dir, "content.txt", "find me please\n")
        matches = run(sandbox.grep_raw("find me", path=work_dir))
        assert len(matches) == 1
        assert "find me" in matches[0].text

