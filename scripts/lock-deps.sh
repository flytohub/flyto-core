#!/bin/bash
# Generate locked requirements from pyproject.toml
# Requires: pip-tools (pip install pip-tools)
set -e
pip-compile --output-file=requirements.lock pyproject.toml
echo "Generated requirements.lock"
