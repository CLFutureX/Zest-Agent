import uuid

from sdk.agent.agent_spec import AgentSpec

from sdk.agent.agent_state import AgentState

from sdk.agent.sub_agent_config import SubAgentSpec





class SubAgentResolver:

    """Resolve child agent specs from parent state and subagent overrides."""



    @staticmethod

    def resolve(parent_state: AgentState, spec: SubAgentSpec) -> AgentSpec:

        system_prompt_kwargs = dict(parent_state.system_prompt_kwargs)

        if spec.system_prompt_kwargs:

            system_prompt_kwargs.update(spec.system_prompt_kwargs)



        return AgentSpec(

            id=spec.id + "-" + uuid.uuid4().hex[:8],

            llm=spec.llm or parent_state.llm,

            tools=parent_state.tools if spec.tools is None else spec.tools,

            mcp_config=dict(parent_state.mcp_config),

            filter_tools_regex=parent_state.filter_tools_regex,

            include_default_tools=list(parent_state.include_default_tools),

            agent_context_spec=parent_state.agent_context_spec,

            custom_system_prompt=(

                spec.custom_system_prompt

                if spec.custom_system_prompt is not None

                else parent_state.custom_system_prompt

            ),

            system_prompt_filename=(

                spec.system_prompt_filename

                if spec.system_prompt_filename is not None

                else parent_state.system_prompt_filename

            ),

            security_policy_filename=(

                spec.security_policy_filename

                if spec.security_policy_filename is not None

                else parent_state.security_policy_filename

            ),

            system_prompt_kwargs=system_prompt_kwargs,

        )
