#!/bin/bash

# This script starts the Gemini Distributed Agent.
# It dynamically finds its own directory to locate the virtual environment
# and the main agent script, making it portable.

# --- Dynamic Path Setup ---
# Get the absolute path of the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# --- Environment ---
# Activate the virtual environment if it exists
VENV_PATH="$SCRIPT_DIR/venv"
if [ -d "$VENV_PATH" ]; then
  echo "Activating virtual environment..."
  source "$VENV_PATH/bin/activate"
fi

# --- Execution ---
# The specific command to start the agent might need to be adjusted
# based on the project's entry point.
echo "Starting the Gemini Distributed Agent..."
python -m gemini_agent.main
