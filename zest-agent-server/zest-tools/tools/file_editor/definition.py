"""File editor tool: view/create/str_replace/ls backed by sandbox."""

from collections.abc import Sequence
from typing import Literal

from pydantic import Field

from sdk.agent.runner_context import RunnerContext

from sdk.tool import (
    Action,
    Observation,
    ToolAnnotations,
    ToolDefinition,
    register_tool,
)


CommandLiteral = Literal["view", "create", "str_replace", "ls"]


class FileEditorAction(Action):
    """Schema for file editor operations."""

    command: CommandLiteral = Field(
        description=(
            "The command to run. Allowed options: "
            "`view` (read file with line numbers), "
            "`create` (create new file), "
            "`str_replace` (replace exact string in file), "
            "`ls` (list directory contents)."
        )
    )
    path: str = Field(description="Absolute path to file or directory.")
    file_text: str | None = Field(
        default=None,
        description="Required for `create`: the content of the file to be created.",
    )
    old_str: str | None = Field(
        default=None,
        description="Required for `str_replace`: the exact string to replace in the file.",
    )
    new_str: str | None = Field(
        default=None,
        description="Required for `str_replace`: the replacement string.",
    )
    view_range: list[int] | None = Field(
        default=None,
        description=(
            "Optional for `view`: [start_line, end_line] (1-indexed). "
            "Use [start, -1] to read from start_line to end of file."
        ),
    )
    offset: int | None = Field(
        default=None,
        ge=0,
        description="Optional for `view`: 0-based line offset to start reading from.",
    )
    limit: int | None = Field(
        default=None,
        ge=1,
        description="Optional for `view`: maximum number of lines to read (default 500).",
    )


class FileEditorObservation(Observation):
    """Observation from file editor operations."""

    command: CommandLiteral = Field(
        description="The command that was run."
    )
    path: str | None = Field(default=None, description="The file path that was operated on.")
    prev_exist: bool = Field(
        default=True,
        description="Indicates if the file previously existed.",
    )
    new_content: str | None = Field(
        default=None, description="The content of the file after the edit."
    )


TOOL_DESCRIPTION = """File editor tool for viewing, creating and editing plain-text files.
* `view` - read file contents with line numbers (supports view_range, offset, limit)
* `create` - create a new file (fails if file already exists)
* `str_replace` - replace an exact string occurrence in a file
* `ls` - list files and directories at a path

Always use absolute file paths (starting with /).
EXACT MATCHING: old_str must match exactly - include sufficient context (3-5 lines) for uniqueness.
"""

class FileEditorTool(ToolDefinition[FileEditorAction, FileEditorObservation]):
    """A ToolDefinition subclass that automatically initializes a FileEditorExecutor."""

    @classmethod
    def create(
        cls,
        context: RunnerContext,
    ) -> Sequence["FileEditorTool"]:
        """Initialize FileEditorTool with a FileEditorExecutor.

        Args:
            context: Runner context to get working directory from.
                         If provided, workspace_root will be taken from
                         context.workspace
        """
        # Import here to avoid circular imports
        from tools.file_editor.impl import FileEditorExecutor

        # Initialize the executor
        executor = FileEditorExecutor(workspace_root=context.workspace.working_dir)

        # Build the tool description with conditional image viewing support
        # Split TOOL_DESCRIPTION to insert image viewing line after the second bullet
        description_lines = TOOL_DESCRIPTION.split("\n")
        base_description = "\n".join(description_lines[:2])  # First two lines
        remaining_description = "\n".join(description_lines[2:])  # Rest of description

        # Add image viewing line if LLM supports vision
        # if context.llm.vision_is_active():
        #     tool_description = (
        #         f"{base_description}\n"
        #         "* If `path` is an image file (.png, .jpg, .jpeg, .gif, .webp, "
        #         ".bmp), `view` displays the image content\n"
        #         f"{remaining_description}"
        #     )
        # else: todo 支持
        tool_description = TOOL_DESCRIPTION

        # Add working directory information to the tool description
        # to guide the agent to use the correct directory instead of root
        working_dir = context.workspace.working_dir
        enhanced_description = (
            f"{tool_description}\n\n"
            f"Your current working directory is: {working_dir}\n"
            f"When exploring project structure, start with this directory "
            f"instead of the root filesystem."
        )

        # Initialize the parent Tool with the executor
        return [
            cls(
                action_type=FileEditorAction,
                observation_type=FileEditorObservation,
                description=enhanced_description,
                annotations=ToolAnnotations(
                    title="file_editor",
                    readOnlyHint=False,
                    destructiveHint=True,
                    idempotentHint=False,
                    openWorldHint=False,
                ),
                executor=executor,
            )
        ]


# Automatically register the tool when this module is imported
register_tool(FileEditorTool.tool_name, FileEditorTool)
