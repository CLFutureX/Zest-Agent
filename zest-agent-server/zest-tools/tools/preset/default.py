"""Default preset configuration for Zest agents."""

from sdk import Agent 
from sdk.agent.agent_spec import AgentContextSpec
from sdk.context.condenser import (
    LLMSummarizingCondenser,
)
from sdk.context.condenser.base import CondenserBase
from sdk.context.skills.skill import Skill
from sdk.llm.llm import LLM
from common.logger import get_logger
from sdk.memory.memory_manager import MemoryManager
from sdk.tool import Tool


logger = get_logger(__name__)


def register_default_tools(enable_browser: bool = True) -> None:
    """Register the default set of tools."""
    # Tools are now automatically registered when imported
    from tools.file_editor import FileEditorTool
    from tools.task_tracker import TaskTrackerTool
    from tools.terminal import TerminalTool
    

    logger.debug(f"Tool: {TerminalTool.tool_name} registered.")
    logger.debug(f"Tool: {FileEditorTool.tool_name} registered.")
    logger.debug(f"Tool: {TaskTrackerTool.tool_name} registered.")

    if enable_browser:
        from tools.browser_use import BrowserToolSet

        logger.debug(f"Tool: {BrowserToolSet.tool_name} registered.")


def register_memory_tools(tools: list[Tool],enable_base_memory: bool = True, enable_experience_memory: bool = True) -> None:
    """Register memory-related tools."""
    if enable_base_memory:
        from sdk.tool.builtins.base_memory_tool import BaseMemoryTool
        logger.debug(f"Tool: {BaseMemoryTool.tool_name} registered.")
        if tools:
            tools.append(Tool(name=BaseMemoryTool.tool_name))

    if enable_experience_memory:
        from sdk.tool.builtins.experience_memory_tool import ExperienceMemoryTool
        from sdk.tool.builtins.memory_review_tool import MemoryReviewTool
        logger.debug(f"Tool: {ExperienceMemoryTool.tool_name} registered.")
        logger.debug(f"Tool: {MemoryReviewTool.tool_name} registered.")
        if tools:
            tools.append(Tool(name=ExperienceMemoryTool.tool_name))
            tools.append(Tool(name=MemoryReviewTool.tool_name))

def register_sale_tools(tools:list[Tool])->None:
    from tools.after_sales_demo.aftersale_qty_tools import QueryForwardOrderTool,QueryAfterSaleOrderTool,QueryIODataTool,CalcAvailableAfterSaleTool 
    if tools:
        tools.append(Tool(name=QueryForwardOrderTool.tool_name))
        tools.append(Tool(name=QueryAfterSaleOrderTool.tool_name))
        tools.append(Tool(name=QueryIODataTool.tool_name))
        tools.append(Tool(name=CalcAvailableAfterSaleTool.tool_name))
    logger.debug(f"Tool: {QueryForwardOrderTool.tool_name} registered.")
    logger.debug(f"Tool: {QueryAfterSaleOrderTool.tool_name} registered.")
    logger.debug(f"Tool: {QueryIODataTool.tool_name} registered.")
    logger.debug(f"Tool: {CalcAvailableAfterSaleTool.tool_name} registered.")
    
def get_default_tools(
    enable_browser: bool = True 
) -> list[Tool]:
    """Get the default set of tool specifications for the standard experience.

    Args:
        enable_browser: Whether to include browser tools.
        enable_base_memory: Whether to include base memory tools.
        enable_experience_memory: Whether to include experience memory tools.
    """
    register_default_tools(enable_browser=enable_browser)
    # # Import tools to access their name attributes
    from tools.file_editor import FileEditorTool
    from tools.task_tracker import TaskTrackerTool
    from tools.terminal import TerminalTool
    

    tools = [
        Tool(name=TerminalTool.tool_name),
        Tool(name=FileEditorTool.tool_name),
        Tool(name=TaskTrackerTool.tool_name),
    ]
    if enable_browser:
        from tools.browser_use import BrowserToolSet 
        tools.append(Tool(name=BrowserToolSet.tool_name)) 

    return tools


def get_default_condenser(llm: LLM) -> CondenserBase:
    # Create a condenser to manage the context. The condenser will automatically
    # truncate conversation history when it exceeds max_size, and replaces the dropped
    # events with an LLM-generated summary.
    condenser = LLMSummarizingCondenser(llm=llm, max_size=80, keep_first=4)

    return condenser


def get_default_agent(
    llm: LLM,
    agent_context_spec: AgentContextSpec  | None = None,
    cli_mode: bool = False,
    enable_base_memory: bool = True,
    enable_experience_memory: bool = True,
    skills: list[Skill] | None = None,
) -> Agent:
    tools = get_default_tools(
        # Disable browser tools in CLI mode
        enable_browser=not cli_mode,
    )
    register_memory_tools(tools, enable_base_memory=enable_base_memory, enable_experience_memory=enable_experience_memory)
   
    agent = Agent(
        llm=llm,
        tools=tools,
        system_prompt_kwargs={"cli_mode": cli_mode},
        condenser=get_default_condenser(
            llm=llm.model_copy(update={"usage_id": "condenser"})
        ),
        agent_context_spec=agent_context_spec,
    )
    return agent
