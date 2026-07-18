"""Events related to agent state updates."""

import uuid
from typing import Any

from pydantic import Field, field_validator

from common.event.types import SourceType
from sdk.event.base import Event


class AgentStateUpdateEvent(Event):
    """Event emitted when a persisted AgentState field changes."""

    source: SourceType = "environment"
    agent_id: str = Field(..., description="Agent id that owns the updated state")
    key: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Updated AgentState field name",
    )
    value: Any = Field(default=None, description="Updated field value")

    @field_validator("key")
    @classmethod
    def validate_key(cls, key: str) -> str:
        if not isinstance(key, str):
            raise ValueError("Key must be a string")
        return key

    def __str__(self) -> str:
        return (
            f"AgentStateUpdate(agent_id={self.agent_id}, key={self.key}, value={self.value})"
        )
