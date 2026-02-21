#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PIDFILE="$SCRIPT_DIR/.megobari/bot.pid"

usage() {
    echo "Usage: ./run.sh <mode>"
    echo ""
    echo "Modes:"
    echo "  watch    — restart on any .py file change (dev mode)"
    echo "  hook     — run in a restart loop, killed by git post-commit hook"
    echo "  once     — run once, no auto-restart"
    echo "  stop     — stop the running bot"
    exit 1
}

write_pid() {
    mkdir -p "$(dirname "$PIDFILE")"
    echo "$1" > "$PIDFILE"
}

read_pid() {
    if [ -f "$PIDFILE" ]; then
        cat "$PIDFILE"
    fi
}

cleanup() {
    rm -f "$PIDFILE"
}

stop_bot() {
    local pid
    pid=$(read_pid)
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        echo "Stopping bot (PID $pid)..."
        kill "$pid"
        # Wait for process to exit
        for _ in $(seq 1 30); do
            kill -0 "$pid" 2>/dev/null || break
            sleep 0.1
        done
        # Force kill if still running
        if kill -0 "$pid" 2>/dev/null; then
            kill -9 "$pid" 2>/dev/null || true
        fi
        cleanup
        echo "Stopped."
    else
        echo "Bot is not running."
        cleanup
    fi
}

run_once() {
    write_pid $$
    trap cleanup EXIT
    exec uv run megobari
}

run_hook() {
    trap cleanup EXIT
    echo "Starting bot in hook mode (restart on git commit)..."
    echo "Set up the hook with: ./run.sh install-hook"
    while true; do
        echo "[$(date '+%H:%M:%S')] Starting bot..."
        write_pid $$
        uv run megobari || true
        echo "[$(date '+%H:%M:%S')] Bot exited, restarting in 1s..."
        sleep 1
    done
}

run_watch() {
    echo "Starting bot in watch mode (restart on .py changes)..."
    write_pid $$
    trap cleanup EXIT
    exec uv run watchfiles --filter python 'megobari' src/
}

install_hook() {
    local hook_path="$SCRIPT_DIR/.git/hooks/post-commit"

    if [ ! -d "$SCRIPT_DIR/.git" ]; then
        echo "Error: not a git repository."
        exit 1
    fi

    mkdir -p "$SCRIPT_DIR/.git/hooks"
    cat > "$hook_path" << 'HOOK'
#!/usr/bin/env bash
# Restart the bot after commit (if running in hook mode)
PIDFILE="$(git rev-parse --show-toplevel)/.megobari/bot.pid"
if [ -f "$PIDFILE" ]; then
    PID=$(cat "$PIDFILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "Restarting bot..."
        kill "$PID"
    fi
fi
HOOK
    chmod +x "$hook_path"
    echo "Installed post-commit hook at $hook_path"
}

# -- Main --

[ $# -lt 1 ] && usage

case "$1" in
    watch)        run_watch ;;
    hook)         run_hook ;;
    once)         run_once ;;
    stop)         stop_bot ;;
    install-hook) install_hook ;;
    *)            usage ;;
esac
