"""
Auth Service
登录 / 登出 / Session 查询的主入口
"""
from __future__ import annotations
import logging
from typing import Optional

from fastapi import Request, Response

from app.core.models import AuthSessionUser, AuthSessionResponse
from app.core.services.user_service import UserService
from app.core.services.auth_session_service import AuthSessionService

COOKIE_NAME = "zest_auth_session"
logger = logging.getLogger(__name__)


def _to_session_user(user) -> AuthSessionUser:
    return AuthSessionUser(
        id=user.user_id,
        username=user.username,
        display_name=user.username,
        email=user.email,
    )


class AuthService:
    def __init__(
        self,
        user_service: UserService,
        session_service: AuthSessionService,
    ):
        self._users = user_service
        self._sessions = session_service

    # ----------------------------------------------------------
    # 查询当前登录态
    # ----------------------------------------------------------
    async def get_current_session(self, request: Request) -> AuthSessionResponse:
        session_id = request.cookies.get(COOKIE_NAME)
        if not session_id:
            return AuthSessionResponse(authenticated=False)
        record = await self._sessions.get_session(session_id)
        if record is None:
            return AuthSessionResponse(authenticated=False)
        user = await self._users.get_user_by_id(record.user_id)
        if user is None:
            return AuthSessionResponse(authenticated=False)
        return AuthSessionResponse(
            authenticated=True,
            user=_to_session_user(user),
        )

    # ----------------------------------------------------------
    # 密码登录
    # ----------------------------------------------------------
    async def login_with_password(
        self,
        account: str,
        password: str,
        request: Request,
        response: Response,
    ) -> Optional[AuthSessionUser]:
        user = await self._users.verify_password(account, password)
        if user is None:
            return None
        ip = request.client.host if request.client else None
        ua = request.headers.get("user-agent")
        record = await self._sessions.create_session(
            user_id=user.user_id, ip=ip, user_agent=ua
        )
        response.set_cookie(
            key=COOKIE_NAME,
            value=record.session_id,
            httponly=True,
            samesite="lax",
            max_age=60 * 60 * 24 * 7,
        )
        return _to_session_user(user)

    # ----------------------------------------------------------
    # 登出
    # ----------------------------------------------------------
    async def logout(self, request: Request, response: Response) -> None:
        session_id = request.cookies.get(COOKIE_NAME)
        if session_id:
            await self._sessions.delete_session(session_id)
        response.delete_cookie(key=COOKIE_NAME)
    # ----------------------------------------------------------
    # Register
    # ----------------------------------------------------------
    async def register(
        self,
        username: str,
        email: str,
        password: str,
    ) -> tuple[Optional[AuthSessionUser], Optional[str]]:
        """Register a new user. Returns (AuthSessionUser | None, error_msg | None)."""
        existing_name = await self._users.get_user_by_account(username)
        if existing_name:
            return None, "username_taken"
        existing_email = await self._users.get_user_by_account(email)  # checks by email
        if existing_email:
            return None, "email_taken"
        user = await self._users.create_user(
            username=username, email=email, password=password
        )
        if user is None:
            return None, "create_failed"
        return _to_session_user(user), None

