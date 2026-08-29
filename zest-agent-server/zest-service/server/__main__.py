import argparse
import atexit
import faulthandler
import os
import signal
from types import FrameType

import uvicorn
from uvicorn import Config

from server.logging_config import LOGGING_CONFIG
from common.logger import DEBUG, get_logger


logger = get_logger(__name__)


class LoggingServer(uvicorn.Server):
    """Custom uvicorn Server that logs signal handling events.

    This subclass overrides handle_exit to add structured logging when
    termination signals are received, ensuring visibility into why the
    server is shutting down.
    """

    def handle_exit(self, sig: int, frame: FrameType | None) -> None:
        """Handle exit signals with logging before delegating to parent."""
        sig_name = signal.Signals(sig).name
        logger.info(
            "Received signal %s (%d), shutting down...",
            sig_name,
            sig,
        )
        super().handle_exit(sig, frame)


def _setup_crash_diagnostics() -> None:
    """Enable crash diagnostics for debugging unexpected terminations.

    Note: faulthandler outputs tracebacks to stderr in plain text format,
    not through the structured JSON logger. This is unavoidable because
    during a segfault, Python's normal logging infrastructure is not
    available. The plain text traceback is still valuable for debugging.
    """
    faulthandler.enable()

    # Register atexit handler to log normal exits
    @atexit.register
    def _log_exit() -> None:
        logger.info("Process exiting via atexit handler")


def main() -> None:
    # Set up crash diagnostics early, before any other initialization
    _setup_crash_diagnostics()

    parser = argparse.ArgumentParser(description="Zest Agent Server App")
    parser.add_argument(
        "--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port", type=int, default=8001, help="Port to bind to (default: 8000)"
    )
    parser.add_argument(
        "--reload",
        dest="reload",
        default=False,
        action="store_true",
        help="Enable auto-reload (disabled by default)",
    )

    args = parser.parse_args()

    os.environ.setdefault("AGENT_SERVER_HOST", args.host)
    os.environ.setdefault("AGENT_SERVER_PORT", str(args.port))

    print(f"🙌 Starting Zest Agent Server on {args.host}:{args.port}")
    print(f"📖 API docs will be available at http://{args.host}:{args.port}/docs")
    print(f"🔄 Auto-reload: {'enabled' if args.reload else 'disabled'}")

    # Show debug mode status
    if DEBUG:
        print("🐛 DEBUG mode: ENABLED (stack traces will be shown)")
    else:
        print("🔒 DEBUG mode: DISABLED")
    print()

    # Configure uvicorn logging based on DEBUG environment variable
    log_level = "debug" if DEBUG else "info"

    # Create uvicorn config
    # 启动fastapi入口
    config = Config(
        "server.api:api",
        host=args.host,
        port=args.port,
        reload=args.reload,
        reload_includes=[
            "zest-service",
            "zest-sdk",
            "zest-tools",
        ],
        log_level=log_level,
        log_config=LOGGING_CONFIG,
        ws="wsproto",  # Use wsproto instead of deprecated websockets implementation
    )

    # Use custom LoggingServer to capture signal handling events
    server = LoggingServer(config)

    try:
        server.run()
    except Exception:
        logger.error("Server crashed with unexpected exception", exc_info=True)
        raise
    except BaseException as e:
        # Catch SystemExit, KeyboardInterrupt, etc. - these are normal termination paths
        logger.info("Server terminated: %s: %s", type(e).__name__, e)
        raise


if __name__ == "__main__":
    main()