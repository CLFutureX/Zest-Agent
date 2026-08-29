from pydantic import BaseModel, Field

from sdk.agent.agent_spec import AgentSpec
from sdk.agent.base import AgentBase
from sdk.agent.agent_state import AgentState
from sdk.conversation.conversation_stats import ConversationStats
from sdk.secret.secret_registry import SecretRegistry
from common.utils.common import ConversationID, ExecutionStatus
from sdk.hooks.config import HookConfig
from sdk.plugin.types import PluginSource
from sdk.secret.secrets import SecretSource
from sdk.security.analyzer import SecurityAnalyzerBase
from sdk.security.confirmation_policy import ConfirmationPolicyBase, NeverConfirm
from sdk.security.llm_analyzer import LLMSecurityAnalyzer
from sdk.workspace.local import LocalWorkspace

class ConversationStateMeta(BaseModel):

    id: ConversationID 

    agent: AgentSpec 
    
    user_id: str 

    workspace: LocalWorkspace   

    secrets: dict[str, SecretSource] = Field(default_factory=dict) 

    tool_module_qualnames: dict[str, str] = Field(default_factory=dict) 

    plugins: list[PluginSource] | None = None 

    hook_config: HookConfig | None = None

    confirmation_policy: ConfirmationPolicyBase = NeverConfirm()

    security_analyzer: SecurityAnalyzerBase = LLMSecurityAnalyzer()

    max_iterations: int = 500

    stuck_detection: bool = Field(default=True)

    enable_base_memory: bool = Field(default=True)
    enable_experience_memory: bool = Field(default=True)

    
    
class ConversationStateSnapshot(BaseModel):
    id: ConversationID
    execution_status: ExecutionStatus = Field(default=ExecutionStatus.IDLE)
    stuck_detection: bool = Field(default=True)
    confirmation_policy: ConfirmationPolicyBase = NeverConfirm()
    security_analyzer: SecurityAnalyzerBase | None = None
    main_agent_state: AgentState | None = Field(default=None)
    stats: ConversationStats = Field(default_factory=ConversationStats)
    secret_registry: SecretRegistry = Field(default_factory=SecretRegistry)
    
