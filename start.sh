#!/usr/bin/env bash
# Start AutoTestX (FastAPI backend + React dev server) for local use.
#
#   ./start.sh            check dependencies and ports, start both, Ctrl+C stops both
#   ./start.sh --check    only check dependencies and ports, then exit
#
# Environment (all optional):
#   AUTOTESTX_API_PORT  backend port  (default 8765)
#   AUTOTESTX_UI_PORT   frontend port (default 5173)
#   PYTHON              python interpreter (default python3)
#
# Nothing is installed automatically; missing pieces are reported with the command to fix them.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_PORT="${AUTOTESTX_API_PORT:-8765}"
UI_PORT="${AUTOTESTX_UI_PORT:-5173}"
if [ -z "${PYTHON:-}" ] && [ -x "$ROOT/.venv/bin/python" ]; then
    PYTHON="$ROOT/.venv/bin/python"
else
    PYTHON="${PYTHON:-python3}"
fi
RUN_DIR="$ROOT/.run"
CHECK_ONLY=0
[ "${1:-}" = "--check" ] && CHECK_ONLY=1

red()   { printf '\033[31m%s\033[0m\n' "$*" >&2; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
ERRORS=0
fail()  { red "  [missing] $*"; ERRORS=$((ERRORS + 1)); }
ok()    { echo "  [ok] $*"; }

echo "AutoTestX: checking environment (project: $ROOT)"

# ---- tools
for tool in perl tclsh iverilog vvp node npm lsof curl; do
    if command -v "$tool" >/dev/null 2>&1; then ok "$tool"; else
        case "$tool" in
            iverilog|vvp) fail "$tool  ->  brew install icarus-verilog" ;;
            node|npm)     fail "$tool  ->  install Node.js (https://nodejs.org or: brew install node)" ;;
            tclsh)        fail "tclsh  ->  install Tcl (macOS ships it; or: brew install tcl-tk)" ;;
            *)            fail "$tool" ;;
        esac
    fi
done

# ---- python and its packages
if command -v "$PYTHON" >/dev/null 2>&1; then
    ok "$PYTHON ($("$PYTHON" --version 2>&1))"
    missing_mods="$("$PYTHON" - <<'PY' 2>/dev/null
import importlib
mods = {"yaml": "PyYAML", "sklearn": "scikit-learn", "joblib": "joblib", "fastapi": "fastapi", "uvicorn": "uvicorn"}
print(" ".join(pkg for mod, pkg in mods.items() if importlib.util.find_spec(mod) is None))
PY
)"
    if [ -n "$missing_mods" ]; then
        fail "python packages: $missing_mods  ->  $PYTHON -m pip install -r requirements.txt"
    else
        ok "python packages (PyYAML, scikit-learn, joblib, fastapi, uvicorn)"
    fi
else
    fail "$PYTHON not found (set PYTHON=/path/to/python3)"
fi

# ---- frontend packages
if [ -d "$ROOT/frontend/node_modules" ] && [ -x "$ROOT/frontend/node_modules/.bin/vite" ]; then
    ok "frontend/node_modules"
else
    fail "frontend dependencies  ->  cd frontend && npm install   (about 130 MB, project-local)"
fi

# ---- ports
port_owner() { lsof -nP -iTCP:"$1" -sTCP:LISTEN 2>/dev/null | awk 'NR==2 {print $1" (pid "$2")"}'; }
if command -v lsof >/dev/null 2>&1; then
    for spec in "backend:$API_PORT:AUTOTESTX_API_PORT" "frontend:$UI_PORT:AUTOTESTX_UI_PORT"; do
        name="${spec%%:*}"; rest="${spec#*:}"; port="${rest%%:*}"; var="${rest#*:}"
        owner="$(port_owner "$port")"
        if [ -n "$owner" ]; then
            fail "port $port ($name) is already in use by $owner  ->  stop it, or run with $var=<other port>"
        else
            ok "port $port ($name) is free"
        fi
    done
fi

# ---- advisory (non-fatal)
[ -f "$ROOT/models/log_classifier.joblib" ] || echo "  [note] no trained ML model yet: run  PYTHONPATH=src $PYTHON -m autotestx evaluate-ml --out reports/ml_evaluation.json"
[ -f "$ROOT/reports/ml_evaluation.json" ]   || echo "  [note] no saved ML evaluation: the ML page will ask you to create one"

if [ "$ERRORS" -gt 0 ]; then
    red "$ERRORS problem(s) found. Fix them and run ./start.sh again."
    exit 1
fi
green "Environment OK."
[ "$CHECK_ONLY" = 1 ] && exit 0

# ---- start (each child in its own process group so Ctrl+C can stop whole trees)
mkdir -p "$RUN_DIR"
set -m
API_PID=""; UI_PID=""
cleanup() {
    trap '' INT TERM
    set +m 2>/dev/null
    echo; echo "Stopping AutoTestX..."
    for pid in $UI_PID $API_PID; do
        [ -n "$pid" ] && kill -TERM -- "-$pid" 2>/dev/null
    done
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        alive=0
        for pid in $UI_PID $API_PID; do [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null && alive=1; done
        [ "$alive" = 0 ] && break
        sleep 0.5
    done
    for pid in $UI_PID $API_PID; do
        [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null && kill -KILL -- "-$pid" 2>/dev/null
    done
    echo "Stopped."
    exit 0
}
trap cleanup INT TERM

cd "$ROOT" || exit 1
PYTHONPATH="$ROOT/src" "$PYTHON" -u -m autotestx.web "$API_PORT" >"$RUN_DIR/backend.log" 2>&1 &
API_PID=$!
echo "Starting backend on 127.0.0.1:$API_PORT ..."
for _ in $(seq 1 30); do
    curl -fs "http://127.0.0.1:$API_PORT/api/health" >/dev/null 2>&1 && break
    kill -0 "$API_PID" 2>/dev/null || { red "Backend exited. See $RUN_DIR/backend.log"; tail -n 15 "$RUN_DIR/backend.log" >&2; exit 1; }
    sleep 0.5
done
curl -fs "http://127.0.0.1:$API_PORT/api/health" >/dev/null 2>&1 || { red "Backend did not become healthy. See $RUN_DIR/backend.log"; cleanup; }

(cd "$ROOT/frontend" && AUTOTESTX_API_PORT="$API_PORT" exec npm run dev -- --port "$UI_PORT" --strictPort) >"$RUN_DIR/frontend.log" 2>&1 &
UI_PID=$!
echo "Starting frontend on 127.0.0.1:$UI_PORT ..."
for _ in $(seq 1 40); do
    curl -fs "http://127.0.0.1:$UI_PORT/" >/dev/null 2>&1 && break
    kill -0 "$UI_PID" 2>/dev/null || { red "Frontend exited. See $RUN_DIR/frontend.log"; tail -n 15 "$RUN_DIR/frontend.log" >&2; cleanup; }
    sleep 0.5
done

echo
green "AutoTestX is running."
echo "  Open:     http://127.0.0.1:$UI_PORT"
echo "  API docs: http://127.0.0.1:$API_PORT/docs"
echo "  Logs:     $RUN_DIR/backend.log, $RUN_DIR/frontend.log"
echo "  Stop:     press Ctrl+C in this terminal"

while kill -0 "$API_PID" 2>/dev/null && kill -0 "$UI_PID" 2>/dev/null; do sleep 1; done
red "A server process exited unexpectedly (see $RUN_DIR/*.log)."
cleanup
