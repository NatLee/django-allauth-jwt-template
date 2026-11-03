"""Third-party login with a fake Google: nothing leaves the test process.

The `responses` library answers Google's HTTP endpoints, so allauth runs its
real Google code: the redirect, the state check, the code-for-token swap and
reading the ID token.
"""

from __future__ import annotations

import datetime as dt
import time
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
import responses
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from django.contrib.auth import get_user_model
from django.urls import reverse

from allauth.socialaccount.models import SocialAccount
from tests.conftest import PASSWORD, tokens_of

pytestmark = pytest.mark.django_db

CLIENT_ID = "test-client-id.apps.googleusercontent.com"
# allauth's default Google endpoints (allauth/socialaccount/providers/google/views.py).
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_CERTS_URL = "https://www.googleapis.com/oauth2/v1/certs"
# Where the demo page wants to land after the provider (HEADLESS_FRONTEND_URLS).
CALLBACK = "/account/provider/callback"


@pytest.fixture(autouse=True)
def google(settings):
    """Google switched on with made-up credentials, as GOOGLE_CLIENT_ID would."""
    settings.SOCIALACCOUNT_PROVIDERS = {
        "google": {"APPS": [{"client_id": CLIENT_ID, "secret": "test-secret", "settings": {}}]}
    }
    with responses.RequestsMock() as mock:
        yield mock


def id_token_claims(email: str, sub: str) -> dict:
    now = int(time.time())
    return {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "sub": sub,
        "email": email,
        "email_verified": True,
        "name": "Ada Lovelace",
        "iat": now,
        "exp": now + 3600,
    }


def google_redirect_login(client, google, email, sub="1001", process="login"):
    """Walk the browser redirect flow; return where allauth sends us back."""
    started = client.post(
        reverse("headless:browser:socialaccount:redirect_to_provider"),
        {"provider": "google", "process": process, "callback_url": CALLBACK},
    )
    assert started.status_code == 302
    authorize = urlsplit(started["Location"])
    assert authorize.netloc == "accounts.google.com"
    state = parse_qs(authorize.query)["state"][0]

    # Google swaps the code for tokens; allauth reads the ID token it got
    # straight from Google over TLS, so the signature is not checked here.
    id_token = jwt.encode(
        id_token_claims(email, sub), "not-checked-but-long-enough-for-hs256", algorithm="HS256"
    )
    google.add(
        responses.POST,
        GOOGLE_TOKEN_URL,
        json={"access_token": "google-access", "expires_in": 3600, "id_token": id_token},
    )
    back = client.get(reverse("google_callback"), {"code": "google-auth-code", "state": state})
    assert back.status_code == 302
    landed = urlsplit(back["Location"])
    assert landed.path == CALLBACK
    return parse_qs(landed.query)


class TestRedirectLogin:
    def test_first_google_login_creates_the_account(self, client, google):
        query = google_redirect_login(client, google, "ada@gmail.com")

        assert query == {}  # no ?error=
        user = get_user_model().objects.get(email="ada@gmail.com")
        assert SocialAccount.objects.get(user=user).uid == "1001"
        assert not user.has_usable_password()

    def test_the_page_then_gets_a_jwt_for_the_api(self, client, google, auth):
        google_redirect_login(client, google, "ada@gmail.com")

        tokens = auth.session_jwt().json()

        assert auth.me(tokens["access_token"]).json()["email"] == "ada@gmail.com"

    def test_a_returning_user_gets_the_same_account(self, client, google):
        google_redirect_login(client, google, "ada@gmail.com")
        client.delete(reverse("headless:browser:account:current_session"))

        query = google_redirect_login(client, google, "ada@gmail.com")

        assert query == {}
        assert get_user_model().objects.count() == 1

    def test_an_email_that_already_has_an_account_is_refused(self, client, google, auth):
        auth.app_signup("ada@gmail.com")

        query = google_redirect_login(client, google, "ada@gmail.com")

        assert query["error"] == ["email_taken"]
        assert not SocialAccount.objects.exists()

    def test_a_domain_outside_the_list_is_refused(self, client, google, settings):
        settings.ALLOWED_EMAIL_DOMAINS = ["example.com"]

        query = google_redirect_login(client, google, "ada@gmail.com")

        assert query["error"] == ["email_domain_not_allowed"]
        assert not get_user_model().objects.exists()

    def test_a_cancelled_login_comes_back_with_an_error(self, client, google):
        started = client.post(
            reverse("headless:browser:socialaccount:redirect_to_provider"),
            {"provider": "google", "process": "login", "callback_url": CALLBACK},
        )
        state = parse_qs(urlsplit(started["Location"]).query)["state"][0]

        back = client.get(reverse("google_callback"), {"error": "access_denied", "state": state})

        query = parse_qs(urlsplit(back["Location"]).query)
        assert query["error"] == ["cancelled"]


class TestConnect:
    def test_a_signed_in_user_can_link_google(self, client, google, auth):
        auth.browser_signup("ada@example.com")

        query = google_redirect_login(client, google, "ada@gmail.com", process="connect")

        assert query == {}
        providers = client.get(reverse("headless:browser:socialaccount:manage_providers"))
        assert [a["provider"]["id"] for a in providers.json()["data"]] == ["google"]

    def test_linking_needs_a_signed_in_user(self, client, google):
        query = google_redirect_login(client, google, "ada@gmail.com", process="connect")

        assert query == {"error": ["permission_denied"], "error_process": ["connect"]}
        assert not SocialAccount.objects.exists()

    def test_a_google_account_cannot_be_linked_to_two_users(self, client, google, auth):
        google_redirect_login(client, google, "ada@gmail.com")
        client.delete(reverse("headless:browser:account:current_session"))
        auth.browser_signup("grace@example.com")

        query = google_redirect_login(client, google, "ada@gmail.com", process="connect")

        assert query["error"] == ["connected_other"]

    def test_linking_also_follows_the_domain_list(self, client, google, auth, settings):
        auth.browser_signup("ada@example.com")
        settings.ALLOWED_EMAIL_DOMAINS = ["example.com"]

        query = google_redirect_login(client, google, "ada@gmail.com", process="connect")

        assert query["error"] == ["email_domain_not_allowed"]


class TestDisconnect:
    def url(self):
        return reverse("headless:browser:socialaccount:manage_providers")

    def test_the_only_login_method_cannot_be_unlinked(self, client, google):
        google_redirect_login(client, google, "ada@gmail.com")
        account = SocialAccount.objects.get()

        response = client.delete(
            self.url(),
            {"provider": "google", "account": account.uid},
            content_type="application/json",
        )

        assert response.status_code == 400
        assert response.json()["errors"][0]["code"] == "no_password"
        assert SocialAccount.objects.exists()

    def test_with_a_password_it_can_be_unlinked(self, client, google, auth):
        auth.browser_signup("ada@example.com")
        google_redirect_login(client, google, "ada@gmail.com", process="connect")
        account = SocialAccount.objects.get()

        response = client.delete(
            self.url(),
            {"provider": "google", "account": account.uid},
            content_type="application/json",
        )

        assert response.status_code == 200
        assert response.json()["data"] == []


class TestProviderToken:
    """An app that signed in with Google's own SDK hands allauth the ID token."""

    @pytest.fixture
    def google_keys(self, google):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test-google")])
        now = dt.datetime.now(dt.UTC)
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(1)
            .not_valid_before(now - dt.timedelta(days=1))
            .not_valid_after(now + dt.timedelta(days=1))
            .sign(key, hashes.SHA256())
        )
        pem = cert.public_bytes(serialization.Encoding.PEM).decode()
        google.add(responses.GET, GOOGLE_CERTS_URL, json={"test-kid": pem})
        return key

    def post_token(self, client, id_token):
        return client.post(
            reverse("headless:app:socialaccount:provider_token"),
            {
                "provider": "google",
                "process": "login",
                "token": {"client_id": CLIENT_ID, "id_token": id_token},
            },
            content_type="application/json",
        )

    def test_a_valid_id_token_returns_a_jwt_pair(self, client, google_keys, auth):
        id_token = jwt.encode(
            id_token_claims("ada@gmail.com", "1001"),
            google_keys,
            algorithm="RS256",
            headers={"kid": "test-kid"},
        )

        response = self.post_token(client, id_token)

        assert response.status_code == 200, response.json()
        access, _ = tokens_of(response)
        assert auth.me(access).json()["email"] == "ada@gmail.com"

    def test_a_forged_id_token_is_refused(self, client, google_keys):
        forger = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        id_token = jwt.encode(
            id_token_claims("ada@gmail.com", "1001"),
            forger,
            algorithm="RS256",
            headers={"kid": "test-kid"},
        )

        response = self.post_token(client, id_token)

        assert response.status_code == 400
        assert not get_user_model().objects.exists()


def test_password_users_can_still_log_in_after_linking(client, google, auth):
    auth.browser_signup("ada@example.com")
    google_redirect_login(client, google, "ada@gmail.com", process="connect")

    assert auth.app_login("ada@example.com", PASSWORD).status_code == 200
