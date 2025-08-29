#!/bin/bash
#
# Gemini CLI Wrapped Launcher
# - Loads env from config/.env
# - Selects API key via select_key.py and shows masked details
# - Ensures @google/gemini-cli is installed and up to date
# - Starts the gemini CLI
#

set -euo pipefail

# --- Helpers ---

mask_key() {
  local k="${1:-}"; local n=${#k}
  if (( n < 8 )); then
    printf '[key too short]'
  else
    printf '%s…%s (len=%d)' "${k:0:4}" "${k: -4}" "$n"
  fi
}

log() { echo "LAUNCHER: $*"; }

have_cmd() { command -v "$1" >/dev/null 2>&1; }

installed_gemini_version() {
  # Prefer the binary's --version if available
  if have_cmd gemini; then
    gemini --version 2>/dev/null | head -n1 | sed -E 's/[^0-9]*([0-9]+\.[0-9]+\.[0-9]+).*/\1/' || true
    return
  fi
  # Fallback: parse npm list (global)
  if have_cmd npm; then
    npm list -g @google/gemini-cli --depth=0 2>/dev/null \
      | sed -nE 's/.*@google\/gemini-cli@([0-9]+\.[0-9]+\.[0-9]+).*/\1/p' || true
    return
  fi
  echo ""
}

latest_gemini_version() {
  # Query npm registry for latest
  if have_cmd npm; then
    npm view @google/gemini-cli version 2>/dev/null || true
  else
    echo ""
  fi
}

ensure_gemini_cli_latest() {
  if ! have_cmd npm; then
    log "ERROR - npm is not installed. Please install Node.js & npm (needed for @google/gemini-cli)."
    exit 1
  fi

  local installed latest newest
  installed="$(installed_gemini_version)"
  latest="$(latest_gemini_version)"

  if [[ -z "$installed" && -z "$latest" ]]; then
    # No npm and/or network issue fetching latest
    log "'gemini' not found and could not determine latest version. Attempting install of @google/gemini-cli@latest…"
    npm install -g @google/gemini-cli
    return
  fi

  if [[ -z "$installed" ]]; then
    log "'gemini' CLI not found. Installing @google/gemini-cli@latest (${latest:-unknown})…"
    npm install -g @google/gemini-cli@latest
    return
  fi

  if [[ -z "$latest" ]]; then
    log "Installed gemini-cli v$installed; unable to check latest (network/registry). Continuing."
    return
  fi

  # Compare semver using sort -V
  newest="$(printf '%s\n%s\n' "$installed" "$latest" | sort -V | tail -n1)"
  if [[ "$newest" != "$installed" ]]; then
    log "Update available: gemini-cli $installed -> $latest. Installing latest…"
    npm install -g @google/gemini-cli@latest
  else
    log "gemini-cli is up to date (v$installed)."
  fi
}

# --- Paths ---

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
PROJECT_ROOT=$(cd -- "$SCRIPT_DIR/.." &>/dev/null && pwd)   # launcher/.. -> project root

# --- Args ---

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <task_id> [mode]"
  echo "Example: $0 task-20250728-alpha interactive"
  exit 1
fi

TASK_ID="$1"
MODE="${2:-interactive}"

echo "--- LAUNCHER: Initializing Task [$TASK_ID] in [$MODE] mode ---"

# --- Load env ---

CONFIG_PATH="$SCRIPT_DIR/config/.env"
if [[ -f "$CONFIG_PATH" ]]; then
  log "Loading environment from $CONFIG_PATH"
  set -a
  # shellcheck disable=SC1090
  . "$CONFIG_PATH"
  set +a
else
  log "Warning - Configuration file not found at $CONFIG_PATH"
fi

# Ensure libpq sees credentials even if DSN omits them
export PGHOST="${PGHOST:-localhost}"
export PGPORT="${PGPORT:-5432}"
export PGDATABASE="${PGDATABASE:-gemini_agents}"
export PGUSER="${PGUSER:-gemini_user}"
export PGPASSWORD="${PGPASSWORD:-}"
export DATABASE_URL="${DATABASE_URL:-}"

# --- Select API key ---

log "Selecting API key…"

# Prefer /srv/gemini/venv, then .venv, then system python
PY_BIN="$PROJECT_ROOT/venv/bin/python"
[[ -x "$PY_BIN" ]] || PY_BIN="$PROJECT_ROOT/.venv/bin/python"
[[ -x "$PY_BIN" ]] || PY_BIN="python3"

GEMINI_API_KEY="$("$PY_BIN" "$SCRIPT_DIR/scripts/select_key.py")"
export GEMINI_API_KEY
log "Using key $(mask_key "$GEMINI_API_KEY") via $(basename "$PY_BIN")"

# --- (Optional) Context populate hook ---

log "Populating context…"
# "$PY_BIN" "$SCRIPT_DIR/scripts/populate_context.py" --task_id "$TASK_ID"
log "(Skipped - populate_context.py not implemented)"

# --- Ensure gemini CLI exists & is latest ---

if ! have_cmd gemini; then
  log "'gemini' CLI not found on PATH."
  ensure_gemini_cli_latest
else
  # Even if present, check for update and install if newer exists
  ensure_gemini_cli_latest
fi

# --- Run CLI ---

log "Starting Gemini CLI. Use Ctrl+D or type 'exit' to end session."
echo "---------------------------------------------------------------------"
cd /
gemini
echo "---------------------------------------------------------------------"
log "Gemini CLI session ended."

# --- Post-session hook ---

log "Logging session details to database…"
# "$PY_BIN" "$SCRIPT_DIR/scripts/log_session.py" --task_id "$TASK_ID"
log "(Skipped - log_session.py not implemented)"

echo "--- LAUNCHER: Task [$TASK_ID] finished ---"
