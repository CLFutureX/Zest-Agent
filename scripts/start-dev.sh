#!/usr/bin/env bash
# scripts/start-dev.sh
# Launches zest-web, zest-app-server, and zest-service in background.
# Startup order: 1) frontend (5173) → 2) app-server (9000) → 3) service (8001)
# Usage:
#   ./scripts/start-dev.sh start    # default: start all three
#   ./scripts/start-dev.sh stop
#   ./scripts/start-dev.sh status
# Requires: redis and mysql running (docker compose up -d).

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

LOG_DIR="$ROOT/.tmp"
mkdir -p "$LOG_DIR"

PIDS_FILE="$LOG_DIR/zest-dev.pids"
touch "$PIDS_FILE"

start_service() {
    local name="$1"; local cwd="$2"; shift 2
    local log="$LOG_DIR/zest-$name.log"
    echo "Starting $name -> log: $log"
    (
        cd "$cwd"
        "$@" >"$log" 2>&1 &
        echo $! >>"$PIDS_FILE"
    )
}

stop_all() {
    if [[ -f "$PIDS_FILE" ]]; then
        while read -r pid; do
            if kill -0 "$pid" 2>/dev/null; then
                echo "Stopping PID $pid"
                kill "$pid" 2>/dev/null || true
            fi
        done <"$PIDS_FILE"
        : >"$PIDS_FILE"
    fi
    pkill -f "vite"                  2>/dev/null || true
    pkill -f "uvicorn app.main:app"  2>/dev/null || true
    pkill -f "python -m server"      2>/dev/null || true
    echo "All Zest dev processes stopped."
}

show_status() {
    for port in 6379 3306; do
        if ! (echo > /dev/tcp/127.0.0.1/$port) 2>/dev/null; then
            echo "[WARN] Port $port not reachable. Run: docker compose up -d"
        fi
    done
    for name in web app-server service; do
        if ([[ "$name" == "web"        ]] && pgrep -f "vite"               >/dev/null) || \
           ([[ "$name" == "app-server" ]] && pgrep -f "uvicorn app.main:app" >/dev/null) || \
           ([[ "$name" == "service"    ]] && pgrep -f "python -m server"   >/dev/null); then
            echo "[RUNNING] $name"
        else
            echo "[STOPPED] $name"
        fi
    done
}

case "${1:-start}" in
    start)
        # Order: 1) frontend → 2) app-server → 3) service
        start_service "web"         "$ROOT/zest-web"                  pnpm dev
        start_service "app-server" "$ROOT/zest-app-server"           uv run uvicorn app.main:app --host 0.0.0.0 --port 9000 --reload
        start_service "service"    "$ROOT/zest-agent-server/zest-service" uv run python -m server --host 0.0.0.0 --port 8001 --reload
        echo
        echo "Endpoints (order: web -> app-server -> service):"
        echo "  http://127.0.0.1:5173  (web)"
        echo "  http://127.0.0.1:9000  (app-server)"
        echo "  http://127.0.0.1:8001  (service)"
        ;;
    stop)    stop_all ;;
    status)  show_status ;;
    *) echo "Usage: $0 {start|stop|status}"; exit 1 ;;
esac
