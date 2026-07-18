
from enum import Enum
import uuid
 




ConversationID = uuid.UUID | str
"""Type alias for conversation IDs."""

AgentID = uuid.UUID | str


class ExecutionStatus(str, Enum):
    """Enum representing the current execution state of the conversation."""

    IDLE = "idle"  # Conversation is ready to receive tasks
    RUNNING = "running"  # Conversation is actively processing
    PAUSED = "paused"  # Conversation execution is paused by user
    WAITING_FOR_CONFIRMATION = (
        "waiting_for_confirmation"  # Conversation is waiting for user confirmation
    )
    FINISHED = "finished"  # Conversation has completed the current task
    ERROR = "error"  # Conversation encountered an error (optional for future use)
    STUCK = "stuck"  # Conversation is stuck in a loop or unable to proceed
    DELETING = "deleting"  # Conversation is in the process of being deleted

