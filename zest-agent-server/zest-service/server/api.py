import asyncio
import traceback
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from redis.asyncio import from_url as redis_from_url
from starlette.requests import Request

from  server.agent_registry import DefaultServerInfoProvider, RedisAgentRegistryClient 
from  server.config import (
    Config,
    get_default_config,
)
from  server.conversation_router import conversation_router
from  server.conversation_service import (
    get_default_conversation_service,
)
from  server.dependencies import create_session_api_key_dependency 
from server.event_router import event_router
from server.file_router import file_router 
from server.middleware import LocalhostCORSMiddleware
from server.server_details_router import (
    get_server_info,
    server_details_router,
)
from server.skills_router import skills_router
from server.sockets import sockets_router
from server.tool_preload_service import get_tool_preload_service
from server.tool_router import tool_router 
from common.logger import DEBUG,get_logger


logger = get_logger(__name__)


@asynccontextmanager
async def api_lifespan(api: FastAPI) -> AsyncIterator[None]:
    service = get_default_conversation_service() 
    tool_preload_service = get_tool_preload_service()
    config = get_default_config()
    registry_client: RedisAgentRegistryClient | None = None
    registry_task: asyncio.Task[None] | None = None

    # Define async functions for starting each service
    async def start_tool_preload_service():
        if tool_preload_service is not None:
            tool_preload_started = await tool_preload_service.start()
            if tool_preload_started:
                logger.info("Tool preload service started successfully")
            else:
                logger.warning("Tool preload service failed to start - skipping")
        else:
            logger.info("Tool preload service is disabled")

    async def start_registry_client():
        nonlocal registry_client, registry_task
      
        host = "127.0.0.1"  if config.agent_server_host == '0.0.0.0' else  config.agent_server_host
        server_info_provider = DefaultServerInfoProvider(
            server_id=config.resolved_agent_server_id,
            host=host,
            port=config.agent_server_port,
            tags=config.registry_tags,
        )
        if config.registry_backend == "local":
            from server.agent_registry import LocalAgentRegistryClient
            registry_client = LocalAgentRegistryClient(
                registry_dir=config.registry_dir,
                server_info_provider=server_info_provider,
                heartbeat_interval=config.heartbeat_interval,
            )
            logger.info("Agent registry backend: local (dir=%s)", config.registry_dir)
        else:
            redis_client = redis_from_url(config.registry_redis_url, decode_responses=True)
            registry_client = RedisAgentRegistryClient(
                redis_client=redis_client,
                server_info_provider=server_info_provider,
                heartbeat_interval=config.heartbeat_interval,
                ttl_seconds=config.heartbeat_timeout,
                key_prefix=config.registry_key_prefix,
            )
            logger.info("Agent registry backend: redis (url=%s)", config.registry_redis_url)
        registry_task = asyncio.create_task(registry_client.register_loop())
        api.state.registry_client = registry_client
        api.state.registry_task = registry_task
        logger.info("Agent registry client started: %s", registry_client.server_id)

    # Start all services concurrently
    await asyncio.gather(start_tool_preload_service(), start_registry_client())
     
    async with service:
        # Store the initialized service in app state for dependency injection
        api.state.conversation_service = service
        try:
            yield
        finally:
            # Define async functions for stopping each service 
            async def stop_tool_preload_service():
                if tool_preload_service is not None:
                    await tool_preload_service.stop()

            async def stop_registry_client():
                if registry_client is None:
                    return
                await registry_client.deregister(registry_client.server_id)
                if registry_task is not None:
                    registry_task.cancel()
                    try:
                        await registry_task
                    except asyncio.CancelledError:
                        pass
                await registry_client.close()

            # Stop all services concurrently
            await asyncio.gather(stop_tool_preload_service(), stop_registry_client())


def _create_fastapi_instance() -> FastAPI:
    """Create the basic FastAPI application instance.

    Returns:
        Basic FastAPI application with title, description, and lifespan.
    """
    return FastAPI(
        title="Zest Agent Server",
        description=(
            "Zest Agent Server - REST/WebSocket interface for Zest AI Agent"
        ),
        lifespan=api_lifespan,
    )


def _find_http_exception(exc: BaseExceptionGroup) -> HTTPException | None:
    """Helper function to find HTTPException in ExceptionGroup.

    Args:
        exc: BaseExceptionGroup to search for HTTPException.

    Returns:
        HTTPException if found, None otherwise.
    """
    for inner_exc in exc.exceptions:
        if isinstance(inner_exc, HTTPException):
            return inner_exc
        # Recursively search nested ExceptionGroups
        if isinstance(inner_exc, BaseExceptionGroup):
            found = _find_http_exception(inner_exc)
            if found:
                return found
    return None


def _add_api_routes(app: FastAPI, config: Config) -> None:
    """Add all API routes to the FastAPI application.

    Args:
        app: FastAPI application instance to add routes to.
    """
    app.include_router(server_details_router)

    dependencies = []
    if config.session_api_keys:
        dependencies.append(Depends(create_session_api_key_dependency(config)))

    api_router = APIRouter(prefix="/api", dependencies=dependencies)
    api_router.include_router(event_router)
    api_router.include_router(conversation_router)
    api_router.include_router(tool_router) 
    api_router.include_router(file_router) 
    api_router.include_router(skills_router)
    app.include_router(api_router)
    app.include_router(sockets_router)


def _setup_static_files(app: FastAPI, config: Config) -> None:
    """Set up static file serving and root redirect if configured.

    Args:
        app: FastAPI application instance.
        config: Configuration object containing static files settings.
    """
    # Only proceed if static files are configured and directory exists
    if not (
        config.static_files_path
        and config.static_files_path.exists()
        and config.static_files_path.is_dir()
    ):
        # Map the root path to server info if there are no static files
        app.get("/")(get_server_info)
        return

    # Mount static files directory
    app.mount(
        "/static",
        StaticFiles(directory=str(config.static_files_path)),
        name="static",
    )

    # Add root redirect to static files
    @app.get("/", tags=["Server Details"])
    async def root_redirect():
        """Redirect root endpoint to static files directory."""
        # Check if index.html exists in the static directory
        # We know static_files_path is not None here due to the outer condition
        assert config.static_files_path is not None
        index_path = config.static_files_path / "index.html"
        if index_path.exists():
            return RedirectResponse(url="/static/index.html", status_code=302)
        else:
            return RedirectResponse(url="/static/", status_code=302)


def _add_exception_handlers(api: FastAPI) -> None:
    """Add exception handlers to the FastAPI application."""

    @api.exception_handler(Exception)
    async def _unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """Handle unhandled exceptions."""
        # Always log that we're in the exception handler for debugging
        logger.debug(
            "Exception handler called for %s %s with %s: %s",
            request.method,
            request.url.path,
            type(exc).__name__,
            str(exc),
        )

        content = {
            "detail": "Internal Server Error",
            "exception": str(exc),
        }
        # In DEBUG mode, include stack trace in response
        if DEBUG:
            content["traceback"] = traceback.format_exc()
        # Check if this is an HTTPException that should be handled directly
        if isinstance(exc, HTTPException):
            return await _http_exception_handler(request, exc)

        # Check if this is a BaseExceptionGroup with HTTPExceptions
        if isinstance(exc, BaseExceptionGroup):
            http_exc = _find_http_exception(exc)
            if http_exc:
                return await _http_exception_handler(request, http_exc)
            # If no HTTPException found, treat as unhandled exception
            logger.error(
                "Unhandled ExceptionGroup on %s %s",
                request.method,
                request.url.path,
                exc_info=(type(exc), exc, exc.__traceback__),
            )
            return JSONResponse(status_code=500, content=content)

        # Logs full stack trace for any unhandled error that FastAPI would
        # turn into a 500
        logger.error(
            "Unhandled exception on %s %s",
            request.method,
            request.url.path,
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        return JSONResponse(status_code=500, content=content)

    @api.exception_handler(HTTPException)
    async def _http_exception_handler(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        """Handle HTTPExceptions with appropriate logging."""
        # Log 4xx errors at info level (expected client errors like auth failures)
        if 400 <= exc.status_code < 500:
            logger.info(
                "HTTPException %d on %s %s: %s",
                exc.status_code,
                request.method,
                request.url.path,
                exc.detail,
            )
        # Log 5xx errors at error level with full traceback (server errors)
        elif exc.status_code >= 500:
            logger.error(
                "HTTPException %d on %s %s: %s",
                exc.status_code,
                request.method,
                request.url.path,
                exc.detail,
                exc_info=(type(exc), exc, exc.__traceback__),
            )
            content = {
                "detail": "Internal Server Error",
                "exception": str(exc),
            }
            if DEBUG:
                content["traceback"] = traceback.format_exc()
            # Don't leak internal details to clients for 5xx errors in production
            return JSONResponse(
                status_code=exc.status_code,
                content=content,
            )

        # Return clean JSON response for all non-5xx HTTP exceptions
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


def create_app(config: Config | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        config: Configuration object. If None, uses default config.

    Returns:
        Configured FastAPI application.
    """
    if config is None:
        config = get_default_config()
    app = _create_fastapi_instance()
    _add_api_routes(app, config)
    _setup_static_files(app, config)
    app.add_middleware(LocalhostCORSMiddleware, allow_origins=config.allow_cors_origins)
    _add_exception_handlers(app)

    return app


# Create the default app instance
api = create_app()