#!/bin/sh
set -e

mkdir -p /app/data

if [ "${DB_ENGINE:-sqlite}" = "postgres" ]; then
    echo "Aguardando PostgreSQL em ${POSTGRES_HOST:-postgres}:${POSTGRES_PORT:-5432}..."
    python - <<'PY'
import os, socket, sys, time

host = os.getenv("POSTGRES_HOST", "postgres")
port = int(os.getenv("POSTGRES_PORT", "5432"))

for _ in range(30):
    try:
        with socket.create_connection((host, port), timeout=2):
            sys.exit(0)
    except OSError:
        time.sleep(1)

print(f"Não foi possível conectar ao PostgreSQL em {host}:{port}", file=sys.stderr)
sys.exit(1)
PY
fi

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    python manage.py migrate --noinput
fi

exec "$@"
