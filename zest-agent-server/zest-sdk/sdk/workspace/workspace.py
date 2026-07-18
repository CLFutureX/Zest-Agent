from typing import Self, overload

from common.logger import get_logger
from sdk.workspace.base import BaseWorkspace
from sdk.workspace.local import LocalWorkspace 


logger = get_logger(__name__)


class Workspace:
    """Factory entrypoint that returns a LocalWorkspace or RemoteWorkspace.

    Usage:
        - Workspace(working_dir=...) -> LocalWorkspace
        - Workspace(working_dir=..., host="http://...") -> RemoteWorkspace
    """

    @overload
    def __new__(
        cls: type[Self],
        *,
        working_dir: str = "workspace/project",
    ) -> LocalWorkspace: ...

     
    def __new__(
        cls: type[Self],
        *,
        host: str | None = None,
        working_dir: str = "workspace/project",
        api_key: str | None = None,
    ) -> BaseWorkspace:
      
        return LocalWorkspace(working_dir=working_dir)
