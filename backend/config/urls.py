from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    # allauth's JSON API for browsers and apps, plus its OpenAPI spec:
    #   /_allauth/browser/v1/...   /_allauth/app/v1/...   /_allauth/openapi.html
    path("_allauth/", include("allauth.headless.urls")),
    # The OAuth callbacks the providers redirect back to, e.g.
    #   /api/allauth/google/login/callback/
    # (same paths as the old template, so registered callback URLs keep working).
    path("api/allauth/", include("allauth.urls")),
    # Your own API.
    path("api/", include("api.urls")),
    # The demo page (a tiny single-page app talking to the APIs above).
    path("", include("demo.urls")),
]
