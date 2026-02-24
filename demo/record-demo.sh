#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────
# record-demo.sh — Record a terminal demo with asciinema
#
# Usage:
#   ./demo/record-demo.sh              # Record the demo
#   ./demo/record-demo.sh --play       # Play the recording
#   ./demo/record-demo.sh --upload     # Upload to asciinema.org
#   ./demo/record-demo.sh --dry-run    # Run demo without recording
# ──────────────────────────────────────────────────────────
set -uo pipefail

DEMO_DIR="$(cd "$(dirname "$0")" && pwd)"
CAST_FILE="$DEMO_DIR/flyto-core-demo.cast"

# Colors
BOLD='\033[1m'
DIM='\033[2m'
CYAN='\033[96m'
GREEN='\033[92m'
RESET='\033[0m'

# ── Helpers ────────────────────────────────────────────────

type_cmd() {
    # Simulate typing a command, then run it
    local cmd="$1"
    printf '$ '
    for ((i = 0; i < ${#cmd}; i++)); do
        printf '%s' "${cmd:$i:1}"
        sleep 0.03
    done
    echo
    sleep 0.3
    eval "$cmd" || true
}

pause() { sleep "${1:-1.5}"; }

separator() {
    echo
    echo -e "${DIM}────────────────────────────────────────${RESET}"
    echo
}

# ── Demo Script ────────────────────────────────────────────

run_demo() {
    export FLYTO_SANDBOX_DIR="$PWD"
    clear
    echo -e "${BOLD}flyto-core${RESET} — 412 modules, trace every step, replay from any point"
    echo
    pause 2

    # ── Part 1: API Pipeline (no browser needed)
    echo -e "${CYAN}# 1. Fetch GitHub user data in 5 steps — no code, just YAML${RESET}"
    pause 1

    type_cmd "flyto recipe api-pipeline --username torvalds"
    pause 2

    separator

    echo -e "${CYAN}# Check the output:${RESET}"
    pause 0.5
    type_cmd "grep -E '\"(username|name|company|location|followers|top_repos)\"' github-profile.json | head -6"
    pause 2

    separator

    # ── Part 2: Replay
    echo -e "${CYAN}# 2. Now replay from step 3 — skip the API calls, reuse cached data${RESET}"
    pause 1

    type_cmd "flyto replay --from-step build_report"
    pause 2

    separator

    echo -e "${CYAN}# Steps 1-2 skipped (HTTP calls). Steps 3-5 re-ran instantly.${RESET}"
    echo -e "${CYAN}# If step 3 had failed, you'd fix the bug and replay — no re-fetching.${RESET}"
    pause 3

    separator

    # ── Part 3: Browser automation (the wow factor)
    echo -e "${CYAN}# 3. Browser automation: competitor intel in 12 YAML steps${RESET}"
    pause 1

    type_cmd "flyto recipe competitor-intel --url https://github.com/pricing"
    pause 2

    separator

    echo -e "${CYAN}# Generated: screenshots + performance metrics + JSON report${RESET}"
    pause 0.5
    type_cmd "ls -lh intel-desktop.png intel-mobile.png intel-report.json"
    pause 2

    separator

    echo -e "${BOLD}pip install flyto-core${RESET}"
    echo -e "412 modules. Trace every step. Replay from any point."
    echo -e "https://github.com/flytohub/flyto-core"
    pause 4
}

# ── Main ───────────────────────────────────────────────────

case "${1:-record}" in
    --play|-p)
        [[ -f "$CAST_FILE" ]] || { echo "No recording. Run without flags first."; exit 1; }
        asciinema play "$CAST_FILE"
        ;;
    --upload|-u)
        [[ -f "$CAST_FILE" ]] || { echo "No recording. Run without flags first."; exit 1; }
        asciinema upload "$CAST_FILE"
        ;;
    --dry-run|-d)
        export BOLD DIM CYAN GREEN RESET
        run_demo
        ;;
    *)
        # Check dependencies
        for cmd in asciinema flyto; do
            command -v "$cmd" &>/dev/null || { echo "Error: $cmd required."; exit 1; }
        done

        echo -e "${BOLD}Recording to:${RESET} $CAST_FILE"
        echo

        # Export functions and vars for subshell
        export BOLD DIM CYAN GREEN RESET
        export -f type_cmd pause separator run_demo

        asciinema rec \
            --title "flyto-core: 412 modules, trace everything, replay from any point" \
            --cols 90 \
            --rows 32 \
            --command "bash -c 'run_demo'" \
            --overwrite \
            "$CAST_FILE"

        echo
        echo -e "${BOLD}Done.${RESET} Upload: asciinema upload $CAST_FILE"
        ;;
esac
