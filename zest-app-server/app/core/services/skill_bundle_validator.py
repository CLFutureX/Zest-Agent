"""Skill bundle（zip）上传校验 —— 机制层。

只做无副作用的结构/安全校验与元数据解析：
- zip 魔数 / 大小 / 文件数 / 解压总和（zip 炸弹）/ 路径穿越 / 符号链接
- 要求含 SKILL.md；解析 frontmatter 提取 name / description

所有阈值均由调用方（策略层）以参数传入，本模块不读配置、不访问网络/存储。
"""
from __future__ import annotations

import io
import re
import stat
import zipfile
from dataclasses import dataclass, field
from typing import Optional

import frontmatter

# SKILL.md 中 name 的合法字符集（与运行时 validate_skill_name 对齐）
SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-_]{0,63}$")
ZIP_MAGIC = b"PK\x03\x04"


class SkillBundleValidationError(ValueError):
    """bundle 校验失败；message 直接面向上传者。"""


@dataclass
class SkillBundleMetadata:
    """从 zip 中解析出的 bundle 元数据。"""

    name: str
    description: Optional[str] = None
    skill_md_paths: list[str] = field(default_factory=list)
    file_count: int = 0
    uncompressed_bytes: int = 0


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    """external_attr 高 16 位是 unix mode；S_IFLNK 位为 1 即符号链接。"""
    mode = info.external_attr >> 16
    return stat.S_ISLNK(mode)


def _safe_relpath(name: str) -> bool:
    """拒绝绝对路径、盘符、.. 段、反斜杠混写。"""
    if not name or name.startswith(("/", "\\")) or ":" in name.split("/")[0]:
        return False
    parts = name.replace("\\", "/").split("/")
    return all(p not in ("", ".", "..") for p in parts)


def validate_zip_bundle(
    zip_bytes: bytes,
    *,
    max_size_mb: int = 10,
    max_uncompressed_mb: int = 50,
    max_file_count: int = 500,
    max_description_chars: int = 1024,
) -> SkillBundleMetadata:
    """校验 skill bundle zip 并解析元数据。

    Raises:
        SkillBundleValidationError: 任一校验不通过。
    """
    if not zip_bytes.startswith(ZIP_MAGIC):
        raise SkillBundleValidationError("不是有效的 zip 文件（魔数校验失败）")

    max_bytes = max_size_mb * 1024 * 1024
    if len(zip_bytes) > max_bytes:
        raise SkillBundleValidationError(f"压缩包超过大小上限 {max_size_mb}MB")

    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile as e:
        raise SkillBundleValidationError(f"zip 结构损坏: {e}") from e

    infos = [i for i in zf.infolist() if not i.is_dir()]
    if len(infos) > max_file_count:
        raise SkillBundleValidationError(f"文件数超过上限 {max_file_count}")

    total_uncompressed = sum(i.file_size for i in infos)
    if total_uncompressed > max_uncompressed_mb * 1024 * 1024:
        raise SkillBundleValidationError(f"解压后总大小超过上限 {max_uncompressed_mb}MB")

    skill_md_paths: list[str] = []
    for info in infos:
        if not _safe_relpath(info.filename):
            raise SkillBundleValidationError(f"非法路径: {info.filename}")
        if _is_symlink(info):
            raise SkillBundleValidationError(f"不允许符号链接: {info.filename}")
        if info.filename.replace("\\", "/").rsplit("/", 1)[-1] == "SKILL.md":
            skill_md_paths.append(info.filename)

    if not skill_md_paths:
        raise SkillBundleValidationError("zip 中未找到 SKILL.md")

    # 解析首个 SKILL.md 的 frontmatter 作为 bundle 元数据
    skill_md_path = sorted(skill_md_paths)[0]
    try:
        raw = zf.read(skill_md_path).decode("utf-8")
    except UnicodeDecodeError as e:
        raise SkillBundleValidationError(f"SKILL.md 不是 UTF-8 编码: {e}") from e
    try:
        parsed = frontmatter.loads(raw)
    except Exception as e:  # frontmatter 解析失败视为格式错误
        raise SkillBundleValidationError(f"SKILL.md frontmatter 解析失败: {e}") from e

    meta = parsed.metadata or {}
    name = str(meta.get("name", "")).strip()
    description = meta.get("description")
    description = str(description).strip() if description is not None else None

    if not SKILL_NAME_PATTERN.match(name):
        raise SkillBundleValidationError(
            "SKILL.md frontmatter 中 name 不合法（需为小写字母/数字开头，"
            "仅含 a-z0-9-_，长度 1-64）"
        )
    if description and len(description) > max_description_chars:
        raise SkillBundleValidationError(f"description 超过 {max_description_chars} 字符")

    return SkillBundleMetadata(
        name=name,
        description=description or None,
        skill_md_paths=skill_md_paths,
        file_count=len(infos),
        uncompressed_bytes=total_uncompressed,
    )
