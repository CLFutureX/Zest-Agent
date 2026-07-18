from collections.abc import Callable
from typing import Any

from common.observability.langfuse_backend import (
    end_active_span,
    init_langfuse,
    observe,
    should_enable_observability,
    start_active_span,
)


def maybe_init_laminar() -> None:
    """Compatibility shim for legacy Laminar imports."""
    init_langfuse()


__all__ = [
    "end_active_span",
    "maybe_init_laminar",
    "observe",
    "should_enable_observability",
    "start_active_span",
]
