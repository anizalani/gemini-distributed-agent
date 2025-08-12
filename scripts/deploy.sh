#!/usr/bin/env bash
set -euo pipefail
cd /opt/gemini-distributed-agent
echo "[deploy] pulling…"
git fetch origin
git switch main
git reset --hard origin/main
echo "[deploy] restarting web ui…"
sudo systemctl restart gemma-web
sleep 1
sudo systemctl --no-pager --full status gemma-web | sed -n '1,20p'
echo "[deploy] health:"
curl -sS http://127.0.0.1:5002/health || true
echo
