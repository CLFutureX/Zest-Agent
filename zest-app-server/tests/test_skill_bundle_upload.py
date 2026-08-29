"""Skill bundle 上传链路针对性测试（app-server 侧，全 stub，无需 MySQL/OSS）。

覆盖：
- validate_zip_bundle：正例 / 魔数 / 无 SKILL.md / 非法 name / 路径穿越 / 符号链接 / 炸弹 / 文件数
- AgentProfileService.create_skill_bundle：命名策略 / hash·version·source / 入库失败回滚 OSS
- AgentProfileService.delete_skill_bundle：OSS 对象 + 元数据同步删除
- 每用户配额
"""
from __future__ import annotations

import hashlib
import io
import zipfile

import pytest

from app.core.models import SkillProfile
from app.api.dependencies import get_agent_profile_service
from app.core.services.skill_bundle_validator import (
    SkillBundleValidationError,
    validate_zip_bundle,
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


def good_bundle(name: str = "demo-skill", desc: str = "测试技能") -> bytes:
    return make_zip({
        "SKILL.md": f"---\nname: {name}\ndescription: {desc}\n---\n\n# 内容\n",
        "scripts/run.sh": "echo hello",
        "references/api.md": "docs",
    })


class MemStorage:
    """内存版 ResourceStorage stub。"""

    def __init__(self):
        self.items: dict[str, object] = {}
        self.fail_create = False

    async def create(self, item):
        if self.fail_create:
            return False
        self.items[item.id] = item
        return True

    async def get(self, id):
        return self.items.get(id)

    async def delete(self, id):
        return self.items.pop(id, None) is not None

    async def list_by_user(self, user_id, filters=None):
        return [i for i in self.items.values() if i.user_id == user_id]

    async def update(self, id, updates):
        if id in self.items:
            for k, v in updates.items():
                setattr(self.items[id], k, v)
            return True
        return False


class FakeOss:
    """OssClient stub：记录对象并支持注入失败。"""

    def __init__(self):
        self.store: dict[str, bytes] = {}
        self.fail_put = False

    def put_bytes(self, key, data):
        if self.fail_put:
            raise RuntimeError("oss down")
        self.store[key] = data
        return key

    def delete(self, key):
        self.store.pop(key, None)
        return True


def make_service(oss: FakeOss | None = None, skill_store: MemStorage | None = None):
    from app.core.services.agent_profile_service import AgentProfileService

    oss = oss or FakeOss()
    mem = MemStorage()
    svc = AgentProfileService(
        llm_config_storage=mem,
        skill_storage=skill_store or mem,
        prompt_storage=mem,
        subagent_config_storage=mem,
        memory_settings_storage=mem,
        oss_client=oss,
    )
    return svc, oss, skill_store or mem


# ═════════════════════════════════════════════
# validate_zip_bundle（机制层）
# ═════════════════════════════════════════════


class TestValidateZipBundle:
    def test_good_bundle(self):
        meta = validate_zip_bundle(good_bundle())
        assert meta.name == "demo-skill"
        assert meta.description == "测试技能"
        assert meta.file_count == 3
        assert len(meta.skill_md_paths) == 1

    def test_rejects_non_zip_magic(self):
        with pytest.raises(SkillBundleValidationError, match="魔数"):
            validate_zip_bundle(b"not a zip at all")

    def test_rejects_missing_skill_md(self):
        with pytest.raises(SkillBundleValidationError, match="SKILL.md"):
            validate_zip_bundle(make_zip({"readme.md": "x"}))

    @pytest.mark.parametrize("bad_name", ["My Skill", " UPPER", "有中文", "-leading-dash", ""])
    def test_rejects_invalid_frontmatter_name(self, bad_name):
        data = make_zip({"SKILL.md": f"---\nname: {bad_name}\n---\nbody\n"})
        with pytest.raises(SkillBundleValidationError, match="name"):
            validate_zip_bundle(data)

    def test_rejects_path_traversal(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            zi = zipfile.ZipInfo("../evil.txt")
            z.writestr(zi, "x")
        with pytest.raises(SkillBundleValidationError, match="非法路径"):
            validate_zip_bundle(buf.getvalue())

    def test_rejects_symlink_entry(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            zi = zipfile.ZipInfo("link")
            zi.external_attr = 0o120777 << 16  # S_IFLNK
            z.writestr(zi, "target")
        with pytest.raises(SkillBundleValidationError, match="符号链接"):
            validate_zip_bundle(buf.getvalue())

    def test_rejects_zip_bomb(self):
        # 100MB 声明解压大小，超 50MB 上限
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("SKILL.md", "---\nname: bomb\n---\nx")
            z.writestr("big.bin", "0" * (60 * 1024 * 1024))
        with pytest.raises(SkillBundleValidationError, match="解压后总大小"):
            validate_zip_bundle(buf.getvalue())

    def test_rejects_too_many_files(self):
        entries = {"SKILL.md": "---\nname: many\n---\nx"}
        for i in range(501):
            entries[f"f{i}.txt"] = "x"
        with pytest.raises(SkillBundleValidationError, match="文件数"):
            validate_zip_bundle(make_zip(entries))

    def test_rejects_oversized_upload(self):
        with pytest.raises(SkillBundleValidationError, match="大小上限"):
            validate_zip_bundle(good_bundle(), max_size_mb=0)

    def test_nested_subdir_skill_md(self):
        meta = validate_zip_bundle(
            make_zip({"sub/SKILL.md": "---\nname: nested\n---\nbody\n"})
        )
        assert meta.name == "nested"


# ═════════════════════════════════════════════
# AgentProfileService.create_skill_bundle（策略层）
# ═════════════════════════════════════════════


class TestCreateSkillBundle:
    @pytest.mark.asyncio
    async def test_frontmatter_name_wins_and_meta_fields(self):
        svc, oss, store = make_service()
        data = good_bundle(name="real-name")
        skill = await svc.create_skill_bundle(
            user_id="u1", name="ignored", zip_bytes=data
        )
        h = hashlib.sha256(data).hexdigest()
        # frontmatter name 优先于表单 name
        assert skill.name == "real-name"
        assert skill.bundle_type == "zip"
        assert skill.content == ""
        assert skill.content_hash == h
        assert skill.version == h[:8]
        assert skill.source == f"oss://{skill.oss_key}@{h[:8]}#{h}"
        # zip 已写入 OSS
        assert oss.store[skill.oss_key] == data
        # 元数据已入库
        assert skill.id in store.items

    @pytest.mark.asyncio
    async def test_rolls_back_oss_when_db_create_fails(self):
        oss = FakeOss()
        store = MemStorage()
        store.fail_create = True
        svc, _, _ = make_service(oss=oss, skill_store=store)
        with pytest.raises(ValueError, match="create failed"):
            await svc.create_skill_bundle(user_id="u1", name="x", zip_bytes=good_bundle())
        # OSS 不留悬挂对象
        assert oss.store == {}

    @pytest.mark.asyncio
    async def test_quota_per_user(self):
        svc, _, _ = make_service()
        svc._skill_max_per_user = 2
        await svc.create_skill_bundle(user_id="u1", name="a", zip_bytes=good_bundle("s-one"))
        await svc.create_skill_bundle(user_id="u1", name="b", zip_bytes=good_bundle("s-two"))
        with pytest.raises(ValueError, match="上限"):
            await svc.create_skill_bundle(user_id="u1", name="c", zip_bytes=good_bundle("s-three"))
        # 其他用户不受影响
        await svc.create_skill_bundle(user_id="u2", name="d", zip_bytes=good_bundle("s-four"))

    @pytest.mark.asyncio
    async def test_propagates_validation_error_as_value_error(self):
        svc, _, _ = make_service()
        with pytest.raises(ValueError):
            await svc.create_skill_bundle(user_id="u1", name="x", zip_bytes=b"garbage")

    @pytest.mark.asyncio
    async def test_inline_create_skill_unchanged(self):
        """回归：inline 文本 skill 创建路径不受 bundle 改造影响。"""
        from app.core.models import CreateSkillProfileRequest

        svc, _, store = make_service()
        req = CreateSkillProfileRequest(
            user_id="u1", name="inline-skill", content="正文", source=None
        )
        skill = await svc.create_skill(req)
        assert skill.content == "正文"
        assert skill.bundle_type is None and skill.oss_key is None


# ═════════════════════════════════════════════
# AgentProfileService.delete_skill_bundle
# ═════════════════════════════════════════════


class TestDeleteSkillBundle:
    @pytest.mark.asyncio
    async def test_deletes_oss_object_and_metadata(self):
        svc, oss, store = make_service()
        skill = await svc.create_skill_bundle(user_id="u1", name="x", zip_bytes=good_bundle())
        assert skill.oss_key in oss.store
        assert await svc.delete_skill_bundle(skill.id) is True
        assert skill.oss_key not in oss.store
        assert skill.id not in store.items

    @pytest.mark.asyncio
    async def test_returns_false_when_missing(self):
        svc, _, _ = make_service()
        assert await svc.delete_skill_bundle("no-such-id") is False



# ═════════════════════════════════════════════
# OSS 能力开关（未配置时禁用 bundle 能力）
# ═════════════════════════════════════════════


class TestOssCapabilitySwitch:
    @pytest.mark.asyncio
    async def test_create_bundle_rejected_without_oss(self):
        """oss_client=None（未配置）时 create_skill_bundle 报清晰错误。"""
        from app.core.services.agent_profile_service import AgentProfileService

        mem = MemStorage()
        svc = AgentProfileService(
            llm_config_storage=mem,
            skill_storage=mem,
            prompt_storage=mem,
            subagent_config_storage=mem,
            memory_settings_storage=mem,
            oss_client=None,
        )
        with pytest.raises(ValueError, match="OSS"):
            await svc.create_skill_bundle(user_id="u1", name="x", zip_bytes=good_bundle())

    @pytest.mark.asyncio
    async def test_delete_bundle_rejected_without_oss(self):
        """未配置 OSS 时删除 bundle 报错（避免 OSS 留下悬挂对象）。"""
        from app.core.services.agent_profile_service import AgentProfileService

        mem = MemStorage()
        svc = AgentProfileService(
            llm_config_storage=mem,
            skill_storage=mem,
            prompt_storage=mem,
            subagent_config_storage=mem,
            memory_settings_storage=mem,
            oss_client=None,
        )
        # 手工塞一个 bundle 元数据（模拟配置丢失前上传的）
        skill = SkillProfile(id="skill-x", user_id="u1", name="s", content="", source="oss://k@v#h",
                             bundle_type="zip", oss_key="skill-bundles/u1/s/v1.zip")
        await mem.create(skill)
        with pytest.raises(ValueError, match="OSS"):
            await svc.delete_skill_bundle(skill.id)
        # 元数据仍在（未被部分删除）
        assert skill.id in mem.items

    def test_is_oss_configured_reads_settings(self, monkeypatch):
        """is_oss_configured：开关 + 四项凭证齐全才为 True。"""
        from app.api import dependencies
        from app.config.settings import settings

        full = {
            "oss_enable": True,
            "oss_access_key_id": "ak",
            "oss_access_key_secret": "sk",
            "oss_endpoint": "http://oss",
            "oss_bucket_name": "bkt",
        }
        saved = {k: getattr(settings, k) for k in full}
        try:
            # 开关关
            for k, v in full.items():
                setattr(settings, k, v)
            setattr(settings, "oss_enable", False)
            assert dependencies.is_oss_configured() is False
            # 开关开但凭证缺
            setattr(settings, "oss_enable", True)
            setattr(settings, "oss_access_key_id", "")
            assert dependencies.is_oss_configured() is False
            # 齐全
            for k, v in full.items():
                setattr(settings, k, v)
            assert dependencies.is_oss_configured() is True
            # 配置齐全时会建真实客户端 —— 不实际连接（oss2 构造惰性），但避免污染单例
            dependencies._oss_client_instance = None
        finally:
            for k, v in saved.items():
                setattr(settings, k, v)
            dependencies._oss_client_instance = None

    def test_get_oss_client_returns_none_when_disabled(self, monkeypatch):
        """未配置时不建客户端、返回 None（不抛错，其他路由注入不受影响）。"""
        from app.api import dependencies
        from app.config.settings import settings

        saved = {k: getattr(settings, k) for k in (
            "oss_enable", "oss_access_key_id", "oss_access_key_secret",
            "oss_endpoint", "oss_bucket_name")}
        try:
            for k in saved:
                setattr(settings, k, "" if k != "oss_enable" else False)
            dependencies._oss_client_instance = None
            assert dependencies.get_oss_client() is None
        finally:
            for k, v in saved.items():
                setattr(settings, k, v)
            dependencies._oss_client_instance = None

    def test_upload_route_guard_returns_400(self):
        """路由守卫：未配置 OSS 时 upload/delete 返回 400 而非 500。"""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.api.agent_profile_route import router
        from app.config.settings import settings

        saved = {k: getattr(settings, k) for k in (
            "oss_enable", "oss_access_key_id", "oss_access_key_secret",
            "oss_endpoint", "oss_bucket_name")}
        for k in saved:
            setattr(settings, k, "" if k != "oss_enable" else False)
        try:
            app = FastAPI()
            # 守卫先于业务依赖抛 400；stub 掉 service 依赖避免触碰 storage_registry
            app.dependency_overrides[get_agent_profile_service] = lambda: None
            app.include_router(router)
            client = TestClient(app)
            # 默认 settings（oss_enable=False）→ 两个 bundle 路由都应 400
            import io as _io

            r = client.post(
                "/api/v1/agent-config/skills/upload",
                files={"file": ("a.zip", _io.BytesIO(b"PK\x03\x04xx"), "application/zip")},
                data={"user_id": "u1", "name": "a"},
            )
            assert r.status_code == 400
            assert "OSS" in r.json()["detail"]
            r2 = client.delete("/api/v1/agent-config/skills/some-id/bundle")
            assert r2.status_code == 400
            # capabilities 接口返回 enabled=false
            r3 = client.get("/api/v1/agent-config/skills/capabilities")
            assert r3.status_code == 200
            assert r3.json()["skill_bundle_enabled"] is False
        finally:
            for k, v in saved.items():
                setattr(settings, k, v)
