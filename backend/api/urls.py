from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from api import views

urlpatterns = [
    path("me", views.MeView.as_view(), name="api-me"),
    path("auth/jwt", views.SessionTokenView.as_view(), name="api-session-jwt"),
    # Docs for the endpoints above (staff only, see SPECTACULAR_SETTINGS).
    path("schema/", SpectacularAPIView.as_view(), name="api-schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="api-schema"), name="api-docs"),
    path("redoc/", SpectacularRedocView.as_view(url_name="api-schema"), name="api-redoc"),
]
