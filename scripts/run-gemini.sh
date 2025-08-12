#!/usr/bin/env bash
set -euo pipefail
cd /opt/gemini-distributed-agent
source venv/bin/activate
exec python gemini_interactive_wrapper.py "$@"
