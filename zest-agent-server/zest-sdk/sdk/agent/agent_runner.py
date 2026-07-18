import threading
from tkinter import N



from common.logger import get_logger

from common.observability import observe

from common.utils.common import ExecutionStatus
from sdk.agent.agent import Agent
from sdk.agent.agent_spec import AgentSpec
from sdk.agent.base import AgentBase
from sdk.agent.exceptions import AgentRunnerRunError
from sdk.agent.runner_context import RunnerContext
from sdk.agent.runtime import AgentRuntime
from sdk.agent.runtime_stage import   MemoryManagerStage, PromptBuildStage, SkillBuildStage, SubAgentRuntimeStage, ToolAssembleStage
from sdk.agent.runtime_pipeline import AgentRuntimePipeline
from sdk.conversation.exceptions import ConversationRunError
from sdk.agent.stuck_detection.stuck_detector import StuckDetector
from sdk.event.conversation_error import ConversationErrorEvent
from sdk.event.llm_convertible.message import MessageEvent
from sdk.hooks.conversation_hooks import HookEventProcessor
from sdk.llm.message import Message, TextContent


logger = get_logger(__name__)


class AgentRunner:
    """Agent执行器，负责完成Agent的整体调度。"""

    _agent: AgentBase
    def __init__(
        self,
        agent_spec: AgentSpec,
        context: RunnerContext,
        max_iterations: int = 200,
        stuck_detector: StuckDetector | None = None,
        hook_processor: HookEventProcessor | None = None,
        user_id: str | None = None,
    ):
        self._lock = threading.Lock()
        self._agent_ready = False
        self._user_id = user_id
        # 使用 model_validate 而非 model_dump() + ** 展开，
        # 避免复杂嵌套对象（LLM、CondenserBase 等）序列化/反序列化时丢失子类信息。
        # 如果传入的 agent_spec 本身已经是 Agent 实例，则直接复用；
        # 否则从 dict 数据构建，保留 Pydantic 的类型校验。
        if isinstance(agent_spec, Agent):
            self._agent = agent_spec
        else:
            self._agent = Agent.model_validate(agent_spec.model_dump())
        self._agent_state = context.agent_state
        self._context = context
        self.max_iterations = max_iterations
        self._stuck_detector = stuck_detector
        self._hook_processor = hook_processor
        self._build_runtime_pipeline()
        self._runtime: AgentRuntime | None = None
        self._ensure_agent_ready()
    
    def _build_runtime_pipeline(self):
        self._pipeline = AgentRuntimePipeline(

            [
                SkillBuildStage(),

                PromptBuildStage(),

                ToolAssembleStage(),

                SubAgentRuntimeStage(), 
            ] 
        )


    def _ensure_agent_ready(self) -> None:
        if self._agent_ready:
            return

        with self._lock:
            if self._agent_ready:
                return

            logger.info("Building agent runtime")
            self._runtime = self._pipeline.build(self._agent, self._context)
            self._agent.bind_runtime(self._runtime) 
            logger.info(
                "Agent runtime ready: prompt_trace=%s, tool_trace=%s",
                self._runtime.prompt_trace,
                self._runtime.tool_trace,
            )
            self._agent.init_state(self._context)
            self._agent_ready = True
    
    

    def send_message(self, message: str | Message, sender: str | None = None):
        
        if isinstance(message, str):
            message = Message(role="user", content=[TextContent(text=message)])

        assert message.role == "user", (
            "Only user messages are allowed to be sent to the agent."
        )
        if message.user_id is None:
            message.user_id = self._user_id
        with self._lock:
            # 相当于调整
            if self._agent_state.execution_status == ExecutionStatus.FINISHED:
                self._agent_state.set_execution_status(ExecutionStatus.IDLE)

            # TODO: We should add test cases for all these scenarios
            activated_skill_names: list[str] = []
            extended_content: list[TextContent] = []

            # Handle per-turn user message (i.e., knowledge agent trigger)
            if self._agent.agent_context_spec:
                # 在发送消息之前，进行上下文加载 - 避免多次重复加载
                ctx = self._runtime.get_user_message_suffix(
                    user_message=message,
                    # We skip skills that were already activated
                    skip_skill_names=self._agent_state.activated_knowledge_skills,
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
                    self._agent_state.activate_knowledge_skills(activated_skill_names)

                memory_ctx = self._runtime.get_user_memory(
                    user_message=message, 
                    activate_ids=self._agent_state.activated_experiences,
                )
                # tuple[list[ExperienceMemory], list[str], list[str]]
                if memory_ctx:
                    content, activate_ids = memory_ctx
                    logger.debug(
                        f"Got augmented user memory: {content}, "
                        f"activated experiences: {activate_ids}"
                    )
                    extended_content.append(content)
                    self._agent_state.activate_experiences(activate_ids)

            # 将 加载的skill归类为extended内容
            user_msg_event = MessageEvent(
                source="user",
                llm_message=message,
                activated_skills=activated_skill_names,
                extended_content=extended_content,
                sender=sender,
            )
            # 通过 EventCenter 发布事件
            self._context.publish_event(
                event=user_msg_event  
            )

    @observe(name="conversation.run")
    def run(self) -> None:
        """执行Agent直到完成。

        在确认模式下：
        - 第一次调用：创建动作但不执行，停止并等待
        - 第二次调用：执行待处理的动作（隐式确认）

        在正常模式下：
        - 立即创建并执行动作

        可以在步骤之间暂停
        """
        # 获取 agent_state
        agent_state = self._context.agent_state

        with self._lock:
            # 如果Agent不在运行状态，标记为运行中
            if agent_state.execution_status in [ExecutionStatus.IDLE, ExecutionStatus.PAUSED, ExecutionStatus.ERROR]:
                agent_state.mark_running()

        iteration = 0
        try:
            while True:
                logger.debug(f"Conversation run iteration {iteration}")
                with self._lock:
                    
                    # 检查暂停标志
                    if agent_state.execution_status in [ExecutionStatus.PAUSED, ExecutionStatus.STUCK]: 
                        break

                    # 检查stuck状态 (通过stuck_detector设置)
                    # TODO: stuck_detector应该调用agent_state的方法来设置状态

                    # 检查Agent是否完成
                    if agent_state.execution_status == ExecutionStatus.FINISHED:
                        if self._hook_processor is not None:
                            should_stop, feedback = self._hook_processor.run_stop(
                                reason="agent_finished"
                            )
                            if not should_stop:
                                logger.info("Stop hook denied agent stopping")
                                if feedback:
                                    prefixed = f"[Stop hook feedback] {feedback}"
                                    feedback_msg = MessageEvent(
                                        source="user",
                                        llm_message=Message(
                                            role="user",
                                            content=[TextContent(text=prefixed)],
                                        ),
                                    )
                                    self._context.publish_event(feedback_msg)
                                # 重置为RUNNING继续执行
                                agent_state.mark_running()
                                continue
                        # 没有钩子或钩子允许停止
                        break 

                    # 如果启用，检查卡住模式
                    if self._stuck_detector:
                        is_stuck = self._stuck_detector.is_stuck(agent_state.events)

                        if is_stuck:
                            logger.warning("Stuck pattern detected.")
                            # 标记Agent为失败状态（stuck导致）
                            agent_state.set_execution_status(ExecutionStatus.STUCK)
                            continue

                    # 在调用agent.step()之前，如果Agent在等待状态，重置为运行中
                    if agent_state.execution_status ==  ExecutionStatus.WAITING_FOR_CONFIRMATION:
                        agent_state.mark_running()

                    # 调用Agent的step方法
                    self._agent.step(self._context)
                    iteration += 1

                    # 检查是否需要等待（例如等待用户确认）
                    # 如果Agent标记为WAITING状态，停止循环等待
                    if agent_state.execution_status == ExecutionStatus.WAITING_FOR_CONFIRMATION:
                        logger.info("Agent waiting for user confirmation or dependency")
                        break

                    if iteration >= self.max_iterations:
                        error_msg = (
                            f"Agent reached maximum iterations limit "
                            f"({self.max_iterations})."
                        )
                        logger.error(error_msg)
                        # 标记Agent为失败
                        agent_state.set_execution_status(ExecutionStatus.ERROR)
                        self._context.publish_event(
                            ConversationErrorEvent(
                                source="environment",
                                code="MaxIterationsReached",
                                detail=error_msg,
                            )
                        )
                        break
        except Exception as e:

            # 标记Agent为失败状态

            agent_state.set_execution_status(ExecutionStatus.ERROR)

            # 添加错误事件

            self._context.publish_event( 
                ConversationErrorEvent( 
                    source="environment", 
                    code=e.__class__.__name__, 
                    detail=str(e),
 
                ) 
            ) 
            # 重新抛出异常，提供更好的UX  
            raise AgentRunnerRunError(self._context.conversation_id, self._agent.id,e) from e
  
