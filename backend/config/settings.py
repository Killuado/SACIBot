import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR.parent / ".env")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "development-only-change-me")
DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "promotions",
    "scrapers",
    "lives",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

if os.getenv("DB_ENGINE", "sqlite").lower() == "postgres":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB", "sacibot"),
            "USER": os.getenv("POSTGRES_USER", "sacibot"),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
            "HOST": os.getenv("POSTGRES_HOST", "localhost"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": Path(os.getenv("SQLITE_PATH", str(BASE_DIR / "db.sqlite3"))),
        }   
    }

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "UNAUTHENTICATED_USER": None,
}

BOT_API_TOKEN = os.getenv("BOT_API_TOKEN", "")
BOT_NOTIFY_URL = os.getenv("BOT_NOTIFY_URL", "http://127.0.0.1:8001/notify")
DISCORD_ADMIN_IDS = {
    uid.strip()
    for uid in (
        os.getenv("DISCORD_ADMIN_IDS")
        or os.getenv("ADMIN_USER_IDS")
        or os.getenv("ADMIN_DISCORD_IDS")
        or ""
    ).split(",")
    if uid.strip()
}


# Scrapers / ingestão
PROMOTION_RETENTION_DAYS = int(os.getenv("PROMOTION_RETENTION_DAYS", "3"))
TELEGRAM_LINK_TTL_SECONDS = int(os.getenv("TELEGRAM_LINK_TTL_SECONDS", "180"))

# YouTube Live Monitor
YOUTUBE_CHECK_INTERVAL = int(os.getenv("YOUTUBE_CHECK_INTERVAL", "120"))
YOUTUBE_RECHECK_LIVE_SECONDS = int(os.getenv("YOUTUBE_RECHECK_LIVE_SECONDS", "300"))
YOUTUBE_LINK_TTL_SECONDS = int(os.getenv("YOUTUBE_LINK_TTL_SECONDS", "180"))
YOUTUBE_INGEST_WORKERS = int(os.getenv("YOUTUBE_INGEST_WORKERS", "4"))
YOUTUBE_MAX_SOURCES = int(os.getenv("YOUTUBE_MAX_SOURCES", "50"))

# Telegram (Telethon). Credenciais em https://my.telegram.org
TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID", "")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
TELEGRAM_SESSION = os.getenv("TELEGRAM_SESSION", str(BASE_DIR / "sacibot_telegram"))
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNELS = [
    channel.strip()
    for channel in os.getenv("TELEGRAM_CHANNELS", "").split(",")
    if channel.strip()
]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "scrapers": {
            "handlers": ["console"],
            "level": os.getenv("SCRAPERS_LOG_LEVEL", "INFO"),
        },
        "lives": {
            "handlers": ["console"],
            "level": os.getenv("SCRAPERS_LOG_LEVEL", "INFO"),
        },
    },
}
