import json

from pydantic import Field, ValidationError, model_validator

import sdk.security.analyzer as analyzer
import sdk.security.risk as risk
from sdk.agent.base import AgentBase
from sdk.agent.runner_context import RunnerContext
from sdk.agent.utils import (
    fix_malformed_tool_arguments,
    make_llm_completion,
    prepare_llm_messages,
)
from sdk.conversation import (
    ConversationState,
)
from sdk.critic.base import CriticResult
from sdk.event import (
    ActionEvent,
    AgentErrorEvent,
    LLMConvertibleEvent,
    MessageEvent,
    ObservationEvent,
    SystemPromptEvent,
    TokenEvent,
    UserRejectObservation,
)
from sdk.event.condenser import (
    Condensation,
    CondensationRequest,
)
from sdk.llm import (
    LLMResponse,
    Message,
    MessageToolCall,
    ReasoningItemModel,
    RedactedThinkingBlock,
    TextContent,
    ThinkingBlock,
)
from sdk.llm.exceptions import (
    FunctionCallValidationError,
    LLMContextWindowExceedError,
)
from sdk.logger import get_logger
from sdk.observability.laminar import (
    maybe_init_laminar,
    observe,
    should_enable_observability,
)
from sdk.observability.utils import extract_action_name
from sdk.security.llm_analyzer import LLMSecurityAnalyzer
from sdk.tool import (
    Action,
    Observation,
)
from sdk.tool.builtins import (
    FinishAction,
    FinishTool,
    ThinkAction,
)
from sdk.tool.builtins.sub_agent_tool import (
    SUBAGENT_DESCRIPTION,
    SubAgentConfig,
    SubAgentTool,
)


logger = get_logger(__name__)
maybe_init_laminar()


class Agent(AgentBase):
    """Main agent implementation for OpenHands.

    The Agent class provides the core functionality for running AI agents that can
    interact with tools, process messages, and execute actions. It inherits from
    AgentBase and implements the agent execution logic.

    Example:
        >>> from sdk import LLM, Agent, Tool
        >>> llm = LLM(model="claude-sonnet-4-20250514", api_key=SecretStr("key"))
        >>> tools = [Tool(name="TerminalTool"), Tool(name="FileEditorTool")]
        >>> agent = Agent(llm=llm, tools=tools)
    """

    # SubAgent配置列表 - 用于支持SubAgent功能
    subagent_configs: list[SubAgentConfig] | None = Field(
        default=None, description="SubAgent配置列表，用于支持SubAgent功能"
    )

    @model_validator(mode="before")
    @classmethod
    def _handle_system_prompt_and_security(cls, data):
        """处理直接的system_prompt参数和安全分析器配置。

        这个validator做两件事：
        1. 如果提供了system_prompt字符串，将其映射到custom_system_prompt字段
        2. 确保llm_security_analyzer=True被设置为默认值
        """
        if not isinstance(data, dict):
            return data

        # 处理直接的system_prompt参数
        if "system_prompt" in data and data["system_prompt"]:
            system_prompt_str = data.pop("system_prompt")
            # 将system_prompt字符串映射到custom_system_prompt字段
            data["custom_system_prompt"] = system_prompt_str

        # 处理安全分析器配置
        kwargs = data.get("system_prompt_kwargs") or {}
        if not isinstance(kwargs, dict):
            kwargs = {}

        kwargs.setdefault("llm_security_analyzer", True)
        data["system_prompt_kwargs"] = kwargs

        return data

    def init_state(
        self,
        state: ConversationState,
        context: RunnerContext,
    ) -> None:
        super().init_state(state, context)
        # TODO(openhands): we should add test to test this init_state will actually
        # modify state in-place

        # Defensive check: Analyze state to detect unexpected initialization scenarios
        # These checks help diagnose issues related to lazy loading and event ordering
        # See: https://github.com/OpenHands/software-agent-sdk/issues/1785
        events = list(context.events)
        has_system_prompt = any(isinstance(e, SystemPromptEvent) for e in events)
        has_user_message = any(
            isinstance(e, MessageEvent) and e.source == "user" for e in events
        )
        has_any_llm_event = any(isinstance(e, LLMConvertibleEvent) for e in events)

        # Log state for debugging initialization order issues
        logger.debug(
            f"init_state called: conversation_id={state.id}, "
            f"event_count={len(events)}, "
            f"has_system_prompt={has_system_prompt}, "
            f"has_user_message={has_user_message}, "
            f"has_any_llm_event={has_any_llm_event}"
        )

        if has_system_prompt:
            # SystemPromptEvent already exists - this is unexpected during normal flow
            # but could happen in persistence/resume scenarios
            logger.warning(
                f"init_state called but SystemPromptEvent already exists. "
                f"conversation_id={state.id}, event_count={len(events)}. "
                f"This may indicate double initialization or a resume scenario."
            )
            return

        # Assert: If there are user messages but no system prompt, something is wrong
        # The system prompt should always be added before any user messages
        if has_user_message:
            event_types = [type(e).__name__ for e in events]
            logger.error(
                f"init_state: User message exists without SystemPromptEvent! "
                f"conversation_id={state.id}, events={event_types}"
            )
            assert not has_user_message, (
                f"Unexpected state: User message exists before SystemPromptEvent. "
                f"conversation_id={state.id}, event_count={len(events)}, "
                f"event_types={event_types}. "
                f"This indicates an initialization order bug - init_state should be "
                f"called before any user messages are added to the conversation."
            )

        system_prompts = self.system_message
        # 如果有SubAgent配置，添加SubAgentTool
        if self.subagent_configs:
            system_prompts += SUBAGENT_DESCRIPTION
            for subagent_config in self.subagent_configs:
                try:
                    # 使用create方法创建SubAgentTool实例
                    subagent_tools = SubAgentTool.create(
                        conv_state=state,
                        subagent_config=subagent_config,
                        tools=self.tools,
                    )
                    # 添加到tools_map
                    self.tools_map[subagent_config.name] = subagent_tools[0]
                    logger.info(
                        f"Added SubAgentTool with {subagent_config.name} subagent"
                    )

                except Exception as e:
                    logger.error(f"Failed to add SubAgentTool: {str(e)}", exc_info=True)

        # Prepare system message
        event = SystemPromptEvent(
            source="agent",
            system_prompt=TextContent(text=system_prompts),
            # Tools are stored as ToolDefinition objects and converted to
            # OpenAI format with security_risk parameter during LLM completion.
            # See make_llm_completion() in agent/utils.py for details.
            tools=list(self.tools_map.values()),
        )
        context.publish_event(event)

    def _should_evaluate_with_critic(self, action: Action | None) -> bool:
        """Determine if critic should evaluate based on action type and mode."""
        if self.critic is None:
            return False

        if self.critic.mode == "all_actions":
            return True

        # For "finish_and_message" mode, only evaluate FinishAction
        # (MessageEvent will be handled separately in step())
        if isinstance(action, FinishAction):
            return True

        return False

    def _evaluate_with_critic(
        self, context: RunnerContext, event: ActionEvent | MessageEvent
    ) -> CriticResult | None:
        """Run critic evaluation on the current event and history."""
        if self.critic is None:
            return None

        try:
            # Build event history including the current event
            events = list(context.events) + [event]
            llm_convertible_events = [
                e for e in events if isinstance(e, LLMConvertibleEvent)
            ]

            # Evaluate without git_patch for now
            critic_result = self.critic.evaluate(
                events=llm_convertible_events, git_patch=None
            )
            logger.info(
                f"✓ Critic evaluation: score={critic_result.score:.3f}, "
                f"success={critic_result.success}"
            )
            return critic_result
        except Exception as e:
            logger.error(f"✗ Critic evaluation failed: {e}", exc_info=True)
            return None

    def _execute_actions(
        self,
        context: RunnerContext,
        action_events: list[ActionEvent],
    ):
        for action_event in action_events:
            self._execute_action_event(context, action_event)

    @observe(name="agent.step", ignore_inputs=["context"])
    def step(
        self,
        context: RunnerContext,
    ) -> None:
        """执行Agent的一个步骤。

        此方法从RunnerContext中获取执行所需的所有数据，包括：
        - 会话状态（execution_status, confirmation_policy等）
        - 事件历史
        - 事件回调函数

        Args:
            context: 运行时上下文，包含Agent执行所需的所有数据
        """
        # Check for pending actions (implicit confirmation)
        # and execute them before sampling new actions.
        pending_actions = RunnerContext.get_unmatched_actions(context.events)
        if pending_actions:
            logger.info(
                "Confirmation mode: Executing %d pending action(s)",
                len(pending_actions),
            )
            self._execute_actions(context, pending_actions)
            return

        # Check if the last user message was blocked by a UserPromptSubmit hook
        # If so, skip processing and mark agent as completed
        for event in reversed(list(context.events)):
            if isinstance(event, MessageEvent) and event.source == "user":
                reason = context.pop_blocked_message(event.id)
                if reason is not None:
                    logger.info(f"User message blocked by hook: {reason}")
                    context.agent_state.mark_completed(
                        result_summary="Message blocked by hook"
                    )
                    return
                break  # Only check the most recent user message

        # Prepare LLM messages using the utility function
        _messages_or_condensation = prepare_llm_messages(
            context.events, condenser=self.condenser, llm=self.llm
        )

        # Process condensation event before agent sampels another action
        if isinstance(_messages_or_condensation, Condensation):
            context.publish_event(_messages_or_condensation)
            return

        _messages = _messages_or_condensation

        logger.info(
            "Sending messages to LLM: "
            f"{json.dumps([m.model_dump() for m in _messages], indent=2)}"
        )

        try:
            llm_response = make_llm_completion(
                self.llm,
                _messages,
                tools=list(self.tools_map.values()),
                event_center=context.event_center,
            )
        except FunctionCallValidationError as e:
            logger.warning(f"LLM generated malformed function call: {e}")
            error_message = MessageEvent(
                source="user",
                llm_message=Message(
                    role="user",
                    content=[TextContent(text=str(e))],
                ),
            )
            context.publish_event(error_message)
            return
        except LLMContextWindowExceedError as e:
            # If condenser is available and handles requests, trigger condensation
            if (
                self.condenser is not None
                and self.condenser.handles_condensation_requests()
            ):
                logger.warning(
                    "LLM raised context window exceeded error, triggering condensation"
                )
                context.publish_event(CondensationRequest())
                return
            # No condenser available or doesn't handle requests; log helpful warning
            self._log_context_window_exceeded_warning()
            raise e

        # LLMResponse already contains the converted message and metrics snapshot
        message: Message = llm_response.message

        # Check if this is a reasoning-only response (e.g., from reasoning models)
        # or a message-only response without tool calls
        has_reasoning = (
            message.responses_reasoning_item is not None
            or message.reasoning_content is not None
            or (message.thinking_blocks and len(message.thinking_blocks) > 0)
        )
        has_content = any(
            isinstance(c, TextContent) and c.text.strip() for c in message.content
        )

        if message.tool_calls and len(message.tool_calls) > 0:
            if not all(isinstance(c, TextContent) for c in message.content):
                logger.warning(
                    "LLM returned tool calls but message content is not all "
                    "TextContent - ignoring non-text content"
                )

            # Generate unique batch ID for this LLM response
            thought_content = [c for c in message.content if isinstance(c, TextContent)]

            action_events: list[ActionEvent] = []
            for i, tool_call in enumerate(message.tool_calls):
                action_event = self._get_action_event(
                    tool_call,
                    context=context,
                    llm_response_id=llm_response.id,
                    security_analyzer=context.security_analyzer,
                    thought=thought_content
                    if i == 0
                    else [],  # Only first gets thought
                    # Only first gets reasoning content
                    reasoning_content=message.reasoning_content if i == 0 else None,
                    # Only first gets thinking blocks
                    thinking_blocks=list(message.thinking_blocks) if i == 0 else [],
                    responses_reasoning_item=message.responses_reasoning_item
                    if i == 0
                    else None,
                )
                if action_event is None:
                    continue
                action_events.append(action_event)

            # Handle confirmation mode - exit early if actions need confirmation
            if self._requires_user_confirmation(context, action_events):
                return

            if action_events:
                self._execute_actions(context, action_events)

            # Emit VLLM token ids if enabled before returning
            self._maybe_emit_vllm_tokens(llm_response, context)
            return

        # No tool calls - emit message event for reasoning or content responses
        if not has_reasoning and not has_content:
            logger.warning("LLM produced empty response - continuing agent loop")

        msg_event = MessageEvent(
            source="agent",
            llm_message=message,
            llm_response_id=llm_response.id,
        )
        # Run critic evaluation if configured for finish_and_message mode
        if self.critic is not None and self.critic.mode == "finish_and_message":
            critic_result = self._evaluate_with_critic(context, msg_event)
            if critic_result is not None:
                # Create new event with critic result
                msg_event = msg_event.model_copy(
                    update={"critic_result": critic_result}
                )
        context.publish_event(msg_event)

        # Emit VLLM token ids if enabled
        self._maybe_emit_vllm_tokens(llm_response, context)

        # Finish agent execution if LLM produced content (awaits user input)
        # Continue if only reasoning without content (e.g., GPT-5 codex thinking)
        if has_content:
            logger.debug("LLM produced a message response - awaits user input")
            context.agent_state.mark_completed(
                result_summary="Agent produced response message"
            )
            return

    def _requires_user_confirmation(
        self, context: RunnerContext, action_events: list[ActionEvent]
    ) -> bool:
        """
        Decide whether user confirmation is needed to proceed.

        Rules:
            1. Confirmation mode is enabled
            2. Every action requires confirmation
            3. A single `FinishAction` never requires confirmation
            4. A single `ThinkAction` never requires confirmation
        """
        # A single `FinishAction` or `ThinkAction` never requires confirmation
        if len(action_events) == 1 and isinstance(
            action_events[0].action, (FinishAction, ThinkAction)
        ):
            return False

        # If there are no actions there is nothing to confirm
        if len(action_events) == 0:
            return False

        # If a security analyzer is registered, use it to grab the risks of the actions
        # involved. If not, we'll set the risks to UNKNOWN.
        if context.security_analyzer is not None:
            risks = [
                risk
                for _, risk in context.security_analyzer.analyze_pending_actions(
                    action_events
                )
            ]
        else:
            risks = [risk.SecurityRisk.UNKNOWN] * len(action_events)

        # Grab the confirmation policy from the context and pass in the risks.
        if any(context.confirmation_policy.should_confirm(risk) for risk in risks):
            # 标记Agent为等待状态（等待用户确认）
            waiting_for = [
                f"user_confirmation_{i}" for i, _ in enumerate(action_events)
            ]
            context.agent_state.mark_waiting(waiting_for)
            return True

        return False

    def _extract_security_risk(
        self,
        arguments: dict,
        tool_name: str,
        read_only_tool: bool,
        security_analyzer: analyzer.SecurityAnalyzerBase | None = None,
    ) -> risk.SecurityRisk:
        requires_sr = isinstance(security_analyzer, LLMSecurityAnalyzer)
        raw = arguments.pop("security_risk", None)

        # Default risk value for action event
        # Tool is marked as read-only so security risk can be ignored
        if read_only_tool:
            return risk.SecurityRisk.UNKNOWN

        # Raises exception if failed to pass risk field when expected
        # Exception will be sent back to agent as error event
        # Strong models like GPT-5 can correct itself by retrying
        if requires_sr and raw is None:
            raise ValueError(
                f"Failed to provide security_risk field in tool '{tool_name}'"
            )

        # When using weaker models without security analyzer
        # safely ignore missing security risk fields
        if not requires_sr and raw is None:
            return risk.SecurityRisk.UNKNOWN

        # Raises exception if invalid risk enum passed by LLM
        security_risk = risk.SecurityRisk(raw)
        return security_risk

    def _extract_summary(self, tool_name: str, arguments: dict) -> str:
        """Extract and validate the summary field from tool arguments.

        Summary field is always requested but optional - if LLM doesn't provide
        it or provides invalid data, we generate a default summary using the
        tool name and arguments.

        Args:
            tool_name: Name of the tool being called
            arguments: Dictionary of tool arguments from LLM

        Returns:
            The summary string - either from LLM or a default generated one
        """
        summary = arguments.pop("summary", None)

        # If valid summary provided by LLM, use it
        if summary is not None and isinstance(summary, str) and summary.strip():
            return summary

        # Generate default summary: {tool_name}: {arguments}
        args_str = json.dumps(arguments)
        return f"{tool_name}: {args_str}"

    def _get_action_event(
        self,
        tool_call: MessageToolCall,
        context: RunnerContext,
        llm_response_id: str,
        security_analyzer: analyzer.SecurityAnalyzerBase | None = None,
        thought: list[TextContent] | None = None,
        reasoning_content: str | None = None,
        thinking_blocks: list[ThinkingBlock | RedactedThinkingBlock] | None = None,
        responses_reasoning_item: ReasoningItemModel | None = None,
    ) -> ActionEvent | None:
        """Converts a tool call into an ActionEvent, validating arguments.

        NOTE: context will be mutated in-place.
        """
        tool_name = tool_call.name
        tool = self.tools_map.get(tool_name, None)
        # Handle non-existing tools
        if tool is None:
            available = list(self.tools_map.keys())
            err = f"Tool '{tool_name}' not found. Available: {available}"
            logger.error(err)
            # Persist assistant function_call so next turn has matching call_id
            tc_event = ActionEvent(
                source="agent",
                thought=thought or [],
                reasoning_content=reasoning_content,
                thinking_blocks=thinking_blocks or [],
                responses_reasoning_item=responses_reasoning_item,
                tool_call=tool_call,
                tool_name=tool_call.name,
                tool_call_id=tool_call.id,
                llm_response_id=llm_response_id,
                action=None,
            )
            context.publish_event(tc_event)
            event = AgentErrorEvent(
                error=err,
                tool_name=tool.name,
                tool_call_id=tool_call.id,
            )
            context.publish_event(event)
            return

        # Validate arguments
        security_risk: risk.SecurityRisk = risk.SecurityRisk.UNKNOWN
        try:
            arguments = json.loads(tool_call.arguments)

            # Fix malformed arguments (e.g., JSON strings for list/dict fields)
            arguments = fix_malformed_tool_arguments(arguments, tool.action_type)
            security_risk = self._extract_security_risk(
                arguments,
                tool.name,
                tool.annotations.readOnlyHint if tool.annotations else False,
                security_analyzer,
            )
            assert "security_risk" not in arguments, (
                "Unexpected 'security_risk' key found in tool arguments"
            )

            summary = self._extract_summary(tool.name, arguments)

            action: Action = tool.action_from_arguments(arguments)
        except (json.JSONDecodeError, ValidationError, ValueError) as e:
            err = (
                f"Error validating args {tool_call.arguments} for tool "
                f"'{tool.name}': {e}"
            )
            # Persist assistant function_call so next turn has matching call_id
            tc_event = ActionEvent(
                source="agent",
                thought=thought or [],
                reasoning_content=reasoning_content,
                thinking_blocks=thinking_blocks or [],
                responses_reasoning_item=responses_reasoning_item,
                tool_call=tool_call,
                tool_name=tool_call.name,
                tool_call_id=tool_call.id,
                llm_response_id=llm_response_id,
                action=None,
            )
            context.publish_event(tc_event)
            event = AgentErrorEvent(
                error=err,
                tool_name=tool_name,
                tool_call_id=tool_call.id,
            )
            context.publish_event(event)
            return

        # Create initial action event
        action_event = ActionEvent(
            action=action,
            thought=thought or [],
            reasoning_content=reasoning_content,
            thinking_blocks=thinking_blocks or [],
            responses_reasoning_item=responses_reasoning_item,
            tool_name=tool.name,
            tool_call_id=tool_call.id,
            tool_call=tool_call,
            llm_response_id=llm_response_id,
            security_risk=security_risk,
            summary=summary,
        )

        # Run critic evaluation if configured
        if self._should_evaluate_with_critic(action):
            critic_result = self._evaluate_with_critic(context, action_event)
            if critic_result is not None:
                # Create new event with critic result
                action_event = action_event.model_copy(
                    update={"critic_result": critic_result}
                )

        context.publish_event(action_event)
        return action_event

    @observe(ignore_inputs=["context"])
    def _execute_action_event(
        self,
        context: RunnerContext,
        action_event: ActionEvent,
    ):
        """Execute an action event and update the context state.

        It will call the tool's executor and update the context & call callback fn
        with the observation.

        If the action was blocked by a PreToolUse hook (recorded in
        context.blocked_actions), a UserRejectObservation is emitted instead
        of executing the action.
        """
        # Check if this action was blocked by a PreToolUse hook
        reason = context.pop_blocked_action(action_event.id)
        if reason is not None:
            logger.info(f"Action '{action_event.tool_name}' blocked by hook: {reason}")
            rejection = UserRejectObservation(
                action_id=action_event.id,
                tool_name=action_event.tool_name,
                tool_call_id=action_event.tool_call_id,
                rejection_reason=reason,
            )
            context.publish_event(rejection)
            return rejection

        tool = self.tools_map.get(action_event.tool_name, None)
        if tool is None:
            raise RuntimeError(
                f"Tool '{action_event.tool_name}' not found. This should not happen "
                "as it was checked earlier."
            )

        # Execute actions!
        try:
            if should_enable_observability():
                tool_name = extract_action_name(action_event)
                observation: Observation = observe(name=tool_name, span_type="TOOL")(
                    tool
                )(action_event.action, context)
            else:
                observation = tool(action_event.action, context)
            assert isinstance(observation, Observation), (
                f"Tool '{tool.name}' executor must return an Observation"
            )
        except ValueError as e:
            # Tool execution raised a ValueError (e.g., invalid argument combination)
            # Convert to AgentErrorEvent so the agent can correct itself
            err = f"Error executing tool '{tool.name}': {e}"
            logger.warning(err)
            error_event = AgentErrorEvent(
                error=err,
                tool_name=tool.tool_name,
                tool_call_id=action_event.tool_call.id,
            )
            context.publish_event(error_event)
            return error_event

        obs_event = ObservationEvent(
            observation=observation,
            action_id=action_event.id,
            tool_name=tool.tool_name,
            tool_call_id=action_event.tool_call.id,
        )
        context.publish_event(obs_event)

        # Mark agent as completed if finish tool is called
        if tool.name == FinishTool.tool_name:
            context.agent_state.mark_completed(
                result_summary="Agent called finish tool"
            )
        return obs_event

    def _maybe_emit_vllm_tokens(
        self, llm_response: LLMResponse, context: RunnerContext
    ) -> None:
        if (
            "return_token_ids" in self.llm.litellm_extra_body
        ) and self.llm.litellm_extra_body["return_token_ids"]:
            token_event = TokenEvent(
                source="agent",
                prompt_token_ids=llm_response.raw_response["prompt_token_ids"],
                response_token_ids=llm_response.raw_response["choices"][0][
                    "provider_specific_fields"
                ]["token_ids"],
            )
            context.publish_event(token_event)

    def _log_context_window_exceeded_warning(self) -> None:
        """Log a helpful warning when context window is exceeded without a condenser."""
        if self.condenser is None:
            logger.warning(
                "\n"
                "=" * 80 + "\n"
                "⚠️  CONTEXT WINDOW EXCEEDED ERROR\n"
                "=" * 80 + "\n"
                "\n"
                "The LLM's context window has been exceeded, but no condenser is "
                "configured.\n"
                "\n"
                "Current configuration:\n"
                f"  • Condenser: None\n"
                f"  • LLM Model: {self.llm.model}\n"
                "\n"
                "To prevent this error, configure a condenser to automatically "
                "summarize\n"
                "conversation history when it gets too long.\n"
                "\n"
                "Example configuration:\n"
                "\n"
                "  from sdk import Agent, LLM\n"
                "  from sdk.context.condenser import "
                "LLMSummarizingCondenser\n"
                "\n"
                "  agent = Agent(\n"
                "      llm=LLM(model='your-model'),\n"
                "      condenser=LLMSummarizingCondenser(\n"
                "          llm=LLM(model='your-model'),  # Can use same or "
                "cheaper model\n"
                "          max_size=120,  # Maximum events before condensation\n"
                "          keep_first=4   # Number of initial events to preserve\n"
                "      )\n"
                "  )\n"
                "\n"
                "For more information, see: "
                "https://docs.openhands.dev/sdk/guides/context-condenser\n"
                "=" * 80
            )
        else:
            condenser_type = type(self.condenser).__name__
            handles_requests = self.condenser.handles_condensation_requests()
            condenser_config = self.condenser.model_dump(
                exclude={"llm"}, exclude_none=True
            )
            condenser_llm_obj = getattr(self.condenser, "llm", None)
            condenser_llm = (
                condenser_llm_obj.model if condenser_llm_obj is not None else "N/A"
            )

            logger.warning(
                "\n"
                "=" * 80 + "\n"
                "⚠️  CONTEXT WINDOW EXCEEDED ERROR\n"
                "=" * 80 + "\n"
                "\n"
                "The LLM's context window has been exceeded.\n"
                "\n"
                "Current configuration:\n"
                f"  • Condenser Type: {condenser_type}\n"
                f"  • Handles Condensation Requests: {handles_requests}\n"
                f"  • Condenser LLM: {condenser_llm}\n"
                f"  • Agent LLM Model: {self.llm.model}\n"
                f"  • Condenser Config: {json.dumps(condenser_config, indent=4)}\n"
                "\n"
                "Your condenser is configured but does not handle condensation "
                "requests\n"
                "(handles_condensation_requests() returned False).\n"
                "\n"
                "To fix this:\n"
                "  1. Use LLMSummarizingCondenser which handles condensation "
                "requests, OR\n"
                "  2. Implement handles_condensation_requests() in your custom "
                "condenser\n"
                "\n"
                "Example with LLMSummarizingCondenser:\n"
                "\n"
                "  from sdk.context.condenser import "
                "LLMSummarizingCondenser\n"
                "\n"
                "  agent = Agent(\n"
                "      llm=LLM(model='your-model'),\n"
                "      condenser=LLMSummarizingCondenser(\n"
                "          llm=LLM(model='your-model'),\n"
                "          max_size=120,\n"
                "          keep_first=4\n"
                "      )\n"
                "  )\n"
                "\n"
                "For more information, see: "
                "https://docs.openhands.dev/sdk/guides/context-condenser\n"
                "=" * 80
            )
