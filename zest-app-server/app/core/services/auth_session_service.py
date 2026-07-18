"""
Auth Session Service
管理登录 session 的生命周期（内存实现，生产可换 Redis/DB）
"""
from __future__ import annotations
import uuid
import asyncio
from datetime import datetime, timedelta
from typing import Optional

from app.core.models import AuthSessionRecord

SESSION_TTL_HOURS = 24 * 7  # 7 天

_sessions: dict[str, AuthSessionRecord] = {}
_lock = asyncio.Lock()


class AuthSessionService:
    """Auth session CRUD - 内存 store，接口稳定，后续可替换实现"""

    async def create_session(
        self,
        user_id: str,
        ip: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> AuthSessionRecord:
        session_id = str(uuid.uuid4())
        record = AuthSessionRecord(
            session_id=session_id,
            user_id=user_id,
            expires_at=datetime.utcnow() + timedelta(hours=SESSION_TTL_HOURS),
            ip=ip,
            user_agent=user_agent,
        )
        async with _lock:
            _sessions[session_id] = record
        return record

    async def get_session(self, session_id: str) -> Optional[AuthSessionRecord]:
        async with _lock:
            record = _sessions.get(session_id)
        if record is None:
            return None
        if datetime.utcnow() > record.expires_at:
            await self.delete_session(session_id)
            return None
        return record

    async def delete_session(self, session_id: str) -> None:
        async with _lock:
            _sessions.pop(session_id, None)

    async def delete_user_sessions(self, user_id: str) -> None:
        async with _lock:
            to_delete = [
                sid for sid, rec in _sessions.items() if rec.user_id == user_id
            ]
            for sid in to_delete:
                del _sessions[sid]
