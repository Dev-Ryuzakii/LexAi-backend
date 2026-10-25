#!/usr/bin/env bash
set -euo pipefail

# Create a dedicated LexAI database in an already-running PostgreSQL container.
# Run from the repository root with POSTGRES_DOCKER_NETWORK set to the network
# shared by the PostgreSQL and LexAI containers.

cd "$(dirname "$0")/.."

postgres_container="${POSTGRES_CONTAINER:-shared-postgres}"
postgres_network="${POSTGRES_DOCKER_NETWORK:?Set POSTGRES_DOCKER_NETWORK to the existing PostgreSQL Docker network}"

docker inspect "$postgres_container" >/dev/null
docker network inspect "$postgres_network" >/dev/null

if [[ ! -f .env ]]; then
  cp .env.example .env
fi

admin_user="$(docker exec "$postgres_container" sh -c 'printf %s "${POSTGRES_USER:-postgres}"')"
psql_in_container=(docker exec -i "$postgres_container" psql -X -v ON_ERROR_STOP=1 -U "$admin_user" -d postgres)

if [[ "$(printf "SELECT 1 FROM pg_roles WHERE rolname = 'lexai_app';\n" | "${psql_in_container[@]}" -At)" == "1" ]]; then
  echo 'The lexai_app role already exists. No database credentials were changed.' >&2
  exit 1
fi
if [[ "$(printf "SELECT 1 FROM pg_database WHERE datname = 'lexai';\n" | "${psql_in_container[@]}" -At)" == "1" ]]; then
  echo 'The lexai database already exists. No database credentials were changed.' >&2
  exit 1
fi

password="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
printf "CREATE ROLE lexai_app LOGIN PASSWORD '%s';\n" "$password" | "${psql_in_container[@]}" >/dev/null
printf 'CREATE DATABASE lexai OWNER lexai_app;\n' | "${psql_in_container[@]}" >/dev/null

LEXAI_DATABASE_URL="postgresql+psycopg://lexai_app:${password}@${postgres_container}:5432/lexai" \
LEXAI_POSTGRES_NETWORK="$postgres_network" python3 - <<'PY'
import os
from pathlib import Path

path = Path('.env')
updates = {
    'DATABASE_URL': os.environ['LEXAI_DATABASE_URL'],
    'POSTGRES_DOCKER_NETWORK': os.environ['LEXAI_POSTGRES_NETWORK'],
}
lines = path.read_text().splitlines()
seen = set()
result = []
for line in lines:
    key = line.split('=', 1)[0].strip() if '=' in line else None
    if key in updates:
        if key not in seen:
            result.append(f'{key}={updates[key]}')
            seen.add(key)
    else:
        result.append(line)
for key, value in updates.items():
    if key not in seen:
        result.append(f'{key}={value}')
path.write_text('\n'.join(result).rstrip() + '\n')
path.chmod(0o600)
PY

echo "Created the lexai database and lexai_app role in ${postgres_container}."
echo "Saved DATABASE_URL and POSTGRES_DOCKER_NETWORK to .env (mode 600). Do not paste .env into chat."
echo 'Next: docker compose -f docker-compose.yml -f docker-compose.postgres.yml up -d --build'
