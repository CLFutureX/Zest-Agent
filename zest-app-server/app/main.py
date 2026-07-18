"""
FastAPI应用入口
"""
from contextlib import asynccontextmanager

from pathlib import Path

from typing import AsyncGenerator



from fastapi import FastAPI

from fastapi.middleware.cors import CORSMiddleware

from fastapi.responses import FileResponse

import logging



from app.config.settings import settings



from app.api import agent_profile_route, agentservers, app_conversation_query_route, app_conversation_route, health, auth_route

from app.api.dependencies import init_storage, init_registry, close_registry, _seed_default_user





# 配置日志

logging.basicConfig(

    level=getattr(logging, settings.log_level),

    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",

    handlers=[

        logging.StreamHandler(),

        logging.FileHandler(settings.log_file, encoding='utf-8')

    ]

)



logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parents[1] / "static"

 





@asynccontextmanager

async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:

    """应用启动事件"""

    logger.info(f"Starting {settings.app_name}")

    logger.info(f"Storage mode: {settings.storage_mode}")

    logger.info(f"Registry mode: {settings.registry_mode}")



    # 创建必要的目录

    import os

    os.makedirs("logs", exist_ok=True)

    os.makedirs(settings.local_data_dir, exist_ok=True)



    # 初始化存储

    await init_storage()

    logger.info("Storage initialized")



    # 预置默认用户（仅内存模式）

    await _seed_default_user()




    # 初始化服务注册中心

    await init_registry()

    logger.info("Registry initialized")



    yield



    """应用关闭事件"""

    logger.info(f"Shutting down {settings.app_name}")



    # 关闭服务注册中心

    await close_registry()

    logger.info("Registry closed")



    # 关闭 PostgreSQL 连接池（如果使用）

     


    # 关闭 MySQL 连接池（如果使用）

    if settings.storage_mode == "mysql":

        from app.core.storage.mysql import close_mysql_pool

        await close_mysql_pool()

        logger.info("MySQL pool closed")





# 创建FastAPI应用

app = FastAPI(

    lifespan=lifespan,

    title=settings.app_name,

    description="Zest-Agent AppServer - 控制面服务",

    version="1.0.0",

    docs_url="/docs",

    redoc_url="/redoc"

)



# 配置CORS

app.add_middleware(

    CORSMiddleware,

    allow_origins=["*"],  # 生产环境应该限制具体域名

    allow_credentials=True,

    allow_methods=["*"],

    allow_headers=["*"],

)



# 注册路由







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

        "status": "running"

    }




 





 

if __name__ == "__main__":
    import uvicorn
   
    uvicorn.run( 
        "app.main:app",
        host=settings.host, 
        port=settings.port, 
        workers=1 if settings.debug else settings.workers
    )
