from __future__ import annotations

import os
import sys
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BASE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

APP_HOME = Path(os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")) / "ZebraHunter"
load_dotenv(BASE_DIR / ".env", override=False)
load_dotenv(APP_HOME / ".env", override=False)


def _int_env(name: str, default: int = 0) -> int:
    try:
        return int((os.getenv(name) or str(default)).strip())
    except Exception:
        return default


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def _list_env(name: str, default_csv: str = "") -> list[str]:
    raw = os.getenv(name, default_csv)
    return [p.strip() for p in str(raw).split(",") if p.strip()]


SECRET_KEY = (os.getenv("DJANGO_SECRET_KEY") or "dev-only-change-me").strip()
DEBUG = _bool_env("DJANGO_DEBUG", True)
ALLOWED_HOSTS = _list_env("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost,testserver")
CSRF_TRUSTED_ORIGINS = _list_env("DJANGO_CSRF_TRUSTED_ORIGINS", "")

if not DEBUG:
    if SECRET_KEY == "dev-only-change-me":
        raise RuntimeError("DJANGO_SECRET_KEY obrigatoria para producao.")
    if not ALLOWED_HOSTS:
        raise RuntimeError("DJANGO_ALLOWED_HOSTS obrigatorio para producao.")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "zhcore",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "webapp.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "webapp" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "webapp.wsgi.application"
ASGI_APPLICATION = "webapp.asgi.application"

data_dir = BASE_DIR / "data"
data_dir.mkdir(parents=True, exist_ok=True)
database_url = (os.getenv("DATABASE_URL") or "").strip()
if database_url:
    DATABASES = {
        "default": dj_database_url.parse(
            database_url,
            conn_max_age=600,
            ssl_require=True,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(data_dir / "web.sqlite3"),
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = os.getenv("TZ", "America/Sao_Paulo")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "webapp" / "static"]
if not DEBUG:
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"},
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "post_login_redirect"
LOGOUT_REDIRECT_URL = "public_home"

# Security hardening
SESSION_COOKIE_SECURE = _bool_env("DJANGO_SESSION_COOKIE_SECURE", not DEBUG)
CSRF_COOKIE_SECURE = _bool_env("DJANGO_CSRF_COOKIE_SECURE", not DEBUG)
SESSION_COOKIE_HTTPONLY = _bool_env("DJANGO_SESSION_COOKIE_HTTPONLY", True)
CSRF_COOKIE_HTTPONLY = _bool_env("DJANGO_CSRF_COOKIE_HTTPONLY", False)
SESSION_COOKIE_SAMESITE = os.getenv("DJANGO_SESSION_COOKIE_SAMESITE", "Lax")
CSRF_COOKIE_SAMESITE = os.getenv("DJANGO_CSRF_COOKIE_SAMESITE", "Lax")
SECURE_SSL_REDIRECT = _bool_env("DJANGO_SECURE_SSL_REDIRECT", not DEBUG)
SECURE_CONTENT_TYPE_NOSNIFF = _bool_env("DJANGO_SECURE_CONTENT_TYPE_NOSNIFF", True)
SECURE_REFERRER_POLICY = os.getenv("DJANGO_SECURE_REFERRER_POLICY", "strict-origin-when-cross-origin")
X_FRAME_OPTIONS = os.getenv("DJANGO_X_FRAME_OPTIONS", "DENY")
SECURE_CROSS_ORIGIN_OPENER_POLICY = os.getenv("DJANGO_SECURE_CROSS_ORIGIN_OPENER_POLICY", "same-origin")
USE_X_FORWARDED_HOST = _bool_env("DJANGO_USE_X_FORWARDED_HOST", not DEBUG)

_hsts_default = 31536000 if not DEBUG else 0
SECURE_HSTS_SECONDS = _int_env("DJANGO_SECURE_HSTS_SECONDS", _hsts_default)
SECURE_HSTS_INCLUDE_SUBDOMAINS = _bool_env("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", SECURE_HSTS_SECONDS > 0)
SECURE_HSTS_PRELOAD = _bool_env("DJANGO_SECURE_HSTS_PRELOAD", False)

_proxy_header = os.getenv("DJANGO_SECURE_PROXY_SSL_HEADER", "HTTP_X_FORWARDED_PROTO,https").strip()
if _proxy_header and "," in _proxy_header:
    _parts = [p.strip() for p in _proxy_header.split(",", 1)]
    if len(_parts) == 2 and _parts[0] and _parts[1]:
        SECURE_PROXY_SSL_HEADER = (_parts[0], _parts[1])

# Logging for production hardening
LOG_DIR = BASE_DIR / "reports" / "webapp"
LOG_DIR.mkdir(parents=True, exist_ok=True)
DJANGO_LOG_LEVEL = os.getenv("DJANGO_LOG_LEVEL", os.getenv("LOG_LEVEL", "INFO")).upper()
DJANGO_LOG_JSON = _bool_env("DJANGO_LOG_JSON", _bool_env("LOG_JSON", False))
DJANGO_LOG_FILE = os.getenv("DJANGO_LOG_FILE", str(LOG_DIR / "django_app.log"))

_default_formatter = "json" if DJANGO_LOG_JSON else "standard"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        },
        "json": {
            "()": "webapp.logging_utils.JsonFormatter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": _default_formatter,
            "level": DJANGO_LOG_LEVEL,
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": DJANGO_LOG_FILE,
            "maxBytes": _int_env("DJANGO_LOG_MAX_BYTES", 5_000_000),
            "backupCount": _int_env("DJANGO_LOG_BACKUP_COUNT", 5),
            "formatter": _default_formatter,
            "level": DJANGO_LOG_LEVEL,
            "encoding": "utf-8",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console", "file"],
            "level": DJANGO_LOG_LEVEL,
            "propagate": False,
        },
        "webapp": {
            "handlers": ["console", "file"],
            "level": DJANGO_LOG_LEVEL,
            "propagate": False,
        },
        "zhcore": {
            "handlers": ["console", "file"],
            "level": DJANGO_LOG_LEVEL,
            "propagate": False,
        },
    },
    "root": {
        "handlers": ["console", "file"],
        "level": DJANGO_LOG_LEVEL,
    },
}

# Celery / filas assincronas
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = _int_env("CELERY_TASK_TIME_LIMIT", 3600)
CELERY_TASK_SOFT_TIME_LIMIT = _int_env("CELERY_TASK_SOFT_TIME_LIMIT", 3300)
CELERY_WORKER_CONCURRENCY = _int_env("CELERY_WORKER_CONCURRENCY", 1)
CELERY_TASK_ALWAYS_EAGER = _bool_env("CELERY_TASK_ALWAYS_EAGER", False)
CELERY_IMPORTS = ("zhcore.tasks",)

_scan_minutes = _int_env("DJANGO_SCHED_SCAN_MINUTES", 0)
_update_minutes = _int_env("DJANGO_SCHED_UPDATE_RESULTS_MINUTES", 0)
_backup_hours = _int_env("DJANGO_SCHED_BACKUP_HOURS", 0)

CELERY_BEAT_SCHEDULE: dict[str, dict[str, object]] = {}
if _scan_minutes > 0:
    CELERY_BEAT_SCHEDULE["scheduled-scan"] = {
        "task": "zhcore.scheduled_scan_task",
        "schedule": float(_scan_minutes) * 60.0,
    }
if _update_minutes > 0:
    CELERY_BEAT_SCHEDULE["scheduled-update-results"] = {
        "task": "zhcore.scheduled_update_results_task",
        "schedule": float(_update_minutes) * 60.0,
    }
if _backup_hours > 0:
    CELERY_BEAT_SCHEDULE["scheduled-backup"] = {
        "task": "zhcore.scheduled_backup_task",
        "schedule": float(_backup_hours) * 3600.0,
    }
