"""Settings come from environment variables; the demo page and system checks."""

from __future__ import annotations

import json
import runpy

import pytest
from django.conf import settings as django_settings
from django.core.exceptions import ImproperlyConfigured
from django.urls import reverse

from accounts.checks import dummy_provider_only_in_debug

SETTINGS_FILE = django_settings.BASE_DIR / "config" / "settings.py"
PROVIDER_VARIABLES = [
    f"{prefix}_{suffix}"
    for prefix in ("GOOGLE", "MS", "LINE")
    for suffix in ("CLIENT_ID", "CLIENT_SECRET")
] + ["MS_TENANT"]


@pytest.fixture
def load_settings(monkeypatch):
    """Evaluate settings.py afresh with the given environment, untouched by .env."""
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: False)
    for name in PROVIDER_VARIABLES:
        monkeypatch.delenv(name, raising=False)

    def load(**env: str) -> dict:
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        return runpy.run_path(str(SETTINGS_FILE))

    return load


class TestFromEnvironment:
    def test_no_client_ids_means_no_providers(self, load_settings):
        assert load_settings()["SOCIALACCOUNT_PROVIDERS"] == {}

    def test_a_client_id_switches_its_provider_on(self, load_settings):
        loaded = load_settings(GOOGLE_CLIENT_ID="g-id", GOOGLE_CLIENT_SECRET="g-secret")

        assert loaded["SOCIALACCOUNT_PROVIDERS"] == {
            "google": {"APPS": [{"client_id": "g-id", "secret": "g-secret", "settings": {}}]}
        }

    def test_microsoft_and_line_keep_their_extra_settings(self, load_settings):
        providers = load_settings(MS_CLIENT_ID="m", LINE_CLIENT_ID="l")["SOCIALACCOUNT_PROVIDERS"]

        assert providers["microsoft"]["APPS"][0]["settings"] == {"tenant": "common"}
        assert providers["line"]["SCOPE"] == ["profile", "openid", "email"]

    def test_microsoft_tenant_can_be_set(self, load_settings):
        providers = load_settings(MS_CLIENT_ID="m", MS_TENANT="contoso.onmicrosoft.com")[
            "SOCIALACCOUNT_PROVIDERS"
        ]

        assert providers["microsoft"]["APPS"][0]["settings"] == {
            "tenant": "contoso.onmicrosoft.com"
        }

    def test_lists_and_numbers(self, load_settings):
        loaded = load_settings(
            DJANGO_ALLOWED_HOSTS="api.example.com, .example.org",
            ALLOWED_EMAIL_DOMAINS="Example.com,example.org",
            JWT_ACCESS_TOKEN_LIFETIME="60",
        )

        assert loaded["ALLOWED_HOSTS"] == ["api.example.com", ".example.org"]
        assert loaded["ALLOWED_EMAIL_DOMAINS"] == ["example.com", "example.org"]
        assert loaded["HEADLESS_JWT_ACCESS_TOKEN_EXPIRES_IN"] == 60

    def test_frontend_url_moves_every_link(self, load_settings):
        urls = load_settings(FRONTEND_URL="https://app.example.com/")["HEADLESS_FRONTEND_URLS"]

        assert urls["account_confirm_email"] == "https://app.example.com/account/verify-email/{key}"
        assert all(url.startswith("https://app.example.com/account/") for url in urls.values())

    def test_a_secret_key_is_required_unless_debugging(self, load_settings, monkeypatch):
        monkeypatch.delenv("DJANGO_SECRET_KEY", raising=False)

        with pytest.raises(ImproperlyConfigured, match="DJANGO_SECRET_KEY"):
            load_settings(DJANGO_DEBUG="false")
        assert load_settings(DJANGO_DEBUG="true")["SECRET_KEY"]

    @pytest.mark.parametrize("name, value", [("DJANGO_DEBUG", "maybe"), ("JWT_ACCESS_TOKEN_LIFETIME", "5m")])
    def test_unreadable_values_stop_the_start(self, load_settings, name, value):
        with pytest.raises(ImproperlyConfigured, match=name):
            load_settings(**{name: value})


class TestDummyProviderCheck:
    @staticmethod
    def apps(settings, *, dummy: bool) -> list[str]:
        """INSTALLED_APPS with or without the dummy provider (a local .env may add it)."""
        others = [app for app in settings.INSTALLED_APPS if app != settings.DUMMY_PROVIDER_APP]
        return [*others, settings.DUMMY_PROVIDER_APP] if dummy else others

    def test_refused_with_debug_off(self, settings):
        settings.DEBUG = False
        settings.INSTALLED_APPS = self.apps(settings, dummy=True)

        assert [e.id for e in dummy_provider_only_in_debug(None)] == ["accounts.E001"]

    def test_fine_while_debugging(self, settings):
        settings.DEBUG = True
        settings.INSTALLED_APPS = self.apps(settings, dummy=True)

        assert dummy_provider_only_in_debug(None) == []

    def test_fine_when_not_installed(self, settings):
        settings.DEBUG = False
        settings.INSTALLED_APPS = self.apps(settings, dummy=False)

        assert dummy_provider_only_in_debug(None) == []


@pytest.mark.django_db
class TestDemoPage:
    def test_page_knows_every_url_it_calls(self, client):
        response = client.get(reverse("demo"))

        assert response.status_code == 200
        assert "csrftoken" in response.cookies
        html = response.content.decode()
        start = html.index('id="playground-config"')
        config = json.loads(html[html.index(">", start) + 1 : html.index("</script>", start)])
        assert config["endpoints"]["refresh"] == "/_allauth/app/v1/tokens/refresh"
        assert config["endpoints"]["sessionJwt"] == "/api/auth/jwt"
        assert config["routes"]["socialaccount_login_error"] == "/account/provider/callback"

    @pytest.mark.parametrize(
        "path", ["/account/verify-email/abc", "/account/password/reset", "/account/provider/callback"]
    )
    def test_page_answers_on_the_paths_allauth_links_to(self, client, path):
        assert client.get(path).status_code == 200

    def test_configured_providers_show_up_for_the_page(self, client, settings):
        settings.SOCIALACCOUNT_PROVIDERS = {
            "line": {"APPS": [{"client_id": "l", "secret": "s", "settings": {}}]}
        }

        config = client.get(reverse("headless:browser:config")).json()["data"]

        listed = {p["id"] for p in config["socialaccount"]["providers"]}
        # (plus "dummy" when a local .env switches the fake provider on)
        assert "line" in listed
        assert not listed & {"google", "microsoft"}
