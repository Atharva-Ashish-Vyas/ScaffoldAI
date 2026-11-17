#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -f .venv/bin/python ]; then echo "Run ./setup_mac.sh first"; exit 1; fi
exec .venv/bin/python -m uvicorn app.server:app --host 127.0.0.1 --port 8000
