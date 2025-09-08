#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# --- Argument Parsing ---
DIRECT_MODE=""
DIRECT_MODEL=""

usage() {
    echo "Usage: $0 [-r] [-i] [-h] [-c] [-a] [-m <model_name>] [-d | --default]"
    echo "  -r: Run in RAG Interactive Mode"
    echo "  -i: Run in Interactive Mode"
    echo "  -h: Run in Headless Mode"
    echo "  -c: Run in Context-Aware Mode"
    echo "  -a: Run in Agentic Mode"
    echo "  -m <model_name>: Specify Gemini model (e.g., gemini-2.5-flash, gemini-2.5-pro). Required for -r and -i."
    echo "  -d, --default: Run in Interactive Mode with gemini-2.5-pro."
    exit 1
}

while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
        -r)
        DIRECT_MODE="rag_interactive"
        shift # past argument
        ;;
        -i)
        DIRECT_MODE="interactive"
        shift # past argument
        ;;
        -h)
        DIRECT_MODE="headless"
        shift # past argument
        ;;
        -c)
        DIRECT_MODE="context"
        shift # past argument
        ;;
        -a)
        DIRECT_MODE="agentic"
        shift # past argument
        ;;
        -m)
        if [[ -n "$2" ]]; then
            DIRECT_MODEL="$2"
            shift # past argument
            shift # past value
        else
            echo "Error: -m requires an argument."
            usage
        fi
        ;;
        -d|--default)
        DIRECT_MODE="interactive"
        DIRECT_MODEL="gemini-2.5-pro"
        shift # past argument
        ;;
        *)    # unknown option
        usage
        ;;
    esac
done

if [[ -n "$DIRECT_MODE" ]]; then
    if [[ ("$DIRECT_MODE" == "rag_interactive" || "$DIRECT_MODE" == "interactive") && -z "$DIRECT_MODEL" ]]; then
        echo "Error: -m <model_name> is required for $DIRECT_MODE mode."
        usage
    fi
    if [[ ("$DIRECT_MODE" == "headless" || "$DIRECT_MODE" == "context" || "$DIRECT_MODE" == "agentic") && -n "$DIRECT_MODEL" ]]; then
        echo "Warning: -m <model_name> is not applicable for $DIRECT_MODE mode and will be ignored."
    fi
fi

if [[ $EUID -ne 0 ]]; then
  echo "This script needs to run with root privileges to access certain directories."
  echo "Attempting to re-run with sudo..."
  exec sudo -E "$0" "$@"
fi

# --- Paths ---
CODE_DIR="${CODE_DIR:-/home/ubuntu/gemini-distributed-agent}"
export CODE_DIR
WORKSPACE_DIR="${GEMINI_WORKSPACE:-/home/ubuntu/gemini_workspace}"
ENV_FILE="$CODE_DIR/.postgres.env"
LAUNCHER="$CODE_DIR/launcher/launch_gemini_task.sh"
WEB_UI_SCRIPT="$CODE_DIR/web_ui.py"
PID_FILE="$CODE_DIR/logs/web_ui.pid"


# --- Symlink Setup ---
# Create /srv if it doesn't exist
mkdir -p /srv

# Symlink directories if they don't exist
if [ ! -L "/srv/countrycat" ]; then
    ln -s "/home/ubuntu/countrycat" "/srv/countrycat"
fi
if [ ! -L "/srv/gemini-distributed-agent" ]; then
    ln -s "/home/ubuntu/gemini-distributed-agent" "/srv/gemini-distributed-agent"
fi
if [ ! -L "/srv/gemini_workspace" ]; then
    ln -s "/home/ubuntu/gemini_workspace" "/srv/gemini_workspace"
fi

# --- Sanity checks ---
[[ -x "$LAUNCHER" ]] || { echo "Launcher not found/executable: $LAUNCHER"; exit 1; }
[[ -f "$CODE_DIR/requirements.txt" ]] || { echo "requirements.txt missing in $CODE_DIR"; exit 1; }
[[ -f "$ENV_FILE" ]] || { echo "Env file missing: $ENV_FILE"; exit 1; }

# --- Python env setup (lives in CODE_DIR) ---
echo "Performing one-time setup..."
cd "$CODE_DIR"
if [[ ! -d "venv" ]]; then
  python3 -m venv venv
fi
# shellcheck disable=SC1091
source venv/bin/activate

pip install --upgrade pip >/dev/null 2>&1
pip install -r requirements.txt >/dev/null 2>&1
npm install >/dev/null 2>&1
npm install -g @google/gemini-cli >/dev/null 2>&1
echo "Setup complete."

# --- Load & export env (so libpq sees PG*/DATABASE_URL) ---
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

# --- Export API keys ---
echo "Exporting API keys from database..."
python3 /srv/gemini/export_keys.py

# --- API Key Configuration ---
LLM_CONFIG_FILE="/srv/gemini/llm_platform_config.json"

if [ -f "$LLM_CONFIG_FILE" ]; then
    # Use jq to extract a specific key-value pair from the gemini object,
    # then export the value as GEMINI_API_KEY.
    GEMINI_API_KEY=$(jq -r '.gemini."gemini-cli-aniz-5"' "$LLM_CONFIG_FILE")
    export GEMINI_API_KEY

    if [ -z "$GEMINI_API_KEY" ]; then
        echo "Error: Could not extract GEMINI_API_KEY from $LLM_CONFIG_FILE."
        exit 1
    fi
else
    echo "Error: LLM config file not found at $LLM_CONFIG_FILE."
    exit 1
fi


# Be explicit (belt & suspenders)
PGHOST="${POSTGRES_HOST:-localhost}"
PGPORT="${POSTGRES_PORT:-5432}"
PGDATABASE="${POSTGRES_DB:-gemini_agents}"
PGUSER="${POSTGRES_USER:-gemini_user}"
PGPASSWORD="${POSTGRES_PASSWORD:-}"
DATABASE_URL="${DATABASE_URL:-}"

# Export these variables for child processes, especially for RAG interactive mode
export PGHOST PGPORT PGDATABASE PGUSER PGPASSWORD DATABASE_URL

# --- Manage Web UI process ---
WEB_UI_SCRIPT="/srv/gemini/web_ui.py"
PID_FILE="$CODE_DIR/logs/web_ui.pid"

# Check if a process is already running and kill it
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null; then
        echo "Web UI is running (PID: $PID). Terminating..."
        sudo kill "$PID"
        # Wait for the process to terminate
        while ps -p "$PID" > /dev/null; do sleep 1; done
        echo "Web UI terminated."
    else
        echo "Found a stale PID file. Removing it."
        sudo rm "$PID_FILE"
    fi
fi

# Start the Web UI
echo "Starting Web UI..."
nohup "$CODE_DIR/venv/bin/python" "$WEB_UI_SCRIPT" > "$CODE_DIR/logs/web_ui.log" 2>&1 &
# Store the new PID
echo $! | sudo tee "$PID_FILE" > /dev/null
echo "Web UI started (PID: $(cat "$PID_FILE"))."



# --- Switch to workspace as the project folder ---
cd "$WORKSPACE_DIR"

# --- Main Menu Loop ---
if [[ -n "$DIRECT_MODE" ]]; then
    TASK_ID="$(TZ=America/Chicago date +%F-%H%M)"
    case "$DIRECT_MODE" in
        "rag_interactive")
            "$CODE_DIR/launcher/rag_interactive_session.sh" "$DIRECT_MODEL"
            ;;
        "interactive")
            "$LAUNCHER" "$TASK_ID" "interactive" "$DIRECT_MODEL"
            ;;
        "headless")
            "$LAUNCHER" "$TASK_ID" "headless"
            ;;
        "context")
            "$LAUNCHER" "$TASK_ID" "context"
            ;;
        "agentic")
            "$LAUNCHER" "$TASK_ID" "agentic"
            ;;
        *)
            echo "Invalid direct mode: $DIRECT_MODE"
            exit 1
            ;;
    esac
    exit 0
fi

while true; do
    echo
    echo "--- Gemini Gembot Menu ---"
    options=(
        "Interactive Mode: Default, for direct interaction."
        "Headless Mode: For single-shot commands."
        "Context-Aware Mode: Interactive session with all files in the current directory as context."
        "Agentic Mode: Autonomous execution of a prompt."
        "RAG Interactive Mode: Interactive session with database-augmented context."
        "Quit"
    )
    select opt in "${options[@]}"; do
        # Regenerate TASK_ID for each new command
        TASK_ID="$(TZ=America/Chicago date +%F-%H%M)"

        case $opt in
            "Interactive Mode: Default, for direct interaction.")
                echo
                echo "--- Choose Gemini Model ---"
                model_options=(
                    "gemini-2.5-flash"
                    "gemini-2.5-pro"
                )
                select model_opt in "${model_options[@]}"; do
                    case $model_opt in
                        "gemini-2.5-flash")
                            "$LAUNCHER" "$TASK_ID" "interactive" "gemini-2.5-flash"
                            break
                            ;;
                        "gemini-2.5-pro")
                            "$LAUNCHER" "$TASK_ID" "interactive" "gemini-2.5-pro"
                            break
                            ;;
                        *)
                            echo "Invalid option $REPLY. Please try again."
                            ;;
                    esac
                done
                break
                ;;
            "Headless Mode: For single-shot commands.")
                "$LAUNCHER" "$TASK_ID" "headless"
                break
                ;;
            "Context-Aware Mode: Interactive session with all files in the current directory as context.")
                "$LAUNCHER" "$TASK_ID" "context"
                break
                ;;
            "Agentic Mode: Autonomous execution of a prompt.")
                "$LAUNCHER" "$TASK_ID" "agentic"
                break
                ;;
            "RAG Interactive Mode: Interactive session with database-augmented context.")
                echo
                echo "--- Choose Gemini Model for RAG Session ---"
                model_options=(
                    "gemini-2.5-flash"
                    "gemini-2.5-pro"
                )
                select model_opt in "${model_options[@]}"; do
                    case $model_opt in
                        "gemini-2.5-flash")
                            "$CODE_DIR/launcher/rag_interactive_session.sh" "gemini-2.5-flash"
                            break
                            ;;
                        "gemini-2.5-pro")
                            "$CODE_DIR/launcher/rag_interactive_session.sh" "gemini-2.5-pro"
                            break
                            ;;
                        *)
                            echo "Invalid option $REPLY. Please try again."
                            ;;
                    esac
                done
                break
                ;;
            "Quit")
                echo "Exiting."
                exit 0
                ;;
            *)
                if [[ "$REPLY" == "/quit" ]]; then
                    echo "Exiting."
                    exit 0
                fi
                echo "Invalid option $REPLY. Please try again."
                break
                ;;
        esac
    done
done
