"""AgentFactory - 从 AgentState 重建 Agent 实例（简化版）

⭐ 简化原则：
1. AgentState 直接持有 Agent 的配置字段（LLM、tools、agent_context）
2. 不需要 AgentConfig 中间层
3. 恢复时只需重新注入 API key（从环境变量或用户输入获取）
4. Pydantic 自动处理序列化/反序列化
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

from sdk.logger import get_logger


if TYPE_CHECKING:
    from sdk.agent.base import AgentBase
    from sdk.context.agent_state import AgentState

logger = get_logger(__name__)


class AgentFactory:
    """从 AgentState 重建 Agent 实例的工厂类（简化版）

    ⭐ 简化后的使用方式：
        >>> # 从 checkpoint 恢复
        >>> agent_state = AgentState.model_validate_json(checkpoint_json)
        >>>
        >>> # 重新注入 API key（从环境变量或用户输入）
        >>> api_key = os.getenv("LLM_API_KEY")
        >>> agent_state.llm.api_key = SecretStr(api_key)
        >>>
        >>> # 重建 Agent（直接使用 Agent 构造函数）
        >>> agent = AgentFactory.rebuild(agent_state)
    """

    @staticmethod
    def rebuild(agent_state: AgentState) -> AgentBase:
        """从 AgentState 重建 Agent 实例（简化版）

        ⭐ 核心思想：Agent 本身就是 Pydantic 模型，直接使用其配置字段即可

        Args:
            agent_state: Agent 状态（已包含 llm、tools、agent_context）

        Returns:
            重建的 Agent 实例

        Raises:
            ValueError: 如果配置无效或 Agent 类型不支持

        Note:
            调用前需要确保 agent_state.llm.api_key 已经被重新注入（不从磁盘读取）
        """
        if not agent_state.llm:
            raise ValueError(
                f"AgentState {agent_state.agent_id} has no LLM configuration. "
                f"Cannot rebuild Agent without LLM."
            )

        logger.info(
            f"Rebuilding Agent {agent_state.agent_id} (type={agent_state.agent_type})"
        )

        # 获取 Agent 类（动态导入）
        agent_class = AgentFactory._get_agent_class(agent_state.agent_type)

        # ⭐ 直接使用 Agent 构造函数（配置字段都是 Pydantic 模型）
        agent = agent_class(
            id=agent_state.agent_id,
            llm=agent_state.llm,  # Pydantic LLM 模型
            tools=agent_state.tools or [],  # Pydantic Tool 模型列表
            agent_context=agent_state.agent_context,  # Pydantic AgentContext 模型
            mcp_config=agent_state.mcp_config,
            filter_tools_regex=agent_state.filter_tools_regex,
            include_default_tools=agent_state.include_default_tools,
            custom_system_prompt=agent_state.custom_system_prompt,
        )

        logger.info(f"Successfully rebuilt Agent {agent_state.agent_id}")

        return agent

    @staticmethod
    def _get_agent_class(agent_type: str):
        """动态获取 Agent 类（简化版）

        Args:
            agent_type: Agent 类型名称（如 'Agent', 'CodeActAgent'）

        Returns:
            Agent 类
        """
        # 默认从 sdk.agent 模块导入
        try:
            module = importlib.import_module("sdk.agent")
            agent_class = getattr(module, agent_type)
            return agent_class
        except (ImportError, AttributeError):
            raise ValueError(f"Unknown agent type: {agent_type}")


# ⭐ 删除不再需要的辅助方法：
# - _rebuild_llm: 不需要，直接使用 agent_state.llm
# - _rebuild_tools: 不需要，直接使用 agent_state.tools
# - _rebuild_agent_context: 不需要，直接使用 agent_state.agent_context
# - _rebuild_critic: 不需要，Critic 应该从 ConversationState 获取（会话级共享）
