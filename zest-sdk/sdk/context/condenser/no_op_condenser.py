from sdk.context.condenser.base import CondenserBase
from sdk.context.view import View
from sdk.event.condenser import Condensation
from sdk.llm import LLM


class NoOpCondenser(CondenserBase):
    """Simple condenser that returns a view un-manipulated.

    Primarily intended for testing purposes.
    """

    def condense(self, view: View, agent_llm: LLM | None = None) -> View | Condensation:  # noqa: ARG002
        return view
