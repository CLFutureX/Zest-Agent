import atexit
import uuid
from collections.abc import Mapping
from pathlib import Path

from sdk.agent.base import AgentBase
from sdk.context.agent_state import ( 
    AgentStateRegistry,
    AgentStateRegistryConsumer,
)
from sdk.context.agent_state_consumer import AgentEventPersistentConsumer
from sdk.context.memory.memory_manager import ExperienceMemoryConsumer
from sdk.context.prompts.prompt import render_template
from sdk.conversation.base import BaseConversation
from sdk.conversation.secret_registry import SecretValue
from sdk.conversation.state import (
    ConversationState,
)
from sdk.conversation.stuck_detector import StuckDetector
from sdk.conversation.title_utils import generate_conversation_title
from sdk.conversation.types import (
    ConversationCallbackType,
    ConversationID,
    ConversationTokenCallbackType,
    StuckDetectionThresholds,
)
from sdk.conversation.visualizer import (
    ConversationVisualizerBase,
    DefaultConversationVisualizer,
)
from sdk.event import (
    CondensationRequest,
    MessageEvent,
    UserRejectObservation,
)
from sdk.event.base import Event
from sdk.event.event_center import (
    EventCenter,
    create_function_consumer,
)
from sdk.hooks import HookConfig, HookEventProcessor, create_hook_callback
from sdk.llm import LLM, Message, TextContent
from sdk.llm.llm_registry import LLMRegistry
from sdk.llm.streaming import LLMStreamChunk
from sdk.logger import get_logger
from sdk.observability.laminar import observe
from sdk.plugin import (
    Plugin,
    PluginSource,
    ResolvedPluginSource,
    fetch_plugin_with_resolution,
)
from sdk.security.analyzer import SecurityAnalyzerBase
from sdk.security.confirmation_policy import (
    ConfirmationPolicyBase,
)
from sdk.tool.builtins.experience_memory_tool import ExperienceMemoryTool
from sdk.utils.cipher import Cipher
from sdk.workspace import LocalWorkspace


logger = get_logger(__name__)


class LocalConversation(BaseConversation):
    agent: AgentBase
    workspace: LocalWorkspace
    user_id: str | None
    _state: ConversationState
    _visualizer: ConversationVisualizerBase | None
    _on_event: ConversationCallbackType
    _on_token: ConversationTokenCallbackType | None
    max_iteration_per_run: int
    _stuck_detector: StuckDetector | None
    llm_registry: LLMRegistry
    _cleanup_initiated: bool
    _hook_processor: HookEventProcessor | None
    # Plugin lazy loading state
    _plugin_specs: list[PluginSource] | None
    _resolved_plugins: list[ResolvedPluginSource] | None
    _plugins_loaded: bool
    _pending_hook_config: HookConfig | None  # Hook config to combine with plugin hooks
    _event_center: EventCenter 

    def __init__(
        self,
        agent: AgentBase,
        workspace: str | Path | LocalWorkspace,
        plugins: list[PluginSource] | None = None,
        persistence_dir: str | Path | None = None,
        conversation_id: ConversationID | None = None,
        user_id: str | None = None,
        callbacks: list[ConversationCallbackType] | None = None,
        token_callbacks: list[ConversationTokenCallbackType] | None = None,
        hook_config: HookConfig | None = None,
        max_iteration_per_run: int = 500,
        stuck_detection: bool = True,
        stuck_detection_thresholds: (
            StuckDetectionThresholds | Mapping[str, int] | None
        ) = None,
        visualizer: (
            type[ConversationVisualizerBase] | ConversationVisualizerBase | None
        ) = DefaultConversationVisualizer,
        secrets: Mapping[str, SecretValue] | None = None,
        cipher: Cipher | None = None,
        **_: object,
    ):
        """Initialize the conversation.

        Args:
            agent: The agent to use for the conversation.
            workspace: Working directory for agent operations and tool execution.
                Can be a string path, Path object, or LocalWorkspace instance.
            plugins: Optional list of plugins to load. Each plugin is specified
                with a source (github:owner/repo, git URL, or local path),
                optional ref (branch/tag/commit), and optional repo_path for
                monorepos. Plugins are loaded in order with these merge
                semantics: skills override by name (last wins), MCP config
                override by key (last wins), hooks concatenate (all run).
            persistence_dir: Directory for persisting conversation state and events.
                Can be a string path or Path object.
            conversation_id: Optional ID for the conversation. If provided, will
                      be used to identify the conversation. The user might want to
                      suffix their persistent filestore with this ID.
            callbacks: Optional list of callback functions to handle events
            token_callbacks: Optional list of callbacks invoked for streaming deltas
            hook_config: Optional hook configuration to auto-wire session hooks.
                If plugins are loaded, their hooks are combined with this config.
            max_iteration_per_run: Maximum number of iterations per run
            visualizer: Visualization configuration. Can be:
                       - ConversationVisualizerBase subclass: Class to instantiate
                         (default: ConversationVisualizer)
                       - ConversationVisualizerBase instance: Use custom visualizer
                       - None: No visualization
            stuck_detection: Whether to enable stuck detection
            stuck_detection_thresholds: Optional configuration for stuck detection
                      thresholds. Can be a StuckDetectionThresholds instance or
                      a dict with keys: 'action_observation', 'action_error',
                      'monologue', 'alternating_pattern'. Values are integers
                      representing the number of repetitions before triggering.
            cipher: Optional cipher for encrypting/decrypting secrets in persisted
                   state. If provided, secrets are encrypted when saving and
                   decrypted when loading. If not provided, secrets are redacted
                   (lost) on serialization.
        """
        super().__init__()  # Initialize with span tracking
        # Mark cleanup as initiated as early as possible to avoid races or partially
        # initialized instances during interpreter shutdown.
        self._cleanup_initiated = False
        self.user_id = user_id

        # Store plugin specs for lazy loading (no IO in constructor)
        # Plugins will be loaded on first run() or send_message() call
        self._plugin_specs = plugins
        self._resolved_plugins = None
        self._plugins_loaded = False
        self._pending_hook_config = hook_config  # Will be combined with plugin hooks
        self._agent_ready = False  # Agent initialized lazily after plugins loaded

        self.agent = agent
        if isinstance(workspace, (str, Path)):
            # LocalWorkspace accepts both str and Path via BeforeValidator
            workspace = LocalWorkspace(working_dir=workspace)
        assert isinstance(workspace, LocalWorkspace), (
            "workspace must be a LocalWorkspace instance"
        )
        self.workspace = workspace
        ws_path = Path(self.workspace.working_dir)
        if not ws_path.exists():
            ws_path.mkdir(parents=True, exist_ok=True)

        # Create-or-resume: factory inspects BASE_STATE to decide
        self.desired_id = conversation_id or uuid.uuid4()
        self._state = ConversationState.create(
            id=self.desired_id,
            agent=agent,
            workspace=self.workspace,
            persistence_dir=self.get_persistence_dir(persistence_dir, self.desired_id)
            if persistence_dir
            else None,
            max_iterations=max_iteration_per_run,
            stuck_detection=stuck_detection,
            cipher=cipher,
            user_id = user_id,
        )
        # ===== 初始化 EventCenter =====
        self._event_center = EventCenter()

        # ===== 订阅事件消费者 =====
        consumers = []

        # 1. Visualizer Consumer（优先级最高，用于可视化）
        if isinstance(visualizer, ConversationVisualizerBase):
            # Use custom visualizer instance
            self._visualizer = visualizer
            self._visualizer.initialize(self._state.stats)
        elif isinstance(visualizer, type) and issubclass(
            visualizer, ConversationVisualizerBase
        ):
            # Instantiate the visualizer class
            self._visualizer = visualizer()
            self._visualizer.initialize(self._state.stats)
        else:
            # No visualization
            self._visualizer = None
        if self._visualizer:
            visualizer_consumer = create_function_consumer(
                conversation_id=self.desired_id,
                callback=self._visualizer.on_event,
                event_types=[Event],
            )
            consumers.append(visualizer_consumer)

        # 2. User Callback Consumers
        if callbacks:
            for idx, callback in enumerate(callbacks):
                user_consumer = create_function_consumer(
                    conversation_id=self.desired_id,
                    callback=callback,
                    event_types=[Event],
                )
                consumers.append(user_consumer)

        # 3. Token Callback Consumers（用于流式输出）
        if token_callbacks:
            for idx, token_callback in enumerate(token_callbacks):
                token_consumer = create_function_consumer(
                    conversation_id=self.desired_id,
                    callback=token_callback,
                    event_types=[LLMStreamChunk],  # Token是字符串类型
                )
                consumers.append(token_consumer)

        # 4. Persistence Consumer（默认：存储到 _events，优先级最低）
        persistence_consumer = AgentEventPersistentConsumer(
            agent_state=self._state.get_main_agent_state(),  # type: ignore
            conversation_id=self.desired_id,
            agent_id=self.agent.id,
        )
        consumers.append(persistence_consumer)

        self._event_center.batch_subscribe(consumers)

        # Defer all hook setup to _ensure_plugins_loaded() for consistency
        # This runs on first run()/send_message() call and handles both
        # explicit hooks and plugin hooks in one place
        self._hook_processor = None

        self.max_iteration_per_run = max_iteration_per_run

        # Initialize stuck detector
        if stuck_detection:
            # Convert dict to StuckDetectionThresholds if needed
            if isinstance(stuck_detection_thresholds, Mapping):
                threshold_config = StuckDetectionThresholds(
                    **stuck_detection_thresholds
                )
            else:
                threshold_config = stuck_detection_thresholds
            self._stuck_detector = StuckDetector(
                thresholds=threshold_config,
            )
        else:
            self._stuck_detector = None

        # Agent initialization is deferred to _ensure_agent_ready() for lazy loading
        # This ensures plugins are loaded before agent initialization
        self.llm_registry = LLMRegistry()

        # Initialize secrets if provided
        if secrets:
            # Convert dict[str, str] to dict[str, SecretValue]
            secret_values: dict[str, SecretValue] = {k: v for k, v in secrets.items()}
            self.update_secrets(secret_values)

        atexit.register(self.close)
        self._start_observability_span(str(self.desired_id))

        from sdk.agent.runner_context import RunnerContext

        # ===== 基于 AgentState 创建 RunnerContext =====
        self._runner_context = RunnerContext.build(
            conversation_state=self._state,
            agent_state=self._state.get_main_agent_state(),
            event_center=self._event_center,
        )
 
        # 订阅会话内的所有状态变化事件
        self._event_center.subscribe(
            AgentStateRegistryConsumer(conversation_id=self.desired_id)
        )
        if self.agent.agent_context and self.agent.agent_context.memory_manager:
            self._event_center.subscribe(
                ExperienceMemoryConsumer(
                    conversation_id=self.desired_id,
                    memory_manager=self.agent.agent_context.memory_manager,
                )
            )

    @property
    def id(self) -> ConversationID:
        """Get the unique ID of the conversation."""
        return self._state.id

    @property
    def state(self) -> ConversationState:
        """Get the conversation state.

        It returns a protocol that has a subset of ConversationState methods
        and properties. We will have the ability to access the same properties
        of ConversationState on a remote conversation object.
        But we won't be able to access methods that mutate the state.
        """
        return self._state

    @property
    def conversation_stats(self):
        return self._state.stats

    @property
    def stuck_detector(self) -> StuckDetector | None:
        """Get the stuck detector instance if enabled."""
        return self._stuck_detector

    @property
    def resolved_plugins(self) -> list[ResolvedPluginSource] | None:
        """Get the resolved plugin sources after plugins are loaded.

        Returns None if plugins haven't been loaded yet, or if no plugins
        were specified. Use this for persistence to ensure conversation
        resume uses the exact same plugin versions.
        """
        return self._resolved_plugins

    def _ensure_plugins_loaded(self) -> None:
        """Lazy load plugins and set up hooks on first use.

        This method is called automatically before run() and send_message().
        It handles both plugin loading and hook initialization in one place
        for consistency.

        The method:
        1. Fetches plugins from their sources (network IO for remote sources)
        2. Resolves refs to commit SHAs for deterministic resume
        3. Loads plugin contents (skills, MCP config, hooks)
        4. Merges plugin contents into the agent
        5. Sets up hook processor with combined hooks (explicit + plugin)
        6. Runs session_start hooks
        """
        if self._plugins_loaded:
            return

        all_plugin_hooks: list[HookConfig] = []

        # Load plugins if specified
        if self._plugin_specs:
            logger.info(f"Loading {len(self._plugin_specs)} plugin(s)...")
            self._resolved_plugins = []

            # Start with agent's existing context and MCP config
            merged_context = self.agent.agent_context
            merged_mcp = dict(self.agent.mcp_config) if self.agent.mcp_config else {}

            for spec in self._plugin_specs:
                # Fetch plugin and get resolved commit SHA
                path, resolved_ref = fetch_plugin_with_resolution(
                    source=spec.source,
                    ref=spec.ref,
                    repo_path=spec.repo_path,
                )

                # Store resolved ref for persistence
                resolved = ResolvedPluginSource.from_plugin_source(spec, resolved_ref)
                self._resolved_plugins.append(resolved)

                # Load the plugin
                plugin = Plugin.load(path)
                logger.debug(
                    f"Loaded plugin '{plugin.manifest.name}' from {spec.source}"
                    + (f" @ {resolved_ref[:8]}" if resolved_ref else "")
                )

                # Merge plugin contents
                merged_context = plugin.add_skills_to(merged_context)
                merged_mcp = plugin.add_mcp_config_to(merged_mcp)

                # Collect hooks
                if plugin.hooks and not plugin.hooks.is_empty():
                    all_plugin_hooks.append(plugin.hooks)

            # Update agent with merged content
            self.agent = self.agent.model_copy(
                update={
                    "agent_context": merged_context,
                    "mcp_config": merged_mcp,
                }
            )

            # Update the agent config in ConversationState and AgentState so API responses reflect loaded plugins
            # 使用 update_agent_config() 更新 AgentState 中的配置
            with self._state:
                self._state.update_agent_config(
                    self.agent, agent_id=None
                )  # None表示更新MainAgent

            logger.info(f"Loaded {len(self._plugin_specs)} plugin(s) via Conversation")

        # Combine explicit hook_config with plugin hooks
        # Explicit hooks run first (before plugin hooks)
        final_hook_config = self._pending_hook_config
        if all_plugin_hooks:
            plugin_hooks = HookConfig.merge(all_plugin_hooks)
            if plugin_hooks is not None:
                if final_hook_config is not None:
                    final_hook_config = HookConfig.merge(
                        [final_hook_config, plugin_hooks]
                    )
                else:
                    final_hook_config = plugin_hooks

        # Set up hook processor with the combined config
        if final_hook_config is not None:
            self._hook_processor, hook_on_event = create_hook_callback(
                hook_config=final_hook_config,
                working_dir=str(self.workspace.working_dir),
                session_id=str(self._state.id),
            )
            self._hook_processor.set_conversation_state(self._state)

            # 将 hook 回调注册为 EventCenter 的消费者
            hook_consumer = create_function_consumer(
                conversation_id=self.desired_id,
                callback=hook_on_event,
            )
            self._event_center.subscribe(hook_consumer)

            self._hook_processor.run_session_start()

        self._plugins_loaded = True

    def _ensure_agent_ready(self) -> None:
        """Ensure agent is fully initialized with plugins loaded.

        This method combines plugin loading and agent initialization to ensure
        the agent is initialized exactly once with complete configuration.

        Called lazily on first send_message() or run() to:
        1. Load plugins (if specified)
        2. Initialize agent with complete plugin config and hooks
        3. Register LLMs in the registry

        This preserves the design principle that constructors should not perform
        I/O or error-prone operations, while eliminating double initialization.

        Thread-safe: Uses state lock to prevent concurrent initialization.
        """
        # Fast path: if already initialized, skip lock acquisition entirely.
        # This is crucial for concurrent send_message() calls during run(),
        # which holds the state lock during agent.step(). Without this check,
        # send_message() would block waiting for the lock even though no
        # initialization is needed.
        if self._agent_ready:
            return

        with self._state:
            # Re-check after acquiring lock in case another thread initialized
            if self._agent_ready:
                return

            # Load plugins first (merges skills, MCP config, hooks)
            self._ensure_plugins_loaded()

            # Initialize agent with complete configuration
            self.agent.init_state(self._state, self._runner_context)

            # Register LLMs in the registry (still holding lock)
            self.llm_registry.subscribe(self._state.stats.register_llm)
            for llm in list(self.agent.get_all_llms()):
                self.llm_registry.add(llm)
             

            self._agent_ready = True

    @observe(name="conversation.send_message")
    def send_message(self, message: str | Message, sender: str | None = None) -> None:
        """Send a message to the agent.

        Args:
            message: Either a string (which will be converted to a user message)
                    or a Message object
            sender: Optional identifier of the sender. Can be used to track
                   message origin in multi-agent scenarios. For example, when
                   one agent delegates to another, the sender can be set to
                   identify which agent is sending the message.
        """
        # Ensure agent is fully initialized (loads plugins and initializes agent)
        self._ensure_agent_ready()

        # Convert string to Message if needed
        if isinstance(message, str):
            message = Message(role="user", content=[TextContent(text=message)])

        assert message.role == "user", (
            "Only user messages are allowed to be sent to the agent."
        )
        with self._state:
            # Get MainAgent's state from registry
            main_agent_state = self._state.get_main_agent_state()
            if not main_agent_state:
                raise RuntimeError("MainAgent state not found")

            # 检查主Agent状态：如果上一个任务已完成，重置为 IDLE（准备接收新消息）
            from sdk.context.agent_state import AgentExecutionStatus

            if main_agent_state.execution_status == AgentExecutionStatus.COMPLETED:
                main_agent_state.execution_status = AgentExecutionStatus.PENDING

            # TODO: We should add test cases for all these scenarios
            activated_skill_names: list[str] = []
            extended_content: list[TextContent] = []

            # Handle per-turn user message (i.e., knowledge agent trigger)
            if self.agent.agent_context:
                # 在发送消息之前，进行上下文加载 - 避免多次重复加载
                ctx = self.agent.agent_context.get_user_message_suffix(
                    user_message=message,
                    # We skip skills that were already activated
                    skip_skill_names=main_agent_state.activated_knowledge_skills,
                )
                # TODO(calvin): we need to update
                # main_agent_state.activated_knowledge_skills
                # so condenser can work
                if ctx:
                    content, activated_skill_names = ctx
                    logger.debug(
                        f"Got augmented user message content: {content}, "
                        f"activated skills: {activated_skill_names}"
                    )
                    extended_content.append(content)
                    main_agent_state.activated_knowledge_skills.extend(
                        activated_skill_names
                    )

                memory_ctx = self.agent.agent_context.get_user_memory(
                    user_message=message,
                    need_load_memory=self._state.load_base_memory,
                    activate_ids=self.main_agent_state.activated_experiences,
                )
                # tuple[list[ExperienceMemory], list[str], list[str]]
                if memory_ctx:
                    content, activate_ids = memory_ctx
                    logger.debug(
                        f"Got augmented user memory: {content}, "
                        f"activated experiences: {activate_ids}"
                    )
                    extended_content.append(content)
                    self.main_agent_state.activated_experiences.extend(activate_ids)

            # 将 加载的skill归类为extended内容
            user_msg_event = MessageEvent(
                source="user",
                llm_message=message,
                activated_skills=activated_skill_names,
                extended_content=extended_content,
                sender=sender,
            )
            # 通过 EventCenter 发布事件
            self._event_center.publish(
                event=user_msg_event,
                conversation_id=self.desired_id,
                agent_id=self.agent.id,
            )

    @observe(name="conversation.run")
    def run(self) -> None:
        """Runs the conversation until the agent finishes.

        In confirmation mode:
        - First call: creates actions but doesn't execute them, stops and waits
        - Second call: executes pending actions (implicit confirmation)

        In normal mode:
        - Creates and executes actions immediately

        Can be paused between steps
        """
        # Ensure agent is fully initialized (loads plugins and initializes agent)
        self._ensure_agent_ready()

        # Import AgentRunner here to avoid circular imports
        # Create RunnerContext from ConversationState
        from sdk.agent.agent_runner import AgentRunner

        # Create and run AgentRunner
        runner = AgentRunner(
            agent=self.agent,
            context=self._runner_context,
            max_iterations=self.max_iteration_per_run,
            stuck_detector=self._stuck_detector,
            hook_processor=self._hook_processor,
        )
        runner.run()

    def set_confirmation_policy(self, policy: ConfirmationPolicyBase) -> None:
        """Set the confirmation policy and store it in conversation state."""
        with self._state:
            self._state.confirmation_policy = policy
        logger.info(f"Confirmation policy set to: {policy}")

    @property
    def events(self):
        assert self._state.get_main_agent_state() is not None
        return self._state.get_main_agent_state().events

    @property
    def main_agent_state(self):
        return self._state.get_main_agent_state()

    def reject_pending_actions(self, reason: str = "User rejected the action") -> None:
        """Reject all pending actions from the agent.

        This is a non-invasive method to reject actions between run() calls.
        Also clears the agent_waiting_for_confirmation flag.
        """
        pending_actions = ConversationState.get_unmatched_actions(self.events)

        with self._state:
            # Get MainAgent's state from registry
            main_agent_state = self._state.get_main_agent_state()
            if not main_agent_state:
                raise RuntimeError("MainAgent state not found")

            # 如果主Agent处于等待确认状态，重置为 PENDING
            from sdk.context.agent_state import AgentExecutionStatus

            if main_agent_state.execution_status == AgentExecutionStatus.WAITING:
                main_agent_state.execution_status = AgentExecutionStatus.PENDING

            if not pending_actions:
                logger.warning("No pending actions to reject")
                return

            for action_event in pending_actions:
                # Create rejection observation
                rejection_event = UserRejectObservation(
                    action_id=action_event.id,
                    tool_name=action_event.tool_name,
                    tool_call_id=action_event.tool_call_id,
                    rejection_reason=reason,
                )
                # 通过 EventCenter 发布事件
                self._event_center.publish(
                    event=rejection_event,
                    conversation_id=self.desired_id,
                    agent_id=self.agent.id,
                )
                logger.info(f"Rejected pending action: {action_event} - {reason}")

    def pause(self) -> None:
        """Pause agent execution.

        This method can be called from any thread to request that the agent
        pause execution. The pause will take effect at the next iteration
        of the run loop (between agent steps).

        Note: If called during an LLM completion, the pause will not take
        effect until the current LLM call completes.
        """

        # 检查是否已经暂停
        # if self._state.is_paused:
        #     return

        # with self._state:
        #     # Re-check after acquiring lock
        #     if self._state.is_paused:
        #         return

        #     # 设置暂停标志
        #     self._state.is_paused = True
        #     pause_event = PauseEvent()
        #     # 通过 EventCenter 发布事件
        #     self._event_center.publish(
        #         event=pause_event,
        #         conversation_id=str(self._state.id)
        #     )
        #     logger.info("Agent execution pause requested")

        logger.info("Agent execution pause requested")

    def update_secrets(self, secrets: Mapping[str, SecretValue]) -> None:
        """Add secrets to the conversation.

        Args:
            secrets: Dictionary mapping secret keys to values or no-arg callables.
                     SecretValue = str | Callable[[], str]. Callables are invoked lazily
                     when a command references the secret key.
        """

        secret_registry = self._state.secret_registry
        secret_registry.update_secrets(secrets)
        logger.info(f"Added {len(secrets)} secrets to conversation")

    def set_security_analyzer(self, analyzer: SecurityAnalyzerBase | None) -> None:
        """Set the security analyzer for the conversation."""
        with self._state:
            self._state.security_analyzer = analyzer

    def close(self) -> None:
        """Close the conversation and clean up all tool executors."""
        # Use getattr for safety - object may be partially constructed
        if getattr(self, "_cleanup_initiated", False):
            return
        self._cleanup_initiated = True
        logger.debug("Closing conversation and cleaning up tool executors")
        hook_processor = getattr(self, "_hook_processor", None)
        if hook_processor is not None:
            hook_processor.run_session_end()
        try:
            self._end_observability_span()
        except AttributeError:
            # Object may be partially constructed; span fields may be missing.
            pass
        try:
            tools_map = self.agent.tools_map
        except (AttributeError, RuntimeError):
            # Agent not initialized or partially constructed
            return
        for tool in tools_map.values():
            try:
                executable_tool = tool.as_executable()
                executable_tool.executor.close()
            except NotImplementedError:
                # Tool has no executor, skip it without erroring
                continue
            except Exception as e:
                logger.warning(f"Error closing executor for tool '{tool.name}': {e}")

    # 如果是普通的单轮会话，则直接
    def ask_agent(self, question: str) -> str:
        """Ask the agent a simple, stateless question and get a direct LLM response.

        This bypasses the normal conversation flow and does **not** modify, persist,
        or become part of the conversation state. The request is not remembered by
        the main agent, no events are recorded, and execution status is untouched.
        It is also thread-safe and may be called while `conversation.run()` is
        executing in another thread.

        Args:
            question: A simple string question to ask the agent

        Returns:
            A string response from the agent
        """
        # Ensure agent is initialized (needs tools_map)
        self._ensure_agent_ready()

        # Import here to avoid circular imports
        from sdk.agent.utils import make_llm_completion, prepare_llm_messages

        template_dir = (
            Path(__file__).parent.parent.parent / "context" / "prompts" / "templates"
        )

        question_text = render_template(
            str(template_dir), "ask_agent_template.j2", question=question
        )

        # Create a user message with the context-aware question
        user_message = Message(
            role="user",
            content=[TextContent(text=question_text)],
        )

        messages = prepare_llm_messages(self.events, additional_messages=[user_message])

        # Get or create the specialized ask-agent LLM
        try:
            question_llm = self.llm_registry.get("ask-agent-llm")
        except KeyError:
            question_llm = self.agent.llm.model_copy(
                update={
                    "usage_id": "ask-agent-llm",
                },
                deep=True,
            )
            self.llm_registry.add(question_llm)

        # Pass agent tools so LLM can understand tool_calls in conversation history
        response = make_llm_completion(
            question_llm, messages, tools=list(self.agent.tools_map.values())
        )

        message = response.message

        # Extract the text content from the LLMResponse message
        if message.content and len(message.content) > 0:
            # Look for the first TextContent in the response
            for content in response.message.content:
                if isinstance(content, TextContent):
                    return content.text

        raise Exception("Failed to generate summary")

    @observe(name="conversation.generate_title", ignore_inputs=["llm"])
    def generate_title(self, llm: LLM | None = None, max_length: int = 50) -> str:
        """Generate a title for the conversation based on the first user message.

        Args:
            llm: Optional LLM to use for title generation. If not provided,
                 uses self.agent.llm.
            max_length: Maximum length of the generated title.

        Returns:
            A generated title for the conversation.

        Raises:
            ValueError: If no user messages are found in the conversation.
        """
        # Use provided LLM or fall back to agent's LLM
        llm_to_use = llm or self.agent.llm

        return generate_conversation_title(
            events=self.events, llm=llm_to_use, max_length=max_length
        )

    def condense(self) -> None:
        """Synchronously force condense the conversation history.

        If the agent is currently running, `condense()` will wait for the
        ongoing step to finish before proceeding.

        Raises ValueError if no compatible condenser exists.
        """

        # Check if condenser is configured and handles condensation requests
        if (
            self.agent.condenser is None
            or not self.agent.condenser.handles_condensation_requests()
        ):
            condenser_info = (
                "No condenser configured"
                if self.agent.condenser is None
                else (
                    f"Condenser {type(self.agent.condenser).__name__} does not handle "
                    "condensation requests"
                )
            )
            raise ValueError(
                f"Cannot condense conversation: {condenser_info}. "
                "To enable manual condensation, configure an "
                "LLMSummarizingCondenser:\n\n"
                "from sdk.context.condenser import LLMSummarizingCondenser\n"
                "agent = Agent(\n"
                "    llm=your_llm,\n"
                "    condenser=LLMSummarizingCondenser(\n"
                "        llm=your_llm,\n"
                "        max_size=120,\n"
                "        keep_first=4\n"
                "    )\n"
                ")"
            )

        # Add a condensation request event
        condensation_request = CondensationRequest()
        # 通过 EventCenter 发布事件
        self._event_center.publish(
            event=condensation_request, conversation_id=self.desired_id
        )

        # Force the agent to take a single step to process the condensation request
        # This will trigger the condenser if it handles condensation requests
        with self._state:
            # Use the existing RunnerContext (already configured with AgentState)
            self.agent.step(self._runner_context)

        logger.info("Condensation request processed")

    def __del__(self) -> None:
        """Ensure cleanup happens when conversation is destroyed."""
        try:
            self.close()
        except Exception as e:
            logger.warning(f"Error during conversation cleanup: {e}", exc_info=True)
