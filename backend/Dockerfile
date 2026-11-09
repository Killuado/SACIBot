# syntax=docker/dockerfile:1
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SQLITE_PATH=/app/data/db.sqlite3

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

COPY . /app/
RUN sed -i 's/\r$//' /app/entrypoint.sh && chmod +x /app/entrypoint.sh && mkdir -p /app/data

ENTRYPOINT ["/app/entrypoint.sh"]

# --------------------------------------------------------------------------- #
# Target 1: sacibot-api (API REST Django + Gunicorn)
# Build: docker build --target api -t <usuario>/sacibot-api:latest ./backend
# --------------------------------------------------------------------------- #
FROM base AS api
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--timeout", "60"]

# --------------------------------------------------------------------------- #
# Target 2: sacibot-live-monitor (Supervisor de Lives do YouTube + Scrapers)
# Build: docker build --target live-monitor -t <usuario>/sacibot-live-monitor:latest ./backend
# --------------------------------------------------------------------------- #
FROM base AS live-monitor
CMD ["python", "manage.py", "run_youtube_monitor"]
