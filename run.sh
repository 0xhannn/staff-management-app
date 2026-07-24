#!/bin/bash
# Staff Management — quick start (Linux/mac)
set -e
cd "$(dirname "$0")"
echo "=================================="
echo " Staff Management"
echo "=================================="
python3 -m venv .venv 2>/dev/null || true
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt
python -c "from database import init_db, seed_data, ensure_master_password_seed, ensure_owner_user; init_db(); seed_data(); ensure_master_password_seed(); ensure_owner_user()"
export PORT="${PORT:-8080}"
python server.py
