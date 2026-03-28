"""
OpenHands Hooks System - Event-driven hooks for automation and control.

Hooks are event-driven scripts that execute at specific lifecycle events
during agent execution, enabling deterministic control over agent behavior.
"""

from sdk.hooks.config import (
    HOOK_EVENT_FIELDS,
    HookConfig,
    HookDefinition,
    HookMatcher,
    HookType,
)
from sdk.hooks.conversation_hooks import (
    HookEventProcessor,
    create_hook_callback,
)
from sdk.hooks.executor import HookExecutor, HookResult
from sdk.hooks.manager import HookManager
from sdk.hooks.types import HookDecision, HookEvent, HookEventType


__all__ = [
    "HOOK_EVENT_FIELDS",
    "HookConfig",
    "HookDefinition",
    "HookMatcher",
    "HookType",
    "HookExecutor",
    "HookResult",
    "HookManager",
    "HookEvent",
    "HookEventType",
    "HookDecision",
    "HookEventProcessor",
    "create_hook_callback",
]
