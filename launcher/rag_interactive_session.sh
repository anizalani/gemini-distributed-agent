#!/usr/bin/env bash
set -euo pipefail


# --- Sanity checks ---
if [ -z "$1" ]; then
    echo "Usage: $0 <model_name> [prompt] [-o <output_file>]"
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
PROMPT="${2:-}"
OUTPUT_FILE=""
# Basic argument parsing for the output file
if [[ "${3:-}" == "-o" ]]; then
    OUTPUT_FILE="${4:-}"
    if [ -z "$OUTPUT_FILE" ]; then
        echo "Error: Missing output file path for -o option."
        exit 1
    fi
fi
SESSION_ID="rag-$(date +%s)"
REQUEST_PIPE="/tmp/${SESSION_ID}.req"
RESPONSE_PIPE="/tmp/${SESSION_ID}.res"
LOG_FILE="/tmp/rag_session.log"
PYTHON_PID=""



# --- Cleanup ---
cleanup() {
    echo "Cleaning up..."
    # Use pkill to forcefully terminate the entire process group of the Python script
    if [ -n "$PYTHON_PID" ] && ps -p "$PYTHON_PID" > /dev/null; then
        pkill -P "$PYTHON_PID"
        kill "$PYTHON_PID" 2>/dev/null
        wait "$PYTHON_PID" 2>/dev/null
    fi
    # Remove the named pipes
    rm -f "$REQUEST_PIPE" "$RESPONSE_PIPE"
    echo "Cleanup complete."
}

trap cleanup EXIT SIGINT SIGTERM

# --- Main ---
# Create named pipes
mkfifo "$REQUEST_PIPE"
mkfifo "$RESPONSE_PIPE"

# Start the Python RAG CLI in the background
# The python script now handles its own logging.
python -u "$RAG_CLI_SCRIPT" --model "$MODEL_NAME" --session-id "$SESSION_ID" --log-file "$LOG_FILE" &
PYTHON_PID=$!

# Open the response pipe on file descriptor 3 for reading.
exec 3<"$RESPONSE_PIPE"

# --- Interactive UI Setup ---
if [ -z "$PROMPT" ]; then
    clear
    echo "--- Gemini RAG Interactive Session ---"
    echo "Model: $MODEL_NAME"
    echo "Type '/quit' to exit."
    echo "------------------------------------"
    echo 
    echo "Ready. Waiting for user input."
fi

# --- Main Loop ---
if [ -n "$PROMPT" ]; then
    # Non-interactive mode: Send prompt, get one response, and exit.
    echo "$PROMPT" > "$REQUEST_PIPE"

    # Wait for the response from the Python script.
    if read -t 600 -u 3 gemini_response; then
        if [[ "$gemini_response" == "USER_CONFIRMATION_REQUEST:"* ]]; then
            # Handle confirmation requests in non-interactive mode
            response_text="$gemini_response\nCannot confirm in non-interactive mode. To execute, run interactively."
        else
            # Store the clean response
            response_text="$gemini_response"
        fi
    else
        # Handle timeouts or errors
        if ! ps -p "$PYTHON_PID" > /dev/null; then
            response_text="Error: The RAG process died while generating a response. Check the log file: $LOG_FILE"
        else
            response_text="Error: Timeout waiting for a response from the RAG process."
        fi
    fi

    # Output the response to the specified file or to the console
    if [ -n "$OUTPUT_FILE" ]; then
        echo -e "$response_text" > "$OUTPUT_FILE"
        echo "Output written to $OUTPUT_FILE"
    else
        echo -e "$response_text"
    fi
else
    # Interactive mode
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

        # Wait for the response from the Python script
        if read -t 600 -u 3 gemini_response; then
            if [[ "$gemini_response" == "USER_CONFIRMATION_REQUEST:"* ]]; then
                echo "$gemini_response"
                read -p "Do you want to execute this command? (y/n): " user_confirmation
                echo "$user_confirmation" > "$REQUEST_PIPE"

                # Wait for the final response after confirmation
                if read -t 600 -u 3 final_response; then
                    echo "Gemini: $final_response"
                else
                    echo "Error: Timeout waiting for final response after confirmation."
                fi
            else
                echo "Gemini: $gemini_response"
                echo
            fi
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
fi


# Close the file descriptor
exec 3<&-

echo "RAG session ended."
