from __future__ import annotations



from abc import ABC, abstractmethod

from concurrent.futures import ThreadPoolExecutor

from typing import Any, Callable, Generic, TypeVar



from pydantic import BaseModel, ConfigDict, Field



InputT = TypeVar("InputT")

OutputT = TypeVar("OutputT")





class ChainContext(BaseModel):

    model_config = ConfigDict(arbitrary_types_allowed=True)



    state: dict[str, Any] = Field(default_factory=dict)

    metadata: dict[str, Any] = Field(default_factory=dict)



    def get(self, key: str, default: Any = None) -> Any:

        return self.state.get(key, default)



    def set(self, key: str, value: Any) -> "ChainContext":

        self.state[key] = value

        return self



    def extend(self, **values: Any) -> "ChainContext":

        self.state.update(values)

        return self



    def child(self) -> "ChainContext":

        return ChainContext(state=dict(self.state), metadata=dict(self.metadata))





class ChainStep(ABC, Generic[InputT, OutputT]):

    name: str



    def __init__(self, name: str | None = None) -> None:

        self.name = name or self.__class__.__name__



    @abstractmethod

    def invoke(self, value: InputT, context: ChainContext) -> OutputT:

        """Process one step and return the next value."""





class FunctionStep(ChainStep[InputT, OutputT]):

    def __init__(

        self,

        func: Callable[[InputT, ChainContext], OutputT],

        name: str | None = None,

    ) -> None:

        super().__init__(name=name or getattr(func, "__name__", "FunctionStep"))

        self._func = func



    def invoke(self, value: InputT, context: ChainContext) -> OutputT:

        return self._func(value, context)





class PassthroughStep(ChainStep[InputT, InputT]):



    def invoke(self, value: InputT, context: ChainContext) -> InputT:



        return value





class ChainStop(Generic[OutputT]):



    def __init__(self, output: OutputT) -> None:

        self.output = output





class ChainResult(BaseModel, Generic[OutputT]):



    model_config = ConfigDict(arbitrary_types_allowed=True)



    output: OutputT

    context: ChainContext

    executed_steps: list[str] = Field(default_factory=list)

    stopped: bool = False





class BranchStep(ChainStep[InputT, Any]):



    def __init__(

        self,

        predicate: Callable[[InputT, ChainContext], bool],

        if_true: "Chain[Any, Any] | ChainStep[Any, Any]",

        if_false: "Chain[Any, Any] | ChainStep[Any, Any] | None" = None,

        name: str | None = None,

    ) -> None:

        super().__init__(name=name or getattr(predicate, "__name__", "branch"))

        self._predicate = predicate

        self._if_true = ensure_chain(if_true)

        self._if_false = ensure_chain(if_false) if if_false is not None else None



    def invoke(self, value: InputT, context: ChainContext) -> Any:

        target = self._if_true if self._predicate(value, context) else self._if_false

        if target is None:

            return value

        result = target.invoke(value, context)

        return ChainStop(result.output) if result.stopped else result.output





class ParallelStep(ChainStep[InputT, dict[str, Any]]):



    def __init__(

        self,


