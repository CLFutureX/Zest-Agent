

from common.utils.common import AgentID, ConversationID

 

class AgentRunnerRunError(RuntimeError):
    """Raised when a conversation run fails.

    Carries the conversation_id and persistence_dir to make resuming/debugging
    easier while preserving the original exception via exception chaining.
    """

    conversation_id: ConversationID
    agent_id: AgentID
    original_exception: BaseException

    def __init__(
        self,
        conversation_id: ConversationID,
        agent_id: AgentID, 
        original_exception: BaseException,
        
        message: str | None = None,
    ) -> None:
        self.conversation_id = conversation_id
        self.agent_id = agent_id
        self.original_exception = original_exception
        default_msg = self._build_error_message(
            conversation_id,agent_id, original_exception 
        )
        super().__init__(message or default_msg)

    @staticmethod
    def _build_error_message(
        conversation_id: ConversationID,
        agent_id: AgentID, 
        original_exception: BaseException, 
    ) -> str:
        """Build a detailed error message with debugging information."""
        lines = [
            f"AgentRunner run failed for id={conversation_id}: {agent_id}:{original_exception}",
        ]
 

        return "\n".join(lines)
