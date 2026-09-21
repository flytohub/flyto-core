#!/bin/bash
# Reconcile the base-runtime lock with pyproject.toml without floating pins.
# Optional capability extras are intentionally installed from their bounded
# pyproject constraints and are tested by the development extra in CI.
set -eu
if [ "$#" -gt 1 ] || { [ "$#" -eq 1 ] && [ "$1" != "--upgrade" ]; }; then
    echo "Usage: $0 [--upgrade]" >&2
    exit 2
fi
# pip-compile reuses an existing lock unless explicitly asked to upgrade.
# Omit its interpreter-version header so supported Python minors do not
# change an otherwise identical dependency lock.
"${PYTHON:-python}" -m piptools compile "$@" --no-header --strip-extras --output-file=requirements.lock pyproject.toml
echo "Generated base-runtime requirements.lock"
