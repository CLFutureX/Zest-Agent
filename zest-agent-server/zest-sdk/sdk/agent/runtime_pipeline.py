from __future__ import annotations



from typing import Protocol



from sdk.agent.agent_spec import AgentSpec
from sdk.agent.runner_context import RunnerContext
from sdk.agent.runtime import AgentRuntime
from sdk.memory.memory_manager import ExperienceMemoryConsumer





class AgentRuntimeBuildStage(Protocol):

    def run(self, agent_spec: AgentSpec, context, runtime: AgentRuntime) -> AgentRuntime:

        ...





class AgentRuntimePipeline:

    def __init__(self, stages: list[AgentRuntimeBuildStage]):

        self._stages = stages



    def build(self, agent_spec: AgentSpec, context: RunnerContext) -> AgentRuntime:

        runtime = AgentRuntime()

        for stage in self._stages:

            runtime = stage.run(agent_spec, context, runtime)
 
        return runtime
    
