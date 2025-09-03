#!/usr/bin/env bash
set -euo pipefail


# --- Sanity checks ---
if [ -z "$1" ]; then
    echo "Usage: $0 <model_name>"
    exit 1
fi

# --- Paths ---
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
CODE_DIR="$(dirname "$SCRIPT_DIR")"
RAG_CLI_SCRIPT="$CODE_DIR/scripts/rag_interactive.py"
# shellcheck disable=SC1091
source "$CODE_DIR/venv/bin/activate"

# --- Variables ---
MODEL_NAME="$1"
SESSION_ID="rag-$(date +%s)"
REQUEST_PIPE="/tmp/${SESSION_ID}.req"
RESPONSE_PIPE="/tmp/${SESSION_ID}.res"
LOG_FILE="$CODE_DIR/logs/rag_session.log"
PYTHON_PID=""



# --- Cleanup ---
cleanup() {
    echo "Cleaning up..."
    # Kill the background Python process
    if [ -n "$PYTHON_PID" ] && ps -p "$PYTHON_PID" > /dev/null; then
        kill "$PYTHON_PID" 2>/dev/null
    fi
    # Remove the named pipes
    rm -f "$REQUEST_PIPE" "$RESPONSE_PIPE"
    # Clear the status bar
    tput cup "$(tput lines)" 0
    tput el
    echo "Cleanup complete."
}

trap cleanup EXIT SIGINT SIGTERM

# --- Main ---
# Create named pipes
mkfifo "$REQUEST_PIPE"
mkfifo "$RESPONSE_PIPE"

# Start the Python RAG CLI in the background
python -u "$RAG_CLI_SCRIPT" --model "$MODEL_NAME" --session-id "$SESSION_ID" > >(tee -a "$LOG_FILE") 2>&1 &
PYTHON_PID=$!

# Open the response pipe on file descriptor 3 for reading.
# This will block until the Python script opens it for writing,
# effectively synchronizing the two processes.
exec 3<"$RESPONSE_PIPE"

# --- Interactive UI Setup ---
clear
echo "--- Gemini RAG Interactive Session ---"
echo "Model: $MODEL_NAME"
echo "Type '/quit' to exit."
echo "------------------------------------"
echo 
echo "Ready. Waiting for user input."

# --- Interactive Loop ---
while true; do
    printf "You: "
    read -r user_input

    if [[ "$user_input" == "/quit" ]]; then
        echo "Exiting RAG session."
        break
    fi

    # Send input to the Python script
    echo "$user_input" > "$REQUEST_PIPE"

    echo "Gemini is thinking..."

    # Check if the background process is still running before waiting for a response
    if ! ps -p "$PYTHON_PID" > /dev/null; then
        echo "Error: The RAG process died unexpectedly. Check the log file: $LOG_FILE"
        break
    fi

    # Wait for the response from the Python script with a 60-second timeout
    # Read from file descriptor 3, which is connected to the response pipe
    if read -t 60 -u 3 gemini_response; then
        echo "Gemini: $gemini_response"
        echo
    else
        # This block will be executed if the read times out or fails
        if ps -p "$PYTHON_PID" > /dev/null; then
            echo "Error: Timeout waiting for a response from the RAG process."
        else
            echo "Error: The RAG process died while generating a response. Check the log file: $LOG_FILE"
            break
        fi
    fi
done

# Close the file descriptor
exec 3<&-

echo "RAG session ended."
