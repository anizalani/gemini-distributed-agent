#!/usr/bin/env bash
set -euo pipefail

# --- Paths ---
CODE_DIR="/srv/gemini"                     # Python code + venv + requirements.txt
WORKSPACE_DIR="/srv/gemini_workspace"      # project working directory
ENV_FILE="$CODE_DIR/launcher/config/.env"  # keep env here per your setup
LAUNCHER="$CODE_DIR/launcher/launch_gemini_task.sh"

# --- Args: allow mode-only or task+mode ---
KNOWN_MODES="interactive debug headless"
ARG1="${1:-}"
ARG2="${2:-}"
DEFAULT_TASK_ID="$(TZ=America/Chicago date +%F-%H%M)"

if [[ -n "$ARG1" && " $KNOWN_MODES " == *" $ARG1 "* ]]; then
  TASK_ID="$DEFAULT_TASK_ID"
  MODE="$ARG1"
else
  TASK_ID="${ARG1:-$DEFAULT_TASK_ID}"
  MODE="${ARG2:-interactive}"
fi

# --- Sanity checks ---
[[ -x "$LAUNCHER" ]] || { echo "Launcher not found/executable: $LAUNCHER"; exit 1; }
[[ -f "$CODE_DIR/requirements.txt" ]] || { echo "requirements.txt missing in $CODE_DIR"; exit 1; }
[[ -f "$ENV_FILE" ]] || { echo "Env file missing: $ENV_FILE"; exit 1; }

# --- Python env setup (lives in CODE_DIR) ---
cd "$CODE_DIR"
if [[ ! -d "venv" ]]; then
  python3 -m venv venv
fi
# shellcheck disable=SC1091
source venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt

# --- Load & export env (so libpq sees PG*/DATABASE_URL) ---
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

# Be explicit (belt & suspenders)
export PGHOST="${PGHOST:-localhost}"
export PGPORT="${PGPORT:-5432}"
export PGDATABASE="${PGDATABASE:-gemini_agents}"
export PGUSER="${PGUSER:-gemini_user}"
export PGPASSWORD="${PGPASSWORD:-}"
export DATABASE_URL="${DATABASE_URL:-}"

# --- Switch to workspace as the project folder, then run launcher (from CODE_DIR) ---
cd "$WORKSPACE_DIR"
if [[ -n "$MODE" ]]; then
  "$LAUNCHER" "$TASK_ID" "$MODE"
else
  "$LAUNCHER" "$TASK_ID"
fi
