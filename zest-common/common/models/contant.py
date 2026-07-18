
from typing import Annotated
from uuid import UUID

from pydantic import PlainSerializer


def _uuid_to_hex(uuid_obj: UUID) -> str:
    """Converts a UUID object to a hex string without hyphens."""
    return uuid_obj.hex


ZestAgentUUID = Annotated[UUID, PlainSerializer(_uuid_to_hex, when_used="json")]