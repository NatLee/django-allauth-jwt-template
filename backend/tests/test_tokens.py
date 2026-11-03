"""The JWT lifecycle: what is issued, refreshing, expiry and logout."""

from __future__ import annotations

import time

import jwt
import pytest
import time_machine
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from django.contrib.auth import get_user_model
from django.urls import reverse

from tests.conftest import bearer, tokens_of

pytestmark = pytest.mark.django_db

# The defaults in settings.py (JWT_ACCESS_TOKEN_LIFETIME / JWT_REFRESH_TOKEN_LIFETIME).
ACCESS_LIFETIME = 300
REFRESH_LIFETIME = 86400


def later(seconds: int):
    """Freeze the clock this many seconds from now."""
    return time_machine.travel(time.time() + seconds, tick=False)


def claims(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])


def test_access_token_says_who_and_for_how_long(signed_up):
    payload = claims(signed_up["access"])

    user = get_user_model().objects.get(email=signed_up["email"])
    assert payload["sub"] == str(user.pk)
    assert payload["token_use"] == "access"
    assert payload["exp"] - payload["iat"] == ACCESS_LIFETIME


def test_refresh_token_lasts_a_day(signed_up):
    payload = claims(signed_up["refresh"])

    assert payload["token_use"] == "refresh"
    assert payload["exp"] - payload["iat"] == REFRESH_LIFETIME


def test_lifetimes_follow_the_settings(auth, settings):
    settings.HEADLESS_JWT_ACCESS_TOKEN_EXPIRES_IN = 60

    access, _ = tokens_of(auth.app_signup("ada@example.com"))

    payload = claims(access)
    assert payload["exp"] - payload["iat"] == 60


def test_refresh_gives_a_new_pair_and_retires_the_old_refresh_token(auth, signed_up):
    response = auth.refresh(signed_up["refresh"])

    assert response.status_code == 200
    access, refresh = tokens_of(response)
    assert refresh != signed_up["refresh"]
    assert auth.me(access).status_code == 200
    # Rotation: each refresh token works once.
    assert auth.refresh(signed_up["refresh"]).status_code == 400


def test_an_access_token_is_not_a_refresh_token(auth, signed_up):
    assert auth.refresh(signed_up["access"]).status_code == 400


def test_expired_access_token_is_refused_and_refresh_still_works(auth, signed_up):
    with later(ACCESS_LIFETIME + 5):
        assert auth.me(signed_up["access"]).status_code == 401

        access, _ = tokens_of(auth.refresh(signed_up["refresh"]))
        assert auth.me(access).status_code == 200


def test_expired_refresh_token_is_refused(auth, signed_up):
    with later(REFRESH_LIFETIME + 5):
        assert auth.refresh(signed_up["refresh"]).status_code == 400


def test_session_endpoint_tells_whether_a_token_is_still_good(auth, signed_up):
    url = reverse("headless:app:account:current_session")

    good = auth.client.get(url, headers=bearer(signed_up["access"]))
    assert good.status_code == 200
    assert good.json()["data"]["user"]["email"] == signed_up["email"]


class TestLogout:
    def test_logout_ends_both_tokens_at_once(self, auth, signed_up):
        response = auth.app_logout(signed_up["access"])

        assert response.status_code == 401  # "you are now signed out"
        assert response.json()["meta"]["is_authenticated"] is False
        assert auth.me(signed_up["access"]).status_code == 401
        assert auth.refresh(signed_up["refresh"]).status_code == 400

    def test_without_stateful_validation_access_tokens_live_until_they_expire(
        self, auth, signed_up, settings
    ):
        settings.HEADLESS_JWT_STATEFUL_VALIDATION_ENABLED = False

        auth.app_logout(signed_up["access"])

        assert auth.me(signed_up["access"]).status_code == 200
        assert auth.refresh(signed_up["refresh"]).status_code == 400

    def test_browser_logout_ends_the_tokens_the_session_got(self, auth):
        auth.browser_signup("ada@example.com")
        tokens = auth.session_jwt().json()

        auth.client.delete(reverse("headless:browser:account:current_session"))

        assert auth.me(tokens["access_token"]).status_code == 401
        assert auth.refresh(tokens["refresh_token"]).status_code == 400


def test_rs256_tokens_can_be_checked_with_the_public_key_alone(auth, settings):
    """With JWT_ALGORITHM=RS256 other services verify tokens without any secret."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    settings.HEADLESS_JWT_ALGORITHM = "RS256"
    settings.HEADLESS_JWT_PRIVATE_KEY = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()

    access, _ = tokens_of(auth.app_signup("ada@example.com"))

    assert jwt.get_unverified_header(access)["alg"] == "RS256"
    assert jwt.decode(access, key.public_key(), algorithms=["RS256"])["token_use"] == "access"
    assert auth.me(access).status_code == 200
