from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Self, overload

from sdk.agent.agent_spec import AgentSpec
from sdk.agent.base import AgentBase
from sdk.conversation.base import BaseConversation, ConversationCallbackType
from sdk.agent.stuck_detection.types import ( 
    ConversationTokenCallbackType,
    StuckDetectionThresholds,
)
from sdk.conversation.visualizer import (
    ConversationVisualizerBase,
    DefaultConversationVisualizer,
)
from sdk.hooks import HookConfig
from common.logger import get_logger
from sdk.plugin import PluginSource
from sdk.secret import SecretValue
from common.utils.common import ConversationID
from sdk.workspace import LocalWorkspace 


if TYPE_CHECKING:
    from sdk.conversation.impl.conversation_impl import LocalConversation
 
logger = get_logger(__name__)


class Conversation:
    """Factory class for creating conversation instances with Zest agents.

    This factory automatically creates either a LocalConversation  

    Returns:
        LocalConversation if workspace is local,  

    Example:
        >>> from sdk import LLM, Agent, Conversation
        >>> from sdk.plugin import PluginSource
        >>> llm = LLM(model="claude-sonnet-4-20250514", api_key=SecretStr("key"))
        >>> agent = Agent(llm=llm, tools=[])
        >>> conversation = Conversation(
        ...     agent=agent,
        ...     workspace="./workspace",
        ...     plugins=[PluginSource(source="github:org/security-plugin", ref="v1.0")],
        ... )
        >>> conversation.send_message("Hello!")
        >>> conversation.run()
    """

    @overload
    def __new__(
        cls: type[Self],
        agent_spec: AgentSpec,
        *,
        workspace: str | Path | LocalWorkspace = "workspace/project",
        plugins: list[PluginSource] | None = None, 
        conversation_id: ConversationID | None = None,
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
        secrets: dict[str, SecretValue] | dict[str, str] | None = None,
        user_id: str | None = None,
    ) -> "LocalConversation": ...
 
    def __new__(
        cls: type[Self],
        agent_spec: AgentSpec,
        *,
        workspace: str | Path | LocalWorkspace  = "workspace/project",
        plugins: list[PluginSource] | None = None, 
        conversation_id: ConversationID | None = None,
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
        secrets: dict[str, SecretValue] | dict[str, str] | None = None,
        user_id: str | None = None,
    ) -> BaseConversation:
        from sdk.conversation.impl.conversation_impl import LocalConversation
        
        return LocalConversation(
            agent_spec=agent_spec,
            plugins=plugins,
            conversation_id=conversation_id,
            callbacks=callbacks,
            token_callbacks=token_callbacks,
            hook_config=hook_config,
            max_iteration_per_run=max_iteration_per_run,
            stuck_detection=stuck_detection,
            stuck_detection_thresholds=stuck_detection_thresholds,
            visualizer=visualizer,
            workspace=workspace, 
            secrets=secrets,
            user_id=user_id,
        )
