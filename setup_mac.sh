#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if command -v python3.10 >/dev/null 2>&1; then PYBIN=python3.10; else PYBIN=python3; fi
"$PYBIN" -m venv .venv
".venv/bin/python" -m pip install --upgrade pip
".venv/bin/python" -m pip install -r requirements.txt
if [ ! -f .env ]; then cp .env.example .env; fi
".venv/bin/python" -m pytest -q
