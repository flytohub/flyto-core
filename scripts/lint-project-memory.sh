#!/usr/bin/env bash
set -euo pipefail

script_dir="$(dirname "${BASH_SOURCE[0]}")"
root="$(git -C "$script_dir/.." rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$root" ]]; then
  root="$script_dir/.."
fi

grep_bin="$(command -v grep || true)"
find_bin="$(command -v find || true)"
[[ -n "$grep_bin" ]] || grep_bin="/usr/bin/grep"
[[ -n "$find_bin" ]] || find_bin="/usr/bin/find"

fail() {
  echo "project-memory lint: $*" >&2
  exit 1
}

required_files=(
  AGENTS.md
  CLAUDE.md
  PROJECT.md
  ARCHITECTURE.md
  STATE.md
  ROADMAP.md
  tasks.md
  DECISIONS.md
  CHANGELOG.md
  docs/README.md
  docs/architecture-map.md
  workflows/README.md
  workflows/idea-capture.md
  workflows/planning.md
  workflows/implementation.md
  workflows/bugfix.md
  workflows/refactor.md
  workflows/investigation.md
  workflows/wrap-up.md
  handoffs/_registry.md
  handoffs/2026-06-21-project-memory-bootstrap.md
)

for rel in "${required_files[@]}"; do
  [[ -f "$root/$rel" ]] || fail "missing required file: $rel"
done

for dir in docs workflows handoffs; do
  [[ -d "$root/$dir" ]] || fail "missing required directory: $dir"
done

"$grep_bin" -qE '^## Current State$' "$root/STATE.md" || fail "STATE.md missing ## Current State"
"$grep_bin" -qE '^## Release Blockers$' "$root/STATE.md" || fail "STATE.md missing ## Release Blockers"
"$grep_bin" -qE '^## Verification Matrix$' "$root/STATE.md" || fail "STATE.md missing ## Verification Matrix"
"$grep_bin" -qE '^## Boundaries$' "$root/ARCHITECTURE.md" || fail "ARCHITECTURE.md missing ## Boundaries"
"$grep_bin" -qE '^## Data Flow$' "$root/ARCHITECTURE.md" || fail "ARCHITECTURE.md missing ## Data Flow"
"$grep_bin" -qE '^## Deployment / Edition$' "$root/ARCHITECTURE.md" || fail "ARCHITECTURE.md missing ## Deployment / Edition"
"$grep_bin" -qE '^## Trust Boundary$' "$root/ARCHITECTURE.md" || fail "ARCHITECTURE.md missing ## Trust Boundary"
"$grep_bin" -q '2026-06-21-project-memory-bootstrap.md' "$root/handoffs/_registry.md" || fail "handoffs/_registry.md missing bootstrap handoff"

secret_files=(
  "$root/AGENTS.md"
  "$root/CLAUDE.md"
  "$root/PROJECT.md"
  "$root/ARCHITECTURE.md"
  "$root/STATE.md"
  "$root/ROADMAP.md"
  "$root/tasks.md"
  "$root/DECISIONS.md"
)
while IFS= read -r -d '' file; do
  secret_files+=("$file")
done < <("$find_bin" "$root/workflows" "$root/handoffs" -type f -name '*.md' -print0)

tmp="${TMPDIR:-/tmp}/project-memory-secrets.$$"
trap 'rm -f "$tmp"' EXIT
secret_pattern='(-----BEGIN [A-Z ]*PRIVATE KEY-----|"private_key"[[:space:]]*:|"client_email"[[:space:]]*:|sk-[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{20,}|ghp_[0-9A-Za-z_]{20,}|glpat-[0-9A-Za-z_-]{20,}|xox[baprs]-[0-9A-Za-z-]{20,})'
if "$grep_bin" -nE "$secret_pattern" "${secret_files[@]}" >"$tmp"; then
  cat "$tmp" >&2
  fail "secret-like material found in project memory docs"
fi

echo "project-memory lint: PASS"
