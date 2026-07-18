import json
from typing import Literal

from sdk.agent.runner_context import RunnerContext
from common.logger import get_logger
from sdk.tool import ToolExecutor
from tools.sandbox.session_manager import get_default_session_manager
from tools.terminal.definition import TerminalAction, TerminalObservation
from tools.terminal.metadata import CmdOutputMetadata


logger = get_logger(__name__)


class TerminalExecutor(ToolExecutor[TerminalAction, TerminalObservation]):
    shell_path: str | None

    def __init__(
        self,
        working_dir: str,
        username: str | None = None,
        no_change_timeout_seconds: int | None = None,
        terminal_type: Literal["tmux", "subprocess"] | None = None,
        shell_path: str | None = None,
        full_output_save_dir: str | None = None,
    ):
        self.working_dir = working_dir
        self.username = username
        self.no_change_timeout_seconds = no_change_timeout_seconds
        self.terminal_type = terminal_type
        self.shell_path = shell_path
        self.full_output_save_dir = full_output_save_dir
        self._sandbox_manager = get_default_session_manager()

    def _build_command(
        self,
        action: TerminalAction,
        sandbox,
        context: RunnerContext | None = None,
    ) -> str:
        command = action.command
        if action.is_input:
            return command

        env_vars: dict[str, str] = {}
        if context is not None:
            try:
                env_vars = context.secret_registry.get_secrets_as_env_vars(command)
            except Exception:
                env_vars = {}

        if not env_vars:
            return command

        shell_type = getattr(sandbox, "shell_type", "bash")
        if shell_type == "cmd":
            exports = " && ".join(
                f"set {key}={value}" for key, value in env_vars.items()
            )
            return f"{exports} && {command}" if command.strip() else exports

        exports = " && ".join(
            f"export {key}={json.dumps(value)}" for key, value in env_vars.items()
        )
        return f"{exports} && {command}" if command.strip() else exports

    def reset(self, context: RunnerContext | None = None) -> TerminalObservation:
        session = self._sandbox_manager.resolve_context(context, self.working_dir)
        self._sandbox_manager.destroy(session.session_id)
        return TerminalObservation.from_text(
            text=(
                "Terminal session has been reset. All previous environment "
                "variables and session state have been cleared."
            ),
            command="[RESET]",
            exit_code=0,
            metadata=CmdOutputMetadata(
                working_dir=session.workspace_root,
                exit_code=0,
            ),
            full_output_save_dir=self.full_output_save_dir,
        )

    def __call__(
        self,
        action: TerminalAction,
        context: RunnerContext | None = None,
    ) -> TerminalObservation:
        if action.reset and action.is_input:
            raise ValueError("Cannot use reset=True with is_input=True")

        reset_prefix = ""
        if action.reset:
            reset_result = self.reset(context)
            if not action.command.strip():
                return reset_result
            reset_prefix = f"{reset_result.text}\n\n"

        session = self._sandbox_manager.resolve_context(context, self.working_dir)
        sandbox = self._sandbox_manager.get_or_create(session)
        command = self._build_command(action, sandbox, context)
        exec_result = self._sandbox_manager.run_in_session( 
            sandbox.execute_command(command, timeout=int(action.timeout or 30)),
        )

        text = exec_result.stdout
        if exec_result.stderr:
            text = f"{text}\n{exec_result.stderr}".strip()
        text = f"{reset_prefix}{text}".strip()

        if context is not None and text:
            try:
                text = context.secret_registry.mask_secrets_in_output(text)
            except Exception:
                pass

        return TerminalObservation.from_text(
            text=text,
            command=(f"[RESET] {action.command}" if action.reset else action.command),
            exit_code=exec_result.exit_code,
            timeout=exec_result.exit_code == -1,
            metadata=CmdOutputMetadata(
                exit_code=exec_result.exit_code,
                working_dir=session.workspace_root,
            ),
            full_output_save_dir=self.full_output_save_dir,
            is_error=exec_result.exit_code not in (0, None),
        )

    def close(self) -> None:
        return None