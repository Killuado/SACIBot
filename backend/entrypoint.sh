#!/bin/sh
set -e

mkdir -p /app/data

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    python manage.py migrate --noinput
fi

exec "$@"
