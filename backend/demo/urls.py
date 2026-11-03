from django.urls import path

from demo import views

urlpatterns = [
    path("", views.playground, name="demo"),
    # The routes allauth links to (see HEADLESS_FRONTEND_URLS in settings).
    path("account/<path:rest>", views.playground),
]
