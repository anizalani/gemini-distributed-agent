#!/bin/bash
#
# Gemini CLI Wrapped Launcher
#
# This script acts as a wrapper for the Gemini CLI, integrating it with
# the distributed agent database backend for context, logging, and API key management.
#

set -e

# --- Configuration ---

# Dynamically determine the absolute path of the script's directory
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
PROJECT_ROOT=$(cd -- "$SCRIPT_DIR/.." &> /dev/null && pwd) # Assumes this script is in a subdir of the project root

# --- Argument Parsing ---

if [ -z "$1" ]; then
  echo "Usage: $0 <task_id> [mode]"
  echo "Example: $0 task-20250728-alpha interactive"
  exit 1
fi

TASK_ID="$1"
MODE="${2:-interactive}" # Default to 'interactive' if not provided

echo "--- LAUNCHER: Initializing Task [$TASK_ID] in [$MODE] mode ---"

# --- Environment Setup ---

# Load environment variables from the central config
CONFIG_PATH="$SCRIPT_DIR/config/.env"
if [ -f "$CONFIG_PATH" ]; then
  echo "LAUCHER: Loading environment from $CONFIG_PATH"
  source "$CONFIG_PATH"
else
  echo "LAUNCHER: Warning - Configuration file not found at $CONFIG_PATH"
fi

# --- Backend Integration ---

# 1. Select the next available API key from the database
echo "LAUNCHER: Selecting API key..."
GEMINI_API_KEY=$($PROJECT_ROOT/.venv/bin/python "$SCRIPT_DIR/scripts/select_key.py")
export GEMINI_API_KEY
echo "LAUNCHER: Using key ending in ${GEMINI_API_KEY: -4}"

# 2. Populate context from previous sessions or related tasks
echo "LAUNCHER: Populating context..."
# python3 "$SCRIPT_DIR/scripts/populate_context.py" --task_id "$TASK_ID"
echo "LAUNCHER: (Skipped - populate_context.py not implemented)" # Placeholder

# --- Gemini CLI Execution ---

# Check if the gemini command exists
if ! command -v gemini &> /dev/null; then
    echo "LAUNCHER: ERROR - The 'gemini' command was not found."
    echo "Please ensure the @google/gemini-cli is installed globally (e.g., 'npm install -g @google/gemini-cli')."
    exit 1
fi

echo "LAUNCHER: Starting Gemini CLI. Use Ctrl+D or type 'exit' to end session."
echo "---------------------------------------------------------------------"

# Launch the interactive Gemini CLI shell
# When the user exits the shell, the script will continue.
gemini

echo "---------------------------------------------------------------------"
echo "LAUNCHER: Gemini CLI session ended."

# --- Post-Session Logging ---

echo "LAUNCHER: Logging session details to database..."
# python3 "$SCRIPT_DIR/scripts/log_session.py" --task_id "$TASK_ID"
echo "LAUNCHER: (Skipped - log_session.py not implemented)" # Placeholder

echo "--- LAUNCHER: Task [$TASK_ID] finished ---"
