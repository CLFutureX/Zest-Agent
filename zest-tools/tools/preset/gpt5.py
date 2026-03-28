"""GPT-5 preset configuration for OpenHands agents.

This preset uses ApplyPatchTool for file edits instead of the default
claude-style FileEditorTool. It mirrors the Gemini preset pattern by
providing optional helpers without changing global defaults.
"""

from sdk import Agent
from sdk.context.condenser import LLMSummarizingCondenser
from sdk.context.condenser.base import CondenserBase
from sdk.llm.llm import LLM
from sdk.logger import get_logger
from sdk.tool import Tool


logger = get_logger(__name__)


def register_gpt5_tools(enable_browser: bool = True) -> None:
    """Register the GPT-5 tool set (terminal, apply_patch, task_tracker, browser)."""
    from openhands.tools.apply_patch import ApplyPatchTool
    from openhands.tools.task_tracker import TaskTrackerTool
    from openhands.tools.terminal import TerminalTool

    logger.debug(f"Tool: {TerminalTool.name} registered.")
    logger.debug(f"Tool: {ApplyPatchTool.name} registered.")
    logger.debug(f"Tool: {TaskTrackerTool.name} registered.")

    if enable_browser:
        from openhands.tools.browser_use import BrowserToolSet

        logger.debug(f"Tool: {BrowserToolSet.name} registered.")


def get_gpt5_tools(enable_browser: bool = True) -> list[Tool]:
    """Get the GPT-5 tool specifications using ApplyPatchTool for edits.

    Args:
        enable_browser: Whether to include browser tools.
    """
    register_gpt5_tools(enable_browser=enable_browser)

    from openhands.tools.apply_patch import ApplyPatchTool
    from openhands.tools.task_tracker import TaskTrackerTool
    from openhands.tools.terminal import TerminalTool

    tools: list[Tool] = [
        Tool(name=TerminalTool.tool_name),
        Tool(name=ApplyPatchTool.tool_name),
        Tool(name=TaskTrackerTool.tool_name),
    ]
    if enable_browser:
        from openhands.tools.browser_use import BrowserToolSet

        tools.append(Tool(name=BrowserToolSet.tool_name))
    return tools


def get_gpt5_condenser(llm: LLM) -> CondenserBase:
    """Get the default condenser for the GPT-5 preset."""
    return LLMSummarizingCondenser(llm=llm, max_size=80, keep_first=4)


def get_gpt5_agent(llm: LLM, cli_mode: bool = False) -> Agent:
    """Get an agent with ApplyPatchTool for unified-diff style file editing."""
    tools = get_gpt5_tools(enable_browser=not cli_mode)
    agent = Agent(
        llm=llm,
        tools=tools,
        system_prompt_kwargs={"cli_mode": cli_mode},
        condenser=get_gpt5_condenser(
            llm=llm.model_copy(update={"usage_id": "condenser"})
        ),
    )
    return agent
