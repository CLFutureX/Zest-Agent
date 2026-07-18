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

        branches: dict[str, "Chain[Any, Any] | ChainStep[Any, Any]"],

        *,

        merge_into_context: bool = False,

        max_workers: int | None = None,

        name: str | None = None,

    ) -> None:

        super().__init__(name=name or "ParallelStep")

        self._branches = {key: ensure_chain(value) for key, value in branches.items()}

        self._merge_into_context = merge_into_context

        self._max_workers = max_workers or max(len(self._branches), 1)



    def invoke(self, value: InputT, context: ChainContext) -> dict[str, Any]:

        def _run(item: tuple[str, Chain[Any, Any]]) -> tuple[str, Any, ChainContext, bool]:

            key, branch = item

            child_context = context.child()

            result = branch.invoke(value, child_context)

            return key, result.output, child_context, result.stopped



        outputs: dict[str, Any] = {}

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:

            for key, output, child_context, stopped in executor.map(_run, self._branches.items()):

                outputs[key] = output

                if self._merge_into_context:

                    context.extend(**child_context.state)

                if stopped:

                    context.set(f"parallel_stopped_{key}", True)

        return outputs





class Chain(Generic[InputT, OutputT]):



    def __init__(self, steps: list[ChainStep[Any, Any]] | None = None) -> None:

        self._steps: list[ChainStep[Any, Any]] = list(steps or [])



    @property

    def steps(self) -> list[ChainStep[Any, Any]]:

        return list(self._steps)



    def then(self, step: "Chain[Any, Any] | ChainStep[Any, Any]") -> "Chain[InputT, Any]":

        if isinstance(step, Chain):

            self._steps.extend(step.steps)

            return self

        self._steps.append(step)

        return self



    def assign(

        self,

        key: str,

        func: Callable[[Any, ChainContext], Any],

        name: str | None = None,

    ) -> "Chain[InputT, Any]":

        def _assign(value: Any, context: ChainContext) -> Any:

            context.set(key, func(value, context))

            return value



        return self.then(FunctionStep(_assign, name=name or f"assign_{key}"))



    def tap(

        self,

        func: Callable[[Any, ChainContext], Any],

        name: str | None = None,

    ) -> "Chain[InputT, Any]":

        def _tap(value: Any, context: ChainContext) -> Any:

            func(value, context)

            return value



        return self.then(FunctionStep(_tap, name=name or getattr(func, "__name__", "tap")))



    def stop_if(

        self,

        predicate: Callable[[Any, ChainContext], bool],

        output: Callable[[Any, ChainContext], Any] | Any,

        name: str | None = None,

    ) -> "Chain[InputT, Any]":

        def _stop_if(value: Any, context: ChainContext) -> Any:

            if not predicate(value, context):

                return value

            stop_output = output(value, context) if callable(output) else output

            return ChainStop(stop_output)



        return self.then(FunctionStep(_stop_if, name=name or getattr(predicate, "__name__", "stop_if")))



    def branch(

        self,

        predicate: Callable[[Any, ChainContext], bool],

        if_true: "Chain[Any, Any] | ChainStep[Any, Any]",

        if_false: "Chain[Any, Any] | ChainStep[Any, Any] | None" = None,

        name: str | None = None,

    ) -> "Chain[InputT, Any]":

        return self.then(BranchStep(predicate, if_true=if_true, if_false=if_false, name=name))



    def parallel(

        self,

        branches: dict[str, "Chain[Any, Any] | ChainStep[Any, Any]"],

        *,

        merge_into_context: bool = False,

        max_workers: int | None = None,

        name: str | None = None,

    ) -> "Chain[InputT, dict[str, Any]]":

        return self.then(

            ParallelStep(

                branches,

                merge_into_context=merge_into_context,

                max_workers=max_workers,

                name=name,

            )

        )



    def invoke(

        self,

        value: InputT,

        context: ChainContext | None = None,

    ) -> ChainResult[Any]:

        runtime_context = context or ChainContext()

        current: Any = value

        executed_steps: list[str] = []

        stopped = False



        for step in self._steps:

            current = step.invoke(current, runtime_context)

            executed_steps.append(step.name)

            if isinstance(current, ChainStop):

                stopped = True

                current = current.output

                break



        return ChainResult(

            output=current,

            context=runtime_context,

            executed_steps=executed_steps,

            stopped=stopped,

        )





def ensure_chain(

    step: "Chain[Any, Any] | ChainStep[Any, Any] | Callable[[Any, ChainContext], Any]",

) -> Chain[Any, Any]:

    if isinstance(step, Chain):

        return step

    if isinstance(step, ChainStep):

        return Chain([step])

    return Chain([FunctionStep(step)])





def chain(

    step: ChainStep[InputT, OutputT] | Callable[[InputT, ChainContext], OutputT],

) -> Chain[InputT, OutputT]:

    return ensure_chain(step)
