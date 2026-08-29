"""OSS skill bundle 运行时物化测试（zest-sdk 侧，stub OSS，全离线）。

覆盖：
- parse_oss_source：正常解析 / 格式错误
- secure_extract_zip：hash 不符 / 路径穿越拒绝
- materialize_oss_skill：首次物化到统一 skills 目录 / hash 一致跳过下载 /
  hash 变化覆盖更新 / 子目录布局 zip
- SkillBuildStage.run：oss:// 占位 skill 展开为真实 skill，oss:// 不进 source
"""
from __future__ import annotations

import hashlib
import io
import json
import shutil
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from sdk.context.skills import oss_fetcher
from sdk.context.skills.oss_fetcher import (
    OssSkillFetchError,
    materialize_oss_skill,
    parse_oss_source,
    secure_extract_zip,
)

# ═════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════


def make_zip(entries: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return buf.getvalue()


def root_bundle(name: str = "demo-bundle", desc: str = "demo-desc") -> bytes:
    """根 SKILL.md 布局。"""
    return make_zip({
        "SKILL.md": f"---\nname: {name}\ndescription: {desc}\n---\n\n# {desc}\n",
        "scripts/run.sh": "echo hello",
    })


class FakeObj:
    def __init__(self, data: bytes):
        self._d = data

    def read(self) -> bytes:
        return self._d


class FakeBucket:
    """oss2.Bucket stub：内存对象表，可断言下载次数。"""

    def __init__(self, store: dict[str, bytes] | None = None):
        self.store = store or {}
        self.get_count = 0

    def get_object(self, key: str):
        self.get_count += 1
        if key not in self.store:
            raise KeyError(key)
        return FakeObj(self.store[key])


@pytest.fixture
def skills_root(tmp_path, monkeypatch):
    """把统一 skills 目录重定向到 tmp，避免污染 ~/.Zest/skills。"""
    root = tmp_path / "skills"
    monkeypatch.setattr(oss_fetcher, "_skills_root", lambda: root)
    return root


# ═════════════════════════════════════════════
# parse_oss_source（机制层）
# ═════════════════════════════════════════════


class TestParseOssSource:
    def test_roundtrip(self):
        key, version, h = parse_oss_source(
            "oss://skill-bundles/u1/s1/abc12345.zip@abc12345#" + "f" * 64
        )
        assert key == "skill-bundles/u1/s1/abc12345.zip"
        assert version == "abc12345"
        assert h == "f" * 64

    @pytest.mark.parametrize(
        "bad",
        [
            "not-oss",
            "oss://onlykey",
            "oss://key@noversion",
        ],
    )
    def test_rejects_malformed(self, bad):
        with pytest.raises(OssSkillFetchError):
            parse_oss_source(bad)


# ═════════════════════════════════════════════
# secure_extract_zip（机制层，纵深防御）
# ═════════════════════════════════════════════


class TestSecureExtractZip:
    def test_rejects_hash_mismatch(self, tmp_path):
        data = root_bundle()
        with pytest.raises(OssSkillFetchError, match="sha256"):
            secure_extract_zip(data, tmp_path / "s", expected_hash="0" * 64)

    def test_rejects_traversal(self, tmp_path):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            zi = zipfile.ZipInfo("../evil.txt")
            z.writestr(zi, "x")
        with pytest.raises(OssSkillFetchError):
            secure_extract_zip(
                buf.getvalue(),
                tmp_path / "s",
                expected_hash=hashlib.sha256(buf.getvalue()).hexdigest(),
            )

    def test_extracts_ok(self, tmp_path):
        data = root_bundle()
        target = tmp_path / "s"
        secure_extract_zip(data, target, expected_hash=hashlib.sha256(data).hexdigest())
        assert (target / "SKILL.md").exists()
        assert (target / "scripts" / "run.sh").exists()


# ═════════════════════════════════════════════
# materialize_oss_skill（统一目录 + meta 新旧判定）
# ═════════════════════════════════════════════


def _marker(oss_key: str, version: str, data: bytes) -> str:
    return f"oss://{oss_key}@{version}#{hashlib.sha256(data).hexdigest()}"


class TestMaterializeOssSkill:
    def test_first_materialize_creates_meta(self, skills_root):
        v1 = root_bundle(desc="v1-body")
        key1 = "skill-bundles/u1/s1/aaaaaaaa.zip"
        bucket = FakeBucket({key1: v1})
        with patch.object(oss_fetcher, "_build_oss_client", return_value=bucket):
            skills = materialize_oss_skill(key1, "aaaaaaaa", hashlib.sha256(v1).hexdigest())
        assert [s.name for s in skills] == ["demo-bundle"]
        assert "v1-body" in skills[0].description or "v1-body" in skills[0].content
        # 物化到统一 skills 根目录下的 frontmatter-name 目录
        d = skills_root / "demo-bundle"
        assert (d / "SKILL.md").exists()
        assert (d / "scripts" / "run.sh").exists()
        meta = json.loads((d / ".zest-meta.json").read_text(encoding="utf-8"))
        assert meta["content_hash"] == hashlib.sha256(v1).hexdigest()
        assert meta["oss_key"] == key1
        # oss:// 不应出现在加载出的 skill source 中（不进 prompt）
        assert not str(skills[0].source).startswith("oss://")

    def test_hash_match_skips_download(self, skills_root):
        v1 = root_bundle(desc="v1-body")
        key1 = "skill-bundles/u1/s1/aaaaaaaa.zip"
        with patch.object(oss_fetcher, "_build_oss_client", return_value=FakeBucket({key1: v1})):
            materialize_oss_skill(key1, "aaaaaaaa", hashlib.sha256(v1).hexdigest())
        # 第二次：bucket 缺对象，若下载必 KeyError
        with patch.object(oss_fetcher, "_build_oss_client", return_value=FakeBucket()):
            skills = materialize_oss_skill(key1, "aaaaaaaa", hashlib.sha256(v1).hexdigest())
        assert [s.name for s in skills] == ["demo-bundle"]

    def test_hash_change_overwrites(self, skills_root):
        v1 = root_bundle(desc="v1-body")
        v2 = root_bundle(desc="v2-body")
        k1 = "skill-bundles/u1/s1/aaaaaaaa.zip"
        k2 = "skill-bundles/u1/s2/bbbbbbbb.zip"
        store = {k1: v1}
        bucket = FakeBucket(store)
        with patch.object(oss_fetcher, "_build_oss_client", return_value=bucket):
            materialize_oss_skill(k1, "aaaaaaaa", hashlib.sha256(v1).hexdigest())
            store[k2] = v2
            skills = materialize_oss_skill(k2, "bbbbbbbb", hashlib.sha256(v2).hexdigest())
        assert "v2-body" in skills[0].description or "v2-body" in skills[0].content
        meta = json.loads((skills_root / "demo-bundle" / ".zest-meta.json").read_text(encoding="utf-8"))
        assert meta["content_hash"] == hashlib.sha256(v2).hexdigest()
        assert meta["oss_key"] == k2
        # 下载了两次
        assert bucket.get_count == 2

    def test_subdir_layout_zip(self, skills_root):
        """子目录布局 zip（SKILL.md 不在根）：解压到以键名命名的目录。"""
        data = make_zip({"my-sub/SKILL.md": "---\nname: my-sub\ndescription: subdir-desc\n---\nbody\n"})
        key = "skill-bundles/u1/s3/cccccccc.zip"
        with patch.object(oss_fetcher, "_build_oss_client", return_value=FakeBucket({key: data})):
            skills = materialize_oss_skill(key, "cccccccc", hashlib.sha256(data).hexdigest())
        assert [s.name for s in skills] == ["my-sub"]
        assert (skills_root / "my-sub" / "SKILL.md").exists()

    def test_download_failure_raises(self, skills_root):
        key = "skill-bundles/u1/s1/missing.zip"
        with patch.object(oss_fetcher, "_build_oss_client", return_value=FakeBucket()):
            with pytest.raises(OssSkillFetchError, match="下载失败"):
                materialize_oss_skill(key, "aaaaaaaa", "0" * 64)


# ═════════════════════════════════════════════
# SkillBuildStage 集成（占位展开）
# ═════════════════════════════════════════════


class TestSkillBuildStage:
    def _run(self, source, bucket):
        from sdk.agent.runtime_stage import SkillBuildStage
        from sdk.context.skills.skill import Skill

        class FakeCtxSpec:
            skills = [Skill(name="demo-bundle", content="", description="占位", source=source)]
            load_user_skills = False
            load_public_skills = False

        class FakeSpec:
            agent_context_spec = FakeCtxSpec()

        class FakeRuntime:
            def copy_with(self, skills=None):
                self.skills = skills
                return self

        rt = FakeRuntime()
        SkillBuildStage().run(FakeSpec(), None, rt)
        return rt.skills

    def test_placeholder_expanded_and_source_localized(self, skills_root):
        data = root_bundle(desc="stage-body")
        key = "skill-bundles/u1/s1/aaaaaaaa.zip"
        marker = _marker(key, "aaaaaaaa", data)
        with patch.object(oss_fetcher, "_build_oss_client", return_value=FakeBucket({key: data})):
            skills = self._run(marker, None)
        assert [s.name for s in skills] == ["demo-bundle"]
        assert not str(skills[0].source).startswith("oss://")
        assert (skills_root / "demo-bundle" / ".zest-meta.json").exists()

    def test_inline_skill_passthrough(self, skills_root):
        """回归：非 oss:// 的 inline skill 原样透传。"""
        from sdk.context.skills.skill import Skill

        skills = self._run("/local/dir", None)
        assert len(skills) == 1
        assert skills[0].source == "/local/dir"
