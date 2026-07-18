from collections.abc import Callable
from functools import wraps
import inspect
import os
from typing import Any

from dotenv import dotenv_values

from common.logger import get_logger


logger = get_logger(__name__)

_LANGFUSE_ENV_KEYS = [
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_HOST",
]

_langfuse_client: Any | None = None
_langfuse_observe: Callable[..., Any] | None = None
_is_initialized = False


def _get_env(key: str) -> str | None:
    return os.getenv(key) or dotenv_values().get(key)


def _load_langfuse_runtime() -> tuple[Callable[..., Any] | None, type[Any] | None]:
    global _langfuse_observe, _langfuse_client
    if _langfuse_observe is not None and _langfuse_client is not None:
        return _langfuse_observe, type(_langfuse_client)

    try:
        from langfuse import Langfuse, observe as langfuse_observe
    except ImportError:
        return None, None

    _langfuse_observe = langfuse_observe
    if _langfuse_client is None:
        _langfuse_client = Langfuse()
    return _langfuse_observe, type(_langfuse_client)


def _get_langfuse_client() -> Any | None:
    global _langfuse_client
    if _langfuse_client is not None:
        return _langfuse_client

    observe_runtime, client_cls = _load_langfuse_runtime()
    if observe_runtime is None or client_cls is None:
        return None
    _langfuse_client = client_cls()
    return _langfuse_client


def init_langfuse() -> None:
    global _is_initialized
    if _is_initialized or not should_enable_observability():
        return

    client = _get_langfuse_client()
    if client is None:
        logger.warning(
            "Langfuse is not installed, but observability is enabled by environment"
        )
        return
    _is_initialized = True


def _strip_ignored_inputs(payload: dict[str, Any], ignore_inputs: list[str]) -> dict[str, Any]:
    filtered = dict(payload)
    for field in ignore_inputs:
        filtered.pop(field, None)
    return filtered


def _update_current_observation(*, input_value: Any | None = None, output_value: Any | None = None, metadata: dict[str, Any] | None = None) -> None:
    client = _get_langfuse_client()
    if client is None:
        return

    update: dict[str, Any] = {}
    if input_value is not None:
        update["input"] = input_value
    if output_value is not None:
        update["output"] = output_value
    if metadata:
        update["metadata"] = metadata
    if not update:
        return

    client.update_current_span(**update)


def _build_observation_metadata(
    *,
    session_id: str | None,
    user_id: str | None,
    metadata: dict[str, Any] | None,
    tags: list[str] | None,
) -> dict[str, Any]:
    payload = dict(metadata or {})
    if session_id is not None:
        payload["session_id"] = session_id
    if user_id is not None:
        payload["user_id"] = user_id
    if tags:
        payload["tags"] = tags
    return payload


def observe(**decorator_kwargs: Any):
    name = decorator_kwargs.get("name")
    session_id = decorator_kwargs.get("session_id")
    user_id = decorator_kwargs.get("user_id")
    ignore_input = decorator_kwargs.get("ignore_input", False)
    ignore_output = decorator_kwargs.get("ignore_output", False)
    ignore_inputs = decorator_kwargs.get("ignore_inputs") or []
    input_formatter = decorator_kwargs.get("input_formatter")
    output_formatter = decorator_kwargs.get("output_formatter")
    metadata = decorator_kwargs.get("metadata")
    tags = decorator_kwargs.get("tags")

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        runtime_observe, _ = _load_langfuse_runtime()
        if runtime_observe is None:
            return func

        observed = runtime_observe(name=name)(func)
        signature = inspect.signature(func)

        def build_input_payload(bound: inspect.BoundArguments) -> dict[str, Any]:
            payload = dict(bound.arguments)
            if ignore_input:
                return {}
            payload = _strip_ignored_inputs(payload, ignore_inputs)
            if input_formatter is not None:
                return {"formatted_input": input_formatter(*bound.args, **bound.kwargs)}
            return payload

        def build_metadata(bound: inspect.BoundArguments) -> dict[str, Any]:
            resolved_session_id = session_id or bound.arguments.get("session_id")
            resolved_user_id = user_id or bound.arguments.get("user_id")
            return _build_observation_metadata(
                session_id=resolved_session_id,
                user_id=resolved_user_id,
                metadata=metadata,
                tags=tags,
            )

        if inspect.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args: Any, **inner_kwargs: Any) -> Any:
                init_langfuse()
                bound = signature.bind_partial(*args, **inner_kwargs)
                _update_current_observation(
                    input_value=build_input_payload(bound),
                    metadata=build_metadata(bound),
                )
                result = await observed(*args, **inner_kwargs)
                if ignore_output:
                    _update_current_observation(output_value=None)
                elif output_formatter is not None:
                    _update_current_observation(output_value=output_formatter(result))
                return result

            return async_wrapper

        @wraps(func)
        def sync_wrapper(*args: Any, **inner_kwargs: Any) -> Any:
            init_langfuse()
            bound = signature.bind_partial(*args, **inner_kwargs)
            _update_current_observation(
                input_value=build_input_payload(bound),
                metadata=build_metadata(bound),
            )
            result = observed(*args, **inner_kwargs)
            if ignore_output:
                _update_current_observation(output_value=None)
            elif output_formatter is not None:
                _update_current_observation(output_value=output_formatter(result))
            return result

        return sync_wrapper

    return decorator


def should_enable_observability() -> bool:
    if any(_get_env(key) for key in _LANGFUSE_ENV_KEYS):
        return True
    return _is_initialized


def start_active_span(name: str, session_id: str | None = None) -> None:
    init_langfuse()
    if not should_enable_observability():
        return

    client = _get_langfuse_client()
    if client is None:
        return
    client.update_current_span(name=name, metadata=_build_observation_metadata(session_id=session_id, user_id=None, metadata=None, tags=None))


def end_active_span() -> None:
    return None
