#!/bin/bash
# Local development start-up: venv, migrations, dev server.
set -e
cd "$(dirname "$0")"

if [ ! -d venv ]; then
    python3 -m venv venv
    ./venv/bin/pip install -r requirements-dev.txt
fi
source venv/bin/activate
[ -f .env ] && set -a && source .env && set +a

mkdir -p data logs
alembic upgrade head
python src/app_api.py
