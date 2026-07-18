"""
User Service
用户查询 / 创建（密码登录场景）
"""
from __future__ import annotations
import uuid
import hashlib
import logging
from typing import Optional

from app.core.models import AuthUser
from app.core.storage.base import UserStorage

logger = logging.getLogger(__name__)


def _hash_password(plain: str) -> str:
    """SHA-256 简单 hash（第一版；生产建议换 bcrypt）"""
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def _verify_password(plain: str, hashed: str) -> bool:
    return _hash_password(plain) == hashed


class UserService:
    def __init__(self, user_storage: UserStorage):
        self._storage = user_storage

    async def get_user_by_id(self, user_id: str) -> Optional[AuthUser]:
        return await self._storage.get_user_by_id(user_id)

    async def get_user_by_account(self, account: str) -> Optional[AuthUser]:
        """按用户名或邮箱查找用户"""
        user = await self._storage.get_user_by_username(account)
        if user is None:
            user = await self._storage.get_user_by_email(account)
        return user

    async def verify_password(self, account: str, password: str) -> Optional[AuthUser]:
        """校验密码，成功返回用户，失败返回 None"""
        user = await self.get_user_by_account(account)
        if user is None or not user.is_active:
            return None
        if not _verify_password(password, user.password_hash):
            return None
        return user

    async def create_user(
        self, username: str, email: str, password: str
    ) -> Optional[AuthUser]:
        """创建新用户，同时校验 username 和 email 唯一性"""
        if await self._storage.get_user_by_username(username):
            return None
        if await self._storage.get_user_by_email(email):
            return None
        user = AuthUser(
            user_id=str(uuid.uuid4()),
            username=username,
            email=email,
            password_hash=_hash_password(password),
        )
        ok = await self._storage.create_user(user)
        return user if ok else None
