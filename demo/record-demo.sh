#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────
# record-demo.sh — Record a terminal demo with asciinema
#
# Usage:
#   ./demo/record-demo.sh              # Record interactive session
#   ./demo/record-demo.sh --play       # Play the recording locally
#   ./demo/record-demo.sh --upload     # Upload to asciinema.org
# ──────────────────────────────────────────────────────────
set -euo pipefail

DEMO_DIR="$(cd "$(dirname "$0")" && pwd)"
CAST_FILE="$DEMO_DIR/flyto-core-demo.cast"
DEMO_URL="${DEMO_URL:-https://github.com/pricing}"

# Colors
BOLD='\033[1m'
CYAN='\033[96m'
RESET='\033[0m'

# ── Helpers ────────────────────────────────────────────────

check_deps() {
    for cmd in asciinema flyto; do
        if ! command -v "$cmd" &>/dev/null; then
            echo "Error: $cmd is required. Install it first."
            exit 1
        fi
    done
}

type_slow() {
    # Simulate typing for demo effect
    local text="$1"
    local delay="${2:-0.04}"
    for ((i = 0; i < ${#text}; i++)); do
        printf '%s' "${text:$i:1}"
        sleep "$delay"
    done
    echo
}

pause() {
    sleep "${1:-1.5}"
}

# ── Demo Script ────────────────────────────────────────────

run_demo() {
    clear
    echo -e "${BOLD}flyto-core demo${RESET} — competitor intel in 12 YAML steps"
    echo
    pause 2

    # Show the recipe
    echo -e "${CYAN}# First, let's look at the recipe:${RESET}"
    pause 0.5
    type_slow "cat src/recipes/competitor-intel.yaml"
    pause 0.5
    cat src/recipes/competitor-intel.yaml
    pause 3

    echo
    echo -e "${CYAN}# Now run it — one command:${RESET}"
    pause 0.5
    type_slow "flyto recipe competitor-intel --url $DEMO_URL"
    pause 0.5
    flyto recipe competitor-intel --url "$DEMO_URL"
    pause 2

    echo
    echo -e "${CYAN}# Check generated files:${RESET}"
    pause 0.5
    type_slow "ls -lh intel-*.png intel-report.json 2>/dev/null || true"
    ls -lh intel-*.png intel-report.json 2>/dev/null || true
    pause 2

    echo
    echo -e "${CYAN}# Peek at the report:${RESET}"
    pause 0.5
    type_slow "head -20 intel-report.json"
    head -20 intel-report.json 2>/dev/null || echo "(no report generated)"
    pause 3

    echo
    echo -e "${BOLD}Done.${RESET} 12 steps, zero Python scripts."
    echo "pip install flyto-core[browser] — https://pypi.org/project/flyto-core/"
    pause 3
}

# ── Main ───────────────────────────────────────────────────

case "${1:-record}" in
    --play|-p)
        if [[ ! -f "$CAST_FILE" ]]; then
            echo "No recording found. Run without flags to record first."
            exit 1
        fi
        asciinema play "$CAST_FILE"
        ;;
    --upload|-u)
        if [[ ! -f "$CAST_FILE" ]]; then
            echo "No recording found. Run without flags to record first."
            exit 1
        fi
        asciinema upload "$CAST_FILE"
        ;;
    *)
        check_deps
        echo -e "${BOLD}Recording demo to:${RESET} $CAST_FILE"
        echo "Press Ctrl-D when the demo finishes."
        echo

        # Record the scripted demo
        asciinema rec \
            --title "flyto-core: 412 modules, trace everything" \
            --cols 100 \
            --rows 30 \
            --command "bash -c '$(declare -f type_slow pause run_demo); DEMO_URL=\"$DEMO_URL\" run_demo'" \
            "$CAST_FILE"

        echo
        echo -e "${BOLD}Saved:${RESET} $CAST_FILE"
        echo "Upload: asciinema upload $CAST_FILE"
        echo "Play:   asciinema play $CAST_FILE"
        ;;
esac
