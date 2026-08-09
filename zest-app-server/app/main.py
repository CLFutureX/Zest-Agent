"""
FastAPI 应用入口
- 启动时装配 StorageBackend / Registry / HealthChecker
- 关闭时按反向顺序释放资源
- 路由统一在 /api/v1 前缀下注册
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    agent_profile_route,
    agentservers,
    app_conversation_query_route,
    app_conversation_route,
    auth_route,
    health,
)
from app.api.dependencies import (
    close_registry,
    close_storage,
    init_registry,
    init_storage,
    _seed_default_user,
)
from app.config.settings import settings

# 配置日志
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(settings.log_file, encoding="utf-8"),
    ],
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """应用生命周期"""
    logger.info("Starting %s", settings.app_name)
    logger.info("Storage mode: %s", settings.storage_mode)
    logger.info("Registry mode: %s", settings.registry_mode)

    # 创建必要的目录
    os.makedirs("logs", exist_ok=True)
    Path(settings.local_data_dir).mkdir(parents=True, exist_ok=True)

    # 初始化存储
    await init_storage()
    logger.info("Storage initialized")

    # 预置默认用户（仅 local 存储模式）
    await _seed_default_user()

    # 初始化服务注册中心
    await init_registry()
    logger.info("Registry initialized")

    yield

    # 关闭
    logger.info("Shutting down %s", settings.app_name)
    await close_registry()
    logger.info("Registry closed")
    await close_storage()
    logger.info("Storage closed")


app = FastAPI(
    lifespan=lifespan,
    title=settings.app_name,
    description="Zest-Agent AppServer - 控制面服务",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# 配置 CORS
# 注意：allow_origins + allow_credentials 不能同时为 ["*"]，浏览器会拒绝。
# 默认放开所有来源但不带凭证；生产请改成具体域名白名单并启用 allow_credentials=True。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由（各 router 自带 /api/v1 前缀）
app.include_router(app_conversation_route.router)
app.include_router(app_conversation_query_route.router)
app.include_router(agent_profile_route.router)
app.include_router(auth_route.router)
app.include_router(health.router)
app.include_router(agentservers.router)


@app.get("/")
async def root():
    """根路径"""
    return {
        "name": settings.app_name,
        "version": "1.0.0",
        "status": "running",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        workers=1 if settings.debug else settings.workers,
    )
