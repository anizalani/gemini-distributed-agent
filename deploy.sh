#!/bin/bash

# This script automates the deployment of the Gemini Distributed Agent.

set -euo pipefail

# --- Configuration ---
REPO_URL="https://github.com/anizalani/gemini-distributed-agent.git"
PROJECT_DIR="gemini-distributed-agent"

# --- Functions ---
log() {
  echo "[DEPLOY] $1"
}

# --- Main ---
log "Starting deployment of Gemini Distributed Agent..."

# 1. Clone the repository
if [ -d "$PROJECT_DIR" ]; then
  log "Project directory already exists. Skipping clone."
else
  log "Cloning repository..."
  git clone "$REPO_URL" "$PROJECT_DIR"
fi

cd "$PROJECT_DIR"

# 2. Create Python virtual environment
if [ -d "venv" ]; then
  log "Virtual environment already exists. Skipping creation."
else
  log "Creating Python virtual environment..."
  python3 -m venv venv
fi

# 3. Install dependencies
log "Installing Python dependencies..."
source venv/bin/activate

pip install -r requirements.txt

log "Installing Node.js dependencies..."
npm install

# 4. Configure environment
log "Configuration needed!"
echo "---------------------------------------------------------------------"
echo "You need to create and configure the '.postgres.env' file."
echo ""
echo "1. Copy the example file:"
echo "   cp .postgres.env.example .postgres.env"
echo ""
echo "2. Edit the '.postgres.env' file with your PostgreSQL database credentials:"
echo "   nano .postgres.env"
echo ""
echo "The file should look like this:"
echo ""
echo "POSTGRES_DB=postgres"
echo "POSTGRES_USER=gemini_user"
echo "POSTGRES_PASSWORD=\"your_password_here\""
echo "POSTGRES_HOST=your_postgres_host_or_ip"
echo "POSTGRES_PORT=5432"
echo ""
echo "Since your new host is on the same tailnet, you can use the tailnet IP of the database host for POSTGRES_HOST."
echo "---------------------------------------------------------------------"

log "Deployment script finished."
