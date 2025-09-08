#!/bin/bash

# This script creates a symlink to the gembot.sh script to make it accessible
# as a system-wide command.

set -euo pipefail

# --- Paths ---

# Source the .env file to get the project paths
if [ -f "/home/ubuntu/gemini-distributed-agent/.env" ]; then
    . "/home/ubuntu/gemini-distributed-agent/.env"
fi

CODE_DIR="${CODE_DIR:-/home/ubuntu/gemini-distributed-agent}"
GEMBOT_SCRIPT="$CODE_DIR/gembot.sh"
SYMLINK_PATH="/usr/local/bin/gembot"

# --- Main ---

if [ ! -f "$GEMBOT_SCRIPT" ]; then
    echo "Error: gembot.sh script not found at $GEMBOT_SCRIPT"
    exit 1
fi

if [ -L "$SYMLINK_PATH" ]; then
    echo "Symlink already exists at $SYMLINK_PATH"
else
    echo "Creating symlink from $SYMLINK_PATH to $GEMBOT_SCRIPT"
    sudo ln -s "$GEMBOT_SCRIPT" "$SYMLINK_PATH"
    echo "Symlink created successfully."
fi
