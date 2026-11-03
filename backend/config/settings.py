"""
Settings for the allauth + JWT template.

Everything that changes between machines comes from environment variables;
`.env.example` at the repository root lists them all. A `.env` file next to
it is read for local runs, and real environment variables always win.
"""

from __future__ import annotations

import os
from pathlib import Path

from corsheaders.defaults import default_headers
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR.parent / ".env")


# ---------------------------------------------------------------------------
# Reading environment variables
# ---------------------------------------------------------------------------

# An empty variable (`NAME=` in .env) means "use the default", like an unset one.

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def env_str(name: str, default: str = "") -> str:
    return os.environ.get(name, "").strip() or default


def env_bool(name: str, default: bool) -> bool:
    value = env_str(name).lower()
    if not value:
        return default
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise ImproperlyConfigured(f"{name} must be true or false, got {value!r}.")


def env_int(name: str, default: int) -> int:
    value = env_str(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        raise ImproperlyConfigured(f"{name} must be a whole number, got {value!r}.") from None


def env_list(name: str, default: list[str] | None = None) -> list[str]:
    """A comma-separated variable, e.g. `localhost,127.0.0.1`."""
    value = env_str(name)
    if not value:
        return list(default or [])
    return [item.strip() for item in value.split(",") if item.strip()]


# ---------------------------------------------------------------------------
# Django core
# ---------------------------------------------------------------------------

DEBUG = env_bool("DJANGO_DEBUG", False)

SECRET_KEY = env_str("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured(
            "Set DJANGO_SECRET_KEY, or DJANGO_DEBUG=true for local development."
        )
    SECRET_KEY = "django-insecure-local-development-only"

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", ["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

# Behind a reverse proxy that terminates HTTPS, Django needs the forwarded host
# and scheme to build the right OAuth callback URLs.
if env_bool("DJANGO_BEHIND_PROXY", False):
    USE_X_FORWARDED_HOST = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "drf_spectacular",
    # Before allauth, so its template for the dummy provider's page wins.
    "demo",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "allauth.socialaccount.providers.microsoft",
    "allauth.socialaccount.providers.line",
    "allauth.headless",
    "accounts",
    "api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
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

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTHENTICATION_BACKENDS = [
    # Django admin logs in with username + password.
    "django.contrib.auth.backends.ModelBackend",
    # Everything else (email + password, third-party accounts) goes through allauth.
    "allauth.account.auth_backends.AuthenticationBackend",
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = env_str("DJANGO_TIME_ZONE", "Asia/Taipei")
USE_I18N = True
USE_TZ = True
# Shows dates as 2026/11/04 18:30:00 in the admin (see config/formats/en/formats.py).
FORMAT_MODULE_PATH = ["config.formats"]

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Development prints emails (signup confirmation, password reset) to the console.
EMAIL_BACKEND = env_str("DJANGO_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env_str("DJANGO_EMAIL_HOST", "localhost")
EMAIL_PORT = env_int("DJANGO_EMAIL_PORT", 25)
EMAIL_HOST_USER = env_str("DJANGO_EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env_str("DJANGO_EMAIL_HOST_PASSWORD")
EMAIL_USE_TLS = env_bool("DJANGO_EMAIL_USE_TLS", False)
DEFAULT_FROM_EMAIL = env_str("DJANGO_DEFAULT_FROM_EMAIL", "webmaster@localhost")


# ---------------------------------------------------------------------------
# CORS: only for a frontend served from another origin (e.g. a Vite dev server).
# The demo page is served by Django itself and needs none of this.
# ---------------------------------------------------------------------------

CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = (
    *default_headers,
    # Headers the allauth API reads (see the allauth "CORS" docs).
    "x-session-token",
    "x-email-verification-key",
    "x-password-reset-key",
)


# ---------------------------------------------------------------------------
# allauth: accounts
# ---------------------------------------------------------------------------

ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*"]
# "optional": people are signed in right away and get a confirmation email.
# "mandatory": they must click the link first. "none": no email at all.
ACCOUNT_EMAIL_VERIFICATION = env_str("ACCOUNT_EMAIL_VERIFICATION", "optional")
ACCOUNT_ADAPTER = "accounts.adapter.AccountAdapter"
SOCIALACCOUNT_ADAPTER = "accounts.adapter.SocialAccountAdapter"

# Only these email domains may sign up or connect a third-party account,
# e.g. `example.com,example.org`. Empty means every domain is welcome.
ALLOWED_EMAIL_DOMAINS = [domain.lower() for domain in env_list("ALLOWED_EMAIL_DOMAINS")]


# ---------------------------------------------------------------------------
# allauth: third-party providers
#
# A provider is switched on by setting its client ID (and secret). The
# callback URL to register with the provider is
#   <your site>/api/allauth/<provider id>/login/callback/
# ---------------------------------------------------------------------------

# provider id -> (variable prefix, the app's "settings", the provider's settings)
SOCIAL_PROVIDERS_FROM_ENV = {
    "google": ("GOOGLE", {}, {}),
    "microsoft": ("MS", {"tenant": env_str("MS_TENANT", "common")}, {}),
    "line": ("LINE", {}, {"SCOPE": ["profile", "openid", "email"]}),
}

SOCIALACCOUNT_PROVIDERS: dict[str, dict] = {}
for provider_id, (prefix, app_settings, provider_settings) in SOCIAL_PROVIDERS_FROM_ENV.items():
    if client_id := env_str(f"{prefix}_CLIENT_ID"):
        app = {
            "client_id": client_id,
            "secret": env_str(f"{prefix}_CLIENT_SECRET"),
            "settings": app_settings,
        }
        SOCIALACCOUNT_PROVIDERS[provider_id] = {**provider_settings, "APPS": [app]}

# A fake provider for trying the social flows without registering anything.
# It lets anyone claim any identity, so Django refuses to start with it while
# DEBUG is off (accounts/checks.py).
DUMMY_PROVIDER_APP = "allauth.socialaccount.providers.dummy"
if env_bool("ENABLE_DUMMY_PROVIDER", False):
    INSTALLED_APPS.append(DUMMY_PROVIDER_APP)


# ---------------------------------------------------------------------------
# allauth: headless API + JWT
# ---------------------------------------------------------------------------

# Only the JSON API: no server-rendered login/signup pages. Provider callback
# URLs (under /api/allauth/) still exist, because the providers redirect there.
HEADLESS_ONLY = True
HEADLESS_SERVE_SPECIFICATION = True  # /_allauth/openapi.html

HEADLESS_TOKEN_STRATEGY = "allauth.headless.tokens.strategies.jwt.JWTTokenStrategy"
# HS256 signs with DJANGO_SECRET_KEY. For RS256 set JWT_ALGORITHM=RS256 and put
# an RSA private key (PEM) in JWT_PRIVATE_KEY, so other services can verify
# tokens with the public key alone.
HEADLESS_JWT_ALGORITHM = env_str("JWT_ALGORITHM", "HS256")
HEADLESS_JWT_PRIVATE_KEY = env_str("JWT_PRIVATE_KEY")
HEADLESS_JWT_ACCESS_TOKEN_EXPIRES_IN = env_int("JWT_ACCESS_TOKEN_LIFETIME", 300)
HEADLESS_JWT_REFRESH_TOKEN_EXPIRES_IN = env_int("JWT_REFRESH_TOKEN_LIFETIME", 86400)
# Check each access token against its session, so logging out (or changing the
# password) ends the token at once instead of when it expires.
HEADLESS_JWT_STATEFUL_VALIDATION_ENABLED = env_bool("JWT_STATEFUL_VALIDATION", True)

# Where allauth sends people from emails and failed third-party logins. The
# demo page answers on these paths; set FRONTEND_URL to hand them to your own
# frontend instead (e.g. https://app.example.com).
FRONTEND_URL = env_str("FRONTEND_URL").rstrip("/")
HEADLESS_FRONTEND_URLS = {
    name: FRONTEND_URL + path
    for name, path in {
        "account_confirm_email": "/account/verify-email/{key}",
        "account_reset_password": "/account/password/reset",
        "account_reset_password_from_key": "/account/password/reset/key/{key}",
        "account_signup": "/account/signup",
        "socialaccount_login_error": "/account/provider/callback",
    }.items()
}


# ---------------------------------------------------------------------------
# Django REST framework + API docs
# ---------------------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        # Authorization: Bearer <access token from allauth>
        "allauth.headless.contrib.rest_framework.authentication.JWTTokenAuthentication",
        # The browser session (with CSRF checks), e.g. while browsing the API docs.
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Template API",
    "DESCRIPTION": "Your own endpoints. Sign-up, login, tokens and third-party "
    "accounts are allauth's API, documented at /_allauth/openapi.html.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    # Like before: only staff can read the docs (log in at /admin/ first).
    "SERVE_PERMISSIONS": ["rest_framework.permissions.IsAdminUser"],
    "SERVE_AUTHENTICATION": ["rest_framework.authentication.SessionAuthentication"],
}
