import os
from pathlib import Path


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production


# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "django-insecure-8t2gl36pmw$)j_u8$*agz_qd(w^5gjx(d9%fn($u77ry)i2!22"

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv("DEBUG", "True").strip().lower() in {"1", "true", "yes", "on"}

ALLOWED_HOSTS = ["127.0.0.1", "localhost", ".pythonanywhere.com"]


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "cards",
    "task2",
    "tgbot",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
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

WSGI_APPLICATION = "config.wsgi.application"


# Database

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Password validation


AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",},
]


# Internationalization


LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True




STATIC_URL = "/static/"


STATIC_ROOT = BASE_DIR / "static"




MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'



DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8755117994:AAHEigraYmQ4EkeZm8GDXHg0a6kJsWR56co")

# Telegram report chat ID – set via env in production
TELEGRAM_REPORT_CHAT_ID = os.getenv("TELEGRAM_REPORT_CHAT_ID", "1381602449")


# ─── Redis ────────────────────────────────────────────────────────────────────
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# ─── Celery ───────────────────────────────────────────────────────────────────
CELERY_BROKER_URL = REDIS_URL + "/0"
CELERY_RESULT_BACKEND = REDIS_URL + "/0"
CELERY_TIMEZONE = "Asia/Tashkent"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"

# crontab schedules — 3600 = har soatda, 86400 = har kunda
CELERY_BEAT_SCHEDULE = {
    # Har daqiqada statistika yuborish (test uchun)
    "hourly-telegram-report": {
        "task": "task2.tasks.send_hourly_report",
        "schedule": 60,
    },
    # Har kuni soat 08:00 da (Tashkent vaqti) statistika yuborish
    "daily-telegram-report": {
        "task": "task2.tasks.send_daily_report",
        "schedule": 86400,
    },
}

# ─── Cache (Redis) ────────────────────────────────────────────────────────────
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL + "/1",
    }
}

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "request_file": {
            "class": "logging.FileHandler",
            "filename": LOG_DIR / "request.log",
            "formatter": "verbose",
            "level": "INFO",
        },
        "error_file": {
            "class": "logging.FileHandler",
            "filename": LOG_DIR / "error.log",
            "formatter": "verbose",
            "level": "ERROR",
        },
    },
    "loggers": {
        "task2.request": {
            "handlers": ["request_file", "console"],
            "level": "INFO",
            "propagate": False,
        },
        "task2.error": {
            "handlers": ["error_file", "console"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}
