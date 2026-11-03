"""
The demo page: one HTML file whose script talks to allauth's browser API and
to your own API. It is only there to show the flows; replace it with your
real frontend.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.csrf import ensure_csrf_cookie

# What the page's script calls, by URL name, so no path is typed twice.
ENDPOINTS = {
    "config": "headless:browser:config",
    "login": "headless:browser:account:login",
    "signup": "headless:browser:account:signup",
    "session": "headless:browser:account:current_session",
    "verifyEmail": "headless:browser:account:verify_email",
    "requestPasswordReset": "headless:browser:account:request_password_reset",
    "resetPassword": "headless:browser:account:reset_password",
    "providerRedirect": "headless:browser:socialaccount:redirect_to_provider",
    "providerSignup": "headless:browser:socialaccount:provider_signup",
    "providers": "headless:browser:socialaccount:manage_providers",
    "refresh": "headless:app:tokens:refresh",
    "sessionJwt": "api-session-jwt",
    "me": "api-me",
}

LINKS = {
    "allauthSpec": "headless:openapi_html",
    "apiDocs": "api-docs",
    "admin": "admin:index",
}


@ensure_csrf_cookie
def playground(request: HttpRequest, rest: str = "") -> HttpResponse:
    config = {
        "endpoints": {key: reverse(name) for key, name in ENDPOINTS.items()},
        "links": {key: reverse(name) for key, name in LINKS.items()},
        # The page's own routes are the paths allauth links to (emails, errors).
        "routes": {
            name: urlsplit(url).path for name, url in settings.HEADLESS_FRONTEND_URLS.items()
        },
    }
    return render(request, "demo/index.html", {"config": config})
