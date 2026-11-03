"""The example endpoint (GET /api/me) and the API docs."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from tests.conftest import PASSWORD

pytestmark = pytest.mark.django_db


def test_no_token_no_entry(auth):
    response = auth.me()

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_a_made_up_token_is_refused(auth):
    assert auth.me("not.a.jwt").status_code == 401


def test_a_token_signed_with_another_key_is_refused(auth, signed_up, settings):
    settings.SECRET_KEY = "a-different-secret-key-that-is-long-enough"
    # allauth caches the signing key per (algorithm, key); a new key means a new config.

    assert auth.me(signed_up["access"]).status_code == 401


def test_a_refresh_token_does_not_open_the_api(auth, signed_up):
    assert auth.me(signed_up["refresh"]).status_code == 401


def test_the_access_token_opens_the_api(auth, signed_up):
    response = auth.me(signed_up["access"])

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == signed_up["email"]
    assert body["authenticated_with"] == "jwt"
    assert body["token_expires_at"] > 0


def test_the_browser_session_opens_the_api_too(auth):
    auth.browser_signup("ada@example.com")

    body = auth.me().json()

    assert body["authenticated_with"] == "session"
    assert body["token_expires_at"] is None


def test_a_deactivated_user_is_shut_out(auth, signed_up):
    get_user_model().objects.filter(email=signed_up["email"]).update(is_active=False)

    assert auth.me(signed_up["access"]).status_code == 401


class TestDocs:
    def test_allauth_spec_is_served(self, client):
        response = client.get(reverse("headless:openapi_json"))

        assert response.status_code == 200
        assert "/_allauth/app/v1/tokens/refresh" in response.json()["paths"]

    def test_api_docs_are_for_staff_only(self, client):
        assert client.get(reverse("api-schema")).status_code == 403

        get_user_model().objects.create_superuser("admin", "admin@example.com", PASSWORD)
        client.login(username="admin", password=PASSWORD)

        response = client.get(reverse("api-schema"))
        assert response.status_code == 200
        assert b"/api/me" in response.content
        assert b"bearer" in response.content
