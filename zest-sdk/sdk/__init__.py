from importlib.metadata import PackageNotFoundError, version

from sdk.agent import Agent, AgentBase
from sdk.context import (
    AgentContext,
    load_project_skills,
    load_skills_from_dir,
    load_user_skills,
)
from sdk.context.condenser import (
    LLMSummarizingCondenser,
)
from sdk.conversation import (
    BaseConversation,
    Conversation,
    ConversationCallbackType,
    ConversationExecutionStatus,
    LocalConversation,
    RemoteConversation,
)
from sdk.conversation.conversation_stats import ConversationStats
from sdk.event import Event, LLMConvertibleEvent
from sdk.event.llm_convertible import MessageEvent
from sdk.io import FileStore, LocalFileStore
from sdk.llm import (
    LLM,
    ImageContent,
    LLMRegistry,
    LLMStreamChunk,
    Message,
    RedactedThinkingBlock,
    RegistryEvent,
    TextContent,
    ThinkingBlock,
    TokenCallbackType,
)
from sdk.logger import get_logger
from sdk.mcp import (
    MCPClient,
    MCPToolDefinition,
    MCPToolObservation,
    create_mcp_tools,
)
from sdk.plugin import Plugin
from sdk.tool import (
    Action,
    Observation,
    Tool,
    ToolDefinition,
    list_registered_tools,
    register_tool,
    resolve_tool,
)
from sdk.workspace import (
    LocalWorkspace,
    RemoteWorkspace,
    Workspace,
)


try:
    __version__ = version("openhands-sdk")
except PackageNotFoundError:
    __version__ = "0.0.0"  # fallback for editable/unbuilt environments

__all__ = [
    "LLM",
    "LLMRegistry",
    "LLMStreamChunk",
    "TokenCallbackType",
    "ConversationStats",
    "RegistryEvent",
    "Message",
    "TextContent",
    "ImageContent",
    "ThinkingBlock",
    "RedactedThinkingBlock",
    "Tool",
    "ToolDefinition",
    "AgentBase",
    "Agent",
    "Action",
    "Observation",
    "MCPClient",
    "MCPToolDefinition",
    "MCPToolObservation",
    "MessageEvent",
    "create_mcp_tools",
    "get_logger",
    "Conversation",
    "BaseConversation",
    "LocalConversation",
    "RemoteConversation",
    "ConversationExecutionStatus",
    "ConversationCallbackType",
    "Event",
    "LLMConvertibleEvent",
    "AgentContext",
    "LLMSummarizingCondenser",
    "FileStore",
    "LocalFileStore",
    "Plugin",
    "register_tool",
    "resolve_tool",
    "list_registered_tools",
    "Workspace",
    "LocalWorkspace",
    "RemoteWorkspace",
    "load_project_skills",
    "load_skills_from_dir",
    "load_user_skills",
    "__version__",
]
