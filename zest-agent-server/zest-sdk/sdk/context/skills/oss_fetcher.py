"""OSS skill bundle 拉取与物化 —— 运行时机制层。

职责（纯机制）：
- 从 OSS 下载 bundle zip 并校验 sha256
- secure_extract_zip：解压时复检路径穿越 / zip 炸弹 / 符号链接（纵深防御）
- 物化到统一 skills 目录 ~/.Zest/skills/<name>/（与本地/用户 skill 同一位置），
  以 .zest-meta.json 中的 content_hash 判断是否需要更新
- 用 load_skills_from_dir 从物化目录加载真实 Skill

策略由调用方决定：oss:// 标记的解析（SkillBuildStage）、缓存目录命名。
OSS 凭证来自环境变量：OSS_ACCESS_KEY_ID / OSS_ACCESS_KEY_SECRET /
OSS_ENDPOINT / OSS_BUCKET_NAME。
"""
from __future__ import annotations

import hashlib
import json
import frontmatter
import io
import os
import stat
import zipfile
from pathlib import Path
from typing import Optional

from filelock import FileLock

from sdk.context.skills.skill import load_skills_from_dir
from common.logger import get_logger

logger = get_logger(__name__)

# 解压防护阈值（机制参数；与上传侧保持一致的量级）
DEFAULT_MAX_UNCOMPRESSED_MB = 50
DEFAULT_MAX_FILE_COUNT = 500

_OSS_ENV_KEYS = {
    "oss_enable":"OSS_ENABLE",
    "access_key_id": "OSS_ACCESS_KEY_ID",
    "access_key_secret": "OSS_ACCESS_KEY_SECRET",
    "endpoint": "OSS_ENDPOINT",
    "bucket_name": "OSS_BUCKET_NAME",
}


class OssSkillFetchError(RuntimeError):
    """OSS skill bundle 拉取/物化失败。"""


def parse_oss_source(source: str) -> tuple[str, str, str]:
    """解析 oss://<key>@<version>#<content_hash> 标记。"""
    if not source.startswith("oss://"):
        raise OssSkillFetchError(f"非 OSS skill source: {source}")
    body = source[len("oss://"):]
    try:
        key, rest = body.rsplit("@", 1)
        version, content_hash = rest.rsplit("#", 1)
    except ValueError as e:
        raise OssSkillFetchError(f"OSS source 格式非法: {source}") from e
    if not key or not version or not content_hash:
        raise OssSkillFetchError(f"OSS source 字段缺失: {source}")
    return key, version, content_hash


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    return stat.S_ISLNK(info.external_attr >> 16)


def _safe_relpath(name: str) -> bool:
    if not name or name.startswith(("/", "\\")) or ":" in name.split("/")[0]:
        return False
    parts = name.replace("\\", "/").split("/")
    return all(p not in ("", ".", "..") for p in parts)


def secure_extract_zip(
    zip_bytes: bytes,
    target_dir: Path,
    *,
    expected_hash: Optional[str] = None,
    max_uncompressed_mb: int = DEFAULT_MAX_UNCOMPRESSED_MB,
    max_file_count: int = DEFAULT_MAX_FILE_COUNT,
) -> None:
    """校验并安全解压 zip 到 target_dir（不信任上传侧，解压时复检）。"""
    if expected_hash:
        actual = hashlib.sha256(zip_bytes).hexdigest()
        if actual != expected_hash:
            raise OssSkillFetchError(
                f"bundle sha256 不匹配: expected={expected_hash} actual={actual}"
            )
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile as e:
        raise OssSkillFetchError(f"zip 结构损坏: {e}") from e

    infos = [i for i in zf.infolist() if not i.is_dir()]
    if len(infos) > max_file_count:
        raise OssSkillFetchError(f"文件数超过上限 {max_file_count}")
    if sum(i.file_size for i in infos) > max_uncompressed_mb * 1024 * 1024:
        raise OssSkillFetchError(f"解压后总大小超过上限 {max_uncompressed_mb}MB")

    target_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(target_dir, 0o700)
    for info in infos:
        if not _safe_relpath(info.filename) or _is_symlink(info):
            raise OssSkillFetchError(f"非法 zip 条目: {info.filename}")
        dest = target_dir / info.filename
        # 双重校验：解析后的绝对路径必须仍在 target_dir 内
        if not str(dest.resolve()).startswith(str(target_dir.resolve()) + os.sep):
            raise OssSkillFetchError(f"路径越界: {info.filename}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            f.write(zf.read(info))


def _build_oss_client():
    """按环境变量构建 oss2 客户端；缺失时抛出可诊断错误。"""
    if not os.environ.get("OSS_ENABLE"):
        return None
    try:
        import oss2
    except ImportError as e:
        raise OssSkillFetchError(
            "运行时未安装 oss2，无法拉取 OSS skill bundle（pip install oss2）"
        ) from e
    cfg = {k: os.environ.get(env, "") for k, env in _OSS_ENV_KEYS.items()}
    missing = [env for env in _OSS_ENV_KEYS.values() if not cfg_k(cfg, env)]
    
    if missing:
        raise OssSkillFetchError(
            f"OSS 凭证未配置（缺少环境变量: {', '.join(missing)}），"
            "无法拉取 OSS skill bundle"
        )
    auth = oss2.Auth(cfg["access_key_id"], cfg["access_key_secret"])
    return oss2.Bucket(auth, cfg["endpoint"], cfg["bucket_name"])


def cfg_k(cfg: dict, env_name: str) -> str:
    """cfg 的键名与 env 名映射取值（辅助 _build_oss_client 的 missing 判断）。"""
    for k, env in _OSS_ENV_KEYS.items():
        if env == env_name:
            return cfg[k]
    return ""


META_FILENAME = ".zest-meta.json"


def _skills_root() -> Path:
    """统一 skill 目录（与用户本地 skill 同一位置）。"""
    return Path.home() / ".Zest" / "skills"


def _root_skill_md_name(zip_bytes: bytes) -> Optional[str]:
    """zip 根层若直接含 SKILL.md，返回其 frontmatter name；否则 None。
    目录名必须等于 name（AgentSkills 校验），故物化时用该名建子目录。"""
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        return None
    for info in zf.infolist():
        if info.is_dir():
            continue
        normalized = info.filename.replace("\\", "/")
        if "/" not in normalized and normalized == "SKILL.md":
            try:
                raw = zf.read(info.filename).decode("utf-8")
                parsed = frontmatter.loads(raw)
                name = str((parsed.metadata or {}).get("name", "")).strip()
                if name:
                    return name
            except Exception:  # noqa: BLE001 —— 解析失败按无根 SKILL.md 处理
                return None
    return None


def _read_skill_meta(skill_dir: Path) -> Optional[dict]:
    """读取物化目录的 .zest-meta.json；无则 None。"""
    meta_path = skill_dir / META_FILENAME
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 —— 损坏的 meta 视为不存在
        return None


def _write_skill_meta(skill_dir: Path, meta: dict) -> None:
    (skill_dir / META_FILENAME).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _is_up_to_date(skill_dir: Path, content_hash: str) -> bool:
    """本地目录内容与标记 hash 一致才视为最新（防旧版本残留）。"""
    if not skill_dir.exists() or not any(skill_dir.rglob("SKILL.md")):
        return False
    meta = _read_skill_meta(skill_dir)
    return bool(meta and meta.get("content_hash") == content_hash)


def materialize_oss_skill(
    oss_key: str,
    version: str,
    content_hash: str,
    *,
    max_uncompressed_mb: int = DEFAULT_MAX_UNCOMPRESSED_MB,
    max_file_count: int = DEFAULT_MAX_FILE_COUNT,
) -> list:
    """下载（或本地已最新）并加载 OSS bundle，返回真实 Skill 列表。

    物化位置与本地/用户 skill 统一：~/.Zest/skills/<name>/。
    新旧判定：目录存在且 .zest-meta.json 的 content_hash 与标记一致才跳过
    下载；否则覆盖式重新解压（先清空目录防旧文件残留）并更新 meta。
    """
    lock_root = _skills_root()
    lock_root.mkdir(parents=True, exist_ok=True)

    # 快路径：meta 索引定位到本地目录且 hash 一致 -> 免下载、免 OSS 凭证
    local_dir = _find_local_dir(content_hash)
    if local_dir and _is_up_to_date(local_dir, content_hash):
        logger.debug(f"OSS skill bundle 本地已最新: {local_dir}")
        return _load_skills_from(local_dir)

    lock_path = lock_root / f".oss-skill-{version}.lock"
    with FileLock(str(lock_path), timeout=120):
        # 双检：抢到锁后可能已被并发会话更新
        local_dir = _find_local_dir(content_hash)
        if local_dir and _is_up_to_date(local_dir, content_hash):
            logger.debug(f"OSS skill bundle 本地已最新（锁内双检）: {local_dir}")
            return _load_skills_from(local_dir)

        bucket = _build_oss_client()
        logger.info(f"拉取 OSS skill bundle: {oss_key} (v{version})")
        try:
            obj = bucket.get_object(oss_key)
            zip_bytes = obj.read()
        except Exception as e:
            raise OssSkillFetchError(f"OSS 下载失败 key={oss_key}: {e}") from e

        # 布局归一化：load_skills_from_dir 只发现 <dir>/<name>/SKILL.md 子目录布局，
        # 且目录名必须等于 frontmatter name；若 SKILL.md 位于 zip 根，
        # 整体解压到 <skills>/<frontmatter-name>/ 以适配。
        root_name = _root_skill_md_name(zip_bytes)
        meta = {"content_hash": content_hash, "version": version, "oss_key": oss_key}
        if root_name:
            # 根 SKILL.md 布局：目录名 = frontmatter name
            skill_dir = _skills_root() / root_name
            import shutil
            if skill_dir.exists():
                shutil.rmtree(skill_dir)
            secure_extract_zip(
                zip_bytes, skill_dir, expected_hash=content_hash,
                max_uncompressed_mb=max_uncompressed_mb, max_file_count=max_file_count,
            )
            _write_skill_meta(skill_dir, meta)
            logger.info(f"OSS skill bundle 已物化: {skill_dir}")
            skill_dirs = [skill_dir]
        else:
            # 子目录布局：zip 内各 <sub>/SKILL.md 本身就是合法的 skill 目录，
            # 直接解压到 skills 根（load_skills_from_dir 只扫一层子目录，
            # 多包一层会导致加载为空）；meta 写入各顶层 skill 目录
            import shutil
            import zipfile as _zipfile
            with _zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                top_dirs = sorted({n.split("/")[0] for n in zf.namelist() if "/" in n and n.split("/")[0]})
            for d in top_dirs:
                target = _skills_root() / d
                if target.exists():
                    shutil.rmtree(target)
            secure_extract_zip(
                zip_bytes, _skills_root(), expected_hash=content_hash,
                max_uncompressed_mb=max_uncompressed_mb, max_file_count=max_file_count,
            )
            skill_dirs = [_skills_root() / d for d in top_dirs]
            for sd in skill_dirs:
                _write_skill_meta(sd, meta)
            logger.info(f"OSS skill bundle 已物化(子目录布局): {[str(s) for s in skill_dirs]}")

    return _load_skills_from(skill_dirs)


def _find_local_dir(content_hash: str) -> Optional[Path]:
    """在统一 skills 根目录下按 .zest-meta.json 的 content_hash 定位本地目录。

    目录名由 frontmatter name 决定、无法从 oss_key 反推，故以 meta 索引；
    skills 目录规模小（每用户配额级），线性扫描成本可忽略。
    """
    root = _skills_root()
    if not root.exists():
        return None
    for child in root.iterdir():
        if not child.is_dir() or child.name.startswith("."):
            continue
        meta = _read_skill_meta(child)
        if meta and meta.get("content_hash") == content_hash:
            return child
    return None


def _load_skills_from(skill_dir: "Path | list[Path]") -> list:
    """加载物化出来的 Skill。

    load_skills_from_dir 要求「父目录/<name>/SKILL.md」布局且目录名=name，
    故必须从统一 skills 根目录（~/.Zest/skills）扫描，再按子目录过滤出本次
    bundle 物化的部分（支持一个 bundle 物化出多个目录）；source 指向各自
    本地目录（oss:// 不进 prompt）。
    """
    dirs = skill_dir if isinstance(skill_dir, list) else [skill_dir]
    repo, knowledge, agent = load_skills_from_dir(_skills_root())
    all_skills = list(repo.values()) + list(knowledge.values()) + list(agent.values())
    prefixes = [str(d.resolve()) + os.sep for d in dirs]
    def _in_bundle(s):
        loc = str(Path(str(getattr(s, "location", dirs[0]))).resolve())
        return any(loc.startswith(p) for p in prefixes)
    skills = [s for s in all_skills if _in_bundle(s)]
    if not skills:
        # 过滤兜底：location 字段缺失时退回全部（保证可用性）
        skills = all_skills
    if not skills:
        raise OssSkillFetchError(f"bundle 加载后无可用 skill: {skill_dir}")
    for s in skills:
        try:
            s.source = str(skill_dir)
        except Exception:  # noqa: BLE001 —— Skill 模型若禁写则跳过
            pass
    return skills
