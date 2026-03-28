from sdk.agent.base import AgentBase
from sdk.agent.runner_context import RunnerContext
from sdk.context.agent_state import AgentExecutionStatus
from sdk.conversation.exceptions import ConversationRunError
from sdk.conversation.stuck_detector import StuckDetector
from sdk.event.conversation_error import ConversationErrorEvent
from sdk.event.llm_convertible.message import MessageEvent
from sdk.hooks.conversation_hooks import HookEventProcessor
from sdk.llm.message import Message, TextContent
from sdk.logger import get_logger
from sdk.observability.laminar import observe


logger = get_logger(__name__)


class AgentRunner:
    """Agent执行器，负责完成Agent的整体调度。

    AgentRunner的职责：
    1. 管理Agent的执行循环
    2. 处理执行状态转换
    3. 检测卡住模式
    4. 处理钩子回调
    5. 管理迭代次数限制

    设计原则：
    - 仅负责调度，不负责持久化和配置
    - 从RunnerContext中获取执行所需的数据
    - 与Agent解耦，通过RunnerContext通信
    """

    def __init__(
        self,
        agent: AgentBase,
        context: RunnerContext,
        max_iterations: int = 200,
        stuck_detector: StuckDetector | None = None,
        hook_processor: HookEventProcessor | None = None,
    ):
        """初始化AgentRunner。

        Args:
            agent: 要执行的Agent实例
            context: 运行时上下文，包含执行所需的所有数据
            max_iterations: 最大迭代次数
            stuck_detector: 卡住检测器（可选）
            hook_processor: 钩子处理器（可选）
        """
        self.agent = agent
        self._context = context
        self.max_iterations = max_iterations
        self._stuck_detector = stuck_detector
        self._hook_processor = hook_processor

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

        with self._context:
            # 如果Agent不在运行状态，标记为运行中
            if agent_state.execution_status != AgentExecutionStatus.RUNNING:
                agent_state.mark_running()

        iteration = 0
        try:
            while True:
                logger.debug(f"Conversation run iteration {iteration}")
                with self._context:
                    # 检查暂停标志
                    if (
                        agent_state.execution_status
                        and agent_state.execution_status == AgentExecutionStatus.WAITING
                    ):
                        logger.info("Execution paused by user")
                        break

                    # 检查stuck状态 (通过stuck_detector设置)
                    # TODO: stuck_detector应该调用agent_state的方法来设置状态

                    # 检查Agent是否完成
                    if agent_state.execution_status == AgentExecutionStatus.COMPLETED:
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

                    # 检查Agent是否失败
                    if agent_state.execution_status == AgentExecutionStatus.FAILED:
                        logger.error(
                            f"Agent failed: {agent_state.metadata.get('error_message', 'Unknown error')}"
                        )
                        break

                    # 如果启用，检查卡住模式
                    if self._stuck_detector:
                        is_stuck = self._stuck_detector.is_stuck(agent_state.events)

                        if is_stuck:
                            logger.warning("Stuck pattern detected.")
                            # 标记Agent为失败状态（stuck导致）
                            agent_state.mark_failed(error_message="Agent stuck in loop")
                            continue

                    # 在调用agent.step()之前，如果Agent在等待状态，重置为运行中
                    if agent_state.execution_status == AgentExecutionStatus.WAITING:
                        agent_state.mark_running()

                    # 调用Agent的step方法
                    self.agent.step(self._context)
                    iteration += 1

                    # 检查是否需要等待（例如等待用户确认）
                    # 如果Agent标记为WAITING状态，停止循环等待
                    if agent_state.execution_status == AgentExecutionStatus.WAITING:
                        logger.info("Agent waiting for user confirmation or dependency")
                        break

                    if iteration >= self.max_iterations:
                        error_msg = (
                            f"Agent reached maximum iterations limit "
                            f"({self.max_iterations})."
                        )
                        logger.error(error_msg)
                        # 标记Agent为失败
                        agent_state.mark_failed(error_message=error_msg)
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
            agent_state.mark_failed(error_message=str(e))

            # 添加错误事件
            self._context.publish_event(
                ConversationErrorEvent(
                    source="environment",
                    code=e.__class__.__name__,
                    detail=str(e),
                )
            )

            # 重新抛出异常，提供更好的UX
            raise ConversationRunError(self._context.id, e, persistence_dir=None) from e
