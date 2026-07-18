"""
Auth 路由
GET  /api/v1/auth/session       — 查询当前登录态
POST /api/v1/auth/login/password — 密码登录
POST /api/v1/auth/logout         — 登出
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.core.models import (
    AuthSessionResponse,
    PasswordLoginRequest,
    PasswordLoginResponse,
    RegisterRequest,
    RegisterResponse,
)
from app.api.dependencies import get_auth_service
from app.core.services.auth_service import AuthService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.get("/session", response_model=AuthSessionResponse)
async def get_session(
    request: Request,
    auth: AuthService = Depends(get_auth_service),
):
    """查询当前登录态（无需鉴权，前端首次加载调用）"""
    return await auth.get_current_session(request)


@router.post("/login/password", response_model=PasswordLoginResponse)
async def login_password(
    body: PasswordLoginRequest,
    request: Request,
    response: Response,
    auth: AuthService = Depends(get_auth_service),
):
    """密码登录"""
    user = await auth.login_with_password(
        account=body.account,
        password=body.password,
        request=request,
        response=response,
    )
    if user is None:
        raise HTTPException(status_code=401, detail="账号或密码错误")
    return PasswordLoginResponse(user=user)


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    auth: AuthService = Depends(get_auth_service),
):
    """登出"""
    await auth.logout(request, response)
    return {"status": "ok"}

@router.post("/register", response_model=RegisterResponse, status_code=201)
async def register(
    body: RegisterRequest,
    auth: AuthService = Depends(get_auth_service),
):
    """注册新用户"""
    user, err = await auth.register(
        username=body.username.strip(),
        email=body.email.strip(),
        password=body.password,
    )
    if err == "username_taken":
        raise HTTPException(status_code=409, detail="Username already taken")
    if err == "email_taken":
        raise HTTPException(status_code=409, detail="Email already registered")
    if user is None:
        raise HTTPException(status_code=500, detail="Registration failed")
    return RegisterResponse(user=user)

