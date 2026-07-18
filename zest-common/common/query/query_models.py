from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class ConversationEventRecord(BaseModel):
    event_id: str
    conversation_id: str
    event_type: str
    source: str
    timestamp: str
    payload: dict[str, Any] = Field(default_factory=dict)


class ConversationEventPage(BaseModel):
    items: list[ConversationEventRecord] = Field(default_factory=list)
    next_cursor: str | None = None
    has_more: bool = False


class ConversationMemoryRecord(BaseModel):
    id: str
    memory_type: str
    category: str | None = None
    title: str | None = None
    content: str
    score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TodoItem(BaseModel):
    """Single todo item from AgentState.todos"""
    content: str
    status: str = "pending"  # pending / in_progress / completed / cancelled


class ConversationStateView(BaseModel):
    """Minimal conversation state view returned to the frontend.

    Derived from ConversationStateSnapshot (dynamic) and optionally
    ConversationStateMeta (static) for agent_id.
    """
    conversation_id: str
    execution_status: str = "idle"   # idle / running / finished / error
    task_description: str = ""
    todos: list[TodoItem] = Field(default_factory=list)
    agent_id: str | None = None