"""Signing up and logging in with email + password."""

from __future__ import annotations

import re
from urllib.parse import unquote

import pytest
from django.core import mail
from django.urls import reverse

from allauth.account.models import EmailAddress
from tests.conftest import PASSWORD, tokens_of

pytestmark = pytest.mark.django_db


def test_app_signup_returns_a_jwt_pair(auth):
    response = auth.app_signup("ada@example.com")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["user"]["email"] == "ada@example.com"
    assert body["meta"]["is_authenticated"] is True
    access, refresh = tokens_of(response)
    assert access.count(".") == 2 and refresh.count(".") == 2


def test_app_login_returns_a_jwt_pair(auth, signed_up):
    response = auth.app_login(signed_up["email"])

    assert response.status_code == 200
    access, _ = tokens_of(response)
    assert auth.me(access).json()["email"] == signed_up["email"]


def test_wrong_password_is_refused(auth, signed_up):
    response = auth.app_login(signed_up["email"], password="not-the-password")

    assert response.status_code == 400
    assert "access_token" not in response.json().get("meta", {})


def test_same_email_cannot_sign_up_twice(auth, signed_up):
    response = auth.app_signup(signed_up["email"])

    assert response.status_code == 400
    assert [e["code"] for e in response.json()["errors"]] == ["email_taken"]


def test_signup_sends_a_confirmation_link_to_the_demo_page(auth):
    auth.app_signup("ada@example.com")

    # ACCOUNT_EMAIL_VERIFICATION="optional": signed in now, link by email.
    (message,) = mail.outbox
    link = re.search(r"/account/verify-email/(\S+)", message.body)
    assert auth.client.get(link.group(0)).status_code == 200
    key = unquote(link.group(1))  # the page decodes it the same way

    response = auth.browser_post("account:verify_email", {"key": key})
    assert response.status_code in (200, 401), response.json()
    assert EmailAddress.objects.get(email="ada@example.com").verified is True


def test_password_reset_link_points_at_the_demo_page(auth, signed_up):
    auth.browser_post("account:request_password_reset", {"email": signed_up["email"]})

    message = mail.outbox[-1]
    key = unquote(re.search(r"/account/password/reset/key/(\S+)", message.body).group(1))
    response = auth.browser_post(
        "account:reset_password", {"key": key, "password": "a-brand-new-passphrase"}
    )
    assert response.status_code in (200, 401), response.json()
    assert auth.app_login(signed_up["email"], password="a-brand-new-passphrase").status_code == 200


class TestEmailDomains:
    def test_a_domain_outside_the_list_cannot_sign_up(self, auth, settings):
        settings.ALLOWED_EMAIL_DOMAINS = ["example.org"]

        response = auth.app_signup("ada@example.com")

        assert response.status_code == 400
        assert [e["code"] for e in response.json()["errors"]] == ["email_domain_not_allowed"]

    def test_a_listed_domain_can_sign_up(self, auth, settings):
        settings.ALLOWED_EMAIL_DOMAINS = ["example.org"]

        assert auth.app_signup("ada@EXAMPLE.org").status_code == 200


class TestBrowserLogin:
    """The demo page logs in with the session cookie, then asks for a JWT."""

    def test_browser_responses_carry_no_tokens(self, auth):
        response = auth.browser_signup("ada@example.com")

        assert response.status_code == 200
        assert "access_token" not in response.json()["meta"]

    def test_the_signed_in_session_can_get_a_jwt_pair(self, auth):
        auth.browser_signup("ada@example.com")

        response = auth.session_jwt()

        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"access_token", "refresh_token"}
        assert auth.me(body["access_token"]).json()["authenticated_with"] == "jwt"

    def test_no_jwt_without_a_signed_in_session(self, auth):
        assert auth.session_jwt().status_code == 403

    def test_the_jwt_endpoint_checks_csrf(self, client):
        from django.test import Client

        strict = Client(enforce_csrf_checks=True)
        csrf = strict.get(reverse("demo")).cookies["csrftoken"].value
        strict.post(
            reverse("headless:browser:account:signup"),
            {"email": "ada@example.com", "password": PASSWORD},
            content_type="application/json",
            headers={"X-CSRFToken": csrf},
        )
        csrf = strict.cookies["csrftoken"].value  # in case logging in rotated it
        url = reverse("api-session-jwt")

        assert strict.post(url).status_code == 403
        assert strict.post(url, headers={"X-CSRFToken": csrf}).status_code == 200
