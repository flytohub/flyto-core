#!/bin/bash
# Generate the base-runtime lock from pyproject.toml.
# Optional capability extras are intentionally installed from their bounded
# pyproject constraints and are tested by the development extra in CI.
set -eu
"${PYTHON:-python}" -m piptools compile --upgrade --strip-extras --output-file=requirements.lock pyproject.toml
echo "Generated base-runtime requirements.lock"
