#!/bin/bash

# This script takes a filename as an argument, reads its content,
# and passes it as a prompt to the Gemini agent, along with any other flags.

# --- Safety Check ---
if [ -z "$1" ]; then
  echo "Usage: $0 <path_to_instruction_file> [--interactive | --agentic] [--permissions <level>]"
  exit 1
fi

INSTRUCTION_FILE="$1"
if [ ! -f "$INSTRUCTION_FILE" ]; then
  echo "Error: File not found at '$INSTRUCTION_FILE'"
  exit 1
fi
shift # Remove the filename from the arguments, leaving only the flags

# --- Dynamic Path Setup ---
# Get the absolute path of the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PYTHON_EXEC="$SCRIPT_DIR/venv/bin/python"
AGENT_SCRIPT="$SCRIPT_DIR/gemini_agent.py"

# --- Execution ---
# Read the entire file content into a variable
PROMPT_CONTENT=$(cat "$INSTRUCTION_FILE")

# Run the agent with the file content as the prompt, passing along any other flags
echo "--- Running agent with instructions from '$INSTRUCTION_FILE' ---"
"$PYTHON_EXEC" "$AGENT_SCRIPT" "$PROMPT_CONTENT" "$@"
echo "--- Agent run complete ---"
