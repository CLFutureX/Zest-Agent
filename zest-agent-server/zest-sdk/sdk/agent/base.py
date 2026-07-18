
from abc import ABC, abstractmethod
from collections.abc import Generator, Iterable
from typing import TYPE_CHECKING
 
from pydantic import BaseModel, PrivateAttr
 
from sdk.agent.agent_spec import   AgentSpec
from sdk.agent.runtime import AgentRuntime

from sdk.llm import LLM

from sdk.tool import ToolDefinition


if TYPE_CHECKING:
    from sdk.agent.runner_context import RunnerContext





class AgentBase(AgentSpec,ABC):

    """Agent 仅负责调度，"""
 
    _runtime: AgentRuntime | None = PrivateAttr(default=None)

    

    @property
    def name(self) -> str:
        return self.__class__.__name__

    def bind_runtime(self, runtime: AgentRuntime) -> None:
        self._runtime = runtime

    def require_runtime(self) -> AgentRuntime:
        if self._runtime is None:
            raise RuntimeError(
                "Agent runtime is not ready; AgentRunner must ensure runtime before access"
            )
        return self._runtime

    @property
    def system_message(self) -> str:
        return self.require_runtime().system_message

    @property
    def tools_map(self) -> dict[str, ToolDefinition]:
        return self.require_runtime().tools_map

    def init_state(
        self,
        context: "RunnerContext",
    ) -> None:
        self.require_runtime()

    @abstractmethod
    def step(
        self,
        context: "RunnerContext",
    ) -> None:
        """Taking a step in the conversation."""

    def model_dump_succint(self, **kwargs):
        if "exclude_none" not in kwargs:
            kwargs["exclude_none"] = True
        dumped = super().model_dump(**kwargs)
        if "tools" in dumped and isinstance(dumped["tools"], dict):
            dumped["tools"] = list(dumped["tools"].keys())
        return dumped

    def get_all_llms(self) -> Generator[LLM]:
        """Recursively yield unique *base-class* LLM objects reachable from `self`.

        - Returns actual object references (not copies).
        - De-dupes by `id(LLM)`.
        - Cycle-safe via a visited set for *all* traversed objects.
        - Only yields objects whose type is exactly `LLM` (no subclasses).
        - Does not handle dataclasses.
        """
        yielded_ids: set[int] = set()
        visited: set[int] = set()

        def _walk(obj: object) -> Iterable[LLM]:
            oid = id(obj)
            # Guard against cycles on anything we might recurse into
            if oid in visited:
                return ()
            visited.add(oid)

            # Traverse LLM based classes and its fields
            # e.g., LLMRouter that is a subclass of LLM
            # yet contains LLM in its fields
            if isinstance(obj, LLM):
                llm_out: list[LLM] = []

                # Yield only the *raw* base-class LLM (exclude subclasses)
                if type(obj) is LLM and oid not in yielded_ids:
                    yielded_ids.add(oid)
                    llm_out.append(obj)

                # Traverse all fields for LLM objects
                for name in type(obj).model_fields:
                    try:
                        val = getattr(obj, name)
                    except Exception:
                        continue
                    llm_out.extend(_walk(val))
                return llm_out

            # Pydantic models: iterate declared fields
            if isinstance(obj, BaseModel):
                model_out: list[LLM] = []
                for name in type(obj).model_fields:
                    try:
                        val = getattr(obj, name)
                    except Exception:
                        continue
                    model_out.extend(_walk(val))
                return model_out

            # Built-in containers
            if isinstance(obj, dict):
                dict_out: list[LLM] = []
                for k, v in obj.items():
                    dict_out.extend(_walk(k))
                    dict_out.extend(_walk(v))
                return dict_out

            if isinstance(obj, (list, tuple, set, frozenset)):
                container_out: list[LLM] = []
                for item in obj:
                    container_out.extend(_walk(item))
                return container_out

            # Unknown object types: nothing to do
            return ()

        # Drive the traversal from self
        yield from _walk(self)
