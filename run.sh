#!/bin/bash
# Flyto Core - Workflow Runner
# Usage: ./run.sh workflow.yaml

cd "$(dirname "$0")"

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is required"
    exit 1
fi

# Install dependencies if needed
if [ ! -d "venv" ] && [ ! -f ".deps_installed" ]; then
    echo "Installing dependencies..."
    pip3 install -r requirements.txt
    touch .deps_installed
fi

# Run
python3 run.py "$@"
