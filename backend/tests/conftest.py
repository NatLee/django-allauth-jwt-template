from __future__ import annotations

import pytest
from django.core.cache import cache
from django.test import Client
from django.urls import reverse

PASSWORD = "correct-horse-battery-staple"


class AuthClient:
    """A test client that knows the template's endpoints."""

    def __init__(self, client: Client) -> None:
        self.client = client

    # --- allauth, app client (tokens, no cookies) ------------------------

    def app_post(self, name: str, data: dict, **headers):
        return self.client.post(
            reverse(f"headless:app:{name}"), data, content_type="application/json", headers=headers
        )

    def app_signup(self, email: str, password: str = PASSWORD):
        return self.app_post("account:signup", {"email": email, "password": password})

    def app_login(self, email: str, password: str = PASSWORD):
        return self.app_post("account:login", {"email": email, "password": password})

    def refresh(self, refresh_token: str):
        return self.app_post("tokens:refresh", {"refresh_token": refresh_token})

    def app_logout(self, access_token: str):
        return self.client.delete(
            reverse("headless:app:account:current_session"), headers=bearer(access_token)
        )

    # --- allauth, browser client (session cookie) -------------------------

    def browser_post(self, name: str, data: dict):
        return self.client.post(
            reverse(f"headless:browser:{name}"), data, content_type="application/json"
        )

    def browser_signup(self, email: str, password: str = PASSWORD):
        return self.browser_post("account:signup", {"email": email, "password": password})

    def browser_session(self):
        return self.client.get(reverse("headless:browser:account:current_session"))

    def session_jwt(self):
        return self.client.post(reverse("api-session-jwt"))

    # --- your API ----------------------------------------------------------

    def me(self, access_token: str | None = None):
        headers = bearer(access_token) if access_token else {}
        return self.client.get(reverse("api-me"), headers=headers)


def bearer(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


def tokens_of(response) -> tuple[str, str]:
    """The (access, refresh) pair from an allauth app response."""
    body = response.json()
    meta = body.get("meta") or body.get("data")
    return meta["access_token"], meta["refresh_token"]


@pytest.fixture(autouse=True)
def known_settings(settings):
    """The defaults from settings.py, whatever a local .env says.

    Tests run both in CI (no .env) and inside the compose container (with
    .env), so each test starts from these and changes what it needs.
    """
    settings.ALLOWED_EMAIL_DOMAINS = []
    settings.SOCIALACCOUNT_PROVIDERS = {}
    settings.ACCOUNT_EMAIL_VERIFICATION = "optional"
    settings.HEADLESS_JWT_ALGORITHM = "HS256"
    settings.HEADLESS_JWT_PRIVATE_KEY = ""
    settings.HEADLESS_JWT_ACCESS_TOKEN_EXPIRES_IN = 300
    settings.HEADLESS_JWT_REFRESH_TOKEN_EXPIRES_IN = 86400
    settings.HEADLESS_JWT_STATEFUL_VALIDATION_ENABLED = True


@pytest.fixture(autouse=True)
def fresh_rate_limits():
    """allauth counts requests per IP in the cache; start every test at zero."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def auth(client: Client) -> AuthClient:
    return AuthClient(client)


@pytest.fixture
def signed_up(auth: AuthClient, db) -> dict:
    """A person who signed up through the app API, with their tokens."""
    response = auth.app_signup("ada@example.com")
    assert response.status_code == 200, response.json()
    access, refresh = tokens_of(response)
    return {"email": "ada@example.com", "access": access, "refresh": refresh}
