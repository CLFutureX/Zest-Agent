from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from typing import Any

from common.utils.async_executor import AsyncExecutor
from sdk.agent.runner_context import RunnerContext
from common.logger import get_logger
from tools.sandbox.base import BaseSandbox as Sandbox
from tools.sandbox.config.settings import RuntimeType, SandboxConfig
from tools.sandbox.provider.process_provider import ProcessSandboxProvider

logger = get_logger(__name__)


@dataclass(frozen=True)
class SandboxSessionContext:
    session_id: str
    workspace_root: str


def run_async(coro):
    """Run async sandbox APIs from sync tool executors."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict[str, Any] = {}
    error: dict[str, BaseException] = {}

    def runner() -> None:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            result["value"] = loop.run_until_complete(coro)
        except BaseException as exc:  # noqa: BLE001
            error["value"] = exc
        finally:
            loop.close()

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()

    if "value" in error:
        raise error["value"]
    return result.get("value")


class SandboxSessionManager:
    """Conversation-scoped sandbox manager with lazy creation and reuse."""

    def __init__(self, config: SandboxConfig | None = None):
        self.config = config or SandboxConfig(mode=RuntimeType.PROCESS)
        self.provider = ProcessSandboxProvider(self.config)
        self.async_executor = AsyncExecutor()

    def resolve_context(
        self,
        context: RunnerContext | None,
        workspace_root: str,
    ) -> SandboxSessionContext:
        session_id = "default"
        if context is not None:
            conversation_id = getattr(context, "conversation_id", None)
            if conversation_id is not None:
                session_id = str(conversation_id)
        return SandboxSessionContext(
            session_id=session_id,
            workspace_root=workspace_root,
        )

    def run_in_session(self, coro):
        return self.async_executor.run_async(coro)

    def get_or_create(self, session: SandboxSessionContext) -> Sandbox:
        return self.async_executor.run_async(
            self.provider.get(
                sandbox_id=session.session_id,
                workspace_root=session.workspace_root,
            )
        )

    def get_or_create_for_context(
        self,
        context: RunnerContext | None,
        workspace_root: str,
    ) -> Sandbox:
        session = self.resolve_context(context, workspace_root)
        return self.get_or_create(session)

    def destroy(self, session_id: str) -> None:
        self.async_executor.run_async(self.provider.destroy(session_id))

    def release(self, session_id: str) -> None:
        self.async_executor.run_async(self.provider.release(session_id))

    def reclaim_idle(self) -> int:
        return self.async_executor.run_async(self.provider.reclaim_idle())


_DEFAULT_MANAGER: SandboxSessionManager | None = None


def get_default_session_manager() -> SandboxSessionManager:
    global _DEFAULT_MANAGER
    if _DEFAULT_MANAGER is None:
        _DEFAULT_MANAGER = SandboxSessionManager()
    return _DEFAULT_MANAGER